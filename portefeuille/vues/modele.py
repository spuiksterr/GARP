import streamlit as st

from pf import portfolio as pfo
from pf import ui
from pf.config import SELECTION_CLAUDE_CSV
from pf.theses import read_thesis

sc = ui.require_data()
mp = ui.model()
w = pfo.model_weights()

st.title("Composition du portefeuille")
st.markdown(
    f"**{len(w)} lignes.** Les poids cibles (fichier profil/portefeuille_modele.csv) partent de vos poids actuels : "
    "les apports du mois les visent. Modifiez-les dans ce fichier (sous Excel, séparateur « ; »). "
    "Les indicateurs fondamentaux ne portent que sur les actions : un ETF ou l'or n'a ni marge ni ROIC."
)
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
c[3].metric("TRI implicite", ui.pct(ch.get("TRI implicite")), border=True)
c[4].metric("Lignes effectives", ui.num(risk.get("nombre_effectif"), 1), border=True,
            help="1 / somme des poids au carré : nombre de lignes équipondérées équivalent.")

tab_lignes, tab_repartition, tab_risque, tab_theses, tab_surv = st.tabs(
    ["Lignes et thèses", "Répartition", "Risque et corrélations", "Fiches de thèse", "Liste de surveillance"])

with tab_lignes:
    poche = st.segmented_control("Poche", ["Toutes", *dict.fromkeys(mp["poche"].dropna())], default="Toutes",
                                 label_visibility="collapsed")
    t = mp.copy()
    t["poids"] = w
    if poche and poche != "Toutes":
        t = t[t["poche"] == poche]
    t = t.join(sc[["score", "moat", "criteres", "ecart_per_historique", "p_fcf", "regards_total", "piotroski",
                   "altman_z", "beneish_m", "tri_implicite", "per_prospectif", "mom_12_1", "statut"]])
    t = ui.as_pct_cols(t, ["poids", "tri_implicite", "mom_12_1", "ecart_per_historique"]).sort_values("poids", ascending=False)
    ui.tableau(
        t[["nom", "enveloppe", "poche", "poids", "score", "moat", "criteres", "ecart_per_historique", "p_fcf", "regards_total",
           "piotroski", "altman_z", "beneish_m", "tri_implicite", "per_prospectif", "mom_12_1",
           "these", "risque_principal", "condition_vente", "alternative", "statut"]],
        width="stretch", height=min(940, 35 * len(t) + 38),
        column_config={
            "nom": st.column_config.TextColumn("Valeur", pinned=True), "enveloppe": "Compte", "poche": "Poche",
            "poids": ui.PCT("Poids"), "score": ui.SCORE("Score"),
            "moat": "Moat estimé", "criteres": st.column_config.TextColumn("Critères", help="Six critères de qualité remplis sur critères évalués"),
            "ecart_per_historique": ui.PCT("PER / histoire", d=0),
            "p_fcf": st.column_config.NumberColumn("P/FCF", format="%.1f"),
            "regards_total": st.column_config.NumberColumn("Regards / 20", format="%d"),
            "piotroski": st.column_config.NumberColumn("Piotroski", format="%d"), "altman_z": st.column_config.NumberColumn("Altman", format="%.1f"),
            "beneish_m": st.column_config.NumberColumn("Beneish", format="%.2f"), "tri_implicite": ui.PCT("TRI implicite"),
            "per_prospectif": st.column_config.NumberColumn("PER prosp.", format="%.1f"),
            "mom_12_1": ui.PCT("Momentum 12-1"), "these": st.column_config.TextColumn("Thèse", width="large"),
            "risque_principal": st.column_config.TextColumn("Risque principal", width="medium"),
            "condition_vente": st.column_config.TextColumn("Condition de vente", width="medium"),
            "alternative": "Alternative", "statut": "Filtres",
        })
    st.download_button("Exporter (CSV)", t.to_csv(sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="portefeuille_modele.csv", mime="text/csv", icon=":material/download:")

with tab_repartition:
    a, b = st.columns(2)
    with a:
        st.markdown("**Par secteur**")
        ui.show(ui.hbar(pfo.breakdown(w, sc, "secteur")))
    with b:
        st.markdown("**Par pays du siège**")
        ui.show(ui.hbar(pfo.breakdown(w, sc, "pays")))
    env = w.groupby(mp["enveloppe"]).sum().sort_values(ascending=False)  # le compte où la ligne est réellement détenue
    poches = w.groupby(mp["poche"]).sum()
    cartes = [({"PEA": "PEA", "CTO": "Compte-titres"}.get(e, e), v) for e, v in env.items()]
    cartes += [(f"Poche {p.lower()}", v) for p, v in poches.sort_values(ascending=False).items()]
    for col, (label, v) in zip(st.columns(len(cartes)), cartes):
        col.metric(label, ui.pct(v), border=True)

with tab_risque:
    if risk:
        c = st.columns(3)
        c[0].metric("Volatilité attendue", ui.pct(risk["volatilite"]), border=True,
                    help="Sur 3 ans de rendements quotidiens en euros. À comparer à ~14-16 % pour le MSCI World.")
        c[1].metric("Ratio de diversification", ui.num(risk["ratio_diversification"], 2), border=True,
                    help="Volatilité moyenne des lignes / volatilité du portefeuille. Plus il est élevé, plus les lignes se compensent.")
        c[2].metric("Nombre effectif", ui.num(risk["nombre_effectif"], 1), border=True)
        st.markdown("**Contribution de chaque ligne au risque total**")
        contrib = risk["contribution_risque"].rename(index=sc["nom"].to_dict())
        ui.show(ui.hbar(contrib))
        st.markdown("**Corrélations des rendements hebdomadaires (3 ans)**")
        names = sc["nom"].to_dict()
        rets = pfo.returns_eur(list(w.index))
        weekly = (1 + rets).resample("W-FRI").prod() - 1
        ui.show(ui.corr_heatmap(weekly.corr(), labels=names))
        st.caption("Bleu : les deux valeurs évoluent en sens opposé. Rouge : elles évoluent ensemble. "
                   "Un bloc rouge signale un risque commun aux lignes concernées.")

with tab_theses:
    names = sc["nom"].to_dict()
    choix = st.selectbox("Valeur", list(w.index), format_func=lambda t: f"{names.get(t, t)} ({t})")
    txt = read_thesis(choix)
    st.markdown(txt or "_Fiche absente : lancez une mise à jour pour la générer._")

with tab_surv:
    st.info("La liste de surveillance et votre watchlist ont maintenant leur page : « Watchlist », dans le menu Analyser. "
            "Un clic sur une valeur y ouvre sa fiche.", icon=":material/star:")
