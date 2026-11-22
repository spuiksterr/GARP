"""Version mobile : l'application du PC, ouverte depuis le téléphone par le réseau privé Tailscale (DEC-1).

Le serveur Streamlit reste réservé à cet ordinateur (localhost). `tailscale serve` le relaie en HTTPS sur le
réseau privé (« tailnet ») : seuls vos appareils connectés à votre compte Tailscale y accèdent, de n'importe où,
sans ouvrir de port sur la box. Le PC doit être allumé et l'application lancée (fenêtre G.A.R.P ou lancer.bat).

Mise en place, une fois : installer Tailscale sur le PC et le téléphone, s'y connecter avec le même compte,
puis `pf mobile`. Sur le téléphone : ouvrir l'adresse affichée, puis « Ajouter à l'écran d'accueil ».
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

PORT = 8501
CHEMINS = [Path(r"C:\Program Files\Tailscale\tailscale.exe"), Path("/usr/bin/tailscale"),
           Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")]


def executable() -> str | None:
    trouve = shutil.which("tailscale")
    return trouve or next((str(p) for p in CHEMINS if p.exists()), None)


def _tailscale(*args: str) -> subprocess.CompletedProcess:
    exe = executable()
    if not exe:
        raise RuntimeError("Tailscale n'est pas installé : https://tailscale.com/download (gratuit pour un usage personnel)")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", timeout=60, **options)


def adresse(statut: dict) -> str | None:
    """Adresse HTTPS de ce PC sur le réseau privé, d'après `tailscale status --json` (None si déconnecté)."""
    if statut.get("BackendState") != "Running":
        return None
    nom = (statut.get("Self") or {}).get("DNSName", "").rstrip(".")
    return f"https://{nom}" if nom else None


def statut() -> dict:
    r = _tailscale("status", "--json")
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {}


def activer(port: int = PORT) -> str:
    """Relaie l'application locale sur le réseau privé ; renvoie l'adresse à ouvrir sur le téléphone."""
    url = adresse(statut())
    if not url:
        raise RuntimeError("Tailscale n'est pas connecté : ouvrez Tailscale (icône près de l'horloge) et "
                           "connectez-vous, avec le même compte que sur le téléphone")
    r = _tailscale("serve", "--bg", str(port))
    if r.returncode != 0:
        raise RuntimeError(f"tailscale serve a échoué : {(r.stderr or r.stdout).strip()[:300]}")
    return url


def desactiver() -> None:
    r = _tailscale("serve", "reset")
    if r.returncode != 0:
        raise RuntimeError(f"tailscale serve reset a échoué : {(r.stderr or r.stdout).strip()[:300]}")
