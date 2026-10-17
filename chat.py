# -*- coding: utf-8 -*-
"""聊天窗口：无边框小面板，点击宠物打开。

- 消息气泡左右分栏（用户右、小团子左）
- AI 回复流式逐字显示（在后台线程请求模型，避免卡界面）
- 顶部可一键检测本地模型服务
"""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


class _Worker(QThread):
    """在后台线程里请求模型，通过信号把结果送回界面线程。"""
    chunk = Signal(str)
    done = Signal(str)
    error = Signal(str)

    def __init__(self, client, history):
        super().__init__()
        self.client = client
        self.history = list(history)

    def run(self):
        try:
            text = self.client.stream_chat(self.history, lambda t: self.chunk.emit(t))
            self.done.emit(text)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class ChatWindow(QWidget):
    MAX_HISTORY = 10  # 只把最近 N 条发给模型（控制上下文长度）

    def __init__(self, pet, client, name: str, emoji: str = "🐳"):
        super().__init__()
        self.pet = pet
        self.client = client
        self.name = name
        self.emoji = emoji
        self.history = []
        self._busy = False
        self._cur_label = None
        self._worker = None
        self._drag_offset = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedWidth(340)
        self.setFixedHeight(520)
        self.setStyleSheet("background: rgba(255, 252, 245, 240);")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        # 顶栏
        bar = QHBoxLayout()
        title = QLabel(f"{self.emoji} {name}")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #5a4632;")
        bar.addWidget(title)
        bar.addStretch()
        self.test_btn = QPushButton("检测模型")
        self.test_btn.setStyleSheet(self._btn_style())
        self.test_btn.clicked.connect(self._test)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet(self._btn_style())
        close_btn.clicked.connect(self.close)
        bar.addWidget(self.test_btn)
        bar.addWidget(close_btn)
        root.addLayout(bar)

        # 消息区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        self.body = QWidget()
        self.body_v = QVBoxLayout(self.body)
        self.body_v.setSpacing(8)
        self.body_v.setContentsMargins(0, 0, 0, 0)
        self.body_v.addStretch()
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)

        # 输入区
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("说点什么吧…（Enter 发送）")
        self.input.setStyleSheet(
            "background: white; border: 2px solid #e6cfa3; border-radius: 10px;"
            "padding: 8px 10px; font-size: 12px;"
        )
        self.input.returnPressed.connect(self.send)
        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(64)
        self.send_btn.setStyleSheet(
            "background: #ffcf87; color: #4a3620; border: none; border-radius: 10px;"
            "font-weight: bold; padding: 6px;"
        )
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.input)
        row.addWidget(self.send_btn)
        root.addLayout(row)

        # 底部用量/费用小字（本地模型显示 ¥0，云端显示实际花费）
        self.usage_label = QLabel("")
        self.usage_label.setStyleSheet("color: #9a8a76; font-size: 11px; padding: 0 2px;")
        self.usage_label.setWordWrap(True)
        root.addWidget(self.usage_label)

    def update_usage(self, text):
        """由 UsageTracker.changed 驱动（可能来自工作线程，Qt 会排队到界面线程）。"""
        self.usage_label.setText(text or "")

    def show_usage(self, text):
        """在聊天区里展示一份用量明细。"""
        self._add_bubble("assistant", text)
        self.show()
        self.raise_()

    @staticmethod
    def _btn_style():
        return (
            "background: #fff; border: 2px solid #e6cfa3; border-radius: 8px;"
            "color: #5a4632; padding: 3px 8px; font-size: 12px;"
        )

    # ---------- 布局 ----------
    def showEvent(self, e):
        super().showEvent(e)
        self.position_near_pet()

    def position_near_pet(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        x = self.pet.x() + self.pet.width() + 16
        if x + self.width() > screen.right() - 8:
            x = self.pet.x() - self.width() - 16
        x = max(screen.left() + 8, min(x, screen.right() - self.width() - 8))
        y = max(screen.top() + 8, min(self.pet.y() - 40, screen.bottom() - self.height() - 8))
        self.move(x, y)

    # ---------- 消息 ----------
    def _add_bubble(self, role, text):
        label = QLabel(text or " ")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setFixedWidth(298)
        if role == "user":
            label.setStyleSheet(
                "background: #d6ecff; color: #14314f; border-radius: 12px; padding: 8px 12px;"
            )
            layout = QHBoxLayout()
            layout.addStretch()
            layout.addWidget(label)
        else:
            label.setStyleSheet(
                "background: #fff6e3; color: #40301f; border-radius: 12px; padding: 8px 12px;"
            )
            layout = QHBoxLayout()
            layout.addWidget(label)
            layout.addStretch()
        self.body_v.addLayout(layout)
        self._scroll_to_bottom()
        return label

    def _scroll_to_bottom(self):
        self.scroll.verticalScrollBar().setValue(self.scroll.maximumHeight())

    def show_note(self, ok: bool, detail: str):
        prefix = "✅ " if ok else "❌ "
        self._add_bubble("assistant", prefix + detail)

    def _test(self):
        ok, detail = self.client.ping()
        self.show_note(ok, detail)

    # ---------- 发送 ----------
    def send(self):
        text = self.input.text().strip()
        if not text or self._busy:
            return
        self.input.clear()
        self.pet._touch()
        self.pet.show_thinking()
        self._add_bubble("user", text)
        self.history.append({"role": "user", "content": text})

        self._busy = True
        self._cur_label = None
        self.send_btn.setEnabled(False)
        self._worker = _Worker(self.client, self.history[-self.MAX_HISTORY:])
        self._worker.chunk.connect(self._on_chunk)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_chunk(self, t):
        if self._cur_label is None:
            self._cur_label = self._add_bubble("assistant", "")
        self._cur_label.setText(self._cur_label.text() + t)
        self._scroll_to_bottom()

    def _on_done(self, text):
        reply = text.strip()
        if reply and self._cur_label is not None:
            self._cur_label.setText(reply)
        self.history.append({"role": "assistant", "content": reply})
        if len(self.history) > self.MAX_HISTORY * 2:
            self.history = self.history[-self.MAX_HISTORY:]
        self._finish(reply)

    def _on_error(self, err):
        if self._cur_label is None:
            self._add_bubble("assistant", "")
        self._cur_label.setText(
            "😿 模型请求失败了：" + str(err)
            + "\n\n可以检查："
            + "\n1) 本地服务是否启动（Ollama / LM Studio）"
            + "\n2) config.json 里 model 名字对不对"
            + "\n3) 用云端 API 的话，api_key / api_key_env 环境变量配了没"
            + "\n（右键桌宠 → 🤖 模型来源，可以切换本地 / 云端）"
        )
        self._finish("")

    def _finish(self, reply):
        self._busy = False
        self._cur_label = None
        self.send_btn.setEnabled(True)
        self.pet.finish_thinking()
        if reply:
            self.pet._be_happy(1.5)
            self.pet.bubble(reply[:120], self.pet.bubble_seconds + 4)

    def shutdown(self):
        """程序退出时收尾：等流式请求线程结束，避免 QThread 被销毁时还在跑。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(3000)

    # ---------- 拖动 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, e):
        self._drag_offset = None
