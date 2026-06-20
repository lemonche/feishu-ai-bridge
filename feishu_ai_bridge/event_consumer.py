import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from .config import (
    LARK_CLI, MY_OPEN_ID, CHAT_ID,
    EVENTS_DIR, PROCESSED_DIR, BASE_DIR,
)
from .feishu import log, log_warn, log_error, log_debug, send_feishu, send_feishu_markdown
from .commands import parse_message, handle_builtin_command

_processed_ids = set()
_processed_ids_lock = threading.Lock()

BUS_STALE_THRESHOLD = 600
_last_event_time = time.time()

_restart_fail_count = 0
_MAX_RESTART_FAILS = 5
_RESTART_BACKOFF = [2, 4, 8, 16, 32, 60]
_RESTART_NOTIFY_THRESHOLD = 3

# 当前 consumer 进程 PID 追踪，防止 kill 时误杀新进程
_current_consumer_pid = None
_current_consumer_lock = threading.Lock()

# stdin keepalive 管道管理
_stdin_write_end = None
_stdin_keepalive_stop = threading.Event()
_prev_lark_log = None

# Task #5 / #10: Dead letter queue for malformed events
DEAD_LETTER_DIR = BASE_DIR / ".dead_letter"
MAX_DEAD_LETTER_FILES = 50

# Task #5: Required fields for event validation
REQUIRED_FIELDS = ['message_id', 'sender_id', 'chat_id', 'content', 'message_type']


def start_event_consumer():
    global _stdin_write_end, _prev_lark_log

    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DEAD_LETTER_DIR.mkdir(parents=True, exist_ok=True)

    _load_processed_ids()

    _cleanup_dead_letters()

    _stdin_keepalive_stop.set()
    if _stdin_write_end and not _stdin_write_end.closed:
        try:
            _stdin_write_end.close()
        except Exception:
            pass

    if _prev_lark_log and not _prev_lark_log.closed:
        try:
            _prev_lark_log.close()
        except Exception:
            pass

    _stdin_keepalive_stop.clear()

    log_debug("启动 lark-cli event consume 进程...")
    _lark_log = open(BASE_DIR / ".lark_event.log", "a", encoding="utf-8")
    _prev_lark_log = _lark_log

    # 使用 PIPE + keepalive 线程防止 stdin EOF
    # lark-cli 将 stdin 关闭视为退出信号，必须保持写入端打开
    # 注意：不使用 start_new_session=True，让消费者留在主进程的进程组中
    # 这样主进程退出/崩溃时，子进程会收到 SIGHUP 自动退出，避免孤儿进程
    proc = subprocess.Popen(
        [LARK_CLI, "event", "consume", "im.message.receive_v1",
         "--as", "bot", "--output-dir", ".feishu_events"],
        stdin=subprocess.PIPE,
        stdout=_lark_log,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(BASE_DIR),
    )
    proc._lark_log = _lark_log
    _stdin_write_end = proc.stdin

    # 写入初始字节激活管道
    try:
        proc.stdin.write("\n")
        proc.stdin.flush()
    except Exception:
        pass

    # 启动 keepalive 守护线程
    t = threading.Thread(
        target=_stdin_keepalive_loop,
        args=(proc.stdin, _stdin_keepalive_stop),
        daemon=True,
    )
    t.start()

    with _current_consumer_lock:
        global _current_consumer_pid
        _current_consumer_pid = proc.pid

    log_debug(f"事件监听进程已启动 (PID: {proc.pid})")
    log_debug(f"事件目录: {EVENTS_DIR}")
    global _last_event_time
    _last_event_time = time.time()
    return proc


def _stdin_keepalive_loop(stdin_pipe, stop_event):
    """每 20 秒写入换行符保持 stdin 管道打开."""
    while not stop_event.is_set():
        stop_event.wait(20)
        if stop_event.is_set():
            break
        try:
            if stdin_pipe and not stdin_pipe.closed:
                stdin_pipe.write("\n")
                stdin_pipe.flush()
        except Exception:
            break


def _load_processed_ids():
    """从 EVENTS_DIR 和 PROCESSED_DIR 加载已处理的 message_id 用于去重."""
    count = 0

    for event_file in EVENTS_DIR.glob("*.json"):
        if not (PROCESSED_DIR / event_file.name).exists():
            continue
        try:
            with open(event_file, "r", encoding="utf-8") as f:
                event = json.load(f)
            mid = event.get("message_id", "")
            if mid:
                _processed_ids.add(mid)
                count += 1
        except Exception:
            pass

    for processed_file in PROCESSED_DIR.glob("*.json"):
        try:
            with open(processed_file, "r", encoding="utf-8") as f:
                event = json.load(f)
            mid = event.get("message_id", "")
            if mid and mid not in _processed_ids:
                _processed_ids.add(mid)
                count += 1
        except Exception:
            pass

    if count > 0:
        log_debug(f"从已处理事件中加载了 {count} 个去重ID")


