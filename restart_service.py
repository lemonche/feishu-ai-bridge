#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import signal

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def kill_all_processes(exclude_pid=None):
    """Kill all related processes, optionally excluding a specific PID."""
    print("🔄 正在清理旧进程...")

    exclude_set = set()
    if exclude_pid:
        exclude_set.add(int(exclude_pid))

    def safe_kill(pid_str, label):
        if not pid_str:
            return
        try:
            pid = int(pid_str)
            if pid in exclude_set or pid == os.getpid():
                return
            os.kill(pid, signal.SIGTERM)
            print(f"  ✅ 终止进程: {pid} ({label})")
        except Exception as e:
            print(f"  ❌ 无法终止 {pid_str}: {e}")

    try:
        result = subprocess.run(['pgrep', '-f', 'python3 main.py'], capture_output=True, text=True)
        if result.returncode == 0:
            for pid in result.stdout.strip().split('\n'):
                safe_kill(pid, 'python3 main.py')
    except Exception:
        pass

    try:
        result = subprocess.run(['pgrep', '-f', 'lark-cli event'], capture_output=True, text=True)
        if result.returncode == 0:
            for pid in result.stdout.strip().split('\n'):
                safe_kill(pid, 'lark-cli event')
    except Exception:
        pass

    try:
        result = subprocess.run(['pgrep', '-f', '@larksuite/cli'], capture_output=True, text=True)
        if result.returncode == 0:
            for pid in result.stdout.strip().split('\n'):
                safe_kill(pid, 'lark-cli')
    except Exception:
        pass

    print("⏳ 等待进程完全退出...")
    time.sleep(3)

    subprocess.run(['pkill', '-f', 'python3 main.py'], capture_output=True)
    subprocess.run(['pkill', '-f', 'lark-cli event'], capture_output=True)
    time.sleep(1)

    print("✅ 旧进程清理完成")

def restart_service(exclude_pid=None):
    """Restart the service"""
    kill_all_processes(exclude_pid=exclude_pid)

    print("\n🚀 正在重新启动服务...")

    os.chdir(BASE_DIR)

    log_file = os.path.join(BASE_DIR, "service_restart.log")

    with open(log_file, "w") as f:
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=f,
            stderr=f,
            start_new_session=True,
            cwd=BASE_DIR
        )

    print(f"✅ 服务已重新启动 (PID: {process.pid})")
    print(f"📝 日志文件: {log_file}")
    print("\n✅ 重启成功！请在飞书中等待几秒后使用。")

if __name__ == "__main__":
    exclude_pid = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--exclude-pid":
        exclude_pid = sys.argv[2]
    restart_service(exclude_pid=exclude_pid)
