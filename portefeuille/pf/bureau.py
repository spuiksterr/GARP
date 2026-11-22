"""Version bureau : l'application dans sa propre fenêtre (pywebview, moteur Edge WebView2 sous Windows).

`pf bureau`, le raccourci « G.A.R.P » (Climax.pyw, sans console) ou la version installée (pf/autonome.py) :
ouvre aussitôt la fenêtre sur un écran d'attente, démarre le serveur Streamlit en arrière-plan, y branche la
fenêtre dès qu'il répond, et l'arrête quand on la ferme. Si un serveur tourne déjà sur le port (lancé par
lancer.bat ou laissé actif pour le téléphone), la fenêtre s'y branche et le laisse tourner. La version installée
prend un autre port, pour ne jamais se brancher sur l'outil de développement.

La fenêtre est toujours en thème sombre (celui de .streamlit/config.toml), quel que soit le réglage de Windows.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import autonome
from .config import ROOT

PORT = 8501
PORT_AUTONOME = 8517
# Adresse IPv4 explicite : « localhost » peut désigner l'adresse IPv6, et serveur_actif, qui teste
# 127.0.0.1, ne verrait alors jamais le serveur démarré.
HOTE = "127.0.0.1"
TITRE = "G.A.R.P"
ICONE = ROOT / "assets" / "climax.ico"
ENTETE = ROOT / "assets" / "entete.png"  # logo et « G.A.R.P » (composer_icones.py), en tête de l'écran d'ouverture
FOND = "#1a1a19"  # [theme.dark] de .streamlit/config.toml

# Écran d'attente : trois étapes et le temps écoulé. La fenêtre passe d'une étape à l'autre par etape(n) ;
# erreur(texte) remplace les étapes par le message d'échec.
ATTENTE = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><style>
html,body{{height:100%;margin:0;background:{FOND};color:#f0efec;font-family:"Source Sans Pro","Segoe UI",sans-serif}}
body{{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px}}
h1{{margin:0;font-size:22px;font-weight:600}}
ol{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px;min-width:330px}}
li{{display:flex;align-items:center;gap:12px;font-size:16px;color:rgba(240,239,236,.45)}}
li i{{width:18px;height:18px;border-radius:50%;border:2px solid #3a3a37;box-sizing:border-box;flex:none}}
li.en-cours{{color:#f0efec}} li.en-cours i{{border-color:#c98b2e;border-top-color:transparent;animation:t 0.9s linear infinite}}
li.fait{{color:rgba(240,239,236,.7)}} li.fait i{{background:#c98b2e;border-color:#c98b2e}}
@keyframes t{{to{{transform:rotate(360deg)}}}}
small{{color:rgba(240,239,236,.6);font-size:14px}} #erreur{{display:none;max-width:560px;text-align:center}}
</style></head><body><h1>Ouverture de G.A.R.P</h1>
<ol><li id="e1" class="en-cours"><i></i>Démarrage du moteur</li>
<li id="e2"><i></i>Chargement de l'outil et de vos données</li>
<li id="e3"><i></i>Ouverture de l'interface</li></ol>
<small id="temps">0 s</small><p id="erreur"></p>
<script>
const t0 = Date.now();
setInterval(() => {{ document.getElementById("temps").textContent = Math.round((Date.now() - t0) / 1000) + " s"; }}, 500);
function etape(n) {{
  for (let i = 1; i <= 3; i++) {{
    document.getElementById("e" + i).className = i < n ? "fait" : (i === n ? "en-cours" : "");
  }}
}}
function erreur(texte) {{
  document.querySelector("ol").style.display = "none";
  document.querySelector("h1").textContent = "G.A.R.P n'a pas pu démarrer";
  const p = document.getElementById("erreur"); p.textContent = texte; p.style.display = "block";
}}
</script></body></html>"""


def page_attente() -> str:
    """L'écran d'attente, avec le logo et le nom en tête (image intégrée : le serveur ne répond pas encore)."""
    if not ENTETE.exists():
        return ATTENTE
    logo = base64.b64encode(ENTETE.read_bytes()).decode("ascii")
    return ATTENTE.replace("<h1>Ouverture de G.A.R.P</h1>",
                           f'<img src="data:image/png;base64,{logo}" alt="G.A.R.P" style="height:80px">'
                           "<h1>Ouverture en cours</h1>", 1)


def serveur_actif(port: int = PORT) -> bool:
    try:
        with socket.create_connection((HOTE, port), timeout=0.5):
            return True
    except OSError:
        return False


