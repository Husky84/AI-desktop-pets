# -*- coding: utf-8 -*-
"""屏幕活动识别：前台窗口 / 空闲时间 / 截图 / 隐私过滤。

只做"采集"，不做"判断"——判断反应放在 watcher.py。
隐私相关：
  - 默认只在本地处理，截图只会发给你自己配置的本地模型
  - blacklist 命中的窗口（密码管理器、网银等）直接跳过截图
  - 桌宠自己的窗口会被忽略，避免自问自答

跨平台：Windows 用 Win32 API；其他平台降级为"只知道空闲时间"。
"""
import base64
import ctypes
import io
import os
import sys
import time

# ---------- 应用分类 ----------
# 进程名（小写） -> 类别
APP_CATEGORIES = {
    "coding": {
        "code.exe", "code - insiders.exe", "cursor.exe", "windsurf.exe",
        "pycharm64.exe", "idea64.exe", "goland64.exe", "webstorm64.exe",
        "devenv.exe", "sublime_text.exe", "notepad++.exe", "vim.exe", "nvim.exe",
        "windowsterminal.exe", "wt.exe", "powershell.exe", "pwsh.exe", "cmd.exe",
        "conhost.exe", "mintty.exe", "git-bash.exe", "bash.exe", "wsl.exe",
        "python.exe", "pythonw.exe", "node.exe", "java.exe", "docker desktop.exe",
        "postman.exe", "insomnia.exe", "dbeaver.exe", "navicat.exe",
        "android studio64.exe", "rider64.exe", "clion64.exe",
        "deepseek harness.exe", "trae.exe", "llm.exe",
    },
    "browsing": {
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
        "vivaldi.exe", "360se.exe", "360chrome.exe", "qqbrowser.exe", "sogouexplorer.exe",
    },
    "media": {
        "potplayermini64.exe", "potplayer.exe", "vlc.exe", "mpc-hc64.exe",
        "mpv.exe", "bilibili.exe", "哔哩哔哩.exe", "iqiyi.exe", "youku.exe",
        "music.exe", "cloudmusic.exe", "qqmusic.exe", "spotify.exe", "foobar2000.exe",
    },
    "game": {
        "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "genshinimpact.exe",
        "yuanshen.exe", "leagueclient.exe", "league of legends.exe", "dota2.exe",
        "cs2.exe", "minecraft.exe", "javaw.exe", "battle.net.exe",
    },
    "office": {
        "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe", "onenote.exe",
        "wps.exe", "et.exe", "wpp.exe", "acrobat.exe", "acrord32.exe",
        "sumatrapdf.exe", "foxitreader.exe", "typora.exe", "obsidian.exe",
        "notion.exe", "onenote.exe",
    },
    "chat": {
        "wechat.exe", "weixin.exe", "qq.exe", "tim.exe", "telegram.exe",
        "discord.exe", "dingtalk.exe", "wxwork.exe", "feishu.exe", "lark.exe",
        "slack.exe", "zoom.exe", "teams.exe", "ms-teams.exe",
    },
    "design": {
        "photoshop.exe", "illustrator.exe", "blender.exe", "figma.exe",
        "xd.exe", "afterfx.exe", "premiere pro.exe", "krita.exe", "clipstudiopaint.exe",
        "sai2.exe", "coreldrw.exe",
    },
    "explorer": {"explorer.exe", "totalcmd64.exe", "everything.exe", "listary.exe"},
}

# 窗口标题里出现这些词，也帮忙判断内容
TITLE_HINTS = [
    ("bilibili", "media"), ("youtube", "media"), ("netflix", "media"),
    ("爱奇艺", "media"), ("腾讯视频", "media"), ("优酷", "media"),
    ("github", "coding"), ("stack overflow", "coding"), ("gitlab", "coding"),
    ("jupyter", "coding"), ("localhost", "coding"),
    ("steam", "game"), ("游戏", "game"),
    ("pdf", "office"), ("word", "office"), ("excel", "office"), ("ppt", "office"),
]

