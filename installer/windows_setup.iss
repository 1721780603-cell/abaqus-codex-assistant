#ifndef StageDir
  #error StageDir must be supplied by build_windows_setup.ps1
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by build_windows_setup.ps1
#endif
#ifndef AppVersion
  #define AppVersion "0.2.2-alpha"
#endif
#ifndef SetupBaseName
  #define SetupBaseName "AbaqusCodexAssistant-Setup-0.2.2-alpha-x64"
#endif
#ifndef ReleaseSerial
  #define ReleaseSerial "00000002000210001"
#endif

[Setup]
AppId={{DCC225A8-53D3-4EC4-9A46-03532CECB5C4}
AppName=Abaqus Codex Assistant
AppVersion={#AppVersion}
AppPublisher=1721780603-cell and contributors
AppPublisherURL=https://github.com/1721780603-cell/abaqus-codex-assistant
AppSupportURL=https://github.com/1721780603-cell/abaqus-codex-assistant/issues
AppUpdatesURL=https://github.com/1721780603-cell/abaqus-codex-assistant/releases
DefaultDirName={localappdata}\Programs\AbaqusCodexAssistant
DefaultGroupName=Abaqus Codex Assistant
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#SetupBaseName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Abaqus Codex Assistant
LicenseFile={#StageDir}\LICENSE
SetupLogging=yes

[Registry]
Root: HKCU; Subkey: "Software\1721780603-cell\AbaqusCodexAssistant"; ValueType: string; ValueName: "ReleaseSerial"; ValueData: "{#ReleaseSerial}"; Flags: uninsdeletekey

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Abaqus Codex Assistant"; Filename: "{app}\AbaqusCodexAssistant.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Abaqus Codex Assistant"; Filename: "{app}\AbaqusCodexAssistant.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AbaqusCodexAssistant.exe"; WorkingDir: "{app}"; Description: "Launch Abaqus Codex Assistant"; Flags: nowait postinstall skipifsilent

[Code]
function IsInsideOrSame(const CandidatePath, RootPath: String): Boolean;
var
  CandidateValue: String;
  RootValue: String;
begin
  CandidateValue := AddBackslash(ExpandFileName(CandidatePath));
  RootValue := AddBackslash(ExpandFileName(RootPath));
  Result := CompareText(Copy(CandidateValue, 1, Length(RootValue)), RootValue) = 0;
end;

function PathsOverlap(const FirstPath, SecondPath: String): Boolean;
begin
  Result := IsInsideOrSame(FirstPath, SecondPath) or
    IsInsideOrSame(SecondPath, FirstPath);
end;

function InitializeSetup(): Boolean;
var
  InstalledSerial: String;
begin
  Result := True;
  if RegQueryStringValue(
    HKCU,
    'Software\1721780603-cell\AbaqusCodexAssistant',
    'ReleaseSerial',
    InstalledSerial
  ) and (CompareText(InstalledSerial, '{#ReleaseSerial}') > 0) then
  begin
    MsgBox(
      'A newer Abaqus Codex Assistant is already installed. Uninstall it before installing this older version.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  CodexHome: String;
  SkillTarget: String;
  PluginTarget: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    Exit;
  CodexHome := GetEnv('CODEX_HOME');
  if CodexHome = '' then
    CodexHome := ExpandConstant('{userprofile}\.codex');
  SkillTarget := AddBackslash(CodexHome) + 'skills\abaqus-modeling-guide';
  PluginTarget := ExpandConstant('{userprofile}\abaqus_plugins\safe_material_action');
  if PathsOverlap(WizardDirValue, SkillTarget) or
    PathsOverlap(WizardDirValue, PluginTarget) then
  begin
    MsgBox(
      'Choose an application folder outside the Codex Skill and Abaqus plug-in folders.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;

function RunIntegration(const Arguments: String; var ResultCode: Integer): Boolean;
begin
  Result := Exec(
    ExpandConstant('{app}\runtime\python.exe'),
    '-I ' + Arguments,
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Started: Boolean;
  DataRoot: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  DataRoot := ExpandConstant('{localappdata}\AbaqusCodexAssistant');
  Started := RunIntegration(
    '-m abaqus_codex integration-setup --yes --data-root "' + DataRoot + '"',
    ResultCode
  );
  if (not Started) or (ResultCode <> 0) then
  begin
    Log(Format('User integration setup failed (started=%d, exit=%d).', [Ord(Started), ResultCode]));
    if not WizardSilent then
      MsgBox(
        'Codex/Abaqus user integration failed, so Setup cannot complete. ' +
        'No model files were changed.',
        mbError, MB_OK
      );
    RaiseException('Abaqus Codex Assistant user integration failed.');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  Started: Boolean;
  Choice: Integer;
  DataRoot: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  while True do
  begin
    DataRoot := ExpandConstant('{localappdata}\AbaqusCodexAssistant');
    Started := RunIntegration(
      '-m abaqus_codex integration-remove --yes --data-root "' + DataRoot + '"',
      ResultCode
    );
    if Started and (ResultCode = 0) then
      Exit;
    Log(Format('User integration removal failed (started=%d, exit=%d).', [Ord(Started), ResultCode]));
    if UninstallSilent then
      Abort;
    Choice := MsgBox(
      'Codex/Abaqus user integration could not be removed. Retry, abort uninstall, ' +
      'or choose Ignore to remove only the core application and leave the integration in place.',
      mbError, MB_ABORTRETRYIGNORE
    );
    if Choice = IDIGNORE then
      Exit;
    if Choice <> IDRETRY then
      Abort;
  end;
end;
