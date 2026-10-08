# -*- coding: utf-8 -*-
"""屏幕观察者：判断"用户现在在干什么"，并决定桌宠该怎么反应。

两层策略：
  轻量层（每 poll_seconds 采样，几乎零成本）
    - 前台进程 / 窗口标题 / 空闲时间 → 归类
    - 靠内置规则给出反馈：久坐、深夜、摸鱼、离开回来…
  视觉层（有冷却，默认 5 分钟一次）
    - 截图交给本地视觉模型，让它以桌宠口吻点评
    - 敏感窗口（密码/网银…）直接跳过，不看也不说

所有耗时操作（视觉请求）都放后台线程，不阻塞界面。
"""
import random
import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal

import activity

# 类别 -> 中文说明（用于给模型/聊天提供上下文）
CATEGORY_LABELS = {
    "coding": "写代码或用终端",
    "browsing": "浏览网页",
    "media": "看视频或听音乐",
    "game": "玩游戏",
    "office": "处理文档",
    "chat": "聊天或开会",
    "design": "做设计",
    "explorer": "整理文件",
    "other": "用电脑",
    "unknown": "没在用什么程序",
}

# 轻量层的台词（不需要模型，随机挑一句）
LINES = {
    "coding": [
        "又在敲代码呀，我安静看着 (oωo)",
        "写代码辛苦啦，记得喝水~",
        "这段 bug 是不是又在装死？我帮你盯着它！",
    ],
    "browsing": [
        "网页翻了半天，找到想要的了吗？",
        "别刷太久哦，眼睛要休息的~",
    ],
    "media": [
        "看视频不叫我一起？(｀へ´)",
        "好看吗好看吗？讲给我听听~",
    ],
    "game": [
        "打赢了吗？赢了要跟我炫耀哦！",
        "游戏打得怎么样呀~",
    ],
    "office": [
        "文档写得怎么样啦，我陪你慢慢弄~",
        "工作加油！累了就摸摸我 (^_^)",
    ],
    "chat": [
        "在跟谁聊天呀，笑得这么开心？",
        "开会辛苦啦，我在这儿等你~",
    ],
    "design": [
        "在做图呀，好看的话给我也画一张！",
        "设计时间到~ 我安静点不打扰你 (｡･ω･｡)",
    ],
    "explorer": [
        "在翻文件呀，别翻丢了哦~",
    ],
    "other": [
        "在忙呀，我就静静趴着~",
    ],
    "unknown": [
        "发呆中……要不我们聊聊天？",
    ],
}

# 视觉点评的提示词（直接用人设，输出短句）
VISION_PROMPT = (
    "这是用户当前的屏幕截图。用一句话（不超过30个字）以桌宠口吻对他正在做的事情做出反应："
    "可以好奇、可以吐槽、可以鼓励，也可以提醒休息。"
    "不要复述截图里的文字内容，不要客套，不要用 Markdown，直接说那句话。"
)


class _VisionWorker(QThread):
    """后台跑一次视觉请求。"""
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, client, image_b64, prompt, system_prompt=None, max_tokens=200):
        super().__init__()
        self.client = client
        self.image_b64 = image_b64
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    def run(self):
        try:
            text = self.client.vision_comment(
                self.image_b64, self.prompt,
                system_prompt=self.system_prompt,
                max_tokens=self.max_tokens,
            )
            self.done.emit((text or "").strip())
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


