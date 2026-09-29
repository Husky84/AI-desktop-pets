# -*- coding: utf-8 -*-
"""宠物窗口：透明、无边框、置顶的小猫。

- 程序化绘制（无需图片素材），支持 idle / walk / happy / thinking / sleep 五种状态
- 头顶气泡显示 AI 的简短回复
- 左键单击：打开聊天窗口；双击：打招呼；右键：菜单
"""
import math
import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QRectF, QTimer, QPointF, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QImage, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QBitmap, QRegion,
)
from PySide6.QtWidgets import QMenu, QWidget

# ---------- 配色 ----------
BODY = QColor(255, 243, 214)          # 身体（奶黄色）
BODY_EDGE = QColor(222, 176, 112)     # 身体描边
EAR_INNER = QColor(255, 183, 197)     # 内耳（粉）
BLUSH = QColor(255, 150, 170, 110)    # 腮红
INK = QColor(70, 52, 38)              # 五官
BELLY = QColor(255, 250, 235)         # 肚皮
BUBBLE_BG = QColor(255, 255, 255, 238)
BUBBLE_EDGE = QColor(208, 172, 128)

# ---------- 代码绘制小猫的配色方案（config 里 pet.theme 可选） ----------
PALETTES = {
    "cream": {"body_top": "#FFFAE4", "body": "#FFE9B8", "belly": "#FFF6DC",
              "ear_in": "#FFC9A3", "blush": QColor(255, 150, 170, 110),
              "edge": "#DEB070", "whisker": "#E5C58F"},
    "mint":  {"body_top": "#F0FFF4", "body": "#BDE8C9", "belly": "#E8FBEF",
              "ear_in": "#F9B8C6", "blush": QColor(255, 140, 160, 100),
              "edge": "#7FB98F", "whisker": "#8FCBA2"},
    "pink":  {"body_top": "#FFF0F5", "body": "#FBC9D8", "belly": "#FFEBF1",
              "ear_in": "#F49BB5", "blush": QColor(255, 120, 150, 110),
              "edge": "#D98BA3", "whisker": "#E3A5BC"},
    "blue":  {"body_top": "#F0F7FF", "body": "#B8D4F5", "belly": "#E7F1FF",
              "ear_in": "#F9B8C6", "blush": QColor(255, 150, 170, 100),
              "edge": "#7FA6D9", "whisker": "#8FB5E5"},
}


# ---------- 序列帧素材 ----------
# 各状态的默认播放帧率，可用 config 里的 pet.fps 覆盖
DEFAULT_FPS = {"idle": 4.0, "walk": 8.0, "happy": 6.0, "thinking": 4.0, "sleep": 2.0}
# 状态 → 优先使用的素材名（找不到就依次回退）
MOOD_ALIAS = {
    "idle": ("idle",),
    "walk": ("walk", "idle"),
    "happy": ("happy", "wave", "idle"),      # 开心 = 挥手
    "thinking": ("thinking", "idle"),
    "sleep": ("sleep", "idle"),
}


def _frame_boxes(img, frames):
    """把整条横向序列图切成 frames 帧，返回每帧不透明内容的包围盒。
    返回的坐标已经是整条带图（strip）坐标系，可直接用于 img.copy()。"""
    fw = img.width() // frames
    h = img.height()
    boxes = []
    for i in range(frames):
        frame = img.copy(i * fw, 0, fw, h)
        mask = QBitmap.fromImage(frame.createAlphaMask())   # 1bpp：不透明处为 1
        rect = QRegion(mask).boundingRect()
        if rect.isEmpty():
            rect = QRect(0, 0, fw, h)
        boxes.append(rect.translated(i * fw, 0))            # 转成整图坐标
    return fw, boxes


