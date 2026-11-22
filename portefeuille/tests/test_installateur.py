"""La version installée (installateur/preparer_outil.ps1) embarque chaque fichier que l'interface lit.

Un oubli ne se voit qu'une fois installé (la page « Méthode et routine » a ainsi planté faute de docs/METHODE.md) :
on relève dans le code les fichiers de assets/, docs/ et static/ lus par l'interface, et l'on vérifie que le script
de construction les copie (dossier entier ou fichier par fichier).
"""
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE.parent / "installateur" / "preparer_outil.ps1"
SOURCES = [RACINE / "app.py", *(RACINE / "vues").glob("*.py"), *(RACINE / "pf").glob("*.py")]
# « "assets" / "entete.png" », « / "docs" / "METHODE.md" », « app/static/polices/Manrope.ttf »…
CHEMIN = re.compile(r'"(assets|docs|static)"\s*/\s*"([^"]+)"')
URL_STATIQUE = re.compile(r'app/(static/[^"\s]+)')


def fichiers_lus() -> set[str]:
    out = set()
    for f in SOURCES:
        for dossier, nom in CHEMIN.findall(f.read_text(encoding="utf-8")):
            out.add(f"{dossier}/{nom}")
    config = (RACINE / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    out |= set(URL_STATIQUE.findall(config))
    return out


def test_chaque_fichier_lu_par_l_interface_est_embarque():
    script = SCRIPT.read_text(encoding="utf-8-sig")
    dossiers = set(re.findall(r'"([\w.]+)"', re.search(r"foreach \(\$d in ([^)]*)\)", script).group(1)))
    fichiers = {c.replace("\\", "/") for c in re.findall(r'Join-Path \$source "([^"]+)"', script)}
    lus = fichiers_lus()
    assert {"docs/METHODE.md", "assets/entete.png", "static/polices/Manrope.ttf"} <= lus
    manquants = [f for f in sorted(lus) if f.split("/")[0] not in dossiers and f not in fichiers]
    assert not manquants, f"lus par l'interface mais absents de la version installée : {manquants}"
    for f in lus:
        assert (RACINE / f).exists(), f