def _cleanup_dead_letters():
    """Task #10: Clean up excess dead letter files, keeping at most MAX_DEAD_LETTER_FILES."""
    if not DEAD_LETTER_DIR.exists():
        return
    dead_files = sorted(
        DEAD_LETTER_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
    )
    if len(dead_files) > MAX_DEAD_LETTER_FILES:
        for old_file in dead_files[:-MAX_DEAD_LETTER_FILES]:
            try:
                old_file.unlink(missing_ok=True)
            except Exception:
                pass


def _kill_specific_process(pid):
    """安全终止指定 PID 的进程及其子进程."""
    try:
        os.kill(pid, 15)  # SIGTERM
        for _ in range(5):
            try:
                os.kill(pid, 0)
                time.sleep(0.5)
            except OSError:
                break
        else:
            os.kill(pid, 9)  # SIGKILL
    except (OSError, ProcessLookupError):
        pass


def _get_child_pids(parent_pid):
    """获取父进程的所有子进程 PID."""
    children = []
    try:
        result = subprocess.run(
            ["pgrep", "-P", str(parent_pid)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for pid_str in result.stdout.strip().split("\n"):
                if pid_str:
                    children.append(int(pid_str))
    except Exception:
        pass
    return children


def _kill_stale_processes(protect_pid=None):
    """终止所有残留的 lark-cli event 进程（可指定保护 PID）."""
    if protect_pid is None:
        with _current_consumer_lock:
            protect_pid = _current_consumer_pid

    killed_any = False

    # 先终止 consumer 进程（保护当前 PID）
    for consumer_pid_str in _find_consumer_processes():
        pid = int(consumer_pid_str)
        if protect_pid and pid == protect_pid:
            continue
        try:
            # 先杀子进程（bus daemon）
            for child in _get_child_pids(pid):
                _kill_specific_process(child)
            _kill_specific_process(pid)
        except Exception:
            pass

    time.sleep(1)

    # 清理可能残留的孤立 event _bus 进程
    for bus_pid_str in _find_bus_processes():
        try:
            _kill_specific_process(int(bus_pid_str))
        except Exception:
            pass

    try:
        subprocess.run(
            [LARK_CLI, "event", "stop", "--force"],
            capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        pass

    time.sleep(1)

    remaining = _find_bus_processes() + _find_consumer_processes()
    if protect_pid:
        remaining = [p for p in remaining if int(p) != protect_pid]

    if remaining:
        # 最后通牒
        for pid_str in remaining:
            try:
                os.kill(int(pid_str), 9)
            except Exception:
                pass
        time.sleep(0.5)
        remaining2 = _find_bus_processes() + _find_consumer_processes()
        if protect_pid:
            remaining2 = [p for p in remaining2 if int(p) != protect_pid]
        if remaining2:
            log_warn(f"[清理] 仍有 {len(remaining2)} 个残留进程: {remaining2}")


def _find_consumer_processes():
    """查找 lark-cli event consume 进程."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "lark-cli event consume"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")
    except Exception:
        pass
    return []


def cleanup_all():
    """服务退出时的全量清理，不保护任何进程."""
    _kill_stale_processes(protect_pid=None)


def cleanup_old_processed(max_age_days: int = 7, max_files: int = 100):
    """清理过期的 processed 文件，防止堆积。

    Args:
        max_age_days: 删除超过此天数的文件（基于 mtime）
        max_files: 最多保留的文件数量（超出部分按 mtime 从旧到新删除）
    """
    if not PROCESSED_DIR.exists():
        return

    try:
        processed_files = sorted(
            PROCESSED_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,  # 新的在前
        )

        now = time.time()
        cutoff = now - max_age_days * 86400
        removed_count = 0

        for i, f in enumerate(processed_files):
            should_remove = False
            try:
                mtime = f.stat().st_mtime
                if mtime < cutoff:
                    should_remove = True
                elif i >= max_files:
                    should_remove = True
            except FileNotFoundError:
                should_remove = True

            if should_remove:
                try:
                    f.unlink(missing_ok=True)
                    removed_count += 1
                except Exception:
                    pass

        if removed_count > 0:
            log_debug(f"[清理] 已删除 {removed_count} 个过期/超出限制的 processed 文件")

        # 同步清理内存中过多的去重 ID
        with _processed_ids_lock:
            if len(_processed_ids) > max_files * 5:
                # 保留最近一半的 ID
                to_keep = max_files * 2
                excess = list(_processed_ids)[:-to_keep] if len(_processed_ids) > to_keep else []
                for mid in excess:
                    _processed_ids.discard(mid)

    except Exception as e:
        log_error(f"[清理] processed 文件清理异常: {e}")

    # Task #10: Also clean up dead letters during periodic cleanup
    _cleanup_dead_letters()


def is_bus_healthy(proc):
    if proc.poll() is not None:
        return False

    bus_procs = _find_bus_processes()
    if not bus_procs:
        log_warn("[BUS检测] 未找到 bus 进程，可能已挂掉")
        return False

    return True


def _find_bus_processes():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "lark-cli event _bus"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")
    except Exception:
        pass
    return []


def check_bus_stale():
    global _last_event_time
    elapsed = time.time() - _last_event_time
    if elapsed > BUS_STALE_THRESHOLD:
        log_warn(f"[BUS检测] 超过 {BUS_STALE_THRESHOLD}s 未收到事件，bus 可能僵死")
        return True
    return False


def reset_restart_count():
    global _restart_fail_count
    _restart_fail_count = 0


def restart_consumer(proc, notify=True):
    global _restart_fail_count
    _restart_fail_count += 1

    if _restart_fail_count > _MAX_RESTART_FAILS:
        log_error(f"事件监听连续失败 {_restart_fail_count} 次，暂停自动重试")
        send_feishu(f"❌ 事件监听连续失败 {_restart_fail_count} 次，已暂停自动重试。请手动检查服务状态或重启服务。")
        return None

    delay_idx = min(_restart_fail_count - 1, len(_RESTART_BACKOFF) - 1)
    delay = _RESTART_BACKOFF[delay_idx]

    log_warn(f"正在重启事件监听... (第{_restart_fail_count}次，{delay}s后启动)")
    if notify and _restart_fail_count >= _RESTART_NOTIFY_THRESHOLD:
        send_feishu(f"🔄 事件监听异常，{delay}s后第{_restart_fail_count}次重建...\n\n⚠️ 重启期间的消息可能丢失，如未收到回复请重新发送")

    # 1. 优雅终止当前进程及其子进程树
    if proc:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        for child_pid in _get_child_pids(proc.pid):
            try:
                os.kill(child_pid, signal.SIGTERM)
            except Exception:
                pass
        if hasattr(proc, "_lark_log") and proc._lark_log and not proc._lark_log.closed:
            try:
                proc._lark_log.close()
            except Exception:
                pass
        with _current_consumer_lock:
            global _current_consumer_pid
            _current_consumer_pid = None

    # 2. 清理可能残留的孤儿消费者进程（不保护任何 PID）
    for stale_pid_str in _find_consumer_processes():
        try:
            stale_pid = int(stale_pid_str)
            for child in _get_child_pids(stale_pid):
                try:
                    os.kill(child, signal.SIGTERM)
                except Exception:
                    pass
            os.kill(stale_pid, signal.SIGTERM)
            log_warn(f"[重启] 终止残留消费者进程: {stale_pid}")
        except (ValueError, ProcessLookupError, OSError):
            pass
    time.sleep(1)

    # 3. 清理残留的旧事件文件（重启期间产生的可能不完整）
    #    只删除空文件或无法解析的损坏文件，保留有效事件
    for f in EVENTS_DIR.glob("*.json"):
        try:
            if f.stat().st_size == 0:
                f.unlink(missing_ok=True)
                continue
            with open(f, "r", encoding="utf-8") as fh:
                json.load(fh)
        except (json.JSONDecodeError, OSError):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass

    time.sleep(delay)

    # 4. 额外等待确保旧进程端口释放
    time.sleep(1)

    new_proc = start_event_consumer()

    # 5. 等待 consumer 初始化完成
    time.sleep(3)

    if new_proc.poll() is not None:
        log_error(f"重启失败 (code: {new_proc.returncode})")
        return new_proc

    log_debug("事件监听重启成功")
    if _restart_fail_count >= _RESTART_NOTIFY_THRESHOLD:
        send_feishu("✅ 事件监听已重建")
    _restart_fail_count = 0
    return new_proc


# Task #5: JSON schema validation + dead letter helpers


def _move_to_dead_letter(src: Path) -> None:
    """Move an invalid event file to the dead letter directory (Task #5/#10)."""
    DEAD_LETTER_DIR.mkdir(exist_ok=True)
    dest = DEAD_LETTER_DIR / src.name
    try:
        shutil.move(str(src), str(dest))
        log_warn(f"事件格式无效，已移入死信队列: {src.name}")
    except Exception as e:
        log_error(f"移入死信队列失败: {src.name} -> {e}")


def _validate_event_fields(event: dict) -> bool:
    """Check that all required fields are present in the event (Task #5)."""
    return all(k in event for k in REQUIRED_FIELDS)


def process_event_files(session_pool, task_queues):
    global _last_event_time, _restart_fail_count

    event_files = sorted(EVENTS_DIR.glob("*.json"))
    if event_files:
        _last_event_time = time.time()
        _restart_fail_count = 0

    for event_file in event_files:
        dest = PROCESSED_DIR / event_file.name

        # 已处理过 → 跳过
        if dest.exists():
            try:
                event_file.unlink(missing_ok=True)
            except Exception:
                pass
            continue

        # 原子操作：先处理，再 rename 到 processed 目录
        try:
            with open(event_file, "r", encoding="utf-8") as f:
                event = json.load(f)
        except Exception as e:
            log_error(f"解析事件文件失败: {e}")
            _move_to_processed(event_file, dest)
            continue

        # Task #5: Validate required fields
        if not _validate_event_fields(event):
            log_warn(f"事件格式无效，缺少必需字段: {event_file.name}")
            message_id = event.get("message_id", "")
            if message_id:
                with _processed_ids_lock:
                    _processed_ids.add(message_id)
            _move_to_dead_letter(event_file)
            continue

        message_id = event.get("message_id", "")
        with _processed_ids_lock:
            if message_id in _processed_ids:
                _move_to_processed(event_file, dest)
                continue
            _processed_ids.add(message_id)

        sender_id = event.get("sender_id", "")
        content = event.get("content", "").strip()
        message_type = event.get("message_type", "")
        chat_id = event.get("chat_id", CHAT_ID)

        if sender_id != MY_OPEN_ID:
            _move_to_processed(event_file, dest)
            continue

        if message_type not in ("text", "post"):
            send_feishu_markdown(f"📎 暂不支持图片/文件等非文本消息（收到类型: {message_type}），请发送文字消息", chat_id)
            _move_to_processed(event_file, dest)
            continue

        if not content:
            _move_to_processed(event_file, dest)
            continue

        # 先 rename 再处理消息，防止处理期间重复读取
        _move_to_processed(event_file, dest)
        _handle_message(content, chat_id, session_pool, task_queues)

    _cleanup_old_events()

    # Task #10: Periodically clean dead letters (keep at most MAX_DEAD_LETTER_FILES)
    _cleanup_dead_letters()


def _move_to_processed(src, dest):
    """原子操作将事件文件移到 processed 目录."""
    try:
        os.rename(src, dest)
    except FileNotFoundError:
        pass
    except OSError:
        # 跨文件系统时 fallback 到 copy + unlink
        try:
            shutil.copy2(src, dest)
            src.unlink(missing_ok=True)
        except Exception:
            pass


def _handle_message(content, chat_id, session_pool, task_queues):
    instruction, is_command, cmd, args = parse_message(content)

    if not instruction:
        return

    if is_command and handle_builtin_command(cmd, args, chat_id, session_pool, task_queues):
        log_debug(f"内置命令: /{cmd}")
        return

    active_session = session_pool.get_active()
    active_name = active_session.name
    tq = task_queues.get(active_name)

    if not tq:
        log_error(f"Session `{active_name}` 无 TaskQueue")
        return

    if is_command:
        log_debug(f"[{active_name}] 收到指令: {instruction}")
    else:
        log_debug(f"[{active_name}] 收到消息(闲聊): {instruction}")

    if tq.is_busy:
        tq.inject_pending(instruction)
        send_feishu_markdown(f"📎 [{active_name}] 你的消息已追加到当前正在执行的任务中，AI 会在处理时参考", chat_id)
        return

    tq.submit(instruction, chat_id, is_command, task_queues)


def _cleanup_old_events(keep_count=100):
    """清理旧的处理后事件文件，防止 processed 目录堆积.

    与 cleanup_old_processed 的 max_files 保持一致，避免冲突。
    """
    processed_files = sorted(
        PROCESSED_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
    )
    if len(processed_files) > keep_count:
        for old_file in processed_files[:-keep_count]:
            try:
                old_file.unlink(missing_ok=True)
            except Exception:
                pass

    with _processed_ids_lock:
        if len(_processed_ids) > keep_count * 5:
            to_remove = list(_processed_ids)[:keep_count * 2]
            for mid in to_remove:
                _processed_ids.discard(mid)
