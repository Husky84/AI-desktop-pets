# -*- coding: utf-8 -*-
"""本地大模型客户端。

支持两种接口（config.json 里 ai.api_format 指定，每个 fallback 也可单独指定）：
  - "ollama" : Ollama 原生接口，base_url 形如 http://localhost:11434
  - "openai" : OpenAI 兼容接口（LM Studio / vLLM / llama.cpp server / KVMem 等），
               base_url 形如 http://127.0.0.1:1234/v1

多端点回退：ai.fallbacks 里可以再列几个端点，主端点连不上会自动试下一个，
并记住可用的那个 —— 本地服务常常"这个开那个关"，不用来回改配置。

另外会剔除推理模型内联在正文里的 thinking 片段（标记可能跨 chunk）。
"""
import json

import requests


class _Endpoint:
    """一个可用的模型端点。"""

    def __init__(self, cfg: dict):
        self.api_format = str(cfg.get("api_format", "openai")).lower()
        self.base_url = str(cfg.get("base_url", "")).rstrip("/")
        self.model = str(cfg.get("model", ""))
        self.api_key = str(cfg.get("api_key", "") or "")

    def label(self):
        return f"{self.base_url} [{self.model}]"


class _ThinkFilter:
    """去掉流式输出里内联的思考块（标记可能被切在多个 chunk 里）。"""

    OPEN, CLOSE = "<" + "think>", "<" + "/think>"

    def __init__(self, emit):
        self._emit = emit
        self._buf = ""
        self._in_think = False
        self.parts = []

    def _out(self, text):
        if text:
            self.parts.append(text)
            self._emit(text)

    def feed(self, text):
        self._buf += text
        while True:
            if self._in_think:
                i = self._buf.find(self.CLOSE)
                if i < 0:                       # 结束标记还没到，只留可能是半个标记的尾巴
                    self._buf = self._buf[-(len(self.CLOSE) - 1):]
                    return
                self._buf = self._buf[i + len(self.CLOSE):]
                self._in_think = False
            else:
                i = self._buf.find(self.OPEN)
                if i < 0:
                    keep = len(self.OPEN) - 1
                    if len(self._buf) > keep:
                        self._out(self._buf[:-keep])
                        self._buf = self._buf[-keep:]
                    return
                if i > 0:
                    self._out(self._buf[:i])
                self._buf = self._buf[i + len(self.OPEN):]
                self._in_think = True

    def flush(self):
        if self._buf and not self._in_think:
            self._out(self._buf)
        self._buf = ""

    @property
    def text(self):
        return "".join(self.parts)


