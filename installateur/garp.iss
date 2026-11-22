; Installateur Windows de G.A.R.P (Inno Setup 6), construit par .github/workflows/app.yml :
;   preparer_outil.ps1 -Sortie <dossier> -Numero <n>, puis ISCC /DNumero=<n> /DSource=<dossier> garp.iss
; Installe l'outil du PC lui-même (Streamlit, celui de lancer.bat) avec son propre Python : rien d'autre à
; installer sur le poste. Installation par utilisateur, sans droits administrateur, dans
; %LOCALAPPDATA%\Programs\G.A.R.P (une installation existante garde son dossier). Les données et le portefeuille
; vont dans %LOCALAPPDATA%\Climax (nom d'origine, gardé pour les données déjà installées, pf/autonome.py) :
; ni une mise à jour ni une désinstallation n'y touchent.

#ifndef Numero
  #define Numero "0"
#endif
#ifndef Source
  #define Source "..\build\garp-pc"
#endif

[Setup]
; Identifiant fixe : ne jamais le changer, sinon les mises à jour s'installeraient à côté de l'ancienne version.
AppId={{C1F39BF6-F0D8-4E0D-AF98-BE0109AFA3AA}
AppName=G.A.R.P
AppVersion=1.0.{#Numero}
AppVerName=G.A.R.P version {#Numero}
AppPublisher=G.A.R.P
AppComments=La croissance, au juste prix.
VersionInfoVersion=1.0.{#Numero}.0
VersionInfoDescription=Installateur de G.A.R.P
DefaultDirName={autopf}\G.A.R.P
DefaultGroupName=G.A.R.P
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=sortie
OutputBaseFilename=GARP-Setup-b{#Numero}
SetupIconFile=..\portefeuille\assets\garp.ico
UninstallDisplayIcon={app}\garp\assets\garp.ico
UninstallDisplayName=G.A.R.P
WizardStyle=modern
WizardImageFile=grande.bmp,grande@2x.bmp
WizardSmallImageFile=petite.bmp,petite@2x.bmp
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
CloseApplications=force
RestartApplications=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[InstallDelete]
; Version précédente remplacée en entier (fichiers disparus compris), dossier du code de l'ancien nom compris.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\garp"
Type: filesandordirs; Name: "{app}\climax"
; Anciennes versions de l'application Flutter pour Windows (jusqu'à la construction 20).
Type: files; Name: "{app}\climax.exe"
Type: files; Name: "{app}\*.dll"
Type: filesandordirs; Name: "{app}\data"
Type: files; Name: "{localappdata}\Climax\outil.json"
; Raccourcis de l'ancien nom (Climax), remplacés par ceux de G.A.R.P.
Type: files; Name: "{autoprograms}\Climax.lnk"
Type: files; Name: "{autodesktop}\Climax.lnk"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\G.A.R.P"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\garp\GARP.pyw"""; \
  WorkingDir: "{app}\garp"; IconFilename: "{app}\garp\assets\garp.ico"; AppUserModelID: "GARP.GARP"; \
  Comment: "La croissance, au juste prix."
Name: "{autodesktop}\G.A.R.P"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\garp\GARP.pyw"""; \
  WorkingDir: "{app}\garp"; IconFilename: "{app}\garp\assets\garp.ico"; AppUserModelID: "GARP.GARP"; \
  Tasks: bureau

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\garp\GARP.pyw"""; WorkingDir: "{app}\garp"; \
  Description: "Lancer G.A.R.P"; Flags: nowait postinstall skipifsilent
; Mise à jour lancée depuis G.A.R.P en silencieux : on le rouvre.
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\garp\GARP.pyw"""; WorkingDir: "{app}\garp"; \
  Flags: nowait; Check: WizardSilent

[UninstallDelete]
; Fichiers compilés créés à l'usage dans le dossier d'installation.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\garp"
Type: filesandordirs; Name: "{app}\climax"
