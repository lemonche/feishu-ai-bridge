"""i18n text registry — all user-facing UI strings extracted for future localization."""

TEXTS = {
    # Help
    "help.title": "📖 帮助",
    "help.content": (
        "**指令前缀:** `/`\n\n"
        "**内置命令:**\n"
        "- `/help` — 显示帮助信息\n"
        "- `/status` — 查看所有 Session 状态\n"
        "- `/reset` — 重置当前 Session 上下文\n"
        "- `/restart` — 重启整个服务（清理所有旧进程）\n"
        "- `/stop` — 强制停止当前 Session 的任务\n"
        "- `/backend` — 查看所有 AI 后端\n"
        "- `/backend <name>` — 切换 AI 后端（如 trae / qwen）\n"
        "- `/profile` — 查看所有配置档案\n"
        "- `/profile <name>` — 切换配置档案\n"
        "- `/session` — 查看所有 Session\n"
        "- `/session new <name>` — 创建新 Session\n"
        "- `/session switch <name>` — 切换到某个 Session\n"
        "- `/session kill <name>` — 终止某个 Session\n\n"
        "**使用方式:**\n"
        "- `/创建一个hello.txt文件` — 指令模式，卡片消息回复\n"
        "- `你好` — 闲聊模式，也转发给AI\n\n"
        "**多 Session:**\n"
        "每个 Session 独立运行，互不干扰\n"
        "执行中的任务在后台继续，可切换到其他 Session 工作"
    ),

    # Status
    "status.title": "📊 全局状态",
    "status.running_time": "**运行时长:** {uptime}",
    "status.backend": "**当前后端:** `{backend}` ({backends})",
    "status.profile": "**当前档案:** `{profile}` — {model}",
    "status.active_session": "**活跃 Session:** `{active_name}`",
    "status.cli_ok": "**{backend} CLI:** ✅ {version}",
    "status.cli_warn": "**{backend} CLI:** ⚠️ 可执行但异常",
    "status.cli_not_found": "**{backend} CLI:** ❌ 未找到 `{path}`",
    "status.cli_timeout": "**{backend} CLI:** ⚠️ 检测超时",
    "status.event_fail": "**事件监听:** ⚠️ 连续失败 {count} 次",
    "status.event_ok": "**事件监听:** ✅ 正常",
    "status.sessions_header": "── Sessions ──",
    "status.session_line": "**`{name}`**{marker}",
    "status.session_state": "  状态: {busy} | 消息: {msg_count} | 完成: {completed}",
    "status.session_current": "  当前: {current}",
    "status.session_no_queue": "**`{name}`**{marker} — 无队列",
    "status.history_header": "── 最近执行 ──",
    "status.history_line": "  {status} [{time}] {session}: {content} ({duration}s)",

    # Reset
    "reset.title": "🔄 Session 已重置",
    "reset.content": "Session: `{name}`\n新 ID: `{new_id}`\n\n上下文已清空",

    # Restart
    "restart.title": "🔄 正在重启...",
    "restart.content": "正在清理旧进程并重启服务...\n\n请等待 10-15 秒，服务将自动重新上线。",

    # Stop
    "stop.idle": "ℹ️ 无运行任务",
    "stop.idle_desc": "Session `{name}` 当前没有正在执行的任务",
    "stop.done": "🛑 任务已停止",
    "stop.done_desc": "**Session:** `{name}`\n**已停止任务:** {task}\n\n进程 PID: `{pid}` 已被终止",
    "stop.fail": "⚠️ 停止失败",
    "stop.fail_desc": "无法停止当前任务，请稍后重试",
    "stop.switch_hint": "⚠️ 请稍候",
    "stop.switch_desc": "当前Session正在执行任务，请等待完成或使用/stop后再切换",

    # Profile
    "profile.title": "🎭 配置档案",
    "profile.list_hint": "\n\n💡 使用 `/profile <name>` 切换档案",
    "profile.not_found": "❌ 档案不存在",
    "profile.not_found_desc": "未找到档案: `{name}`\n\n使用 `/profile` 查看所有可用档案",
    "profile.switched": "🎭 档案已切换",
    "profile.switched_desc": "**已切换到:** `{name}`\n\n- 模型: {model}\n- 描述: {desc}\n{overrides}",

    # Backend
    "backend.title": "🤖 AI 后端",
    "backend.list_hint": "\n\n💡 使用 `/backend <name>` 切换后端",
    "backend.not_found": "❌ 后端不存在",
    "backend.not_found_desc": "未找到后端: `{name}`\n\n可用后端: {available}",
    "backend.already": "ℹ️ 已是当前后端",
    "backend.already_desc": "当前已经是 `{name}` 后端",
    "backend.switched": "🤖 后端已切换",
    "backend.switched_desc": "**已切换到:** `{name}`\n- 路径: `{path}`\n- Session ID: `{sid}`\n- 超时: {timeout}s",
    "backend.switch_fail": "❌ 切换失败",
    "backend.switch_fail_desc": "无法切换到 `{name}`",

    # Session
    "session.title": "🗂️ Session 管理",
    "session.list_hint": "\n\n💡 `/session new <name>` 创建 | `/session switch <name>` 切换 | `/session kill <name>` 终止",
    "session.unknown_cmd": "❓ 未知子命令",
    "session.unknown_desc": "用法:\n- `/session` — 查看所有 Session\n- `/session new <name>` — 创建新 Session\n- `/session switch <name>` — 切换 Session\n- `/session kill <name>` — 终止 Session",
    "session.create_missing": "❌ 缺少名称",
    "session.create_missing_desc": "用法: `/session new <name>`",
    "session.create_invalid": "❌ 名称无效",
    "session.create_invalid_desc": "Session 名称仅支持字母、数字、连字符和下划线",
    "session.create_dup": "❌ 名称已存在",
    "session.create_dup_desc": "Session `{name}` 已存在，请使用其他名称",
    "session.created": "✅ Session 已创建",
    "session.created_desc": "**名称:** `{name}`\n**Session ID:** `{sid}`\n\n已自动切换到新 Session",
    "session.switch_missing": "❌ 缺少名称",
    "session.switch_missing_desc": "用法: `/session switch <name>`",
    "session.switch_notfound": "❌ Session 不存在",
    "session.switch_notfound_desc": "未找到 Session `{name}`\n\n使用 `/session` 查看所有 Session",
    "session.switched": "🔄 已切换 Session",
    "session.switched_desc": "**当前 Session:** `{name}`\n**状态:** {busy}\n**Session ID:** `{sid}`",
    "session.kill_missing": "❌ 缺少名称",
    "session.kill_missing_desc": "用法: `/session kill <name>`",
    "session.kill_main": "❌ 无法终止",
    "session.kill_main_desc": "主 Session (main) 不可终止",
    "session.killed": "🗑️ Session 已终止",
    "session.killed_desc": "Session `{name}` 已终止\n当前活跃 Session: `{new_active}`",
    "session.kill_fail": "❌ 终止失败",
    "session.kill_fail_desc": "未找到 Session `{name}`",

    # Queue / Execution
    "queue.full": "⚠️ [{name}] 任务队列已满，请稍后再试",
    "queue.full_hint": "\n💡 可用 `/session new <name>` 创建新 Session 或 `/session switch <name>` 切换到空闲 Session",
    "queue.full_idle": "\n可切换: {idle}",
    "queue.full_retry": "\n请稍后重试",
    "queue.queued": "📋 [{name}] 任务已排队 (队列: {size})",
    "queue.inject": "📎 [{name}] 你的消息已追加到当前正在执行的任务中，AI 会在处理时参考",
    "queue.internal_error": "❌ [{name}] 任务执行遇到内部错误，请重试或使用 /reset 重置",
    "queue.worker_error": "🚨 [{name}] 任务执行线程已停止，请/restart 重启服务",
    "exec.timeout": "⏰ Session 已超时重置",
    "exec.timeout_desc": "Session `{name}` 因超过 {timeout_desc} 未使用，上下文已自动清空\n本次对话将从新上下文开始",
    "exec.command": "🤖 收到指令",
    "exec.command_desc": "**[{name}]** {content}\n\n正在执行... (超时限制: {timeout_min}分钟)",
    "exec.thinking": "💭 正在思考",
    "exec.thinking_desc": "**[{name}]** {content}\n\n处理中...",
    "exec.done": "✅ 执行完成",
    "exec.stopped": "🛑 任务已停止",
    "exec.error": "⚠️ 执行遇到问题",
    "exec.retry": "🔄 重试中",
    "exec.retry_desc": "执行失败，{delay}s 后自动重试\n**原因:** {reason}",
    "exec.cancelled": "🛑 已取消",
    "exec.cancelled_desc": "**指令:** {instruction}\n\n任务已被用户停止",
    "exec.progress": "⏳ 执行中...",
    "exec.progress_desc": "**指令:** {instruction}\n\n**已执行步骤:** {step_count} | **已用时:** {elapsed}\n\n_仍在执行中，请耐心等待..._",
    "exec.progress_simple": "**已执行步骤:** {step_count}\n\n_正在处理中..._",
    "exec.heartbeat": "**指令:** {instruction}\n\n**已执行步骤:** {step_count} | **已用时:** {elapsed}\n\n_仍在执行中，请耐心等待..._",

    # Service lifecycle
    "service.online": "🟢 服务上线",
    "service.online_desc": "桥接服务 v7 已启动\nSession: `{session}`{restored}\n\n支持多 Session 并行执行",
    "service.offline": "🔴 服务下线",
    "service.offline_desc": "桥接服务已停止\n运行时长: {uptime}",
    "service.event_rebuilt": "✅ 事件监听已重建",
    "service.event_rebuilding": "🔄 事件监听异常，{delay}s后第{count}次重建...\n\n⚠️ 重启期间的消息可能丢失，如未收到回复请重新发送",
    "service.event_max_fail": "❌ 事件监听连续失败 {count} 次，已暂停自动重试。请手动检查服务状态或重启服务。",

    # Misc
    "misc.unsupported": "📎 暂不支持图片/文件等非文本消息（收到类型: {type}），请发送文字消息",
    "misc.card_fallback": "卡片发送失败，以下是文字摘要：\n\n⚠️ {title}\n{desc}",
    "misc.card_final_fallback": "⚠️ {title}",
    "misc.non_text": "📎 暂不支持图片/文件等非文本消息（收到类型: {type}），请发送文字消息",
    "misc.event_invalid": "事件格式无效，缺少必需字段: {file}",
}


def t(key: str, **kwargs) -> str:
    """Look up a text by key and format it with kwargs."""
    text = TEXTS.get(key, key)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text
