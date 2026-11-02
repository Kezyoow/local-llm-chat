# 贡献指南 · Contributing

欢迎 PR 和 Issue。这个项目很小，规则也很少。

## 环境准备

```bash
git clone https://github.com/Kezyoow/local-llm-chat.git
cd local-llm-chat
pip install -r requirements.txt
```

跑起来需要一个本地推理服务（Ollama 或任意 OpenAI 兼容服务），不是开发也能跑。

## 代码结构

```
qwen_chat.py   界面、会话、附件、测速（一个类 ChatApp 撑起来的）
providers.py   后端适配层，最值得扩展的地方
extract.py     文件解析，纯函数，好测
tests/         不需要网络和 GPU 的冒烟测试
```

## 加一个新后端

大多数情况**不需要**写新类——只要服务兼容 `/v1/chat/completions`，在
`providers.PRESETS` 里加一行就行：

```python
PRESETS = [
    ...
    ("MyServer", "openai", "http://127.0.0.1:9999"),
]
```

如果协议真的不一样（比如流式格式不同），照 `OllamaBackend` 写一个类：

1. 继承 `BaseBackend`，实现 `ping()` / `list_models()` / `stream_chat()`
2. `stream_chat` 用 `yield ("content", str)` 逐块吐字，最后 `yield ("done", metrics)`
3. 注册到 `BACKENDS = {"myproto": MyBackend}`
4. 在 `tests/test_basic.py` 里加两条断言

## 改界面

配色常量都在 `qwen_chat.py` 顶部。改完记得看一眼小窗口（1240×820）和最大化两种情况，
面板是按窗口尺寸动态渲染的，容易在小尺寸下挤压。

## 提 PR 之前

```bash
python -m compileall -q .        # 语法
python tests/test_basic.py       # 冒烟测试，应显示"通过 15 项"
```

不要提交这些东西（`.gitignore` 里已经排除了，别强行 `git add -f`）：

- `settings.json`（含你的本地路径）
- `sessions/`（你的聊天记录）
- `assets/background.jpg`、`assets/side_card.jpg`（个人素材，注意版权）

## 提交信息

用 [Conventional Commits](https://www.conventionalcommits.org/) 前缀，一句话说清做了什么：

```
feat: 支持 Ollama 的 num_predict 参数
fix: 设置里切后端后状态栏没刷新
docs: 补充 LM Studio 的端口说明
ci: 升级 checkout 到 v7
```

## 代码风格

- 4 空格缩进，单行尽量不超过 100 字符
- 注释用中文（项目主要受众是中文用户），变量名英文
- 不引入第三方 UI 库，只用标准库 + Pillow
- 异常要吃掉就写 `except Exception: pass`，别裸 `except:`
- 新增文件读写一律 `encoding="utf-8"`

## Issue

提 bug 请填模板，重点说清 **用的什么后端 + 什么版本 + 报错原文**。
只说"不能用"没法定位。
