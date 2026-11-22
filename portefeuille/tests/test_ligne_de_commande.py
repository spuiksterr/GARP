"""Les commandes de lecture de la ligne de commande s'exécutent sur le jeu d'essai, sans réseau (ticket K-04).

Celles qui téléchargent (maj, esef, investisseurs, indices) ou écrivent un fichier (export) ne sont pas lancées.
"""
import pytest

from pf.__main__ import main

COMMANDES = [
    ["contexte", "MSFT", "--hors-ligne"],
    ["contexte", "MC.PA", "--hors-ligne"],
    ["contexte", "NUKL.DE", "--hors-ligne"],
    ["risques"],
    ["idees"],
    ["screener", "--top", "5"],
    ["fiche", "ASML.AS"],
    ["regards", "--top", "5"],
    ["modele"],
    ["construire", "--n", "8"],
    ["suivi"],
    ["apport", "1000", "--compte", "PEA"],
    ["verifier"],
]


@pytest.mark.parametrize("args", COMMANDES, ids=" ".join)
def test_commande(args, capsys):
    main(args)
    sortie = capsys.readouterr().out
    assert sortie.strip(), "aucune sortie"
    assert "Traceback" not in sortie
