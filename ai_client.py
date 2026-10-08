# -*- coding: utf-8 -*-
"""大模型客户端：本地（Ollama / LM Studio / vLLM…）或云端 API 都能接。

两种接口（每个来源可单独指定）：
  - "ollama" : Ollama 原生接口，base_url 形如 http://localhost:11434
  - "openai" : OpenAI 兼容接口（LM Studio / vLLM / llama.cpp / 各云厂商 API）

多来源（ai.profiles）：可以配置多个"模型来源"，比如本地的 LM Studio 和
云端的 DeepSeek API，运行时用右键菜单切换；`active` 指定默认用哪个。
  - 聊天用一个来源、看图用另一个来源也行：ai.vision_profile

多端点回退：每个来源里可以写 fallbacks，主端点连不上自动试下一个，
并记住可用的那个 —— 本地服务常常"这个开那个关"，不用来回改配置。

另外会剔除推理模型内联在正文里的 thinking 片段（标记可能跨 chunk）。
"""
import json
import os

import requests

# 这些键属于"全局"设置，不会从顶层继承进每个来源
_GLOBAL_KEYS = ("profiles", "active", "vision_profile", "fallbacks")


class _Endpoint:
    """一个可用的模型端点（某个来源下的一个地址）。"""

    def __init__(self, cfg: dict):
        self.api_format = str(cfg.get("api_format", "openai")).lower()
        self.base_url = str(cfg.get("base_url", "")).rstrip("/")
        self.model = str(cfg.get("model", ""))
        # api_key 可以直接写，也可以只写环境变量名（避免把密钥留在配置文件里）
        self.api_key = str(cfg.get("api_key", "") or "")
        env_name = str(cfg.get("api_key_env", "") or "").strip()
        if not self.api_key and env_name:
            self.api_key = os.environ.get(env_name, "")
        self.proxy = str(cfg.get("proxy", "") or "").strip()
        self.extra_body = dict(cfg.get("extra_body") or {})
        self.temperature = cfg.get("temperature")
        self.max_tokens = cfg.get("max_tokens")

    def label(self):
        return f"{self.base_url} [{self.model}]"

    def proxies(self):
        return {"http": self.proxy, "https": self.proxy} if self.proxy else None


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
        self._cfg = dict(ai_cfg)
        self.system_prompt = ai_cfg.get("system_prompt", "")
        self._base_system_prompt = self.system_prompt
        self._context = ""
        self.temperature = float(ai_cfg.get("temperature", 0.8))
        self.max_tokens = int(ai_cfg.get("max_tokens", 512))
        self.extra_body = dict(ai_cfg.get("extra_body") or {})
        self.session = requests.Session()

        # ---- 模型来源（profiles）----
        self.profiles = self._build_profiles(ai_cfg)
        active = str(ai_cfg.get("active") or "").strip()
        if active not in self.profiles:
            active = next(iter(self.profiles))
        self.active_profile = active
        self.vision_profile = str(ai_cfg.get("vision_profile") or "").strip()
        self.endpoints = []
        self.active = 0                    # 当前可用的端点下标
        self._load_endpoints(active)

    # ---------- 来源管理 ----------
    @staticmethod
    def _build_profiles(ai_cfg: dict) -> dict:
        """把配置整理成 {来源名: 该来源的配置}。

        写了 ai.profiles 就用它；没写则兼容旧的扁平写法（整体当成一个来源）。
        """
        profiles = ai_cfg.get("profiles")
        if isinstance(profiles, dict) and profiles:
            base = {k: v for k, v in ai_cfg.items() if k not in _GLOBAL_KEYS}
            out = {}
            for name, one in profiles.items():
                merged = dict(base)
                merged.update(one or {})
                # 顶层 fallbacks 不继承，避免本地回退端点被套到云端来源上
                if isinstance(one, dict) and "fallbacks" in one:
                    merged["fallbacks"] = one["fallbacks"]
                else:
                    merged.pop("fallbacks", None)
                out[str(name)] = merged
            return out
        flat = {k: v for k, v in ai_cfg.items() if k != "profiles"}
        return {"default": flat}

    def _build_endpoint_list(self, name):
        """按来源名构造端点列表（不修改实例状态，便于多线程并发取用）。"""
        p = self.profiles[name]
        raw = [p]
        for fb in (p.get("fallbacks") or []):
            merged = dict(p)               # 继承该来源的 api_format / api_key 等
            merged.update(fb or {})
            raw.append(merged)
        return [_Endpoint(c) for c in raw if str(c.get("base_url", "")).strip()]

    def _load_endpoints(self, name):
        self.endpoints = self._build_endpoint_list(name)
        self.active = 0

    def profile_names(self):
        return list(self.profiles.keys())

    def use_profile(self, name):
        """运行时切换模型来源（聊天与默认看图都走它）。"""
        if name not in self.profiles:
            return False
        self.active_profile = name
        self._load_endpoints(name)
        print(f"[桌宠] 模型来源切换为：{name}（{self.endpoint_info()}）")
        return True

    def profile_vision(self, name):
        """该来源能不能看图：True / False / None（没写，当作可以试）。"""
        p = self.profiles.get(name)
        if not p:
            return False
        v = p.get("vision")
        return None if v is None else bool(v)

    def vision_profile_name(self):
        """决定用哪个来源看图。

        优先 ai.vision_profile；否则用当前来源（只要没明确写 vision:false）；
        再否则找第一个明确声明支持视觉的来源；都没有则返回 None（关掉视觉层）。
        """
        if self.vision_profile and self.vision_profile in self.profiles:
            return self.vision_profile
        if self.profile_vision(self.active_profile) is not False:
            return self.active_profile
        for name in self.profiles:
            if self.profile_vision(name) is True:
                return name
        return None

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

    def vision_comment(self, image_b64, prompt, system_prompt=None, max_tokens=None,
                       profile=None):
        """把一张 base64 JPEG 交给视觉模型（多模态），返回回答文本。

        system_prompt 传 "" 可临时不要人设（做客观描述时用）。
        profile 指定用哪个来源看图（不传则用当前来源）。
        """
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]
        return self.stream_chat([{"role": "user", "content": content}],
                                lambda _t: None,
                                max_tokens=max_tokens,
                                system_prompt=system_prompt,
                                profile=profile)

    def endpoint_info(self):
        return f"[{self.active_profile}] " + " + ".join(ep.label() for ep in self.endpoints)

    # ---------- 连通性 ----------
    def ping(self, profile=None):
        """逐个端点探测，返回 (是否有可用端点, 多行说明)。"""
        eps = self._endpoints_for(profile)
        ok_any, lines = False, []
        for ep in eps:
            try:
                if ep.api_format == "ollama":
                    r = self.session.get(ep.base_url + "/api/tags", timeout=2,
                                         proxies=ep.proxies())
                    r.raise_for_status()
                    names = [m.get("name", "") for m in r.json().get("models", [])]
                    info = "已装模型：" + (", ".join(names) or "（无）")
                else:
                    r = self.session.get(ep.base_url + "/models", timeout=4,
                                         headers=self._headers(ep), proxies=ep.proxies())
                    r.raise_for_status()
                    ids = [m.get("id", "") for m in (r.json().get("data") or [])]
                    info = "可用模型：" + (", ".join(ids[:5]) or "（无）")
                ok_any = True
                lines.append(f"✅ {ep.label()} {info}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"❌ {ep.label()} 连不上（{type(e).__name__}）")
        return ok_any, "\n".join(lines)

    # ---------- 对话 ----------
    def _endpoints_for(self, profile=None):
        if profile and profile in self.profiles and profile != self.active_profile:
            return self._build_endpoint_list(profile)
        return self.endpoints

    def stream_chat(self, history, on_chunk, max_tokens=None, system_prompt=None,
                    profile=None):
        """发起对话：每收到一段可见文本就回调 on_chunk(text)，返回完整回复。

        端点失败（且还没吐出任何内容）时自动回退到下一个端点。
        max_tokens / system_prompt 可临时覆盖配置值（视觉点评会用到）。
        """
        eps = self._endpoints_for(profile)
        if not eps:
            raise RuntimeError("没有可用的模型端点，请检查 config.json 的 ai 配置")
        using_default = eps is self.endpoints
        order = ([self.active] + [i for i in range(len(eps)) if i != self.active]
                 if using_default else list(range(len(eps))))
        last_err = None
        for idx in order:
            ep = eps[idx]
            flt = _ThinkFilter(on_chunk)
            try:
                text = self._chat(ep, history, flt, max_tokens, system_prompt)
                if using_default:
                    self.active = idx       # 记住这次成功的端点
                return text
            except Exception as e:  # noqa: BLE001
                last_err = e
                if flt.text:            # 已经吐过字了就别重试，避免重复输出
                    raise
                print(f"[桌宠] 端点 {ep.label()} 失败：{e}")
        raise RuntimeError(f"模型端点都连不上：{last_err}")

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
            "options": {
                "temperature": ep.temperature if ep.temperature is not None else self.temperature,
                "num_predict": max_tokens or ep.max_tokens or self.max_tokens,
            },
        }
        raw_parts = []
        with self.session.post(ep.base_url + "/api/chat", json=body, stream=True,
                               timeout=(10, None), headers=self._headers(ep),
                               proxies=ep.proxies()) as r:
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
            "temperature": ep.temperature if ep.temperature is not None else self.temperature,
            "max_tokens": max_tokens or ep.max_tokens or self.max_tokens,
        }
        # 来源自己的参数优先（比如本地关思考用 reasoning_effort=none，云端不需要）
        body.update(self.extra_body)
        body.update(ep.extra_body)
        raw_parts = []
        with self.session.post(ep.base_url + "/chat/completions", json=body, stream=True,
                               timeout=(10, None), headers=self._headers(ep),
                               proxies=ep.proxies()) as r:
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
