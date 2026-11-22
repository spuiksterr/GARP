# Crée les raccourcis « G.A.R.P (projet) » (bureau et menu Démarrer) qui ouvrent l'outil de ce dossier, sans console.
# Nom distinct de « G.A.R.P », le raccourci de la version installée (GARP-Setup), pour que l'un ne remplace pas l'autre.
# Clic droit > « Exécuter avec PowerShell ». Les relancer après avoir déplacé le dossier du projet.
$ici = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $ici ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { Write-Host "Environnement absent : lancez d'abord installer.bat"; exit 1 }
$shell = New-Object -ComObject WScript.Shell
$dossiers = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) ""))
foreach ($d in $dossiers) {
    $lnk = $shell.CreateShortcut((Join-Path $d "G.A.R.P (projet).lnk"))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = '"' + (Join-Path $ici "GARP.pyw") + '"'
    $lnk.WorkingDirectory = $ici
    $lnk.IconLocation = (Join-Path $ici "assets\garp.ico") + ",0"
    $lnk.Description = "G.A.R.P, outil du dossier du projet : la croissance, au juste prix"
    $lnk.Save()
    Write-Host "Raccourci créé : $(Join-Path $d 'G.A.R.P (projet).lnk')"
}
