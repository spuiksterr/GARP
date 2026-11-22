"""Lanceur de la version bureau, sans console (double-clic, raccourci « G.A.R.P » ou version installée)."""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

try:
    # Version installée (autonome.json posé par la construction) : données dans %LOCALAPPDATA%\Climax, avant
    # tout import de pf.config.
    from pf.autonome import preparer

    preparer(RACINE)
    from pf.bureau import ouvrir

    ouvrir()
except Exception as exc:  # pas de console : on affiche l'erreur dans une boîte de dialogue
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, f"G.A.R.P n'a pas pu démarrer :\n\n{exc}", "G.A.R.P", 0x10)
