#define AppVersion "1.2.0"
[Setup]
AppId={{7C9ED44E-FF72-447A-BE2C-84F956C3CDEE}
AppName=Nelsonict AI
AppVersion={#AppVersion}
AppPublisher=Nelsonict Services Limited
DefaultDirName={localappdata}\Programs\NelsonictAI
DefaultGroupName=Nelsonict AI
PrivilegesRequired=lowest
OutputDir=..\..\dist\installers
OutputBaseFilename=Nelsonict-AI-1.2.0-Windows-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
[Files]
Source: "..\..\dist\nelsonict-ai\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Nelsonict AI when I sign in"; Flags: unchecked
[Icons]
Name: "{group}\Nelsonict AI"; Filename: "{app}\nelsonict-ai.exe"
Name: "{userdesktop}\Nelsonict AI"; Filename: "{app}\nelsonict-ai.exe"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NelsonictAI"; ValueData: """{app}\nelsonict-ai.exe"" --service"; Tasks: startup; Flags: uninsdeletevalue
[Run]
Filename: "{app}\nelsonict-ai.exe"; Description: "Open Nelsonict AI"; Flags: nowait postinstall skipifsilent
