#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小冒烟测试：不需要网络、不需要 GPU、不需要 tkinter。
CI 里跑：  python tests/test_basic.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import providers
import extract

pass_count = 0
fail_count = 0


def check(name, cond):
    global pass_count, fail_count
    if cond:
        pass_count += 1
        print(f"  ok   {name}")
    else:
        fail_count += 1
        print(f"  FAIL {name}")


print("providers:")
b = providers.make_backend("ollama", "http://127.0.0.1:11434")
check("ollama 工厂返回 OllamaBackend", isinstance(b, providers.OllamaBackend))
check("ollama 去掉尾部斜杠", b.base_url == "http://127.0.0.1:11434")
check("ollama label", b.label == "Ollama")

x = providers.make_backend("openai", "http://127.0.0.1:1234")
check("openai 工厂返回 OpenAIBackend", isinstance(x, providers.OpenAIBackend))
check("openai 自动补 /v1", x._api("/models") == "http://127.0.0.1:1234/v1/models")

x2 = providers.OpenAIBackend("http://localhost:8080/v1")
check("openai 已带 /v1 不重复", x2._api("/chat/completions")
      == "http://localhost:8080/v1/chat/completions")

try:
    providers.make_backend("nope", "http://x")
    check("未知协议应抛错", False)
except providers.BackendError:
    check("未知协议应抛错", True)

try:
    providers.make_backend("ollama", "")
    check("空地址应抛错", False)
except providers.BackendError:
    check("空地址应抛错", True)

check("api_key 进 Authorization 头",
      providers.make_backend("openai", "http://x", "k123")._headers()
      .get("Authorization") == "Bearer k123")

print("extract:")
check("中文字数估算 > 0", extract.estimate_tokens("你好，世界") > 0)
check("空字符串估算为 0", extract.estimate_tokens("") == 0)
check("英文估算小于字符数", extract.estimate_tokens("hello world" * 10) < 110)

missing = extract.extract(os.path.join(HERE, "no_such_file.xyz"))
check("不存在的文件返回 error", bool(missing.get("error")))

unknown = extract.extract(os.path.join(HERE, "test_basic.py"))
check("源码文件可解析为文本", unknown.get("kind") == "text" and unknown.get("chars", 0) > 0)

ctx, warns = extract.build_context([])
check("空附件上下文为空", ctx == "" and warns == [])

print()
print(f"通过 {pass_count} 项，失败 {fail_count} 项")
sys.exit(1 if fail_count else 0)
