# -*- coding: utf-8 -*-
"""AI 桌宠入口。

运行：
    python main.py                 # 直接运行
    python main.py --config 路径   # 指定配置文件

启动后：
    - 桌面上会出现一只桌宠（置顶、可拖动）
    - 单击：打开聊天窗口 / 双击：打招呼 / 右键：菜单
"""
import json
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ai_client import LocalAIClient
from chat import ChatWindow
from pet import PetWindow
from usage import UsageTracker
from watcher import ScreenWatcher

DEFAULT_CFG = {
    "ai": {
        "api_format": "ollama",
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b",
        "api_key": "",
        "fallbacks": [],
        "system_prompt": "你是小团子，一只住在用户电脑桌面上的 DeepSeek 鲸鱼娘桌宠，说话简短可爱。",
        "temperature": 0.8,
        "max_tokens": 400,
        "extra_body": {},
    },
    "pet": {
        "name": "小团子",
        "emoji": "🐳",
        "auto_walk": True,
        "bubble_seconds": 9,
        "sleep_after_seconds": 240,
        "theme": "cream",
        "image": "",
        "images": {},
        "frames": 0,      # 0 = 按 宽÷高 自动推算
        "height": 250,
        "fps": {},
        "click_mask": False,   # Windows 无需遮罩（透明像素本就点击穿透）
    },
}

# 配置被自动修复 / 解析失败时的提示，启动后会显示在聊天窗口里
CONFIG_NOTE = None

APP_NAME = "ai-deskpet"
CONFIG_NAME = "config.json"
CONFIG_PATH = None          # 实际使用的配置文件路径


def user_config_dir() -> Path:
    """用户级配置目录：Windows 用 %APPDATA%，其他平台用 ~/.config。"""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def _cli_config_arg(argv):
    """取出 --config 参数（并把它从 argv 里摘掉，免得 Qt 报未知参数）。"""
    rest, path = [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--config" and i + 1 < len(argv):
            path = argv[i + 1]
            i += 2
            continue
        if a.startswith("--config="):
            path = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    return rest, path


def find_config(explicit=None) -> Path:
    """按优先级定位配置文件：

    --config 参数 > 环境变量 AI_DESKPET_CONFIG > 当前目录 > 脚本目录 > 用户配置目录

    都没找到时返回一个"该新建"的路径：脚本目录可写就用脚本目录
    （git clone 场景，配置就在项目里），否则用用户配置目录（pip 安装场景）。
    """
    if explicit:
        return Path(explicit)
    env = os.environ.get("AI_DESKPET_CONFIG")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for cand in (Path.cwd() / CONFIG_NAME, here / CONFIG_NAME,
                 user_config_dir() / CONFIG_NAME):
        if cand.exists():
            return cand
    # 都没找到：pip 安装（site-packages）就用用户配置目录，
    # 否则（git clone / 解压运行）配置就放在项目目录里，方便就地修改
    if any(p in str(here).lower() for p in ("site-packages", "dist-packages")):
        return user_config_dir() / CONFIG_NAME
    probe = here / CONFIG_NAME
    try:                              # 试着建一下，判断脚本目录是否可写
        probe.touch(exist_ok=True)
        return probe
    except OSError:
        return user_config_dir() / CONFIG_NAME


def _default_config_text() -> str:
    """默认配置文本：优先用随包的 config.example.json，其次用内置默认值。"""
    example = Path(__file__).resolve().parent / "config.example.json"
    if example.exists():
        try:
            return example.read_text(encoding="utf-8")
        except OSError:
            pass
    return json.dumps(DEFAULT_CFG, ensure_ascii=False, indent=2) + "\n"


def load_config(explicit=None) -> dict:
    """读取 config.json；文件不存在就自动生成一份，方便用户照着改。

    容错：Windows 路径里的单反斜杠（如 "E:\\桌宠\\a.png"）不是合法 JSON 转义，
    严格解析失败时会自动按路径修复一遍，并把提示显示在聊天窗口里，
    避免 pythonw 无控制台时"配置被静默忽略"。
    """
    global CONFIG_NOTE, CONFIG_PATH
    p = find_config(explicit)
    CONFIG_PATH = p
    cfg = None
    if p.exists() and p.stat().st_size > 0:
        text = p.read_text(encoding="utf-8")
        try:
            cfg = json.loads(text)
        except Exception:  # noqa: BLE001
            try:
                cfg = json.loads(text.replace("\\", "/"))
                CONFIG_NOTE = ("config.json 里有非法转义（Windows 路径请用正斜杠，"
                               "例如 assets/x.png），已自动修复。")
            except Exception as e:  # noqa: BLE001
                CONFIG_NOTE = f"config.json 解析失败，已改用默认设置：{e}"
            print("[桌宠]", CONFIG_NOTE)
    else:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_default_config_text(), encoding="utf-8")
            CONFIG_NOTE = f"已生成默认配置：{p}（按需修改后重启桌宠生效）"
            print("[桌宠]", CONFIG_NOTE)
        except OSError as e:
            print("[桌宠] 无法写入配置文件：", e)
    if not isinstance(cfg, dict):
        cfg = json.loads(json.dumps(DEFAULT_CFG))
    # 与默认值合并，防止配置缺字段
    for key, val in DEFAULT_CFG.items():
        cfg.setdefault(key, {})
        for k, v in val.items():
            cfg[key].setdefault(k, v)
    return cfg


