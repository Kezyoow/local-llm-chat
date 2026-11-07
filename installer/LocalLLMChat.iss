; Local LLM Chat —— Inno Setup 安装脚本
; 编译：build_installer.ps1 会自动调用 ISCC.exe 并传入路径
; 手动编译：ISCC.exe /DSrcDir="..\build\dist\LocalLLMChat" /DOutDir="..\build\installer" installer\LocalLLMChat.iss

#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif
#ifndef SrcDir
  #define SrcDir "..\build\dist\LocalLLMChat"
#endif
#ifndef OutDir
  #define OutDir "..\build\installer"
#endif

#define MyAppName "Local LLM Chat"
#define MyAppNameZh "本地大模型助手"
#define MyAppPublisher "Kezyoow"
#define MyAppURL "https://github.com/Kezyoow/local-llm-chat"
#define MyAppExeName "LocalLLMChat.exe"

[Setup]
AppId={{A7F3E5C1-9B4D-4E2A-8C6F-1D2E3B4A5C60}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#MyAppName} Setup
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutDir}
OutputBaseFilename=LocalLLMChat-Setup-{#AppVersion}
SetupIconFile=..\qwen.ico
UninstallDisplayIcon={app}\qwen.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
; 纯当前用户安装：不请求管理员权限，装到 %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\qwen.ico"; Comment: "{#MyAppNameZh}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\qwen.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
