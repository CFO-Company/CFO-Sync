#define MyAppName "CFO Sync"
#ifndef MyAppVersion
#define MyAppVersion "1.2.1"
#endif
#define MyAppPublisher "CFO Sync"
#define MyAppExeName "CFO-Sync.exe"

[Setup]
AppId={{D4A37F6C-7D4A-4D2D-B57A-0C99C6369E34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\CFO Sync
DefaultGroupName=CFO Sync
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=CFO-Sync-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
Source: "..\dist\CFO-Sync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CFO Sync"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\CFO Sync"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir CFO Sync"; Flags: nowait
