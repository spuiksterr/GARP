"""Version installée de l'outil : import d'un portefeuille, archive des données de la nuit et son installation."""
import json
import zipfile

import pandas as pd
import pytest

from pf import autonome, export_outil
from pf import import_portefeuille as imp
from pf.config import CONFIG_DIR, DATA_DIR

VALEURS = pd.DataFrame({
    "nom": ["Air Liquide", "LVMH Moët Hennessy Louis Vuitton", "Alphabet", "Global X Uranium UCITS ETF", "American Airlines", "Airbus"],
    "pays": ["France", "France", "États-Unis", "Irlande", "États-Unis", "France"],
    "fonds": [False, False, False, True, False, False],
}, index=pd.Index(["AI.PA", "MC.PA", "GOOGL", "NUKL.DE", "AAL", "AIR.PA"], name="ticker"))


@pytest.mark.parametrize("brut, attendu", [
    ("1 234,56 €", 1234.56), ("1,234.56", 1234.56), ("34,5 %", 34.5), ("1’234.5", 1234.5),
    ("(12,5)", -12.5), ("1.234.567", 1234567), ("Alphabet", None), ("", None),
])
def test_lecture_des_nombres(brut, attendu):
    assert imp.lire_nombre(brut) == attendu


def test_export_de_courtier_avec_isin_et_montants():
    texte = ("Compte PEA n° 123\n"
             "Libellé;ISIN;Quantité;Cours;Montant (EUR);+/- value\n"
             "AIR LIQUIDE;FR0000120073;10;180,50;1 805,00;+120,00\n"
             "LVMH MOET HENNESSY;FR0000121014;2;650,00;1 300,00;-50,00\n"
             "Liquidités;;;;95,00;\n"
             "Total;;;;3 200,00;\n")
    r = imp.importer(texte, VALEURS)
    assert [li.ticker for li in r.lignes] == ["AI.PA", "MC.PA", None]
    assert r.lignes[1].confiance == imp.Confiance.PROBABLE  # nom proche, à vérifier par l'utilisateur
    assert r.lignes[2].ignoree  # liquidités écartées d'office
    assert r.methode == "poids ou montants du fichier"
    assert r.lignes[0].poids == pytest.approx(1805 / 3105 * 100)
    assert sum(li.poids for li in r.lignes) == pytest.approx(100)


def test_liste_tapee_a_la_main_et_ticker_sans_place():
    r = imp.importer("Alphabet 20\nAir Liquide 12\nNUKL.DE 5", VALEURS)
    assert [li.ticker for li in r.lignes] == ["GOOGL", "AI.PA", "NUKL.DE"]
    assert all(li.confiance == imp.Confiance.SURE for li in r.lignes)
    # « AI » sans place de cotation : départagé par le pays de l'ISIN.
    r = imp.importer("Ticker;ISIN;Poids\nAI;FR0000120073;50\nAIR;NL0000235190;50", VALEURS)
    assert r.lignes[0].ticker == "AI.PA"


def test_un_fonds_ne_se_confond_pas_avec_une_societe():
    r = imp.importer("Global X Uranium UCITS ETF;10\nAmerican Airlines Group;5", VALEURS)
    assert [li.ticker for li in r.lignes] == ["NUKL.DE", "AAL"]


def test_quantites_et_cours_en_euros_puis_correspondances_retenues():
    r = imp.importer("Nom;Quantité\nAlphabet;10\nAir Liquide;5", VALEURS, cours_eur={"GOOGL": 150.0, "AI.PA": 180.0})
    assert r.methode == "quantités × derniers cours"
    assert r.lignes[0].poids == pytest.approx(1500 / 2400 * 100)
    r = imp.importer("Ma société préférée 10", VALEURS, correspondances={imp.normaliser("Ma société préférée"): "MC.PA"})
    assert r.lignes[0].ticker == "MC.PA" and r.lignes[0].confiance == imp.Confiance.SURE