class _Notifier(QObject):
    """后台线程 → 界面线程 的信号桥。"""
    ping_done = Signal(bool, str)
    greet_ok = Signal(str)


def main():
    argv, config_arg = _cli_config_arg(sys.argv[1:])
    app = QApplication([sys.argv[0]] + argv)
    app.setApplicationName("AI 桌宠")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei", 10))

    cfg = load_config(config_arg)
    pet = PetWindow(cfg)
    client = LocalAIClient(cfg["ai"])
    pet.set_client(client)

    # ---- 用量 / 费用统计（云端 API 按官方价计费，本地模型记 0）----
    usage_path = (Path(CONFIG_PATH).parent / "usage.json") if CONFIG_PATH else None
    tracker = UsageTracker(usage_path)
    client.on_usage = tracker.record
    pet.set_tracker(tracker)

    chat = ChatWindow(pet, client, cfg["pet"].get("name", "小团子"),
                      cfg["pet"].get("emoji", "🐳"))
    pet.set_chat_window(chat)
    tracker.changed.connect(chat.update_usage)
    pet.usage_requested.connect(lambda: chat.show_usage(tracker.summary_text()))
    chat.update_usage(tracker.chat_line())

    pet.show()

    # 后台检测本地模型服务，结果写进聊天窗口
    notifier = _Notifier()
    notifier.ping_done.connect(chat.show_note)

    if CONFIG_NOTE:                      # 配置有问题时闪一下聊天窗口告诉用户
        chat.show_note(False, CONFIG_NOTE)
        chat.show()
        QTimer.singleShot(6000, chat.hide)

    def _check():
        ok, detail = client.ping()
        notifier.ping_done.emit(ok, detail)

    threading.Thread(target=_check, daemon=True).start()

    # 启动问候：后台线程问模型，回来后再冒泡（不卡界面）
    def _do_ai_greet():
        try:
            reply = client.stream_chat(
                [{"role": "user", "content": "（打招呼：向用户打个简短、可爱的招呼）"}],
                lambda _t: None,
            )
        except Exception:
            return
        notifier.greet_ok.emit(reply)

    pet.ai_greet_requested.connect(
        lambda: threading.Thread(target=_do_ai_greet, daemon=True).start()
    )
    notifier.greet_ok.connect(pet.apply_greet_reply)

    # ---- 屏幕观察：让桌宠知道你正在干什么 ----
    watcher = ScreenWatcher(cfg, client)
    pet.set_watcher(watcher)
    watcher.comment.connect(pet.react)                   # 主动冒泡反馈
    watcher.context_changed.connect(client.set_context)  # 聊天时它"知道"你在干嘛
    watcher.busy_changed.connect(pet.set_busy)           # 分析中切思考动作
    watcher.error.connect(pet.react)
    watcher.start()
    app.aboutToQuit.connect(watcher.shutdown)   # 退出时等后台线程收尾
    app.aboutToQuit.connect(chat.shutdown)

    # ---- 模型来源切换：本地模型 <-> 云端 API ----
    def _on_profile_changed(name):
        pet.react(f"好，接下来用「{name}」陪你 (^_^)")
        try:                                     # 记住选择，下次启动还用这个
            if CONFIG_PATH and Path(CONFIG_PATH).exists():
                data = json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8"))
                data.setdefault("ai", {})["active"] = name
                Path(CONFIG_PATH).write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                print(f"[桌宠] 已把默认模型来源写回 {CONFIG_PATH}")
        except Exception as e:  # noqa: BLE001
            print("[桌宠] 保存模型来源失败：", e)

    pet.profile_changed.connect(_on_profile_changed)

    # 注意：greet() 会 emit ai_greet_requested，必须放在上面 connect 之后调用，
    # 否则启动时的 AI 问候没人接收（这个顺序踩过一次坑）。
    pet.greet()

    QTimer.singleShot(4000, chat.position_near_pet)  # 宠物若走动，聊天窗跟随一次

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