def load_sprites(pet_cfg, dpr=1.0):
    """读取 pet.image（单条序列图）或 pet.images（每个动作一条），
    返回 {动作名: [QPixmap, ...]}；没配置图片时返回 None。

    处理要点（针对 AI 生图常见的"播放时抖动"）：
      1. 每帧单独裁掉透明留白
      2. 按内容水平居中、底边对齐到地面
      3. 所有动作共用同一个缩放比例，切换状态时大小不跳
      4. dpr：按屏幕缩放比例生成素材，避免被系统二次放大而发糊
    """
    frames_cfg = int(pet_cfg.get("frames", 0) or 0)
    target_h = float(pet_cfg.get("height", 250) or 250)
    dpr = float(dpr) or 1.0

    wanted = {}
    single = str(pet_cfg.get("image", "") or "").strip()
    if single:
        wanted["idle"] = single                     # 单图模式：所有状态共用这一条
    for key, val in (pet_cfg.get("images") or {}).items():
        if str(val or "").strip():
            wanted[str(key)] = str(val).strip()
    if not wanted:
        return None

    loaded, max_h = {}, 0
    for key, rel in wanted.items():
        fp = Path(str(rel).replace("\\", "/").strip())   # 兼容手写反斜杠路径
        if not fp.is_absolute():
            fp = Path(__file__).parent / fp
        if not fp.exists():
            print(f"[桌宠] 找不到素材：{fp}")
            continue
        img = QImage(str(fp)).convertToFormat(QImage.Format_ARGB32)
        if img.isNull():
            print(f"[桌宠] 素材读取失败：{fp}")
            continue
        frames = frames_cfg or max(1, round(img.width() / img.height()))
        _, boxes = _frame_boxes(img, frames)
        loaded[key] = (img, boxes)
        max_h = max([max_h] + [b.height() for b in boxes])
    if not loaded:
        return None

    # 直接按"设备像素"缩放：目标设备高度 = 逻辑高度 × 屏幕缩放
    scale = (target_h * dpr) / max_h if max_h else 1.0
    sprites = {}
    for key, (img, boxes) in loaded.items():
        seq = []
        for b in boxes:
            sub = img.copy(b)
            w = max(1, int(round(b.width() * scale)))
            h = max(1, int(round(b.height() * scale)))
            pm = QPixmap.fromImage(
                sub.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            )
            pm.setDevicePixelRatio(dpr)   # 逻辑尺寸 = height，设备分辨率 = 原始像素
            seq.append(pm)
        sprites[key] = seq
        print(f"[桌宠] 素材 {key}: {len(seq)} 帧, 设备 {seq[0].width()}x{seq[0].height()} "
              f"(逻辑 {seq[0].width() / dpr:.0f}x{seq[0].height() / dpr:.0f}, dpr={dpr})")
    return sprites


