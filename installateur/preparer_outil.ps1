# Assemble la version installée de l'outil du PC (Streamlit), sans rien demander au poste de l'utilisateur :
#   <Sortie>\python : Python 3.12 et les bibliothèques de portefeuille/requirements.txt (sans les outils de test) ;
#   <Sortie>\garp : le code (pf, vues, app.py, GARP.pyw), le thème, la configuration livrée, autonome.json.
# Appelé par .github/workflows/app.yml sur un serveur Windows, après actions/setup-python. Vérifie ensuite que
# le serveur de l'outil démarre et répond.
param(
    [string]$Sortie = "build\garp-pc",
    [int]$Numero = 0
)
$ErrorActionPreference = "Stop"
$racine = (Resolve-Path "$PSScriptRoot\..").Path
$source = Join-Path $racine "portefeuille"
if (Test-Path $Sortie) { Remove-Item $Sortie -Recurse -Force }
New-Item -ItemType Directory -Force $Sortie | Out-Null
$Sortie = (Resolve-Path $Sortie).Path
$python = Join-Path $Sortie "python"
$code = Join-Path $Sortie "garp"

# 1. Python : copie de l'installation du serveur, sans tests, éditeur, Tk ni fichiers de développement.
$pyDir = Split-Path (Get-Command python).Source
$exclus = "Lib\test", "Lib\idlelib", "Lib\tkinter", "Lib\turtledemo", "Lib\site-packages", "tcl", "Tools", "Doc",
          "include", "libs", "Scripts" | ForEach-Object { Join-Path $pyDir $_ }
robocopy $pyDir $python /E /XD @exclus /XF *.pdb /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "copie de Python impossible ($LASTEXITCODE)" }
$py = Join-Path $python "python.exe"
& $py -m ensurepip --default-pip | Out-Null

# 2. Bibliothèques, aux versions figées du projet (sans pytest).
$exigences = Join-Path $env:RUNNER_TEMP "exigences.txt"
Get-Content (Join-Path $source "requirements.txt") | Where-Object { $_ -notmatch '^\s*pytest' } |
    Set-Content $exigences -Encoding utf8
& $py -m pip install --disable-pip-version-check --no-warn-script-location -q -r $exigences
if ($LASTEXITCODE -ne 0) { throw "installation des bibliothèques impossible" }
& $py -m pip uninstall -y -q pip | Out-Null
# Tests embarqués des grosses bibliothèques : inutiles à l'usage, une centaine de mégaoctets.
$sp = Join-Path $python "Lib\site-packages"
Get-ChildItem $sp -Directory -Recurse -Filter tests |
    Where-Object { $_.FullName -match '\\site-packages\\(pandas|numpy|scipy|pyarrow)\\' } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 3. Code de l'outil.
New-Item -ItemType Directory -Force $code | Out-Null
foreach ($d in "pf", "vues", ".streamlit", "static", "config", "profil.exemple") {
    robocopy (Join-Path $source $d) (Join-Path $code $d) /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copie de $d impossible" }
}
New-Item -ItemType Directory -Force (Join-Path $code "assets") | Out-Null
Copy-Item (Join-Path $source "assets\garp.png"), (Join-Path $source "assets\garp.ico"),
    (Join-Path $source "assets\entete.png") (Join-Path $code "assets")
Copy-Item (Join-Path $source "app.py"), (Join-Path $source "GARP.pyw") $code
# Documents lus par l'interface (page « Méthode et routine »).
New-Item -ItemType Directory -Force (Join-Path $code "docs") | Out-Null
Copy-Item (Join-Path $source "docs\METHODE.md") (Join-Path $code "docs")
@{ version = $Numero; depot = "spuiksterr/GARP" } | ConvertTo-Json | Set-Content (Join-Path $code "autonome.json") -Encoding utf8
& $py -m compileall -q -j 0 (Join-Path $code "pf") (Join-Path $code "vues") | Out-Null

# 4. Contrôle : l'outil s'importe et son serveur répond, avec des données vides dans un dossier temporaire.
$env:PF_DOSSIER = Join-Path $env:RUNNER_TEMP "garp-essai"
$env:PF_AUTONOME = "1"
& $py -c "import sys; sys.path.insert(0, r'$code'); import pf.ui, pf.bureau, pf.import_portefeuille, webview, clr"
if ($LASTEXITCODE -ne 0) { throw "l'outil ne s'importe pas" }
# Adresse IPv4 explicite, comme la fenêtre de l'outil (pf/bureau.py) : « localhost » peut désigner l'adresse IPv6,
# et le contrôle échouait alors sur un serveur pourtant démarré.
$serveur = Start-Process $py -ArgumentList "-m", "pf.serveur", "app.py", "--server.port", "8599",
    "--server.address", "127.0.0.1", "--server.headless", "true" -WorkingDirectory $code -PassThru -NoNewWindow
$ok = $false
for ($i = 0; $i -lt 120 -and -not $ok; $i++) {
    Start-Sleep -Seconds 1
    try {
        $ok = (Invoke-WebRequest "http://127.0.0.1:8599/_stcore/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200
    } catch { }
}
Stop-Process -Id $serveur.Id -Force -ErrorAction SilentlyContinue
if (-not $ok) { throw "le serveur de l'outil ne répond pas" }
Get-ChildItem $code -Recurse -Directory -Filter __pycache__ | Where-Object { $_.FullName -notmatch '\\(pf|vues)\\' } |
    Remove-Item -Recurse -Force
$taille = (Get-ChildItem $Sortie -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Outil assemblé : {0:N0} Mo dans {1}" -f $taille, $Sortie)
