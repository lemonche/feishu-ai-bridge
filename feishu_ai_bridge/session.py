import json
import time
import threading

from .config import SESSION_TIMEOUT_SECONDS, BASE_DIR
from .feishu import log, log_warn, log_debug

_STATE_FILE = BASE_DIR / ".session_state.json"


def _format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m{s}s"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    return f"{h}h{m}m"


def _load_state():
    if not _STATE_FILE.exists():
        return None
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_warn(f"[WARN] 加载 Session 状态失败: {e}")
        return None


def _save_state(sessions_data, active_name):
    try:
        state = {
            "sessions": sessions_data,
            "active_name": active_name,
            "saved_at": time.time(),
        }
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_warn(f"[WARN] 保存 Session 状态失败: {e}")


class Session:
    def __init__(self, name, session_id=None):
        self.name = name
        self._session_id = session_id or f"fb-{name}-{int(time.time())}"
        self._last_active = time.time()
        self._message_count = 0
        self._lock = threading.Lock()
        self._created_at = time.time()

    @property
    def session_id(self):
        with self._lock:
            self._check_timeout()
            return self._session_id

    @property
    def session_id_safe(self):
        """Get session_id without triggering timeout check side effect."""
        with self._lock:
            return self._session_id

    def touch(self):
        with self._lock:
            self._last_active = time.time()
            self._message_count += 1

    def update_last_active(self):
        """Thread-safe update of last_active timestamp without incrementing message count."""
        with self._lock:
            self._last_active = time.time()

    def get_session_id(self):
        """Public accessor for session_id without side effects."""
        with self._lock:
            return self._session_id

    def reset(self):
        with self._lock:
            old = self._session_id
            self._session_id = f"fb-{self.name}-{int(time.time())}"
            self._last_active = time.time()
            self._message_count = 0
            log_debug(f"Session[{self.name}] 重置: {old} → {self._session_id}")
            return self._session_id

    def _check_timeout(self):
        elapsed = time.time() - self._last_active
        if elapsed > SESSION_TIMEOUT_SECONDS:
            old = self._session_id
            self._session_id = f"fb-{self.name}-{int(time.time())}"
            self._last_active = time.time()
            self._message_count = 0
            log_debug(f"Session[{self.name}] 超时({elapsed:.0f}s)，重置: {old} → {self._session_id}")

    def check_and_consume_timeout(self):
        with self._lock:
            elapsed = time.time() - self._last_active
            if elapsed > SESSION_TIMEOUT_SECONDS:
                old = self._session_id
                self._session_id = f"fb-{self.name}-{int(time.time())}"
                self._last_active = time.time()
                self._message_count = 0
                log_debug(f"Session[{self.name}] 超时({elapsed:.0f}s)，重置: {old} → {self._session_id}")
                return True
            return False

    @property
    def info(self):
        with self._lock:
            self._check_timeout()
            elapsed = time.time() - self._last_active
            age = time.time() - self._created_at
            return {
                "name": self.name,
                "session_id": self._session_id,
                "last_active_ago": _format_duration(elapsed),
                "message_count": self._message_count,
                "timeout_seconds": SESSION_TIMEOUT_SECONDS,
                "age_seconds": int(age),
            }


class SessionPool:
    def __init__(self):
        self._sessions = {}
        self._active_name = None
        self._lock = threading.Lock()
        self._restore_state()

    def _restore_state(self):
        state = _load_state()
        if not state or "sessions" not in state:
            self._create_session("main")
            return

        restored_count = 0
        for name, data in state["sessions"].items():
            session_id = data.get("session_id")
            session = Session(name, session_id=session_id)
            self._sessions[name] = session
            restored_count += 1
            log_debug(f"Session[{name}] 已恢复: {session.session_id}")

        # 确保 "main" 始终存在
        if "main" not in self._sessions:
            self._create_session("main")
            restored_count += 1

        saved_active = state.get("active_name", "main")

        # 启动时始终恢复为 "main"
        if saved_active != "main":
            if saved_active in self._sessions:
                log_warn(f"[WARN] 上次活跃 Session 是 '{saved_active}'，启动后将自动切换回 'main'")
            else:
                log_warn(f"[WARN] 上次活跃 Session '{saved_active}' 已不存在，回退到 'main'")

        self._active_name = "main"
        log_debug(f"已恢复 {restored_count} 个 Session，当前活跃: main")

    def _create_session(self, name):
        session = Session(name)
        self._sessions[name] = session
        self._active_name = name
        log_debug(f"Session[{name}] 已创建: {session.session_id}")
        self._persist()
        return session

    def _persist(self):
        sessions_data = {}
        for name, session in self._sessions.items():
            sessions_data[name] = {
                "session_id": session.get_session_id(),
            }
        _save_state(sessions_data, self._active_name)

    def get_active(self):
        with self._lock:
            if self._active_name and self._active_name in self._sessions:
                return self._sessions[self._active_name]
            if self._sessions:
                first = next(iter(self._sessions))
                self._active_name = first
                return self._sessions[first]
            return self._create_session("main")

    def get(self, name):
        with self._lock:
            return self._sessions.get(name)

    def switch(self, name):
        with self._lock:
            if name in self._sessions:
                self._active_name = name
                self._persist()
                return self._sessions[name]
            return None

    def create(self, name):
        with self._lock:
            if name in self._sessions:
                return None
            session = Session(name)
            self._sessions[name] = session
            self._active_name = name
            log_debug(f"Session[{name}] 已创建: {session.session_id}")
            self._persist()
            return session

    def kill(self, name):
        with self._lock:
            if name == "main":
                return False
            if name not in self._sessions:
                return False
            del self._sessions[name]
            if self._active_name == name:
                self._active_name = next(iter(self._sessions), "main")
            self._persist()
            return True

    @property
    def active_name(self):
        with self._lock:
            return self._active_name

    def list_sessions(self):
        with self._lock:
            result = []
            for name, session in self._sessions.items():
                info = session.info
                info["is_active"] = (name == self._active_name)
                result.append(info)
            return result

    def all_sessions(self):
        with self._lock:
            return dict(self._sessions)