class PetWindow(QWidget):
    W = 340
    H = 560      # 放大宠物后留出气泡空间
    TICK_MS = 66  # 约 15fps

    # 信号：请求 AI 问候 / 收到 AI 问候（后台线程不阻塞界面）
    ai_greet_requested = Signal()
    ai_greet_reply = Signal(str)

    def __init__(self, cfg: dict):
        super().__init__()
        pet_cfg = cfg.get("pet", {})
        self.name = pet_cfg.get("name", "小团子")
        self.auto_walk = bool(pet_cfg.get("auto_walk", True))
        self.bubble_seconds = int(pet_cfg.get("bubble_seconds", 9))
        self.sleep_after = int(pet_cfg.get("sleep_after_seconds", 240))

        # 形象：theme = 代码小猫的配色；image / images = 自定义序列帧素材
        self.theme = pet_cfg.get("theme", "cream")
        self._pet_cfg = pet_cfg
        self._dpr = self._screen_dpr()
        self._sprites = load_sprites(pet_cfg, self._dpr)   # None = 用代码画的小猫
        # 窗口形状遮罩：Windows 的透明窗口本身就按 alpha 做点击穿透，不需要；
        # 其他平台默认开启，可用 config 的 pet.click_mask 强制开关。
        self._click_mask = bool(pet_cfg.get("click_mask", sys.platform != "win32"))
        self._fps = dict(DEFAULT_FPS)
        for k, v in (pet_cfg.get("fps") or {}).items():
            try:
                self._fps[str(k)] = float(v)
            except (TypeError, ValueError):
                pass
        self._sleep_start = None

        self.chat_win = None
        self.client = None
        self.history = []          # 最近的对话 [{"role": ..., "content": ...}]

        # 状态机
        self.mood = "idle"
        self.t = 0.0
        now = time.time()
        self.blink_until = 0.0
        self.sleep_until = now + self.sleep_after
        self.walk_until = now + random.uniform(6, 15)
        self.happy_until = 0.0
        self.dir = 1.0
        self.speed = 70.0

        # 交互
        self._press_pos = None
        self._dragged = False
        self.speech = ""
        self._sprite = QPixmap(self.W, self.H)
        self._sprite.fill(Qt.transparent)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # 不抢焦点
        self.setFixedSize(self.W, self.H)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.width() // 2 - self.W // 2, screen.height() - self.H)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(self.TICK_MS)
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self._clear_bubble)
        self._click_timer = QTimer(self)  # 延迟单击，用来区分单击/双击
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self.open_chat)

    # ================= 高 DPI =================
    def _screen_dpr(self) -> float:
        """当前屏幕的缩放比例（125% 缩放 = 1.25）。"""
        scr = self.screen() or QGuiApplication.primaryScreen()
        return float(scr.devicePixelRatio()) if scr else 1.0

    def showEvent(self, e):
        super().showEvent(e)
        # 窗口挪到不同缩放比例的显示器后，重新按新比例生成素材
        dpr = self._screen_dpr()
        if abs(dpr - self._dpr) > 1e-6:
            self._dpr = dpr
            sprites = load_sprites(self._pet_cfg, dpr)
            if sprites:
                self._sprites = sprites
            self._render()

    # ================= 状态 =================
    def _touch(self):
        """任何用户接触都会让它保持清醒。"""
        self.sleep_until = time.time() + self.sleep_after
        if self.mood == "sleep":
            self.mood = "idle"
            self.bubble("喵~ 我醒啦 (oωo)")

    def set_mood(self, mood):
        self.mood = mood
        self.update()

    def show_thinking(self):
        self.set_mood("thinking")
        self.bubble("……")

    def finish_thinking(self):
        if self.mood == "thinking":
            self.set_mood("idle")

    def bubble(self, text, seconds=None):
        self.speech = text or ""
        if self.speech:
            self.bubble_timer.start(int((seconds or self.bubble_seconds) * 1000))
        else:
            self.bubble_timer.stop()
        self.update()

    def _clear_bubble(self):
        self.speech = ""
        self.update()

    def _tick(self):
        self.t += self.TICK_MS / 1000
        now = time.time()

        # 眨眼
        if now > self.blink_until and random.random() < 0.02:
            self.blink_until = now + random.uniform(0.1, 0.2)

        # 犯困 → 睡觉
        if self.mood not in ("thinking",) and now > self.sleep_until:
            self.mood = "sleep"
        elif self.mood == "sleep" and now < self.sleep_until:
            self.mood = "idle"

        # 闲逛
        if self.mood == "idle":
            if now > self.walk_until and self.auto_walk and random.random() < 0.08:
                self.mood = "walk"
                self.dir = random.choice((-1.0, 1.0))
                self.walk_until = now + random.uniform(2.5, 8)
            else:
                self.walk_until = now + random.uniform(5, 15)
        elif self.mood == "walk":
            self._walk_step()
            if now > self.walk_until:
                self.mood = "idle"
                self.walk_until = now + random.uniform(6, 18)
        elif self.mood == "happy":
            if now > self.happy_until:
                self.mood = "idle"

        self._render()

    def _walk_step(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = self.x() + self.speed * self.dir * self.TICK_MS / 1000
        if x < screen.left() + 10:
            x = screen.left() + 10
            self.dir = 1.0
        elif x + self.W > screen.right() - 10:
            x = screen.right() - 10 - self.W
            self.dir = -1.0
        self.move(int(x), self.y())

    def _be_happy(self, seconds=1.2):
        if self.mood != "sleep":
            self.set_mood("happy")
        self.happy_until = time.time() + seconds

    # ================= 对外接口 =================
    def set_chat_window(self, chat_win):
        self.chat_win = chat_win

    def set_client(self, client):
        self.client = client

    def greet(self):
        """启动时的问候。"""
        self._be_happy(2.5)
        hour = time.localtime().tm_hour
        if hour < 5:
            text = "你怎么还没睡呀……(z_z)"
        elif hour < 10:
            text = "早上好！今天也要元气满满哦 (^_^)"
        elif hour < 18:
            text = "下午好~ 我来陪你啦 (oωo)"
        else:
            text = "晚上好！今天过得怎么样？"
        self.bubble(text, 10)
        if self.client is not None:
            self.ai_greet_requested.emit()  # main.py 会起后台线程去问模型

    def apply_greet_reply(self, reply):
        """AI 问候回来（界面线程执行）。"""
        reply = reply.strip()
        if not reply:
            return
        self.history.append({"role": "user", "content": "（打招呼）"})
        self.history.append({"role": "assistant", "content": reply})
        self.bubble(reply[:120], 12)
        self._be_happy(1.5)

    def open_chat(self):
        self._touch()
        if self.chat_win is None:
            return
        self.chat_win.show()
        self.chat_win.raise_()
        self._be_happy(1.0)

    def sleep_now(self):
        self.set_mood("sleep")
        self.sleep_until = time.time() + max(self.sleep_after, 180)
        self.bubble("zzZ……")

    def toggle_walk(self):
        self.auto_walk = not self.auto_walk
        if not self.auto_walk and self.mood == "walk":
            self.set_mood("idle")
        self.bubble("走动：" + ("开" if self.auto_walk else "关"))

    # ================= 交互 =================
    def mousePressEvent(self, e):
        self._touch()
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._dragged = False

    def mouseMoveEvent(self, e):
        if self._press_pos is not None and e.buttons() & Qt.LeftButton:
            cur = e.globalPosition().toPoint()
            if abs(cur.x() - self._press_pos.x()) > 4 or abs(cur.y() - self._press_pos.y()) > 4:
                self._dragged = True
            if self._dragged:
                self.move(self.frameGeometry().topLeft() + (cur - self._press_pos))
                self._press_pos = cur

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._press_pos is not None and not self._dragged:
            # 延迟 260ms 再执行：如果其实是双击，会在双击事件里取消
            self._click_timer.start(260)
        self._press_pos = None
        self._dragged = False

    def mouseDoubleClickEvent(self, e):
        self._click_timer.stop()
        self._touch()
        self._be_happy(2.0)
        self.bubble("喵呜~ 好痒 (^_^)")

    def contextMenuEvent(self, e):
        self._touch()
        menu = QMenu(self)
        menu.addAction("💬 打开聊天", self.open_chat)
        menu.addAction("👋 打个招呼", self.greet)
        if self.mood == "sleep":
            menu.addAction("⏰ 叫醒", lambda: self._touch())
        else:
            menu.addAction("💤 睡一会儿", self.sleep_now)
        menu.addAction("🚶 走动 开/关", self.toggle_walk)
        if not self._sprites:
            theme_menu = menu.addMenu("🎨 配色（代码小猫）")
            for key, label in (("cream", "🍦 奶油"), ("mint", "🌿 薄荷"),
                               ("pink", "🌸 樱粉"), ("blue", "💧 海蓝")):
                act = theme_menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(key == self.theme)
                act.triggered.connect(lambda _=False, k=key: self._set_theme(k))
        menu.addSeparator()
        menu.addAction("👋 退出", lambda: QGuiApplication.instance().quit())
        menu.exec(e.globalPos())

    def _set_theme(self, key):
        if key in PALETTES and key != self.theme:
            self.theme = key
            self.bubble("换个颜色~ 好看吗? (oωo)")

    # ================= 绘制 =================
    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._sprite)
        p.end()

    def _render(self):
        """把当前状态画到透明 sprite，并把它同时用作鼠标遮罩
        （透明区域不响应点击，不会挡住桌面上的其他操作）。

        高 DPI 关键点：按"设备像素"建画布（逻辑尺寸 × 屏幕缩放），
        再整体 scale，绘制代码仍用逻辑坐标 —— 这样 125%/150% 缩放下不会糊。
        """
        dpr = self._dpr or 1.0
        img = QImage(int(round(self.W * dpr)), int(round(self.H * dpr)),
                     QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.scale(dpr, dpr)   # 之后仍按逻辑坐标 (self.W × self.H) 绘制

        pet_r = 50
        cx = self.W / 2
        base_y = self.H - 30 - pet_r  # 身体中心静止位置

        # 影子
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawEllipse(QRectF(cx - 46, self.H - 26, 92, 14))

        # 上下浮动
        bob = 0.0
        if self.mood in ("idle", "happy"):
            bob = math.sin(self.t * 2.2) * 3
        elif self.mood == "walk":
            bob = -abs(math.sin(self.t * 7)) * 6
        elif self.mood == "sleep":
            bob = math.sin(self.t * 1.2) * 2
        cy = base_y - bob

        # 思考 / 睡觉 / 开心时的小符号
        if self.mood == "thinking":
            p.setPen(QPen(INK, 3, Qt.SolidLine, Qt.RoundCap))
            for i, ph in enumerate((0.0, 0.6, 1.2)):
                a = (self.t * 2.2 + ph) % (math.pi * 2)
                p.drawPoint(QPointF(cx + 66 + 8 * math.cos(a), cy - 58 + 8 * math.sin(a)))
        if self.mood == "sleep":
            p.setPen(QPen(QColor(120, 130, 160), 2.5, Qt.SolidLine, Qt.RoundCap))
            p.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
            for dx, dy, size in ((46, -84, 11), (62, -104, 14), (80, -128, 17)):
                p.setFont(QFont("Microsoft YaHei", size, QFont.Bold))
                p.drawText(QPointF(cx + dx, cy + dy + (self.t * 8) % 10 - 10), "Z")

        self._draw_pet(p, cx, cy, pet_r)

        # 气泡（画在宠物上面一层）
        if self.speech:
            self._draw_bubble(p)

        p.end()
        self._sprite = QPixmap.fromImage(img)
        self._sprite.setDevicePixelRatio(dpr)
        if self._click_mask:
            # 必须用 createAlphaMask 取 alpha 轮廓；
            # 直接 QBitmap.fromImage(彩色图) 是按亮度做 1bit 抖动，
            # 会把角色裁成约 50% 的网点空洞（颜色也会一起丢）。
            mask_img = img
            if abs(dpr - 1.0) > 1e-6:
                mask_img = img.scaled(int(round(self.W)), int(round(self.H)),
                                      Qt.IgnoreAspectRatio, Qt.FastTransformation)
            try:
                self.setMask(QBitmap.fromImage(mask_img.createAlphaMask(Qt.ThresholdDither)))
            except Exception:  # noqa: BLE001  个别平台不支持遮罩时退化为整窗可点
                pass
        self.update()

    def _draw_pet(self, p, cx, cy, r):
        if self._sprites:
            self._draw_sprites(p, cx, cy)
        else:
            self._draw_cat(p, cx, cy, r)

    def _pick_seq(self):
        """按当前状态挑一条序列帧（找不到就按 MOOD_ALIAS 回退）。"""
        for key in MOOD_ALIAS.get(self.mood, (self.mood, "idle")):
            seq = self._sprites.get(key)
            if seq:
                return seq
        return None

    def _draw_sprites(self, p, cx, cy):
        """画自定义序列帧：素材已在加载时裁边、居中、统一缩放，
        这里只需按当前状态的帧率取帧，并把底边对齐到地面 (cy + 50)。"""
        seq = self._pick_seq()
        if not seq:
            return
        n = len(seq)
        fps = self._fps.get(self.mood, 4.0)
        if self.mood == "sleep":
            # 犯困→入睡：播完一次后停在最后一帧
            if self._sleep_start is None:
                self._sleep_start = time.time()
            idx = min(int((time.time() - self._sleep_start) * fps), n - 1)
        else:
            self._sleep_start = None
            idx = int(self.t * fps) % n
        pix = seq[idx]
        p.drawPixmap(QPointF(cx - pix.width() / 2.0, cy + 50 - pix.height()), pix)

    def _draw_cat(self, p, cx, cy, r):
        pal = PALETTES.get(self.theme, PALETTES["cream"])
        body = QColor(pal["body"])
        body_top = QColor(pal["body_top"])
        belly = QColor(pal["belly"])
        ear_in = QColor(pal["ear_in"])
        blush = pal["blush"]
        edge = QColor(pal["edge"])
        whisker = QColor(pal["whisker"])
        mood = self.mood
        blinking = time.time() < self.blink_until
        ear_lift = 0 if mood in ("happy", "walk") else 4  # 开心/走路时耳朵更尖

        # ---- 耳朵 ----
        ear_pen = QPen(edge, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(ear_pen)
        for sx in (-1, 1):
            tip = QPointF(cx + sx * r * 0.72, cy - r * 1.42 + ear_lift)
            b1 = QPointF(cx + sx * r * 0.58, cy - r * 0.72)
            b2 = QPointF(cx + sx * r * 0.02, cy - r * 0.92)
            outer = QPolygonF([b1, tip, b2])
            p.setBrush(body)
            p.drawPolygon(outer)
            inner = QPolygonF([
                QPointF(cx + sx * r * 0.55, cy - r * 0.80 + ear_lift * 0.4),
                QPointF(cx + sx * r * 0.70, cy - r * 1.26 + ear_lift),
                QPointF(cx + sx * r * 0.16, cy - r * 0.88),
            ])
            p.setBrush(ear_in)
            p.drawPolygon(inner)

        # ---- 身体 ----
        grad = QLinearGradient(0, cy - r, 0, cy + r)
        grad.setColorAt(0.0, body_top)
        grad.setColorAt(1.0, body)
        p.setPen(QPen(edge, 3, Qt.SolidLine))
        p.setBrush(grad)
        p.drawEllipse(QRectF(cx - r, cy - r * 0.94, r * 2, r * 1.88))

        # ---- 肚皮 ----
        p.setPen(Qt.NoPen)
        p.setBrush(belly)
        p.drawEllipse(QRectF(cx - r * 0.5, cy + r * 0.08, r, r * 0.82))

        # ---- 腮红 ----
        p.setBrush(blush)
        p.drawEllipse(QRectF(cx - r * 0.78, cy + r * 0.06, r * 0.34, r * 0.22))
        p.drawEllipse(QRectF(cx + r * 0.44, cy + r * 0.06, r * 0.34, r * 0.22))

        # ---- 眼睛 ----
        eye_y = cy - r * 0.12
        ex = r * 0.42
        p.setPen(QPen(INK, 3.5, Qt.SolidLine, Qt.RoundCap))
        for sx in (-1, 1):
            e = cx + sx * ex
            if mood == "sleep" or (mood not in ("happy",) and blinking):
                # 闭眼：一条向下的弧线
                path = QPainterPath(QPointF(e - 8, eye_y))
                path.quadTo(QPointF(e, eye_y + 9), QPointF(e + 8, eye_y))
                p.drawPath(path)
            elif mood == "happy":
                # 弯眼 ^ ^
                path = QPainterPath(QPointF(e - 8, eye_y + 3))
                path.quadTo(QPointF(e, eye_y - 7), QPointF(e + 8, eye_y + 3))
                p.drawPath(path)
            else:
                # 思考时视线朝左上
                ox = -2 if mood == "thinking" else 0
                p.setPen(Qt.NoPen)
                p.setBrush(INK)
                p.drawEllipse(QRectF(e - 6 + ox, eye_y - 7, 12, 13))
                p.setBrush(QColor(255, 255, 255))
                p.drawEllipse(QRectF(e - 2.5 + ox, eye_y - 5, 4, 4))
                p.setPen(QPen(INK, 3.5, Qt.SolidLine, Qt.RoundCap))

        # ---- 鼻子和嘴 ----
        p.setPen(Qt.NoPen)
        p.setBrush(INK)
        p.drawEllipse(QRectF(cx - 3.5, cy + r * 0.24, 7, 5.5))
        p.setPen(QPen(INK, 2.5, Qt.SolidLine, Qt.RoundCap))
        if mood == "happy":
            mouth = QPainterPath(QPointF(cx - 12, cy + r * 0.40))
            mouth.quadTo(QPointF(cx, cy + r * 0.52), QPointF(cx + 12, cy + r * 0.40))
            p.drawPath(mouth)
        else:
            p.drawArc(QRectF(cx - 7, cy + r * 0.30, 7, 8), 200 * 16, 140 * 16)
            p.drawArc(QRectF(cx, cy + r * 0.30, 7, 8), 20 * 16, 140 * 16)

        # ---- 胡须 ----
        p.setPen(QPen(whisker, 1.6, Qt.SolidLine, Qt.RoundCap))
        for sx in (-1, 1):
            for dy, length in ((-4, 22), (2, 20), (8, 17)):
                x1 = cx + sx * r * 0.62
                y1 = cy + r * 0.18 + dy
                p.drawLine(QPointF(x1, y1), QPointF(x1 + sx * length, y1 - 2))

        # ---- 小脚 ----
        p.setPen(QPen(edge, 2, Qt.SolidLine))
        p.setBrush(body)
        for sx in (-1, 1):
            p.drawEllipse(QRectF(cx + sx * r * 0.42 - 11, cy + r * 0.80, 22, 14))

    def _draw_bubble(self, p):
        fm = QFontMetrics(QFont("Microsoft YaHei", 11))
        box_w = self.W - 24
        lines = []
        for raw in self.speech.splitlines():
            cur = ""
            for ch in raw or " ":
                if fm.horizontalAdvance(cur + ch) > box_w - 36:
                    lines.append(cur)
                    cur = ch
                else:
                    cur += ch
            lines.append(cur)
        lines = [ln or " " for ln in lines[:8]]
        line_h = fm.height()
        box_h = line_h * len(lines) + 20
        bx = 12
        by = 12
        tip_x = self.W // 2
        tip_y = by + box_h

        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, box_w, box_h), 14, 14)
        path.moveTo(tip_x - 14, tip_y - 1)
        path.lineTo(tip_x, tip_y + 16)
        path.lineTo(tip_x + 14, tip_y - 1)
        path.closeSubpath()

        p.setPen(QPen(BUBBLE_EDGE, 2))
        p.setBrush(BUBBLE_BG)
        p.drawPath(path)

        p.setFont(QFont("Microsoft YaHei", 11))
        p.setPen(QColor(60, 45, 35))
        for i, ln in enumerate(lines):
            p.drawText(QRectF(bx + 14, by + 10 + i * line_h, box_w - 28, line_h),
                       Qt.AlignLeft | Qt.AlignVCenter, ln)
