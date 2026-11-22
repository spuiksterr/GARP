"""Importer son portefeuille : export du courtier, tableau copié ou lignes tapées, puis vérification avant
d'enregistrer les poids cibles (profil/portefeuille_modele.csv). Mêmes règles que l'application (pf/import_portefeuille)."""
import copy
import shutil
from datetime import date

import pandas as pd
import streamlit as st

from pf import import_portefeuille as imp
from pf import positions, ui
from pf.config import (
    MODELE_CSV,
    PROFIL_DIR,
    SECTEUR_FONDS,
    ecrire_json,
    lire_json,
    load_model_portfolio,
    load_universe,
    write_csv_fr,
)

CORRESPONDANCES = PROFIL_DIR / "import_correspondances.json"
HORS = "— hors des données —"
COMPTES = ["PEA", "CTO"]

sc = ui.require_data()
st.title("Importer mon portefeuille")
st.markdown(
    "Reprenez vos lignes depuis l'export de votre courtier (CSV ou classeur Excel), un tableau copié depuis la page "
    "« positions » de son site, ou une simple liste tapée à la main. Vous vérifiez chaque ligne avant d'enregistrer : "
    "les poids obtenus deviennent les **poids cibles** de la page « Composition »."
)

univers = load_universe()
valeurs = univers[univers.index.isin(sc.index)][["nom", "pays", "secteur"]].copy()
valeurs["fonds"] = valeurs["secteur"] == SECTEUR_FONDS
eligibilite = univers["enveloppe"].to_dict() if "enveloppe" in univers.columns else {}


def compte_propose(ticker: str | None) -> str:
    """Compte de la ligne : celui de la composition actuelle, sinon le compte-titres pour une valeur non éligible au
    PEA (action américaine…), sinon le compte par défaut choisi."""
    defaut = st.session_state["import_compte"]
    if not ticker:
        return defaut
    actuel = mp["enveloppe"].get(ticker) if "enveloppe" in mp.columns else None
    if actuel in COMPTES:
        return actuel
    return "CTO" if eligibilite.get(ticker) == "CTO" else defaut
noms = valeurs["nom"].astype(str).to_dict()
libelles = {t: f"{noms[t]} ({t})" for t in sorted(valeurs.index, key=lambda t: noms[t].lower())}

tab_fichier, tab_texte = st.tabs(["Fichier de mon courtier", "Coller ou saisir mes lignes"])
with tab_fichier:
    fichiers = st.file_uploader(
        "Export des positions, CSV ou Excel (Boursorama, Degiro, Fortuneo, Saxo…), un ou plusieurs comptes",
        type=["xlsx", "xlsm", "csv", "txt", "tsv"], accept_multiple_files=True)
    st.caption("Classeur Excel : toutes les feuilles qui ressemblent à un tableau de positions sont lues. Un ancien "
               "fichier .xls est à réenregistrer au format .xlsx dans Excel.")
with tab_texte:
    texte = st.text_area(
        "Une ligne par valeur : nom, ticker ou ISIN, puis le poids en %, le montant ou la quantité",
        height=220, placeholder="Alphabet 20\nAir Liquide 12\nUS0378331005 8\nNUKL.DE 5")

c = st.columns([1, 1, 2], vertical_alignment="bottom")
compte = c[0].selectbox("Compte par défaut", COMPTES, help="Compte attribué aux nouvelles lignes ; "
                        "modifiable ligne par ligne ci-dessous.")
if c[1].button("Lire mes lignes", type="primary", icon=":material/upload_file:", width="stretch"):
    textes, illisibles = [], []
    for f in fichiers or []:
        try:
            textes += imp.textes_fichier(f.getvalue())
        except ValueError as e:
            illisibles.append(f"{f.name} : {e}")
    for message in illisibles:
        st.error(message, icon=":material/error:")
    if texte.strip():
        textes.append(texte)
    if not textes:
        if not illisibles:
            st.warning("Choisissez un fichier ou collez vos lignes d'abord.")
    else:
        r = imp.importer(textes, valeurs, correspondances=lire_json(CORRESPONDANCES, {}) or {})
        if not r.lignes:
            st.warning("Aucune ligne reconnue. Il faut au moins un nom, un ticker ou un ISIN par ligne.")
        else:
            st.session_state["import_resultat"] = r
            st.session_state["import_compte"] = compte
            st.session_state.pop("import_table", None)

