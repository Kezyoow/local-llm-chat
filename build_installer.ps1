# 构建 Windows 安装包（需要 Python 3.10+ 和 Inno Setup 6）
#
#   pwsh -File build_installer.ps1
#   pwsh -File build_installer.ps1 -Version 0.3.1
#
# 产物：build\installer\LocalLLMChat-Setup-<版本>.exe

param(
    [string]$Version = "0.3.0",
    [string]$Python = "",
    [switch]$SkipVenv
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$build = Join-Path $root "build"
$venv = Join-Path $root ".venv-build"

# ---------------------------------------------------------------- 1. 构建环境
if (-not $SkipVenv) {
    if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
        Write-Host "创建虚拟环境 $venv ..." -ForegroundColor Cyan
        $base = if ($Python) { $Python } else { "python" }
        & $base -m venv $venv
    }
    $py = Join-Path $venv "Scripts\python.exe"
    Write-Host "安装依赖 ..." -ForegroundColor Cyan
    & $py -m pip install -q --disable-pip-version-check `
        -i https://pypi.tuna.tsinghua.edu.cn/simple `
        pillow pypdf python-docx openpyxl python-pptx pyinstaller
} else {
    $py = if ($Python) { $Python } else { "python" }
}

# ---------------------------------------------------------------- 2. PyInstaller
Write-Host "打包 exe ..." -ForegroundColor Cyan
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Path $build -Force | Out-Null

& $py -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name LocalLLMChat `
    --icon (Join-Path $root "qwen.ico") `
    --add-data "$root\qwen.ico;." `
    --add-data "$root\assets\default_bg.jpg;assets" `
    --add-data "$root\assets\default_side.jpg;assets" `
    --hidden-import pypdf --hidden-import docx --hidden-import openpyxl --hidden-import pptx `
    --distpath (Join-Path $build "dist") `
    --workpath (Join-Path $build "work") `
    --specpath $build `
    (Join-Path $root "qwen_chat.py")

$exe = Join-Path $build "dist\LocalLLMChat\LocalLLMChat.exe"
if (-not (Test-Path $exe)) { throw "打包失败：找不到 $exe" }
Write-Host "exe 就绪：$exe" -ForegroundColor Green

# ---------------------------------------------------------------- 3. Inno Setup
$iscc = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Warning "没找到 Inno Setup 6（ISCC.exe），跳过安装包，只保留 build\dist\LocalLLMChat"
    Write-Warning "安装：winget install JRSoftware.InnoSetup"
    return
}

Write-Host "编译安装包 ..." -ForegroundColor Cyan
& $iscc "/DAppVersion=$Version" `
         "/DSrcDir=$(Join-Path $build 'dist\LocalLLMChat')" `
         "/DOutDir=$(Join-Path $build 'installer')" `
         (Join-Path $root "installer\LocalLLMChat.iss") | Out-Host

$setup = Join-Path $build "installer\LocalLLMChat-Setup-$Version.exe"
if (Test-Path $setup) {
    $mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
    Write-Host "完成：$setup ($mb MB)" -ForegroundColor Green
} else {
    throw "安装包未生成，检查上面的 ISCC 输出"
}
