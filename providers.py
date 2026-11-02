#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地大模型后端适配层
================================================================
支持两种协议，覆盖几乎所有本地推理服务：

    ollama  → Ollama 原生 /api/chat
              支持 think（思考链）、图片、精确 token 统计

    openai  → OpenAI 兼容 /v1/chat/completions
              覆盖 LM Studio、llama.cpp server、vLLM、LocalAI、
              Jan、text-generation-webui、KoboldCpp、SGLang …

流式接口约定
------------
    stream_chat(...) 逐条 yield：
        ("content",  str)   正文增量
        ("thinking", str)   思考链增量（ollama 支持；openai 兼容服务可能没有）
        ("done",     dict)  结束，携带 metrics
    metrics 里可能含：
        eval_count / eval_duration / prompt_eval_count / prompt_eval_duration
        （OpenAI 兼容服务一般只有 completion_tokens）
"""

import json
import sys
import time
import urllib.error
import urllib.request


class BackendError(Exception):
    pass


class BaseBackend:
    kind = "base"
    label = "未知"

    def __init__(self, base_url, api_key="", timeout=1800):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout

    # ---------------- 公共
    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def _get(self, path, timeout=5):
        req = urllib.request.Request(self.base_url + path, headers=self._headers())
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    # ---------------- 需要子类实现
    def ping(self):
        raise NotImplementedError

    def list_models(self):
        raise NotImplementedError

    def stream_chat(self, model, messages, images=None, temperature=0.6,
                    num_ctx=8192, think=False):
        raise NotImplementedError


# ================================================================ Ollama
class OllamaBackend(BaseBackend):
    kind = "ollama"
    label = "Ollama"

    def ping(self):
        d = self._get("/api/version", timeout=3)
        return d.get("version", "?")

    def list_models(self):
        d = self._get("/api/tags", timeout=8)
        out = []
        for m in d.get("models", []):
            name = m.get("name") or m.get("model") or ""
            if name:
                out.append(name)
        return sorted(set(out))

    # ---------------- 模型管理（Ollama 专有）
    def list_models_detail(self):
        """返回每个模型的体积 / 参数量 / 量化方式。"""
        d = self._get("/api/tags", timeout=8)
        out = []
        for m in d.get("models", []):
            det = m.get("details") or {}
            name = m.get("name") or m.get("model") or ""
            if not name:
                continue
            out.append({
                "name": name,
                "size": m.get("size") or 0,
                "params": det.get("parameter_size") or "",
                "quant": det.get("quantization_level") or "",
                "family": det.get("family") or "",
                "modified": m.get("modified_at") or "",
            })
        return sorted(out, key=lambda x: x["name"])

    def running(self):
        """当前加载在显存里的模型。"""
        d = self._get("/api/ps", timeout=8)
        out = {}
        for m in d.get("models", []):
            name = m.get("name") or m.get("model") or ""
            if name:
                out[name] = {
                    "vram": m.get("size_vram") or 0,
                    "size": m.get("size") or 0,
                    "until": m.get("expires_at") or "",
                }
        return out

    def pull(self, name):
        """拉取模型，逐条 yield 进度对象。"""
        payload = {"model": name, "stream": True}
        req = urllib.request.Request(
            self.base_url + "/api/pull",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers())
        with urllib.request.urlopen(req, timeout=7200) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                yield obj
                if obj.get("status") == "success" or obj.get("error"):
                    break

    def delete(self, name):
        payload = {"model": name}
        req = urllib.request.Request(
            self.base_url + "/api/delete",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="DELETE")
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status

    # ---------------- 释放资源
    def unload(self, name):
        """立刻把模型从显存里卸掉（keep_alive=0）。"""
        payload = {"model": name, "messages": [], "keep_alive": 0, "stream": False}
        req = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
            return True
        except Exception:
            return False

    def unload_all(self):
        """卸载所有正在占用显存的模型，返回卸载了几个。"""
        try:
            names = list(self.running().keys())
        except Exception:
            names = []
        n = 0
        for name in names:
            if self.unload(name):
                n += 1
        return n

    def stop_server(self):
        """结束 ollama 进程（连同它占的内存一起释放）。"""
        import subprocess
        try:
            if sys.platform == "win32":
                creation = 0x08000000
                subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                               capture_output=True, timeout=10,
                               creationflags=creation)
            else:
                subprocess.run(["pkill", "-f", "ollama"],
                               capture_output=True, timeout=10)
            return True
        except Exception:
            return False

    def stream_chat(self, model, messages, images=None, temperature=0.6,
                    num_ctx=8192, think=False):
        msgs = [dict(m) for m in messages]
        if images and msgs:
            msgs[-1] = dict(msgs[-1])
            msgs[-1]["images"] = images

        payload = {
            "model": model,
            "messages": msgs,
            "stream": True,
            "think": bool(think),
            "options": {
                "temperature": float(temperature),
                "num_ctx": int(num_ctx),
            },
        }
        req = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers())

        metrics = {}
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message") or {}
                if msg.get("thinking"):
                    yield ("thinking", msg["thinking"])
                if msg.get("content"):
                    yield ("content", msg["content"])
                if obj.get("done"):
                    metrics = {
                        "eval_count": obj.get("eval_count"),
                        "eval_duration": obj.get("eval_duration"),
                        "prompt_eval_count": obj.get("prompt_eval_count"),
                        "prompt_eval_duration": obj.get("prompt_eval_duration"),
                    }
                    break
        yield ("done", metrics)


# ================================================================ OpenAI 兼容
class OpenAIBackend(BaseBackend):
    kind = "openai"
    label = "OpenAI 兼容"

    # ---------------- 路径自动兼容 /v1
    def _api(self, path):
        base = self.base_url
        if not base.endswith("/v1") and "/v1/" not in base:
            base += "/v1"
        return base + path

    def ping(self):
        req = urllib.request.Request(self._api("/models"), headers=self._headers())
        with urllib.request.urlopen(req, timeout=3) as r:
            json.load(r)
        return "ok"

    def list_models(self):
        req = urllib.request.Request(self._api("/models"), headers=self._headers())
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.load(r)
        out = []
        for m in d.get("data", []):
            mid = m.get("id") or m.get("name") or ""
            if mid:
                out.append(mid)
        return sorted(set(out))

    # ---------------- 只读（该协议没有拉取/删除接口）
    def list_models_detail(self):
        return [{"name": n, "size": 0, "params": "", "quant": "",
                 "family": "", "modified": ""} for n in self.list_models()]

    def running(self):
        return {}

    def pull(self, name):
        raise BackendError("OpenAI 兼容后端不支持拉取模型，请用该服务自带的工具")

    def delete(self, name):
        raise BackendError("OpenAI 兼容后端不支持删除模型")

    @staticmethod
    def _encode_messages(messages, images):
        """把最后一条 user 消息转成 content 数组（文本 + 图片）。"""
        out = []
        for i, m in enumerate(messages):
            m = dict(m)
            if i == len(messages) - 1 and images and m.get("role") == "user":
                parts = [{"type": "text", "text": m.get("content") or ""}]
                for b64 in images:
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + b64},
                    })
                m["content"] = parts
            out.append(m)
        return out

    def stream_chat(self, model, messages, images=None, temperature=0.6,
                    num_ctx=8192, think=False):
        payload = {
            "model": model,
            "messages": self._encode_messages(messages, images),
            "stream": True,
            "temperature": float(temperature),
            "stream_options": {"include_usage": True},
        }
        req = urllib.request.Request(
            self._api("/chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers())

        usage = {}
        started = time.time()
        first_at = None
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    obj = json.loads(body)
                except Exception:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                for ch in obj.get("choices", []):
                    delta = ch.get("delta") or {}
                    if delta.get("reasoning_content"):
                        yield ("thinking", delta["reasoning_content"])
                    if delta.get("content"):
                        if first_at is None:
                            first_at = time.time()
                        yield ("content", delta["content"])
        elapsed = time.time() - (first_at or started)
        n = usage.get("completion_tokens") or 0
        metrics = {
            "eval_count": n,
            "eval_duration": int(elapsed * 1e9) if n else None,
            "prompt_eval_count": usage.get("prompt_tokens"),
            "prompt_eval_duration": None,
        }
        yield ("done", metrics)


# ================================================================ 工厂
BACKENDS = {
    "ollama": OllamaBackend,
    "openai": OpenAIBackend,
}

PRESETS = [
    ("Ollama", "ollama", "http://127.0.0.1:11434"),
    ("LM Studio", "openai", "http://127.0.0.1:1234"),
    ("llama.cpp (llama-server)", "openai", "http://127.0.0.1:8080"),
    ("vLLM", "openai", "http://127.0.0.1:8000"),
    ("Jan", "openai", "http://127.0.0.1:1337"),
    ("LocalAI", "openai", "http://127.0.0.1:8080"),
    ("text-generation-webui", "openai", "http://127.0.0.1:5000"),
    ("KoboldCpp", "openai", "http://127.0.0.1:5001"),
]


def make_backend(kind, base_url, api_key=""):
    cls = BACKENDS.get((kind or "ollama").lower())
    if cls is None:
        raise BackendError(f"未知后端类型：{kind}")
    if not base_url:
        raise BackendError("没有配置服务地址")
    return cls(base_url, api_key)


def probe(base_url, api_key=""):
    """尝试识别某个地址是什么后端，返回 (kind, version)。"""
    for kind in ("ollama", "openai"):
        try:
            b = make_backend(kind, base_url, api_key)
            v = b.ping()
            return kind, v
        except Exception:
            continue
    return None, None