if n := st.session_state.pop("import_fait", None):
    st.success(f"Portefeuille enregistré : {n} lignes. Retrouvez-les dans « Composition ».", icon=":material/check:")
base: imp.ResultatImport | None = st.session_state.get("import_resultat")
if base is None:
    st.stop()
# Les corrections partent chaque fois des lignes lues, gardées intactes.
r = imp.ResultatImport(copy.deepcopy(base.lignes), base.methode)

st.subheader("Vérifier les lignes")
mp = load_model_portfolio()
table = pd.DataFrame({
    "statut": ["Ignorée" if li.ignoree else li.confiance.value for li in r.lignes],
    "fichier": [li.libelle for li in r.lignes],
    "isin": [li.isin or "" for li in r.lignes],
    "valeur": [libelles.get(li.ticker, HORS) if li.ticker else HORS for li in r.lignes],
    "compte": [compte_propose(li.ticker) for li in r.lignes],
    "ignorer": [li.ignoree for li in r.lignes],
})
edite = st.data_editor(
    table, key="import_table", hide_index=True, width="stretch", height=min(700, 35 * len(table) + 38),
    disabled=["statut", "fichier", "isin"],
    column_config={
        "statut": st.column_config.TextColumn("Statut", width="small"),
        "fichier": st.column_config.TextColumn("Ligne du fichier", width="medium"),
        "isin": st.column_config.TextColumn("ISIN", width="small"),
        "valeur": st.column_config.SelectboxColumn("Valeur retenue", options=[HORS, *libelles.values()],
                                                   required=True, width="large"),
        "compte": st.column_config.SelectboxColumn("Compte", options=COMPTES, required=True, width="small"),
        "ignorer": st.column_config.CheckboxColumn("Ignorer", width="small"),
    })

# Corrections appliquées, puis poids recalculés.
par_libelle = {v: t for t, v in libelles.items()}
for li, (_, e) in zip(r.lignes, edite.iterrows()):
    choisi = par_libelle.get(e["valeur"])
    if choisi != li.ticker:
        li.ticker, li.confiance = choisi, imp.Confiance.SURE if choisi else imp.Confiance.AUCUNE
    li.ignoree = bool(e["ignorer"])
quantites = [li.ticker for li in r.lignes if li.ticker and li.quantite is not None and li.prix is None]
cours = {}
if quantites:
    px = ui.eur_prices(tuple(sorted(set(quantites))))
    cours = px.ffill().iloc[-1].dropna().to_dict() if not px.empty else {}
r.methode = imp.calculer_poids(r.lignes, cours)
r.retenues = [li for li in r.lignes if not li.ignoree]
comptes = {li.ticker: e["compte"] for li, (_, e) in zip(r.lignes, edite.iterrows()) if li.ticker}

retenues = r.retenues
hors = [li for li in retenues if li.ticker is None]
m = st.columns(4)
m[0].metric("Lignes retenues", len(retenues), border=True)
m[1].metric("Reconnues", sum(li.confiance == imp.Confiance.SURE for li in retenues), border=True)
m[2].metric("À vérifier", sum(li.confiance == imp.Confiance.PROBABLE for li in retenues), border=True)
m[3].metric("Hors des données", len(hors), border=True,
            help="L'outil ne suit que les valeurs de ses données : ces lignes ne seront pas enregistrées.")
st.caption(f"Poids calculés d'après les {r.methode}. Corrigez la colonne « Valeur retenue » si besoin : "
           "la correction est retenue pour les prochains imports.")
