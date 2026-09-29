#!/usr/bin/env bash
# ============================================================
#  AI 桌宠 启动器 (macOS / Linux)
#  找到 Python 3.10+ 后交给 tools/launch.py（依赖检查 + 启动）
# ============================================================
set -u
cd "$(dirname "$0")"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 \
     && "$c" -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
    PY="$c"
    break
  fi
done

if [ -z "$PY" ]; then
  echo
  echo " [X] 没有找到 Python 3.10 或更高版本"
  echo "     macOS : brew install python"
  echo "     Ubuntu: sudo apt install python3 python3-pip"
  echo
  exit 1
fi

exec "$PY" tools/launch.py "$@"
