"""Mon portefeuille : qualité fondamentale, verdict de prix et thèses de vos lignes."""
import math

import streamlit as st

from pf import portfolio as pfo
from pf import prix_achat as pa
from pf import ui
from pf import watchlist as wl
from pf.config import SELECTION_CLAUDE_CSV, load_strategy
from pf.theses import read_thesis

sc = ui.require_data()
mp = ui.model()
w = pfo.model_weights()
strat = load_strategy()
names = sc["nom"].to_dict()

titre, bouton = st.columns([4, 1.3], vertical_alignment="bottom")
titre.title("Mon portefeuille")
if bouton.button("Importer mon portefeuille", icon=":material/upload_file:", width="stretch"):
    st.switch_page("vues/importer.py")
if mp.empty:
    st.info("Aucune ligne pour l'instant : importez votre portefeuille depuis l'export de votre courtier (CSV ou "
            "Excel), ou ajoutez des lignes dans « Risques & équilibre → Poids cibles ».", icon=":material/upload_file:")
st.markdown(
    f"**{len(w)} lignes.** Chacune est analysée comme une action du screener : qualité de l'entreprise, prix "
    "comparé à votre prix d'achat, signaux d'alerte. Les fonds (ETF, or) n'ont que leur cours.")
if SELECTION_CLAUDE_CSV.exists():
    st.caption("La sélection de 25 valeurs proposée par Claude le 29/10/2026 reste archivée "
               "(profil/selection_claude_2026-10.csv) : la page « Backtest » permet de la comparer à votre portefeuille.")

ch = pfo.characteristics(w, sc)
risk = pfo.risk_profile(w)
c = st.columns(5)
c[0].metric("Rentabilité moyenne", ui.pct(ch.get("Rentabilité (ROIC/ROE) moyenne")), border=True,
            help="ROIC (ou ROE pour les financières) moyen sur 4-5 ans, pondéré.")
c[1].metric("Marge opérationnelle", ui.pct(ch.get("Marge opérationnelle")), border=True)
c[2].metric("Croissance attendue", ui.pct(ch.get("Croissance attendue")), border=True)
c[3].metric("TRI implicite", ui.pct(ch.get("TRI implicite")), border=True,
            help="Rendement annuel attendu au cours actuel si la croissance retenue se réalise, moyenne pondérée.")
c[4].metric("Lignes effectives", ui.num(risk.get("nombre_effectif"), 1), border=True,
            help="1 / somme des poids au carré : nombre de lignes équipondérées équivalent.")

tab_lignes, tab_theses = st.tabs(["Analyse des lignes", "Thèses"])

with tab_lignes:
    regl = pa.reglages(strat)
    suivies = wl.load_watchlist()
    vises = {t: float(v) for t, v in suivies["prix_cible"].items() if isinstance(v, (int, float)) and math.isfinite(v)}
    prix = pa.tableau(sc, {t: "Portefeuille" for t in w.index}, strat["valorisation"], regl["rendement"],
                      regl["marge"], vises)
    if prix.empty:
        st.caption("Aucune ligne analysable.")
    else:
        nb = prix["verdict"].value_counts()
        k = st.columns(5)
        for col, v in zip(k, pa.VERDICTS.values()):
            col.metric(v, int(nb.get(v, 0)), border=True, help=pa.EXPLICATIONS[v])
        k[4].metric("Hors des filtres", int((prix["statut"] == "Exclu").sum()), border=True,
                    help="Lignes qui ne passent plus les filtres de qualité : leur thèse est à relire.")
        t = prix.join(sc.reindex(columns=["homme_cle", "alertes", "motifs_exclusion", "perf_12m"]))
        t["poids"] = w.reindex(t.index)
        t["alerte"] = [(x if isinstance(x, str) and x else "") or (y if isinstance(y, str) and y else "")
                       for x, y in zip(t["motifs_exclusion"], t["alertes"])]
        t.insert(0, "symbole", t.index)
        t = ui.as_pct_cols(t, ["poids", "ecart_achat", "tri_implicite", "perf_12m"])
        t = t.sort_values("poids", ascending=False)
        t["verdict"] = ui.pastilles_verdict(t["verdict"])
        selection = ui.tableau(
            t[["symbole", "nom", "poids", "verdict", "ecart_achat", "cours", "prix_achat", "devise", "score", "moat",
               "criteres", "tri_implicite", "perf_12m", "homme_cle", "statut", "alerte"]],
            hide_index=True, width="stretch", height=min(760, 35 * len(t) + 38), on_select="rerun",
            selection_mode="single-cell", key=ui.cle_tableau("mp_lignes"),
            column_config={
                "symbole": st.column_config.TextColumn("Ticker", pinned=True),
                "nom": st.column_config.TextColumn("Valeur", pinned=True, width="medium"), "poids": ui.PCT("Poids"),
                "verdict": ui.colonne_verdict(), "ecart_achat": ui.PCT("Cours / prix d'achat", "Négatif : sous votre prix d'achat.", 0),
                "cours": st.column_config.NumberColumn("Cours", format="%.2f"),
                "prix_achat": st.column_config.NumberColumn("Prix d'achat", format="%.2f"), "devise": "Devise",
                "score": ui.SCORE("Note GARP"), "moat": "Moat estimé",
                "criteres": st.column_config.TextColumn("Critères", help="Critères de qualité remplis sur évalués."),
                "tri_implicite": ui.PCT("TRI implicite"), "perf_12m": ui.PCT("12 mois"),
                "homme_cle": st.column_config.NumberColumn("Homme-clé / 10", format="%.1f"),
                "statut": "Filtres", "alerte": st.column_config.TextColumn("Alerte", width="large"),
            })
        ui.fiche_au_clic(t, selection, "mp_lignes")
        st.caption(f"Prix d'achat au rendement exigé de {ui.pct(regl['rendement'], 1)} et avec une marge de "
                   f"{ui.pct(regl['marge'], 0)} (réglables dans « La bonne action au bon prix »). Cliquez sur une "
                   "valeur pour ouvrir sa fiche. Outil d'aide à la décision, pas un conseil.")
    st.download_button("Exporter la composition (CSV)", mp.to_csv(sep=";").encode("utf-8-sig"),
                       file_name="portefeuille_modele.csv", mime="text/csv", icon=":material/download:")

with tab_theses:
    choix = st.selectbox("Valeur", list(w.index), format_func=lambda t: f"{names.get(t, t)} ({t})")
    txt = read_thesis(choix)
    st.markdown(txt or "_Fiche absente : lancez une mise à jour pour la générer._")
