# Changelog

本文件记录所有值得注意的改动。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

分类约定：`Added` 新功能 · `Changed` 行为变化 · `Fixed` 修 bug · `Removed` 移除 ·
`Security` 安全相关 · `Known limitations` 已知限制。

## [Unreleased]

（下个版本的改动先写在这里，发版时整段移到对应版本号下）

## [0.3.0] - 2026-11-07

### Added

- **Windows 一键安装包**：`LocalLLMChat-Setup-0.3.0.exe`（约 19 MB），双击即装，
  不需要预装 Python；当前用户安装、无需管理员权限，自带桌面 / 开始菜单快捷方式与卸载器
- **可复现的构建流程**：`build_installer.ps1` 自动建虚拟环境、跑 PyInstaller、编译
  `installer/LocalLLMChat.iss`（Inno Setup）
- **`--selftest` 自检模式**：打包后校验内置资源、后端连通性、窗口与性能面板能否创建

### Changed

- 打包后资源从 exe 内部读取（`RES_DIR`），用户数据改为写入可写目录：
  优先 `%APPDATA%\LocalLLMChat`，不可写时依次回退到 `%LOCALAPPDATA%`、用户目录、临时目录
- 源码运行时行为不变，仍使用脚本所在目录

## [0.2.1] - 2026-11-02

### Added

- **退出即释放显存**：关闭窗口时自动卸载所有已加载模型（`/api/chat` 带 `keep_alive=0`），
  可在模型管理里勾选"退出客户端时关闭模型服务并释放显存"（默认开启）
- **启动自动拉起**：连不上本地 Ollama 时自动执行 `ollama serve`，服务被关掉也不影响下次打开

### Fixed

- **窗口与任务栏图标**：改用 `qwen.ico`，不再是 tkinter 默认的羽毛图标
- **自动拉起服务时弹出 CMD 黑窗**：`DETACHED_PROCESS` 与 `CREATE_NO_WINDOW` 标志语义冲突，
  改为 `STARTUPINFO` + `SW_HIDE` + `CREATE_NO_WINDOW`
- **线程安全**：服务就绪通知改为写入 UI 队列，不再从工作线程直接调用 tkinter
  （无 mainloop 时会抛 `main thread is not in main loop`）

### Changed

- 启动时先做 0.35 秒端口探测再决定是否拉起服务，就绪时间从约 13 秒降到约 8 秒
- 设置 `AppUserModelID`，任务栏不再和 `pythonw` 进程合并成一组

## [0.2.0] - 2026-11-02

### Added

- **模型管理窗口**：查看体积 / 参数量 / 量化方式 / 显存占用，拉取（带进度）、删除、双击切换
  （Ollama 后端完整支持；OpenAI 兼容后端只读展示）
- **顶栏快速切换**：点右上角模型胶囊直接弹列表，不用进设置
- **性能监控窗口**：GPU 利用率、显存、温度、功耗、系统内存、CPU、实时 tok/s，
  每秒刷新并绘制 60 秒滚动曲线（无需 psutil，直接读 `nvidia-smi` 与 Win32 API）
- **删除对话**：会话列表右键即可删除单条记录
- **拖拽上传**：文件直接拖进窗口（Windows `WM_DROPFILES`）
- **图片缩略图**：图片附件 chip 上显示 24×24 预览
- **深色模式**：设置 → 外观 → 主题，即时重建界面并保留当前对话

### Changed

- 背景图与面板渲染加缓存，窗口缩放不再重复解码 JPEG / 重算磨砂
- 全局配色改为 `LIGHT` / `DARK` 双调色板，由 `apply_theme()` 统一切换

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
  - 附中性渐变默认素材，无版权限制
- **零配置**：连上服务后自动选中第一个可用模型
- **工程**：GitHub Actions 多平台 CI（Ubuntu / Windows × Python 3.10 / 3.12）、
  15 项冒烟测试、Dependabot、Issue / PR 模板、双语 README

### Known limitations

- tkinter 子控件不支持真透明，卡片中间无法透出背景
- 扫描版 PDF 没有文字层，提取不到内容
- 不支持 `.doc` / `.xls` / `.ppt` 旧格式

[Unreleased]: https://github.com/Kezyoow/local-llm-chat/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Kezyoow/local-llm-chat/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Kezyoow/local-llm-chat/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Kezyoow/local-llm-chat/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Kezyoow/local-llm-chat/releases/tag/v0.1.0
