[Setup]
AppId={{35063ED7-9DB3-45CD-BE74-BFAF9F15BBE9}
AppName=JAD Print
AppVersion=0.1.0
AppPublisher=JAD
DefaultDirName={localappdata}\Programs\JAD Print
DefaultGroupName=JAD Print
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=JADPrint-Instalador-0.1.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\JADPrint.exe
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear accesos directos en el escritorio"; Flags: unchecked
Name: "startupagent"; Description: "Iniciar el agente de impresión al entrar a Windows (después de vincular esta PC)"; Flags: unchecked

[Files]
Source: "..\.build\package\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Consola administrador"; Filename: "{app}\JADPrint.exe"; Parameters: "hub"
Name: "{group}\Agente de impresión"; Filename: "{app}\JADPrint.exe"; Parameters: "agent"
Name: "{group}\Desinstalar JAD Print"; Filename: "{uninstallexe}"
Name: "{autodesktop}\JAD Print - Consola"; Filename: "{app}\JADPrint.exe"; Parameters: "hub"; Tasks: desktopicon
Name: "{autodesktop}\JAD Print - Agente"; Filename: "{app}\JADPrint.exe"; Parameters: "agent"; Tasks: desktopicon
Name: "{userstartup}\JAD Print - Agente"; Filename: "{app}\JADPrint.exe"; Parameters: "agent"; Tasks: startupagent

[Run]
Filename: "{app}\JADPrint.exe"; Description: "Abrir JAD Print"; Flags: nowait postinstall skipifsilent
