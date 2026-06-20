#!/usr/bin/env python3
"""
Feishu AI Anydoor
飞书消息 → 多Session路由 → 异步队列执行 → 富文本对话回传飞书

启动: python3 main.py
守护: launchctl load com.feishu-ai-anydoor.plist
"""

import atexit
import os
import subprocess
import time
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from feishu_ai_bridge.config import (
    SESSION_TIMEOUT_SECONDS, POLL_INTERVAL,
    STATUS_UPDATE_INTERVAL, COMMAND_PREFIX, MAX_QUEUE_SIZE,
    HEALTH_CHECK_INTERVAL, CHAT_ID, PID_FILE, validate_startup,
    get_app_context, ACTIVE_BACKEND, BACKENDS,
)
from feishu_ai_bridge.feishu import log, log_info, log_warn, log_error, log_debug, send_reply, send_feishu_markdown
from feishu_ai_bridge.session import SessionPool
from feishu_ai_bridge.queue import TaskQueue
from feishu_ai_bridge.commands import set_service_start_time
from feishu_ai_bridge.event_consumer import (
    start_event_consumer, process_event_files,
    is_bus_healthy, check_bus_stale, restart_consumer,
    cleanup_all, cleanup_old_processed, reset_restart_count,
)


def _uptime(ctx):
    elapsed = int(time.time() - ctx.start_time)
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h{minutes}m"
    return f"{minutes}m{seconds}s"


def _cleanup():
    ctx = get_app_context()
    log_info("正在清理资源...")

    if ctx.event_proc and ctx.event_proc.poll() is None:
        ctx.event_proc.terminate()
        try:
            ctx.event_proc.wait(timeout=5)
        except Exception:
            ctx.event_proc.kill()
        log_info("事件监听进程已关闭")

    from feishu_ai_bridge.event_consumer import _kill_stale_processes
    _kill_stale_processes(protect_pid=None)

    cleanup_all()

    try:
        send_feishu_markdown(
            f"🔴 桥接服务已停止\n\n运行时长: {_uptime(ctx)}",
            CHAT_ID,
        )
    except Exception:
        pass

    log_info("清理完成")

    # 移除 PID 文件
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _signal_handler(sig, frame):
    ctx = get_app_context()
    ctx.running = False
    log_info(f"收到停止信号 (signal {sig})，即将清理并退出...")


