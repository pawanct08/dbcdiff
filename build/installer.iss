; ============================================================
;  dbcdiff  –  Inno Setup installer script
;  Produces:  Output\dbcdiff-setup.exe
;
;  Requirements:
;    1. Build the standalone exe first:
;         python -m PyInstaller --onefile --windowed --name dbcdiff ^
;                --add-data "dbcdiff;dbcdiff" dbcdiff/__main__.py
;    2. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
;    3. Open this file in the Inno Setup IDE and click  Build > Compile
;       (or run:  iscc.exe build\installer.iss)
; ============================================================

#define AppName      "dbcdiff"
#define AppVersion   "0.2.0"
#define AppPublisher "C T"
#define AppURL       "https://github.com/pcw1kor/dbcdiff"
#define AppExeName   "dbcdiff.exe"
#define AppExeSrc    "..\dist\dbcdiff.exe"

[Setup]
AppId={{E4B7F2A1-3C9D-4E6B-B0A5-2F8D1C7E9340}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Install to  C:\Program Files\dbcdiff\
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output installer
OutputDir=Output
OutputBaseFilename=dbcdiff-setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

; Require admin so we can write to HKCR (file association)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Wizard appearance
WizardStyle=modern
WizardImageFile=compiler:WizModernImage-IS.bmp
WizardSmallImageFile=compiler:WizModernSmallImage-IS.bmp

; Uninstaller
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}

; Minimum OS: Windows 10
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "{cm:CreateDesktopIcon}";   GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunch";   Description: "Pin to Taskbar (Windows 7+)";                                       Flags: unchecked

[Files]
; Main executable
Source: "{#AppExeSrc}"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\{#AppName}";             Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";   Filename: "{uninstallexe}"

; Desktop (optional task)
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; ── .dbc file-type association ──────────────────────────────────────────────
; Map .dbc extension → logical type key "dbcFile"
Root: HKCR; Subkey: ".dbc";                                     ValueType: string; ValueName: ""; ValueData: "dbcFile";                     Flags: uninsdeletevalue createvalueifdoesntexist

; Friendly name shown in Explorer's "Type" column
Root: HKCR; Subkey: "dbcFile";                                  ValueType: string; ValueName: ""; ValueData: "DBC Network Database File";    Flags: uninsdeletekey

; Default icon  (uses the exe's built-in icon)
Root: HKCR; Subkey: "dbcFile\DefaultIcon";                      ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"",0";   Flags: uninsdeletekey

; ── Shell context-menu verb  "Open with dbcdiff" ────────────────────────────
; Shown when the user right-clicks any .dbc file in Explorer
Root: HKCR; Subkey: "dbcFile\shell\OpenInDbcdiff";              ValueType: string; ValueName: ""; ValueData: "Open with dbcdiff";           Flags: uninsdeletekey
Root: HKCR; Subkey: "dbcFile\shell\OpenInDbcdiff";              ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExeName}"",0"; Flags: uninsdeletekey
Root: HKCR; Subkey: "dbcFile\shell\OpenInDbcdiff\command";      ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" --file-a ""%1"""; Flags: uninsdeletekey

; ── Uninstall: restore Explorer cache ────────────────────────────────────────
; After uninstall, notify the shell so the .dbc association disappears immediately.
; (handled automatically by "uninsdeletekey" / "uninsdeletevalue" flags above)

[Run]
; Offer to launch the app after installation
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Refresh shell icon cache on uninstall so Explorer stops showing the custom icon
Filename: "ie4uinit.exe"; Parameters: "-show"; RunOnceId: "RefreshIcons"

[Code]
// Notify Explorer of shell-association changes during install and uninstall
procedure RefreshShellAssociations();
begin
  // SHChangeNotify(SHCNE_ASSOCCHANGED=0x08000000, SHCNF_IDLIST=0x0000, 0, 0)
  // Easiest portable way in Inno Setup is to run assoc command below
  Exec('cmd.exe', '/c assoc .dbc=dbcFile', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RefreshShellAssociations();
end;
