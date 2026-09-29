# -*- coding: utf-8 -*-
"""桌宠启动助手（被 run.bat / run.sh 调用）。

职责：
  1. 挑一个最合适的 Python：优先「已经装好 PySide6」的那个，
     避免机器上装了多个 Python 时，往一个干净的 Python 里重复下 250MB
  2. 缺依赖时问一句再装
  3. 用 pythonw（Windows）或普通解释器把 main.py 拉起来

为什么中文提示放在 Python 而不是 .bat 里：
  cmd.exe 按系统码页解析批处理文件，UTF-8 中文会把同一行后面的命令一起
  吃掉（表现为一堆 "'mport' is not recognized"）。
为什么 run.bat 里没有 call :label：
  LF-only 换行时 cmd 的标签扫描会错位（git 规范化换行符很容易造成
  LF-only），所以批处理只做最简单的探测，逻辑全放这里。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements.txt"

_VERSION_OK = "import sys\nassert sys.version_info >= (3, 10)\n"
_DEPS_OK = _VERSION_OK + "import PySide6, requests\n"


def _setup_console():
    """让中文在控制台里正常显示：Windows 切到 UTF-8 输出码页；
    实在不行就退化成可替换字符，绝不让编码问题把启动流程搞崩。"""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:  # noqa: BLE001
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


_setup_console()


def say(msg=""):
    print(msg, flush=True)


def hold(msg=""):
    """出错时停一下，免得双击运行时窗口一闪而过看不到原因。"""
    if msg:
        say(msg)
    if sys.stdin and sys.stdin.isatty():
        try:
            input("按回车键退出...")
        except EOFError:
            pass


def _check(cmd, code):
    try:
        return subprocess.run(cmd + ["-c", code],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        return False


def python_candidates():
    """当前解释器 + 机器上其他常见的 Python 位置。"""
    out = [[sys.executable]]

    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            out.append([launcher, "-3"])

    for name in ("python3", "python"):
        p = shutil.which(name)
        if p and "windowsapps" not in p.lower():      # 跳过 Microsoft Store 占位符
            out.append([p])

    exe_name = "python.exe" if os.name == "nt" else "python3"
    roots = [os.environ.get("LOCALAPPDATA"), "C:\\",
             os.environ.get("ProgramData"), os.environ.get("USERPROFILE")]
    for root in roots:
        if not root:
            continue
        root_p = Path(root)
        if not root_p.exists():
            continue
        try:
            for d in sorted(root_p.glob("Python3*"), reverse=True):
                exe = d / exe_name
                if exe.exists():
                    out.append([str(exe)])
        except OSError:
            pass
        for name in ("miniconda3", "anaconda3"):
            exe = root_p / name / exe_name
            if exe.exists():
                out.append([str(exe)])

    seen, uniq = set(), []
    for cmd in out:
        try:
            key = os.path.normcase(os.path.abspath(cmd[0]))
        except OSError:
            key = cmd[0].lower()
        if key not in seen:
            seen.add(key)
            uniq.append(cmd)
    return uniq


def pick_interpreter():
    """返回 (解释器命令, 是否换了一个)。优先选依赖已装好的。"""
    me = [sys.executable]
    if _check(me, _DEPS_OK):
        return me, False
    for cmd in python_candidates():
        if cmd == me:
            continue
        if _check(cmd, _DEPS_OK):
            return cmd, True
    return me, False


def windowed(cmd):
    """Windows 下换成 pythonw.exe：启动桌宠时不弹出黑色控制台窗口。"""
    if os.name != "nt":
        return cmd
    exe = Path(cmd[0])
    if exe.name.lower() != "python.exe":
        return cmd                                  # py -3 / py 启动器直接沿用
    cand = exe.with_name("pythonw.exe")
    return [str(cand)] + cmd[1:] if cand.exists() else cmd


def main():
    say()
    say("  ===== AI 桌宠 =====")
    say(f"  [1/3] Python {sys.version.split()[0]}  ({sys.executable})")

    best, switched = pick_interpreter()
    if switched:
        say(f"        检测到另一个 Python 已装好依赖，改用它：{best[0]}")

    if _check(best, _DEPS_OK):
        say("  [2/3] 依赖已就绪")
    else:
        say("  [2/3] 缺少依赖：PySide6 / requests")
        say("        提示：PySide6 约 250MB，第一次安装会慢一些")
        try:
            ans = input("        现在自动安装吗？(Y/n) ").strip().lower()
        except EOFError:
            ans = "n"
        if ans in ("n", "no"):
            hold(f"  已取消。请手动执行：\n    {best[0]} -m pip install -r \"{REQ}\"")
            return 1
        say("        安装中...")
        if subprocess.call(best + ["-m", "pip", "install", "-r", str(REQ)]) != 0:
            hold(f"  [X] 安装失败，请手动执行：\n    {best[0]} -m pip install -r \"{REQ}\"")
            return 1
        say("        安装完成")

    run_cmd = windowed(best)
    if os.name == "nt" and Path(run_cmd[0]).name.lower() == "python.exe":
        say("        提示：没找到 pythonw.exe，会附带一个控制台窗口")

    entry = ROOT / "main.py"
    if not entry.exists():
        hold(f"  [X] 找不到主程序：{entry}")
        return 1

    say("  [3/3] 启动中...（关掉本窗口不影响桌宠）")
    try:
        subprocess.Popen(run_cmd + [str(entry)], cwd=str(ROOT))
    except OSError as e:
        hold(f"  [X] 启动失败：{e}")
        return 1
    say()
    return 0


if __name__ == "__main__":
    sys.exit(main())
