"""Styles d'investisseur (pf/styles.py) : questionnaire, profil, notes, comparaison ; regards hors du score."""
import json

import pandas as pd
import pytest

from pf import backtest_pit as bp
from pf import portfolio as pfo
from pf import prix_achat as pa
from pf import styles as sty
from pf.config import STRATEGIE_JSON, load_strategy
from pf.scoring import build_screener


@pytest.fixture(scope="module")
def sc():
    return build_screener()


def test_chaque_style_a_sa_notation_et_son_backtest():
    assert set(sty.STYLES) == {"qualite", "croissance", "garp", "valeur", "momentum"}
    for s in sty.STYLES.values():
        assert s.notation in pfo.NOTATIONS and s.backtest in bp.METHODES
    # Plus de moyenne des quatre regards comme méthode ; chaque regard reste à part.
    assert "regards" not in pfo.NOTATIONS and {"buffett", "munger", "fisher", "smith"} <= set(pfo.NOTATIONS)
    assert 6 <= len(sty.QUESTIONS) <= 8


def test_chaque_style_peut_etre_propose():
    for cible in sty.STYLES:
        # La réponse qui donne le plus de points au style, à chaque question.
        reponses = {q.cle: max(q.reponses, key=lambda k, q=q: q.reponses[k][1].get(cible, 0)) for q in sty.QUESTIONS}
        p = sty.proposer(reponses)
        assert p.style == cible, (cible, p.points)
        assert p.raisons and sty.STYLES[cible].libelle in sty.explication(p)


def test_sans_reponse_le_style_par_defaut_et_les_hesitations():
    p = sty.proposer({})
    assert p.style == sty.DEFAUT and not p.raisons
    # Deux réponses opposées, à égalité : le second style est signalé.
    p = sty.proposer({"priorite": "decote", "regret": "rate"})
    assert {p.style, p.second} == {"valeur", "croissance"}
    assert "juste derrière" in sty.explication(p)
    # Réponse inconnue : ignorée.
    assert sty.proposer({"priorite": "nimporte"}).points == dict.fromkeys(sty.STYLES, 0)


def test_profil_enregistre(tmp_path, monkeypatch):
    monkeypatch.setattr(sty, "STYLE_JSON", tmp_path / "style.json")
    assert sty.profil() == {} and sty.style_choisi() == sty.DEFAUT
    sty.enregistrer("valeur", {"priorite": "decote"}, "valeur")
    assert sty.style_choisi() == "valeur"
    sty.enregistrer("qualite")  # choix direct : les réponses et la proposition restent
    p = sty.profil()
    assert p["style"] == "qualite" and p["propose"] == "valeur" and p["reponses"] == {"priorite": "decote"}
    with pytest.raises(ValueError):
        sty.enregistrer("regards")
    (tmp_path / "style.json").write_text(json.dumps({"style": "inconnu"}), encoding="utf-8")
    assert sty.style_choisi() == sty.DEFAUT


def test_les_styles_classent_differemment(sc):
    actions = sc[sc["statut"] != "Fonds"]
    notes = {s: sty.note(actions, s) for s in sty.STYLES}
    for n in notes.values():
        assert n.notna().sum() >= 5 and n.dropna().between(0, 101).all()
    assert notes["valeur"].idxmax() != notes["croissance"].idxmax()


def test_le_classement_suit_le_style_et_pas_le_verdict(sc):
    vcfg = load_strategy()["valorisation"]
    sources = dict.fromkeys(sc.index[sc["statut"] == "Éligible"], "Univers")
    sans = pa.tableau(sc, sources, vcfg, 0.09, 0.2)
    note = sty.note(sc[sc["statut"] != "Fonds"], "momentum")
    avec = pa.tableau(sc, sources, vcfg, 0.09, 0.2, note=note)
    # Le prix d'achat et le verdict ne dépendent pas du style.
    assert avec["verdict"].sort_index().equals(sans["verdict"].sort_index())
    assert avec["prix_achat"].sort_index().equals(sans["prix_achat"].sort_index())
    ordre = {v: i for i, v in enumerate(pa.VERDICTS.values())}
    for _, groupe in avec.groupby(avec["verdict"].map(ordre)):
        assert groupe["note_style"].fillna(-1).is_monotonic_decreasing


def test_comparaison_des_styles(sc):
    elig = sc.index[sc["statut"] == "Éligible"]
    verdicts = pd.Series("Au bon prix", index=elig)  # tout au bon prix : seule la tête de classement compte
    choix = sty.retenues(sc, verdicts, part=0.5)
    assert set(choix) == set(sty.STYLES)
    for tickers in choix.values():
        assert tickers and len(tickers) == round(len(elig) * 0.5) and set(tickers) <= set(elig)
    rec = sty.recoupements(choix)
    for s in sty.STYLES:
        lib = sty.STYLES[s].libelle
        assert rec.loc[lib, lib] == len(choix[s])
    assert (rec.values == rec.values.T).all()
    freq = sty.frequence(choix)
    assert freq["nb_styles"].is_monotonic_decreasing and freq["nb_styles"].max() <= len(sty.STYLES)
    t = freq.index[0]
    assert freq.loc[t, "nb_styles"] == sum(t in v for v in choix.values())
    # Aucun verdict admis : rien n'est retenu.
    assert all(not v for v in sty.retenues(sc, pd.Series("À attendre", index=elig)).values())


def test_les_regards_ne_comptent_plus_dans_le_score():
    brut = json.loads(STRATEGIE_JSON.read_text(encoding="utf-8"))
    brut["poids_score"]["regards"] = 1  # ancienne stratégie, gardée par une version installée
    STRATEGIE_JSON.write_text(json.dumps(brut), encoding="utf-8")
    try:
        assert load_strategy()["poids_score"]["regards"] == 0
    finally:
        brut["poids_score"]["regards"] = 0
        STRATEGIE_JSON.write_text(json.dumps(brut, indent=2, ensure_ascii=False), encoding="utf-8")
