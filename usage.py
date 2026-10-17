# -*- coding: utf-8 -*-
"""云端 API 的用量与费用统计。

为什么要单独算：
  DeepSeek 按「百万 tokens」计价，而且价格分两个维度——
    1. 输入分「缓存命中 / 未命中」（命中便宜 50 倍）
    2. 高峰 / 空闲时段（空闲是高峰的一半）
  所以不能只拿总 token 数乘一个单价，必须按 usage 里的
  prompt_cache_hit_tokens / prompt_cache_miss_tokens 分别计价。

用量数据来源：接口返回的 usage 字段（流式的最后一个 chunk 会带上）。
本地模型没有价格，按免费计，但 token 数照常统计。

价格表默认内置官方价（2026-09 抓取，单位：元 / 百万 tokens），
也可以在 config 的对应来源里写 pricing 覆盖（比如官方调价、或换成美元计价）。
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

# 北京时间
BEIJING = timezone(timedelta(hours=8))

# 官方价目表：(空闲, 高峰)，单位 元 / 百万 tokens
DEFAULT_PRICING = {
    "deepseek-flash": {
        "cache_hit": (0.02, 0.04),
        "cache_miss": (1.0, 2.0),
        "output": (4.0, 8.0),
    },
    "deepseek-v4-pro": {
        "cache_hit": (0.15, 0.30),
        "cache_miss": (4.5, 9.0),
        "output": (13.5, 27.0),
    },
    # 旧别名，当前由 flash 提供服务、按 flash 计费
    "deepseek-chat": {
        "cache_hit": (0.02, 0.04),
        "cache_miss": (1.0, 2.0),
        "output": (4.0, 8.0),
    },
}


def is_peak(when=None, holidays=()):
    """是否处于高峰时段。

    北京时间周一至周五 9:00-12:00、14:00-18:00 为高峰；
    周末与中国法定节假日全天为空闲。节假日需要自己填（holidays 里放 "2026-10-01"）。

    返回 (是否高峰, 时段名, 北京时间字符串)
    """
    dt = when or datetime.now(BEIJING)
    day = dt.strftime("%Y-%m-%d")
    off_holiday = day in set(holidays or ())
    peak = dt.weekday() < 5 and not off_holiday and (9 <= dt.hour < 12 or 14 <= dt.hour < 18)
    return peak, ("高峰" if peak else "空闲"), dt.strftime("%Y-%m-%d %H:%M")


def get_pricing(model, override=None):
    """取某个模型的价格表，返回 (价格 dict, 货币)。取不到返回 (None, currency)。"""
    override = override or {}
    currency = override.get("currency") or "¥"
    if override.get("cache_miss") is not None:
        # 允许直接在 config 里写 pricing，格式与内置一致
        table = {k: tuple(v) if isinstance(v, (list, tuple)) else v
                 for k, v in override.items() if k in ("cache_hit", "cache_miss", "output")}
        if table:
            return table, currency
    base = DEFAULT_PRICING.get(str(model or "").strip())
    return (dict(base) if base else None), currency


def compute_cost(usage, table, peak):
    """按用量和价格表算钱，返回 (费用, 明细 dict)。"""
    detail = {
        "cache_hit": int(usage.get("prompt_cache_hit_tokens") or 0),
        "cache_miss": int(usage.get("prompt_cache_miss_tokens") or 0),
        "output": int(usage.get("completion_tokens") or 0),
    }
    if detail["cache_hit"] == 0 and detail["cache_miss"] == 0:
        # 有些服务只给 prompt_tokens，没有缓存细分，就全按未命中算
        detail["cache_miss"] = int(usage.get("prompt_tokens") or 0)
    if not table:
        return None, detail
    idx = 1 if peak else 0
    cost = 0.0
    for key, tokens in detail.items():
        price = table.get(key)
        if price is None:
            continue
        cost += tokens * (price[idx] if isinstance(price, (list, tuple)) else price) / 1_000_000.0
    return cost, detail


def _blank():
    return {"cost": 0.0, "requests": 0, "prompt": 0, "completion": 0,
            "cache_hit": 0, "cache_miss": 0, "free_requests": 0}


def _add(acc, cost, detail, free=False):
    acc["requests"] = acc.get("requests", 0) + 1
    acc["prompt"] = acc.get("prompt", 0) + detail["cache_hit"] + detail["cache_miss"]
    acc["completion"] = acc.get("completion", 0) + detail["output"]
    acc["cache_hit"] = acc.get("cache_hit", 0) + detail["cache_hit"]
    acc["cache_miss"] = acc.get("cache_miss", 0) + detail["cache_miss"]
    if free or cost is None:
        acc["free_requests"] = acc.get("free_requests", 0) + 1
    else:
        acc["cost"] = round(acc.get("cost", 0.0) + cost, 6)
    return acc


def _fmt_tokens(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


class UsageTracker(QObject):
    """记录每次请求的 token 与费用，落盘到 usage.json，并给出可读摘要。

    changed 信号在每次记录后发出（可能来自工作线程，Qt 会自动排队到界面线程）。
    """

    changed = Signal(str)

    def __init__(self, path=None, currency="¥"):
        super().__init__()
        self.path = Path(path) if path else None
        self.currency = currency
        self._lock = threading.Lock()
        self.data = {"total": _blank(), "by_day": {}, "by_model": {}}
        self.session = _blank()
        self.last_line = ""
        self._load()

    # ---------- 落盘 ----------
    def _load(self):
        if not self.path or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in ("total", "by_day", "by_model"):
                    if isinstance(raw.get(key), dict):
                        self.data[key] = raw[key]
                self.currency = raw.get("currency") or self.currency
        except Exception as e:  # noqa: BLE001
            print(f"[桌宠] 读取用量记录失败（忽略）：{e}")

    def _save(self):
        if not self.path:
            return
        payload = dict(self.data)
        payload["currency"] = self.currency
        payload["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"[桌宠] 写入用量记录失败（忽略）：{e}")

    # ---------- 记账 ----------
    def record(self, info: dict):
        """info 由 ai_client 提供：
        {model, usage, pricing, free, source}
        """
        usage = info.get("usage") or {}
        model = str(info.get("model") or "?")
        free = bool(info.get("free"))
        peak, period, now_str = is_peak(holidays=info.get("holidays") or ())
        table, currency = get_pricing(model, info.get("pricing"))
        cost, detail = compute_cost(usage, table, peak)
        if free:
            cost = None

        with self._lock:
            day = now_str[:10]
            _add(self.session, cost, detail, free)
            _add(self.data["total"], cost, detail, free)
            _add(self.data["by_day"].setdefault(day, _blank()), cost, detail, free)
            _add(self.data["by_model"].setdefault(model, _blank()), cost, detail, free)
            if currency and not free:
                self.currency = currency
            self._save()
            self.last_line = self._line(detail, cost, table, peak, period)

        self.changed.emit(self.chat_line())
        return self.last_line

    def _line(self, detail, cost, table, peak, period):
        hit = detail["cache_hit"]
        miss = detail["cache_miss"]
        total_in = hit + miss
        rate = f"缓存命中 {hit / total_in:.0%}" if total_in else "无输入"
        tokens = f"入 {_fmt_tokens(total_in)} / 出 {_fmt_tokens(detail['output'])}"
        if cost is None:
            if table is None:
                return f"{tokens}（未配置价格）"
            return f"{tokens}（免费）"
        return f"{tokens} · {rate} · {period} · {self.currency}{cost:.6f}"

    # ---------- 摘要 ----------
    def _one(self, acc):
        cost = self.currency + f"{acc.get('cost', 0.0):.4f}"
        return (f"{acc.get('requests', 0)} 次 · "
                f"{_fmt_tokens(acc.get('prompt', 0) + acc.get('completion', 0))} tokens · {cost}")

    def session_text(self):
        s = self.session
        if not s.get("requests"):
            return ""
        tail = f" · {s.get('free_requests', 0)} 次免费" if s.get("free_requests") else ""
        return f"本次会话：{self._one(s)}{tail}"

    def summary_text(self, lines=3):
        t = self.data.get("total", {})
        day = self.data.get("by_day", {}).get(time.strftime("%Y-%m-%d"), _blank())
        out = [f"💰 用量统计（{self.currency}）",
               f"本次会话：{self._one(self.session)}",
               f"今天：{self._one(day)}",
               f"累计：{self._one(t)}"]
        models = self.data.get("by_model", {})
        for name, acc in list(models.items())[:lines]:
            out.append(f"  · {name}：{self._one(acc)}")
        peak, period, _ = is_peak()
        out.append(f"当前是{period}时段（{'高峰价' if peak else '半价'}）")
        return "\n".join(out)

    def chat_line(self):
        """聊天窗口底部那一行小字。"""
        s = self.session
        if not s.get("requests"):
            return ""
        t = self.data.get("total", {})
        return (f"本次 {self.currency}{s.get('cost', 0.0):.4f} · "
                f"累计 {self.currency}{t.get('cost', 0.0):.4f} · "
                f"{_fmt_tokens(s.get('prompt', 0) + s.get('completion', 0))} tokens")