class ScreenWatcher(QObject):
    """定时观察屏幕，产出"该说什么"。"""

    comment = Signal(str)           # 想让桌宠冒泡的内容
    context_changed = Signal(str)   # 活动上下文变化（给聊天用）
    busy_changed = Signal(bool)     # 是否正在做视觉分析（桌宠切"思考"状态）
    error = Signal(str)             # 视觉调用失败（只报一次，避免刷屏）

    def __init__(self, cfg: dict, client, parent=None):
        super().__init__(parent)
        w = cfg.get("watch") or {}
        self.cfg = w
        self.client = client
        self.enabled = bool(w.get("enabled", True))
        self.poll_seconds = max(5, int(w.get("poll_seconds", 15)))
        self.min_gap = max(20, int(w.get("min_gap_seconds", 150)))
        self.vision_on = bool(w.get("vision", True))
        self.vision_interval = max(30, int(w.get("vision_interval_seconds", 300)))
        self.max_width = int(w.get("max_width", 1024))
        self.extra_private = [str(k).lower() for k in (w.get("blacklist") or [])]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._worker = None
        self._last_comment = 0.0
        # 从启动时刻起算，避免刚开机就截图点评（想立刻看可以点右键菜单）
        self._last_vision = time.time()
        self._vision_failed = False
        self._error_reported = False

        self._app = ""
        self._category = "unknown"
        self._since = time.time()
        self._idle_notified = False
        self._long_stay_notified = False
        self._night_notified = False
        self._last_context = ""

    # ---------------- 生命周期 ----------------
    def start(self):
        if not self.enabled:
            print("[桌宠] 屏幕观察已关闭（config 里 watch.enabled）")
            return
        self._timer.start(self.poll_seconds * 1000)
        print(f"[桌宠] 屏幕观察已启动：每 {self.poll_seconds}s 采样，"
              f"视觉点评间隔 {self.vision_interval}s")

    def stop(self):
        self._timer.stop()

    def shutdown(self):
        """程序退出时收尾：等视觉线程结束，避免 QThread 被销毁时还在运行。"""
        self.stop()
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(3000)

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        if self.enabled:
            self.start()
        else:
            self.stop()
        return self.enabled

    # ---------------- 采样 ----------------
    def _sample(self):
        snap = activity.snapshot()
        if snap.get("private") and self.extra_private:
            text = f"{snap.get('title', '')} {snap.get('app', '')}".lower()
            if any(k in text for k in self.extra_private):
                snap["private"] = True
        return snap

    def tick(self):
        if not self.enabled:
            return
        snap = self._sample()
        now = time.time()

        # 桌宠自己的窗口：忽略
        if snap.get("self"):
            return

        app = snap.get("app", "")
        cat = snap.get("category", "unknown")
        idle = snap.get("idle", 0)
        private = bool(snap.get("private"))

        # 切程序了
        switched = app != self._app
        if switched:
            self._app = app
            self._category = cat
            self._since = now
            self._long_stay_notified = False

        mins = (now - self._since) / 60

        # ---- 以下提醒与窗口内容无关，隐私窗口也照常 ----
        if idle > 600:
            if not self._idle_notified:
                self._idle_notified = True
                self._say("人跑哪去了……我在这儿等你回来哦 (｡･ω･｡)", force=True)
            self._update_context(snap, mins)
            return
        if self._idle_notified and idle < 5:
            self._idle_notified = False
            self._say("你回来啦！刚刚我还以为你把我忘了呢 (^_^)", force=True)
            self._update_context(snap, mins)
            return

        hour = time.localtime().tm_hour
        if 0 <= hour < 5 and idle < 60:
            if not self._night_notified:
                self._night_notified = True
                self._say(random.choice([
                    "都这个点了还不睡？我陪你，但你要答应我明天补觉 (oωo)",
                    "深夜模式启动……要不要我安静一点？",
                ]), force=True)
                self._update_context(snap, mins)
                return
        else:
            self._night_notified = False

        # ---- 隐私窗口：不点评、不截图、标题也不进上下文 ----
        if private:
            self._update_context(snap, mins)
            return

        # ---- 久坐提醒 ----
        if idle < 120:
            if mins > 50 and not self._long_stay_notified:
                self._long_stay_notified = True
                self._say(self._long_stay_line(cat, mins), force=True)
                self._update_context(snap, mins)
                return
            if mins > 90 and random.random() < 0.25:
                self._say("坐了好久好久啦，站起来走两步嘛~", force=True)
                self._update_context(snap, mins)
                return

        # ---- 常规陪伴（有冷却；刚换程序时更愿意搭话）----
        if cat != "unknown" and idle < 120:
            chance = 0.55 if switched else 0.22
            if random.random() < chance:
                self._say(self._category_line(cat))
                self._update_context(snap, mins)
                return

        # ---- 视觉点评（更长的冷却）----
        if self.vision_on and idle < 120 and (now - self._last_vision) >= self.vision_interval:
            self.look_now()

        self._update_context(snap, mins)

    def _update_context(self, snap, mins):
        ctx = self._context_text(snap, mins)
        if ctx and ctx != self._last_context:
            self._last_context = ctx
            self.context_changed.emit(ctx)

    # ---------------- 说话 ----------------
    def _category_line(self, cat):
        pool = LINES.get(cat) or LINES["other"]
        return random.choice(pool)

    def _long_stay_line(self, cat, mins):
        if cat == "media":
            return f"都看了 {int(mins)} 分钟了，眼睛不酸吗？也分我一点嘛~"
        if cat == "coding":
            return f"连续写了 {int(mins)} 分钟代码了，起来动动肩膀吧！"
        if cat == "game":
            return f"玩了 {int(mins)} 分钟啦，赢够了吗？"
        return f"你已经忙了 {int(mins)} 分钟了，休息一下嘛~"

    def _say(self, text, force=False):
        now = time.time()
        if not text:
            return
        if not force and (now - self._last_comment) < self.min_gap:
            return
        self._last_comment = now
        print(f"[桌宠] 观察反馈：{text}")
        self.comment.emit(text)

    def _context_text(self, snap, mins):
        if snap.get("idle", 0) > 600:
            return "用户暂时离开了电脑（键鼠空闲超过 10 分钟）。"
        if snap.get("private"):
            # 隐私窗口：只告诉模型"别打听"，不给任何标题线索
            return "用户正在处理隐私相关的窗口，不要读取也不要猜测其内容。"
        label = CATEGORY_LABELS.get(snap.get("category", "unknown"), "用电脑")
        title = (snap.get("title") or "").strip()
        if len(title) > 40:
            title = title[:40] + "…"
        parts = [f"用户正在{label}"]
        if title:
            parts.append(f"当前窗口标题：{title}")
        if mins >= 3:
            parts.append(f"已经持续约 {int(mins)} 分钟")
        return "；".join(parts) + "。"

    # ---------------- 视觉 ----------------
    def look_now(self, manual=False):
        """立刻做一次视觉点评（manual=True 表示用户主动点的）。"""
        if self._worker is not None and self._worker.isRunning():
            return
        if not self.vision_on and not manual:
            return

        snap = self._sample()
        if snap.get("private"):
            if manual:
                self.comment.emit("这个窗口我就不看啦，隐私要紧 (｡･ω･｡)")
            return
        if snap.get("self") and manual:
            return

        b64, w, h = activity.grab_screen_b64(max_width=self.max_width)
        if not b64:
            if manual:
                self.error.emit("截屏失败了，可能被系统拦住了")
            return
        print(f"[桌宠] 视觉点评：截屏 {w}x{h}（{len(b64)//1024}KB），交给模型…")

        if manual:
            self.comment.emit("让我看看你在干嘛……")
        self._last_vision = time.time()
        self.busy_changed.emit(True)

        self._worker = _VisionWorker(self.client, b64, VISION_PROMPT,
                                     system_prompt=None, max_tokens=200)
        self._worker.done.connect(self._on_vision_done)
        self._worker.failed.connect(self._on_vision_failed)
        self._worker.start()

    def _on_vision_done(self, text):
        self.busy_changed.emit(False)
        self._error_reported = False
        if text:
            self._say(text, force=True)
        else:
            # 模型没给出内容（例如思考占满预算），退回轻量层的台词，别让桌宠哑掉
            self._say(self._category_line(self._category), force=True)

    def _on_vision_failed(self, err):
        self.busy_changed.emit(False)
        print(f"[桌宠] 视觉点评失败：{err}")
        # 只在第一次失败时报一次，避免刷屏；之后自动退回轻量层
        if not self._error_reported:
            self._error_reported = True
            self.vision_on = False
            self.error.emit("这个模型好像看不了图，我先只用窗口标题陪你啦（详情看控制台）")