def journal_serveur() -> Path | None:
    """Sortie du serveur de la version installée, pour comprendre un échec au démarrage."""
    return autonome.dossier_local() / "serveur.log" if autonome.actif() else None


def demarrer_serveur(port: int = PORT, attente: float = 180, etape=None) -> subprocess.Popen:
    """Serveur Streamlit sans fenêtre, réservé à cet ordinateur ; rend la main quand il répond. Lancé par
    pf.serveur, qui charge d'abord les modules de l'outil : la première page s'ouvre ensuite sans attendre.
    Au tout premier lancement, Windows lit chaque fichier pour la première fois : une minute ou plus."""
    python = sys.executable.replace("pythonw.exe", "python.exe")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    journal = journal_serveur()
    sortie = subprocess.DEVNULL
    if journal is not None:
        journal.parent.mkdir(parents=True, exist_ok=True)
        sortie = open(journal, "w", encoding="utf-8")  # noqa: SIM115 (gardé ouvert par le serveur)
    proc = subprocess.Popen(
        [python, "-m", "pf.serveur", str(ROOT / "app.py"), "--server.port", str(port),
         "--server.address", HOTE, "--server.headless", "true"],
        cwd=ROOT, stdout=sortie, stderr=subprocess.STDOUT, **options)
    if etape:
        etape(2)
    fin = time.time() + attente
    while time.time() < fin:
        if proc.poll() is not None:
            ou = f" (détail dans {journal})" if journal else " (lancez lancer.bat pour voir l'erreur)"
            raise RuntimeError(f"le serveur de l'application s'est arrêté au démarrage{ou}")
        if serveur_actif(port):
            return proc
        time.sleep(0.3)
    proc.terminate()
    raise RuntimeError(f"le serveur ne répond pas après {attente:.0f} secondes")


def _barre_de_titre_sombre(fenetre) -> None:
    """Barre de titre Windows sombre, assortie au contenu, même si Windows est réglé en clair."""
    try:
        import ctypes

        poignee = fenetre.native.Handle.ToInt32()
        oui = ctypes.c_int(1)
        # 20 : DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 2004 et suivants, Windows 11).
        ctypes.windll.dwmapi.DwmSetWindowAttribute(poignee, 20, ctypes.byref(oui), ctypes.sizeof(oui))
    except Exception:  # autre système, ou pywebview sans fenêtre native : barre de titre par défaut
        pass


def _identite_windows() -> None:
    """G.A.R.P, et non Python, dans la barre des tâches (même identifiant que le raccourci de l'installateur)."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Climax.Climax")
    except Exception:
        pass


def ouvrir(port: int | None = None) -> None:
    """Ouvre la fenêtre de l'application ; bloque jusqu'à sa fermeture."""
    import webview

    port = port or (PORT_AUTONOME if autonome.actif() else PORT)
    _identite_windows()
    # Thème sombre imposé : le moteur Edge de la fenêtre se croit en mode sombre, et Streamlit applique
    # [theme.dark] de .streamlit/config.toml. Cette variable remplace les options de pywebview : on reprend la sienne.
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--force-dark-mode --disable-features=ElasticOverscroll"
    serveur: list[subprocess.Popen] = []
    fenetre = webview.create_window(TITRE, html=page_attente(), width=1440, height=920, min_size=(900, 600),
                                    background_color=FOND)
    fenetre.events.shown += lambda: _barre_de_titre_sombre(fenetre)

    def etape(n: int) -> None:
        try:
            fenetre.evaluate_js(f"etape({n})")
        except Exception:  # page pas encore prête : l'étape suivante corrigera l'affichage
            pass

    def brancher() -> None:
        try:
            if not serveur_actif(port):
                serveur.append(demarrer_serveur(port, etape=etape))
            etape(3)
            fenetre.load_url(f"http://{HOTE}:{port}")
        except Exception as exc:
            try:
                fenetre.evaluate_js(f"erreur({json.dumps(str(exc))})")
            except Exception:  # fenêtre fermée entre-temps
                pass

    options = {"storage_path": str(autonome.dossier_local() / "fenetre")} if autonome.actif() else {}
    try:
        # private_mode=False : garde les réglages de l'interface (thème) d'une session à l'autre.
        webview.start(brancher, private_mode=False, icon=str(ICONE) if ICONE.exists() else None, **options)
    finally:
        for proc in serveur:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