def test_composition_modifiee_dans_l_outil():
    from pf.portfolio import nouvelle_composition

    existant = pd.DataFrame({"ticker": ["AI.PA", "MSFT"], "nom": ["Air Liquide", "Microsoft"], "enveloppe": ["PEA", "CTO"],
                             "poche": ["Cœur", "Cœur"], "conviction": ["2", "1"], "poids_cible": ["50", "50"],
                             "these": ["Gaz industriels", "Cloud"], "risque_principal": ["", ""],
                             "condition_vente": ["", ""], "alternative": ["", ""]}).set_index("ticker")
    lignes = [("AI.PA", "PEA", "Cœur", 30.0), ("GOOGL", "CTO", "", 20.0), ("AI.PA", "PEA", "Cœur", 10.0),
              (None, "CTO", "Cœur", 5.0), ("MC.PA", "PEA", "Cœur", 0.0)]
    m = nouvelle_composition(existant, lignes, {"GOOGL": "Alphabet"}).set_index("ticker")
    assert list(m.index) == ["AI.PA", "GOOGL"]  # MSFT retirée, ligne sans valeur et poids nul ignorés
    assert m.loc["AI.PA", "poids_cible"] == pytest.approx(66.67) and m.loc["GOOGL", "poids_cible"] == pytest.approx(33.33)
    assert m.loc["AI.PA", "these"] == "Gaz industriels" and m.loc["GOOGL", "nom"] == "Alphabet"
    assert m.loc["GOOGL", "poche"] == "Cœur"
    with pytest.raises(ValueError):
        nouvelle_composition(existant, [("AI.PA", "PEA", "Cœur", 0.0)])


def _classeur(feuilles: dict[str, list[list]]) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for nom, lignes in feuilles.items():
        ws = wb.create_sheet(nom)
        for ligne in lignes:
            ws.append(ligne)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def test_classeur_excel_feuilles_de_positions():
    from datetime import date

    octets = _classeur({
        "Synthèse": [["Portefeuille au", date(2026, 11, 20)], ["Total", 3105.0]],
        "PEA": [["Compte PEA"], [], ["Libellé", "ISIN", "Quantité", "Montant (EUR)", "Poids"],
                ["AIR LIQUIDE", "FR0000120073", 10, 1805.0, 0.5813], ["Liquidités", None, None, 95.0, 0.0306]],
        "CTO": [["Nom", "Ticker", "Valorisation"], ["Alphabet Inc. Class A", "GOOGL", 1500.25],
                ["Global X Uranium UCITS ETF", "NUKL.DE", 0.00001]],
    })
    assert imp.est_classeur(octets)
    textes = imp.textes_fichier(octets)
    assert len(textes) == 2  # la feuille de synthèse, sans en-tête de positions, est écartée
    r = imp.importer(textes, VALEURS)
    assert [li.ticker for li in r.lignes] == ["AI.PA", None, "GOOGL", "NUKL.DE"]
    assert r.lignes[1].ignoree  # liquidités
    assert r.lignes[0].taille == pytest.approx(0.5813)  # poids au format pourcentage d'Excel : une fraction
    assert r.lignes[3].taille == pytest.approx(0.00001)  # sans notation scientifique perdue en route


