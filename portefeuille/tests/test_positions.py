"""Photo du portefeuille : remplacée à chaque import, valorisée au dernier cours, journal en secours."""
import pytest

from pf import positions


@pytest.fixture
def photo_isolee(tmp_path, monkeypatch):
    monkeypatch.setattr(positions, "POSITIONS_CSV", tmp_path / "positions.csv")
    return tmp_path / "positions.csv"


def test_sans_photo_le_journal_sert_de_depart(photo_isolee):
    p = positions.photo()  # le jeu d'essai a un journal (ASML, Air Liquide, Microsoft, Costco)
    assert {"ASML.AS", "AI.PA", "MSFT", "COST"} <= set(p["ticker"])
    assert positions.date_photo() is None


def test_chaque_import_remplace_la_photo(photo_isolee):
    from datetime import date

    n = positions.enregistrer([{"ticker": "MSFT", "compte": "CTO", "quantite": 4},
                               {"ticker": "MSFT", "compte": "CTO", "quantite": 1},
                               {"ticker": "AI.PA", "compte": "PEA", "quantite": 10},
                               {"ticker": "", "compte": "PEA", "quantite": 3},
                               {"ticker": "COST", "compte": "CTO", "quantite": 0}], jour=date(2026, 11, 22))
    assert n == 2
    p = positions.photo().set_index("ticker")
    assert p.loc["MSFT", "quantite"] == 5 and p.loc["AI.PA", "compte"] == "PEA"
    assert positions.date_photo() == "2026-11-22"
    positions.enregistrer([{"ticker": "ASML.AS", "compte": "PEA", "quantite": 2}])
    assert list(positions.photo()["ticker"]) == ["ASML.AS"]  # l'ancienne photo est remplacée, pas complétée


def test_positions_valorisees_en_euros(photo_isolee):
    positions.enregistrer([{"ticker": "MSFT", "compte": "CTO", "quantite": 4},
                           {"ticker": "AI.PA", "compte": "PEA", "quantite": 10}])
    p = positions.positions()
    assert set(p.columns) >= {"compte", "ticker", "quantite", "cours_eur", "valeur_eur", "poids"}
    assert (p["valeur_eur"] > 0).all() and p["poids"].sum() == pytest.approx(1)
    assert p["valeur_eur"].is_monotonic_decreasing
