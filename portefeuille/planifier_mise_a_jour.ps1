# Planifie la mise à jour quotidienne du portefeuille (Planificateur de tâches Windows, utilisateur courant).
# - chaque jour à 6 h 30 ; réveille l'ordinateur s'il est en veille ;
# - si l'heure est manquée (ordinateur éteint, session fermée), elle part dès que possible ;
# - sans fenêtre (pythonw) ; journal dans data\journaux ; complète une fois par semaine, rapide sinon.
# Lancer : clic droit > Exécuter avec PowerShell. Pour la retirer : planifier_mise_a_jour.ps1 -Retirer
param([switch]$Retirer, [string]$Heure = "06:30")
$nom = "Portefeuille - mise a jour"
if ($Retirer) {
    Unregister-ScheduledTask -TaskName $nom -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Tâche « $nom » retirée."
    return
}
$dossier = $PSScriptRoot
$python = Join-Path $dossier ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $python)) { Write-Error "Environnement absent : lancez d'abord installer.bat"; return }
$action = New-ScheduledTaskAction -Execute $python -Argument "-m pf maj --auto" -WorkingDirectory $dossier
$declencheur = New-ScheduledTaskTrigger -Daily -At $Heure
$reglages = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $nom -Action $action -Trigger $declencheur -Settings $reglages -Force `
    -Description "Mise à jour des cours, scores et actualités du portefeuille (complète une fois par semaine)." | Out-Null
Write-Output "Tâche « $nom » planifiée chaque jour à $Heure (réveil de la veille, rattrapage au démarrage)."
