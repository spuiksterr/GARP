"""Les tests tournent sur le jeu d'essai versionné (tests/jeu_essai/), sans réseau ni données personnelles.

Le jeu est copié dans un dossier temporaire (les tests peuvent écrire sans l'abîmer) que désigne PF_DOSSIER,
avant toute importation de `pf`. Pour tester sur les données réelles du poste : PF_TESTS_REELS=1.
"""
import atexit
import os
import shutil
import socket
import tempfile
from pathlib import Path

import pytest

JEU_ESSAI = Path(__file__).resolve().parent / "jeu_essai"
REELS = os.environ.get("PF_TESTS_REELS") == "1"

if not REELS:
    _tmp = Path(tempfile.mkdtemp(prefix="pf_essai_"))
    shutil.copytree(JEU_ESSAI, _tmp / "donnees")
    os.environ["PF_DOSSIER"] = str(_tmp / "donnees")
    os.environ.pop("PF_PROFIL", None)
    atexit.register(shutil.rmtree, _tmp, ignore_errors=True)


@pytest.fixture(autouse=True)
def sans_reseau(monkeypatch):
    """Toute connexion hors de la machine échoue : un test qui dépend du réseau doit le simuler."""
    if REELS:
        return
    connect, create_connection = socket.socket.connect, socket.create_connection
    locales = ("127.0.0.1", "::1", "localhost")

    def _locale(adresse) -> bool:
        return isinstance(adresse, tuple) and adresse[0] in locales

    def connect_local(sock, adresse, *args, **kwargs):
        if not _locale(adresse):
            raise OSError(f"réseau coupé pendant les tests : {adresse}")
        return connect(sock, adresse, *args, **kwargs)

    def create_connection_local(adresse, *args, **kwargs):
        if not _locale(adresse):
            raise OSError(f"réseau coupé pendant les tests : {adresse}")
        return create_connection(adresse, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect_local)
    monkeypatch.setattr(socket, "create_connection", create_connection_local)
