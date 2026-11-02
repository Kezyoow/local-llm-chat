# Changelog

本文件记录所有值得注意的改动。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- **拖拽上传**：把文件拖进窗口即可添加（Windows 下走 `WM_DROPFILES`）
- **图片缩略图**：图片附件的 chip 上直接显示 24×24 预览
- **深色模式**：设置 → 外观 → 主题，切换即时重建界面并保留当前对话

### Changed

- 背景图与面板渲染加缓存，窗口缩放时不再重复解码 JPEG / 重算磨砂
- 全局配色改为 `LIGHT` / `DARK` 两套调色板，`apply_theme()` 统一切换

## [0.1.0] - 2026-11-02

首个公开版本。

### Added

- **多后端支持**：Ollama 原生协议 + OpenAI 兼容协议
  - 内置预设：Ollama、LM Studio、llama.cpp、vLLM、Jan、LocalAI、text-generation-webui、KoboldCpp
  - 设置里可测试连通性、一键拉取模型列表
- **文件阅读**：PDF、Word、Excel、PowerPoint、CSV、Markdown、源码、EPUB、RTF
  - 单文件上限 80MB，一次最多 12 个
  - 超长文档按比例截断并提示
- **图片理解**：自动路由到视觉模型；支持 `Ctrl+V` 粘贴截图
- **对话**：流式输出、随时停止、多轮上下文、历史会话本地保存
- **速度观测**：生成中实时估算 tok/s，结束后给出精确值（首尾延迟、提示词速度）
- **测速面板**：固定提示词与生成长度，多次结果可对比
- **界面**：玻璃拟态风格、圆角卡片、磨砂背景
  - 可自定义窗口背景与侧栏图片（设置 → 外观）
  - 附图中性渐变默认素材，无版权限制
- **零配置**：连上服务后自动选中第一个可用模型
- **工程**：GitHub Actions 多平台 CI（Ubuntu / Windows × Python 3.10 / 3.12）、
  15 项冒烟测试、Dependabot、Issue / PR 模板

### Known limitations

- tkinter 子控件不支持真透明，卡片中间无法透出背景
- 扫描版 PDF 没有文字层，提取不到内容
- 不支持 `.doc` / `.xls` / `.ppt` 旧格式

[Unreleased]: https://github.com/Kezyoow/local-llm-chat/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Kezyoow/local-llm-chat/releases/tag/v0.1.0
