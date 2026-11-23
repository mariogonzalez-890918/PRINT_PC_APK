[Setup]
AppId={{35063ED7-9DB3-45CD-BE74-BFAF9F15BBE9}
AppName=PRINTER-TAB
AppVersion=0.5.0
AppPublisher=Área de TI GMP
DefaultDirName={localappdata}\Programs\PRINTER-TAB
DefaultGroupName=PRINTER-TAB
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PRINTER-TAB-Instalador-0.5.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\pc\app.ico
UsePreviousGroup=no
UninstallDisplayIcon={app}\PRINTER-TAB.exe
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo PRINTER-TAB en el escritorio"
Name: "startupagent"; Description: "Iniciar el agente de impresión al entrar a Windows (después de vincular esta PC)"; Flags: unchecked

[Files]
Source: "..\.build\package\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PRINTER-TAB"; Filename: "{app}\PRINTER-TAB.exe"
Name: "{group}\Desinstalar PRINTER-TAB"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PRINTER-TAB"; Filename: "{app}\PRINTER-TAB.exe"; Tasks: desktopicon
Name: "{userstartup}\PRINTER-TAB"; Filename: "{app}\PRINTER-TAB.exe"; Parameters: "agent"; Tasks: startupagent

[InstallDelete]
Type: files; Name: "{app}\JADPrint.exe"
Type: files; Name: "{autodesktop}\JAD Print - Consola.lnk"
Type: files; Name: "{autodesktop}\JAD Print - Agente.lnk"
Type: files; Name: "{userstartup}\JAD Print - Agente.lnk"
Type: files; Name: "{userprograms}\JAD Print\Consola administrador.lnk"
Type: files; Name: "{userprograms}\JAD Print\Agente de impresión.lnk"
Type: files; Name: "{userprograms}\JAD Print\Desinstalar JAD Print.lnk"

[Run]
Filename: "{app}\PRINTER-TAB.exe"; Description: "Abrir PRINTER-TAB"; Flags: nowait postinstall skipifsilent