if hors:
    st.warning("Hors des données, donc non enregistrées : " + ", ".join(li.libelle for li in hors)
               + ". Choisissez la valeur correspondante, ou cochez « Ignorer ».", icon=":material/warning:")

nouveau = imp.lignes_modele(r, mp, st.session_state["import_compte"], noms)
if nouveau.empty:
    st.stop()
nouveau["enveloppe"] = [comptes.get(t, e) for t, e in zip(nouveau["ticker"], nouveau["enveloppe"])]
st.subheader("Composition qui sera enregistrée")
total = nouveau["poids_cible"].sum()
apercu = nouveau[["ticker", "nom", "enveloppe", "poids_cible"]].assign(poids_cible=nouveau["poids_cible"] / total * 100)
ui.tableau(apercu, hide_index=True, width="stretch", height=min(600, 35 * len(apercu) + 38),
           column_config={"ticker": "Ticker", "nom": "Valeur", "enveloppe": "Compte",
                          "poids_cible": ui.PCT("Poids cible")})


# Quantités : la photo du portefeuille (pf/positions.py), remplacée en entier à chaque import, sert à mesurer le
# poids réel des lignes. Réimporter son portefeuille la met à jour.
avec_q = [li for li in r.retenues if li.ticker and li.quantite and li.quantite > 0]
avec_quantites = st.toggle(
    f"Enregistrer aussi mes quantités ({len(avec_q)} lignes)",
    value=bool(avec_q), disabled=not avec_q, key="import_quantites",
    help="Les quantités remplacent la photo du portefeuille prise au dernier import. L'onglet « Équilibre » de « Analyse "
         "de mon portefeuille » et le tableau de bord mesurent alors vos poids réels. Le fichier ne donne pas de "
         "quantités : seuls les poids sont enregistrés." if not avec_q else
    "Les quantités remplacent la photo du portefeuille prise au dernier import. L'onglet « Équilibre » de « Analyse de "
    "mon portefeuille » et le tableau de bord mesurent alors vos poids réels.")


def lignes_photo() -> list[dict]:
    return [{"ticker": li.ticker, "compte": comptes.get(li.ticker, st.session_state["import_compte"]),
             "quantite": li.quantite} for li in avec_q]


def enregistrer() -> None:
    if MODELE_CSV.exists():
        shutil.copy2(MODELE_CSV, MODELE_CSV.with_name(f"portefeuille_modele.avant-import-{date.today():%Y-%m-%d}.csv"))
    write_csv_fr(nouveau, MODELE_CSV)
    if avec_quantites and avec_q:
        positions.enregistrer(lignes_photo())
    correspondances = lire_json(CORRESPONDANCES, {}) or {}
    for li in r.lignes:
        if not li.ignoree:
            correspondances[li.cle] = li.ticker or ""
    ecrire_json(CORRESPONDANCES, correspondances, indent=1)
    st.cache_data.clear()
    st.session_state.pop("import_resultat", None)
    st.session_state["import_fait"] = len(nouveau)


@st.dialog("Remplacer le portefeuille ?")
def confirmer() -> None:
    st.write(f"Les {len(mp)} lignes actuelles de la composition seront remplacées par ces {len(nouveau)} lignes. "
             "L'ancienne composition est gardée dans le dossier du profil.")
    a, b = st.columns(2)
    if a.button("Remplacer", type="primary", width="stretch"):
        enregistrer()
        st.rerun()
    if b.button("Annuler", width="stretch"):
        st.rerun()


if st.button(f"Enregistrer ({len(nouveau)} lignes)", type="primary", icon=":material/check:"):
    if mp.empty:
        enregistrer()
        st.rerun()
    else:
        confirmer()
st.caption("Votre portefeuille est ensuite analysé dans « Analyse de mon portefeuille ». "
           "Outil d'aide à la décision, pas un conseil en investissement personnalisé.")