def test_formats_de_fichier_refuses():
    with pytest.raises(ValueError, match="xls"):
        imp.textes_fichier(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    with pytest.raises(ValueError, match="illisible"):
        imp.textes_fichier(b"PK\x03\x04 pas un vrai classeur")
    assert imp.textes_fichier("Alphabet;20,5".encode("cp1252")) == ["Alphabet;20,5"]


def test_composition_enregistree_garde_les_theses():
    r = imp.importer("Alphabet 60\nAir Liquide 30\nAlphabet 10", VALEURS)  # doublon de deux comptes
    existant = pd.DataFrame({"ticker": ["AI.PA"], "nom": ["Air Liquide"], "enveloppe": ["PEA"], "poche": ["Cœur"],
                             "conviction": ["2"], "poids_cible": ["25"], "these": ["Gaz industriels"],
                             "risque_principal": [""], "condition_vente": [""], "alternative": [""]})
    m = imp.lignes_modele(r, existant.set_index("ticker"), "CTO", {"GOOGL": "Alphabet"}).set_index("ticker")
    assert m.loc["GOOGL", "poids_cible"] == pytest.approx(70)
    assert m.loc["GOOGL", "enveloppe"] == "CTO" and m.loc["GOOGL", "nom"] == "Alphabet"
    assert m.loc["AI.PA", "these"] == "Gaz industriels" and m.loc["AI.PA", "enveloppe"] == "PEA"


def _archive(chemin, contenu: dict[str, bytes]):
    with zipfile.ZipFile(chemin, "w") as z:
        for nom, octets in contenu.items():
            z.writestr(nom, octets)
    return chemin


def test_installation_de_l_archive_epargne_les_fichiers_personnels(tmp_path):
    dossier = tmp_path / "donnees"
    (dossier / "config").mkdir(parents=True)
    (dossier / "data").mkdir()
    (dossier / "config" / "strategie.json").write_text("{\"mienne\": 1}", encoding="utf-8")
    (dossier / "data" / "transactions.csv").write_text("journal", encoding="utf-8")
    zip_path = _archive(tmp_path / "a.zip", {
        "config/univers.csv": b"ticker;nom\n", "config/strategie.json": b"{}",
        "data/cache/indicateurs.parquet": b"x", "data/historique/scores.parquet": b"y"})
    assert autonome.installer_archive(zip_path, dossier) == 3
    assert (dossier / "config" / "univers.csv").read_bytes() == b"ticker;nom\n"
    assert (dossier / "config" / "strategie.json").read_text(encoding="utf-8") == "{\"mienne\": 1}"
    assert (dossier / "data" / "transactions.csv").read_text(encoding="utf-8") == "journal"
    assert not [p for p in dossier.iterdir() if p.name.startswith(".maj-")]  # dossier temporaire effacé


@pytest.mark.parametrize("intrus", ["profil/portefeuille_modele.csv", "data/transactions.csv",
                                    "data/cache/../../evasion.txt"])
def test_archive_refusee_hors_des_donnees_publiques(tmp_path, intrus):
    zip_path = _archive(tmp_path / "a.zip", {"data/cache/indicateurs.parquet": b"x", intrus: b"!"})
    with pytest.raises(ValueError):
        autonome.installer_archive(zip_path, tmp_path / "donnees")
    assert not (tmp_path / "donnees" / "data" / "cache" / "indicateurs.parquet").exists()


def test_export_de_l_archive_sans_donnee_personnelle(tmp_path):
    chemin = export_outil.exporter(tmp_path)
    with zipfile.ZipFile(chemin) as z:
        noms = z.namelist()
    assert "config/univers.csv" in noms
    assert any(n.startswith("data/cache/") for n in noms)
    assert all(n.startswith(autonome.PREFIXES) for n in noms)
    assert not any("transactions" in n or n.startswith("profil/") for n in noms)
    assert len([f for f in export_outil.fichiers() if f.is_relative_to(CONFIG_DIR)]) == len(list(CONFIG_DIR.glob("*")))
    assert DATA_DIR.exists()


def test_donnees_de_la_nuit_en_arriere_plan(tmp_path, monkeypatch):
    """Recherche et téléchargement dans un fil à part, installation seulement à la demande."""
    archive = {"id": 7, "taille": 10, "date": "2026-11-19T00:18:59Z"}
    source = _archive(tmp_path / "source.zip", {"data/cache/indicateurs.parquet": b"x", "config/univers.csv": b"u"})
    monkeypatch.setattr(autonome, "archive_distante", lambda j: archive)
    monkeypatch.setattr(autonome, "derniere_version", lambda j: {"numero": 99})
    monkeypatch.setattr(autonome, "etat_local", lambda: {"archive": "2026-11-18T00:00:00Z"})

    def faux_telechargement(chemin, jeton_, vers, taille, progression=None):
        progression(0.5)
        vers.write_bytes(source.read_bytes())

    monkeypatch.setattr(autonome, "_telecharger", faux_telechargement)
    # Un poste à part : l'installation ne doit pas toucher au jeu d'essai partagé par les autres tests.
    from pf import config

    poste = tmp_path / "poste"
    (poste / "data").mkdir(parents=True)
    (poste / "data" / "transactions.csv").write_text("journal", encoding="utf-8")
    monkeypatch.setattr(config, "DOSSIER", poste)
    monkeypatch.setattr(config, "DATA_DIR", poste / "data")
    tache = autonome.TacheNuit()
    autonome.chercher_en_arriere_plan(tache, "jeton").join(10)
    assert tache.statut == "pret" and tache.version == {"numero": 99} and tache.fichier.exists()
    assert autonome.chercher_en_arriere_plan(autonome.TacheNuit(statut="telechargement"), "j") is None  # déjà en cours
    etat = autonome.installer_en_attente(tache)
    assert etat["archive"] == archive["date"] and tache.statut == "a_jour" and not autonome._fichier_attente().exists()
    assert (poste / "config" / "univers.csv").read_bytes() == b"u"
    assert (poste / "data" / "transactions.csv").read_text(encoding="utf-8") == "journal"  # journal personnel intact
    # Données déjà les dernières : rien à télécharger.
    monkeypatch.setattr(autonome, "etat_local", lambda: {"archive": archive["date"]})
    tache = autonome.TacheNuit()
    autonome.chercher_en_arriere_plan(tache, "jeton").join(10)
    assert tache.statut == "a_jour"


def test_screener_livre_tout_pret_et_son_empreinte(tmp_path, monkeypatch):
    from pf import scoring
    from pf.config import load_strategy

    chemin = export_outil.exporter(tmp_path)
    with zipfile.ZipFile(chemin) as z:
        assert {"data/cache/screener.parquet", "data/cache/screener.meta.json"} <= set(z.namelist())
    strategie = load_strategy()
    pret = scoring.screener_prepare(strategie)
    pd.testing.assert_frame_equal(pret, scoring.build_screener(strategy=strategie))
    # Stratégie changée sur le poste : le screener livré ne vaut plus, il faut le recalculer.
    autre = {**strategie, "poids_piliers": {**strategie["poids_piliers"], "qualite": 99}}
    assert scoring.screener_prepare(autre) is None
    # Indicateurs changés sur le poste (pf homme-cle) : idem.
    monkeypatch.setattr(scoring, "METRICS_PARQUET", tmp_path / "autres_indicateurs.parquet")
    assert scoring.screener_prepare(strategie) is None


def test_preparation_de_la_version_installee(tmp_path, monkeypatch):
    racine = tmp_path / "garp"
    (racine / "config").mkdir(parents=True)
    (racine / "config" / "univers.csv").write_text("livré", encoding="utf-8")
    monkeypatch.setenv("PF_AUTONOME", "0")
    monkeypatch.setenv("PF_DOSSIER", str(tmp_path / "donnees"))
    assert not autonome.preparer(racine)  # pas de marqueur : projet de développement
    (racine / "autonome.json").write_text(json.dumps({"version": 21}), encoding="utf-8-sig")
    (tmp_path / "donnees" / "config").mkdir(parents=True)
    (tmp_path / "donnees" / "config" / "univers.csv").write_text("téléchargé", encoding="utf-8")
    assert autonome.preparer(racine)
    assert autonome.actif()
    assert (tmp_path / "donnees" / "config" / "univers.csv").read_text(encoding="utf-8") == "téléchargé"
    assert (tmp_path / "donnees" / "data").is_dir()


@pytest.mark.parametrize("jeton_, attendu", [(None, None), ("", None), ("abc", "Bearer abc")])
def test_depot_public_lu_sans_jeton(monkeypatch, jeton_, attendu):
    """Dépôt public : sans jeton, aucune en-tête d'autorisation ; avec, jointe à api.github.com seulement."""
    vues = []

    def ouverture(req, timeout):
        vues.append(req)
        return "réponse"

    monkeypatch.setattr(autonome.urllib.request, "urlopen", ouverture)
    assert autonome._ouvrir("/releases", jeton_) == "réponse"
    req = vues[0]
    assert req.full_url == f"https://api.github.com/repos/{autonome.DEPOT}/releases"
    assert req.get_header("Authorization") == attendu
    assert "Authorization" not in req.headers  # en-tête « non redirigée » quand il y en a une