class LocalAIClient:
    def __init__(self, ai_cfg: dict):
        self.system_prompt = ai_cfg.get("system_prompt", "")
        self._base_system_prompt = self.system_prompt
        self._context = ""
        self.temperature = float(ai_cfg.get("temperature", 0.8))
        self.max_tokens = int(ai_cfg.get("max_tokens", 512))
        self.extra_body = dict(ai_cfg.get("extra_body") or {})
        self.session = requests.Session()

        raw = [dict(ai_cfg)]
        for fb in (ai_cfg.get("fallbacks") or []):
            merged = dict(ai_cfg)          # 继承 api_format / api_key / 采样参数
            merged.update(fb or {})
            raw.append(merged)
        self.endpoints = [_Endpoint(c) for c in raw if str(c.get("base_url", "")).strip()]
        self.active = 0                    # 当前可用的端点下标

    # ---------- 工具 ----------
    def _headers(self, ep):
        return {"Authorization": f"Bearer {ep.api_key}"} if ep.api_key else {}

    def _messages(self, history, system_prompt=None):
        sys_prompt = self.system_prompt if system_prompt is None else system_prompt
        msgs = []
        if sys_prompt:
            msgs.append({"role": "system", "content": sys_prompt})
        msgs.extend(history)
        return msgs

    def set_context(self, text):
        """设置动态上下文（比如"用户现在在用 VS Code 写 Python"），
        会拼到人设提示词后面，让桌宠聊天时"知道你正在干什么"。"""
        self._context = (text or "").strip()
        if self._context:
            self.system_prompt = (self._base_system_prompt
                                 + "\n\n【你现在能感知到的情况】\n" + self._context).strip()
        else:
            self.system_prompt = self._base_system_prompt

    def vision_comment(self, image_b64, prompt, system_prompt=None, max_tokens=None):
        """把一张 base64 JPEG 交给视觉模型（多模态），返回回答文本。

        system_prompt 传 "" 可临时不要人设（做客观描述时用）。
        """
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]
        return self.stream_chat([{"role": "user", "content": content}],
                                lambda _t: None,
                                max_tokens=max_tokens,
                                system_prompt=system_prompt)

    def endpoint_info(self):
        return " + ".join(ep.label() for ep in self.endpoints)

    # ---------- 连通性 ----------
    def ping(self):
        """逐个端点探测，返回 (是否有可用端点, 多行说明)。"""
        ok_any, lines = False, []
        for ep in self.endpoints:
            try:
                if ep.api_format == "ollama":
                    r = self.session.get(ep.base_url + "/api/tags", timeout=2)
                    r.raise_for_status()
                    names = [m.get("name", "") for m in r.json().get("models", [])]
                    info = "已装模型：" + (", ".join(names) or "（无）")
                else:
                    r = self.session.get(ep.base_url + "/models", timeout=2,
                                         headers=self._headers(ep))
                    r.raise_for_status()
                    ids = [m.get("id", "") for m in (r.json().get("data") or [])]
                    info = "可用模型：" + (", ".join(ids[:5]) or "（无）")
                ok_any = True
                lines.append(f"✅ {ep.label()} {info}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"❌ {ep.label()} 连不上（{type(e).__name__}）")
        return ok_any, "\n".join(lines)

    # ---------- 对话 ----------
    def stream_chat(self, history, on_chunk, max_tokens=None, system_prompt=None):
        """发起对话：每收到一段可见文本就回调 on_chunk(text)，返回完整回复。

        主端点失败（且还没吐出任何内容）时自动回退到下一个端点。
        max_tokens / system_prompt 可临时覆盖配置值（视觉点评会用到）。
        """
        order = [self.active] + [i for i in range(len(self.endpoints)) if i != self.active]
        last_err = None
        for idx in order:
            ep = self.endpoints[idx]
            flt = _ThinkFilter(on_chunk)
            try:
                text = self._chat(ep, history, flt, max_tokens, system_prompt)
                self.active = idx       # 记住这次成功的端点
                return text
            except Exception as e:  # noqa: BLE001
                last_err = e
                if flt.text:            # 已经吐过字了就别重试，避免重复输出
                    raise
                print(f"[桌宠] 端点 {ep.label()} 失败：{e}")
        raise RuntimeError(f"本地模型端点都连不上：{last_err}")

    def _chat(self, ep, history, flt, max_tokens=None, system_prompt=None):
        if ep.api_format == "ollama":
            return self._ollama_chat(ep, history, flt, max_tokens, system_prompt)
        return self._openai_chat(ep, history, flt, max_tokens, system_prompt)

    # ---------- Ollama ----------
    def _ollama_chat(self, ep, history, flt, max_tokens=None, system_prompt=None):
        body = {
            "model": ep.model,
            "messages": self._messages(history, system_prompt),
            "stream": True,
            "options": {"temperature": self.temperature,
                        "num_predict": max_tokens or self.max_tokens},
        }
        raw_parts = []
        with self.session.post(ep.base_url + "/api/chat", json=body, stream=True,
                               timeout=(10, None), headers=self._headers(ep)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = (data.get("message") or {}).get("content", "")
                if token:
                    raw_parts.append(token)
                    flt.feed(token)
                if data.get("done"):
                    break
        flt.flush()
        return self._visible(flt, raw_parts)

    # ---------- OpenAI 兼容 ----------
    def _openai_chat(self, ep, history, flt, max_tokens=None, system_prompt=None):
        body = {
            "model": ep.model,
            "messages": self._messages(history, system_prompt),
            "stream": True,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        body.update(self.extra_body)      # 提供方特有参数，如关闭思考
        raw_parts = []
        with self.session.post(ep.base_url + "/chat/completions", json=body, stream=True,
                               timeout=(10, None), headers=self._headers(ep)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                if not text.startswith("data:"):
                    continue
                payload = text[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                choices = chunk.get("choices") or [{}]
                delta = choices[0].get("delta") or {}
                token = delta.get("content")
                if token:
                    raw_parts.append(token)
                    flt.feed(token)
        flt.flush()
        return self._visible(flt, raw_parts)

    @staticmethod
    def _visible(flt, raw_parts):
        """思考块被剔干净后若什么都不剩（例如思考就把 token 用完了），退回原文。"""
        if flt.text:
            return flt.text
        return "".join(raw_parts).strip()