def _acquire_pid_lock():
    """Acquire the PID file lock to prevent duplicate instances. (Task #2)"""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)  # 检查进程是否存活
            log_error(f"[启动失败] 另一个实例正在运行 (PID: {old_pid})，如需强制启动请删除 {PID_FILE}")
            sys.exit(1)
        except (ValueError, ProcessLookupError, OSError):
            log_info("[启动] 清理残留 PID 文件")
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            PID_FILE.unlink(missing_ok=True)

    try:
        fd = os.open(str(PID_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        log_error(f"[启动失败] 另一个实例正在运行 (PID 文件已创建)，如需强制启动请删除 {PID_FILE}")
        sys.exit(1)

    stale_mains = []
    try:
        result = subprocess.run(
            ["pgrep", "-f", "main.py"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for pid_str in result.stdout.strip().split("\n"):
                if pid_str:
                    pid = int(pid_str)
                    if pid != os.getpid():
                        stale_mains.append(pid)
    except Exception:
        pass

    if stale_mains:
        log_warn(f"[启动] 发现 {len(stale_mains)} 个残留主进程: {stale_mains}，正在清理...")
        for pid in stale_mains:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        time.sleep(3)
        for pid in stale_mains:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        time.sleep(1)


def _print_startup_info():
    """Print startup banner with configuration details. (Task #2)"""
    log_info("=" * 50)
    log_info("飞书 ↔ Trae CLI 桥接服务 v7")
    log_info(f"超时: {SESSION_TIMEOUT_SECONDS}s")
    log_info(f"轮询间隔: {POLL_INTERVAL}s")
    log_info(f"状态推送间隔: {STATUS_UPDATE_INTERVAL}s")
    log_info(f"指令前缀: {COMMAND_PREFIX}")
    log_info(f"最大队列: {MAX_QUEUE_SIZE}")
    log_info(f"健康检查: {HEALTH_CHECK_INTERVAL}s")
    log_info("=" * 50)


def _detect_cli_version():
    """Detect CLI version once at startup for /status cache. (Task #4)"""
    backend_cfg = BACKENDS.get(ACTIVE_BACKEND, {})
    backend_path = backend_cfg.get("path", "")
    if not backend_path:
        return "⚠️ 未配置"
    try:
        cli_path = Path(backend_path).expanduser()
        result = subprocess.run(
            [str(cli_path), "--version"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return f"✅ {result.stdout.strip()[:30]}"
        return "⚠️ 可执行但异常"
    except FileNotFoundError:
        return f"❌ 未找到 `{backend_path}`"
    except Exception:
        return "⚠️ 检测超时"


def _run_event_loop(ctx):
    """Main event loop: poll for events, health checks, and cleanup. (Task #2)"""
    last_health_check = time.time()
    last_processed_cleanup = time.time()
    _consumer_paused_until = 0.0

    while ctx.running:
        try:
            if ctx.event_proc is None or ctx.event_proc.poll() is not None:
                if time.time() < _consumer_paused_until:
                    time.sleep(1)
                    continue

                if ctx.event_proc is not None and ctx.event_proc.poll() is not None:
                    exit_code = ctx.event_proc.returncode
                    log_warn(f"事件监听进程已退出 (code: {exit_code})，清空引用并补偿处理积压事件")
                    ctx.event_proc = None
                    process_event_files(ctx.session_pool, ctx.task_queues)
                    if exit_code == 0:
                        time.sleep(3)
                    continue

                # ctx.event_proc is None: 异步触发重建
                log_info("正在重启事件监听...")
                startup_grace = (time.time() - ctx.start_time) < 60
                ctx.event_proc = restart_consumer(None, notify=not startup_grace)
                if ctx.event_proc is None:
                    _consumer_paused_until = time.time() + 60
                    log_warn("事件监听进入 60s 冷却期")
                continue

            now = time.time()
            if now - last_health_check >= HEALTH_CHECK_INTERVAL:
                last_health_check = now

                if not is_bus_healthy(ctx.event_proc):
                    log_warn("[健康检查] bus 进程异常，触发自动重建")
                    ctx.event_proc = restart_consumer(ctx.event_proc)
                    if ctx.event_proc is None:
                        _consumer_paused_until = time.time() + 60
                    continue

                if check_bus_stale():
                    log_warn("[健康检查] 事件流僵死，触发自动重建")
                    ctx.event_proc = restart_consumer(ctx.event_proc)
                    if ctx.event_proc is None:
                        _consumer_paused_until = time.time() + 60
                    continue

                active = ctx.session_pool.active_name
                with ctx.task_queues_lock:
                    busy_count = sum(1 for tq in ctx.task_queues.values() if tq.is_busy)
                    total_completed = sum(tq.status_info["total_completed"] for tq in ctx.task_queues.values())
                reset_restart_count()
                log_debug(f"[健康检查] active={active} sessions={len(ctx.task_queues)} busy={busy_count} completed={total_completed}")

            if now - last_processed_cleanup >= 3600:
                last_processed_cleanup = now
                cleanup_old_processed()

            process_event_files(ctx.session_pool, ctx.task_queues)

        except Exception as e:
            log_error(f"处理异常: {e}")

        time.sleep(POLL_INTERVAL)

    log_info("桥接服务正在停止...")


def main():
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    atexit.register(_cleanup)

    from feishu_ai_bridge.event_consumer import _kill_stale_processes
    _kill_stale_processes(protect_pid=None)
    time.sleep(2)

    # PID 锁
    _acquire_pid_lock()

    # 初始启动时清理上次运行的残留资源
    cleanup_all()
    # 清理过期 processed 文件
    cleanup_old_processed()

    errors, warnings = validate_startup()
    if errors:
        for e in errors:
            log_error(f"[启动失败] {e}")
        sys.exit(1)
    for w in warnings:
        log_warn(f"[警告] {w}")

    _print_startup_info()

    # 初始化 AppContext
    ctx = get_app_context()
    ctx.start_time = time.time()

    # 一次性检测 CLI 版本，后续 /status 直接读缓存 (Task #4)
    ctx.cli_version_cache = _detect_cli_version()
    log_debug(f"CLI版本缓存: {ctx.cli_version_cache}")

    ctx.session_pool = SessionPool()
    set_service_start_time(time.time())

    all_sessions = ctx.session_pool.all_sessions()
    ctx.task_queues = {name: TaskQueue(s) for name, s in all_sessions.items()}
    for name, tq in ctx.task_queues.items():
        tq.start_worker()
        log_info(f"[{name}] TaskQueue 已创建 (恢复)")

    ctx.event_proc = start_event_consumer()
    reset_restart_count()

    time.sleep(3)

    if ctx.event_proc.poll() is not None:
        err = ctx.event_proc.stderr.read() if ctx.event_proc.stderr else ""
        log_error(f"初始事件监听进程退出 (code: {ctx.event_proc.returncode}), stderr: {err[:300]}")

    active = ctx.session_pool.get_active()
    session_count = len(ctx.task_queues)
    restored_note = f"\n已恢复 {session_count} 个 Session" if session_count > 1 else ""
    send_feishu_markdown(
        f"🟢 桥接服务已上线\n\nSession: `{active.session_id}`{restored_note}\n\n支持多 Session 并行执行",
        CHAT_ID,
    )

    _run_event_loop(ctx)


if __name__ == "__main__":
    main()
