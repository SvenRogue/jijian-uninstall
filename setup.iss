; 极简卸载 安装脚本 (Inno Setup 6)
; 编译：iscc setup.iss

#define MyAppName "极简卸载"
#define MyAppNameEn "JiJian Uninstall"
#define MyAppVersion "1.1.0-preview.1"
#define MyAppPublisher "SvenRogue"
#define MyAppExeName "极简卸载.exe"

[Setup]
AppId={{8F3C2A61-7B4E-4D19-9C3A-2E7B45A1D8F0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
LicenseFile=LICENSE
VersionInfoVersion=1.1.0.1
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=极简卸载-安装程序-{#MyAppVersion}
SetupIconFile=app\assets\jijian.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "创建快捷方式"

[Files]
Source: "dist\极简卸载\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "应用卸载与残留审阅"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "应用卸载与残留审阅"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Recovery data and logs remain available after uninstall.