# 命中就跳过截图（避免把密码、支付信息送去分析）
PRIVATE_KEYWORDS = [
    "password", "passwd", "bitwarden", "1password", "keepass", "lastpass",
    "密码", "银行", "网银", "支付宝", "微信支付", "paypal", "支付",
    "身份", "身份证", "credential", "secret", "token", "私钥", "助记词",
    "seed phrase", "recovery code", "两步验证", "authenticator",
]

# 桌宠自己的窗口标题（避免自问自答）
SELF_TITLES = ("AI 桌宠", "小团子", "ai-deskpet")


def _is_windows():
    return sys.platform == "win32"


# ======================= Windows 采集 =======================
if _is_windows():
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]

    def _window_title(hwnd):
        n = _user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _window_pid(hwnd):
        pid = ctypes.c_ulong()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _process_name(pid):
        if not pid:
            return ""
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            _kernel32.CloseHandle(handle)
        return ""

    def idle_seconds():
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not _user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        # GetTickCount 是 32 位会回绕，用 GetTickCount64 做高位补偿
        tick = _kernel32.GetTickCount64() & 0xFFFFFFFF
        return max(0.0, (tick - info.dwTime) / 1000.0)
else:
    def idle_seconds():
        return 0.0


def categorize(app, title):
    """把进程名 / 窗口标题归到一个类别。"""
    app_l = (app or "").lower()
    title_l = (title or "").lower()
    for cat, names in APP_CATEGORIES.items():
        if app_l in names:
            return cat
    for token, cat in TITLE_HINTS:
        if token in title_l:
            return cat
    if app_l:
        return "other"
    return "unknown"


def is_private(title, app=""):
    """命中隐私关键词则不该截图。"""
    text = f"{title or ''} {app or ''}".lower()
    return any(k in text for k in PRIVATE_KEYWORDS)


def is_self(title):
    return any(k in (title or "") for k in SELF_TITLES)


def snapshot():
    """采集一次当前活动状态。

    返回 dict：
      app       进程名（如 Code.exe）
      title     窗口标题
      category  归类（coding / browsing / media / game / office / chat / design / explorer / other）
      idle      键鼠空闲秒数
      private   是否属于不该截图的窗口
      self      是否是桌宠自己的窗口
    """
    info = {
        "app": "", "title": "", "category": "unknown",
        "idle": idle_seconds(), "private": False, "self": False, "ts": time.time(),
    }
    if _is_windows():
        try:
            hwnd = _user32.GetForegroundWindow()
            if hwnd:
                title = _window_title(hwnd)
                app = _process_name(_window_pid(hwnd))
                info["title"] = title
                info["app"] = app
                info["self"] = is_self(title)
                info["private"] = is_private(title, app)
        except Exception:  # noqa: BLE001
            pass
    info["category"] = categorize(info["app"], info["title"])
    return info


# ======================= 截图 =======================
def grab_screen_b64(max_width=1024, quality=72):
    """截取主屏并转成 base64 JPEG（给视觉模型用）。

    必须在有 QApplication 的进程里调用（用的是 Qt 的抓屏）。
    返回 (base64字符串, 宽, 高)，失败返回 (None, 0, 0)。
    """
    try:
        from PySide6.QtCore import QBuffer, QByteArray, Qt
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None, 0, 0
        shot = screen.grabWindow(0)
        if shot.isNull():
            return None, 0, 0
        if shot.width() > max_width:
            shot = shot.scaledToWidth(max_width, Qt.SmoothTransformation)

        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QBuffer.WriteOnly)
        shot.save(buf, "JPEG", quality)
        buf.close()
        return base64.b64encode(bytes(data)).decode("ascii"), shot.width(), shot.height()
    except Exception:  # noqa: BLE001
        return None, 0, 0


def describe_for_log(info):
    app = info.get("app") or "?"
    title = (info.get("title") or "")[:60]
    return f"{app} | {title} | {info.get('category')} | 空闲{info.get('idle', 0):.0f}s"


if __name__ == "__main__":   # 手动自测：python activity.py
    for _ in range(3):
        s = snapshot()
        print(describe_for_log(s), "| private:", s["private"], "| self:", s["self"])
        time.sleep(1)
