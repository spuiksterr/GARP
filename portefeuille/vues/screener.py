import plotly.graph_objects as go
import streamlit as st

from pf import ui
from pf import watchlist as wl
from pf.config import load_strategy

ui.require_data()
strat = load_strategy()

st.title("Screener")
st.caption("Étape 1 : les filtres d'exclusion écartent les entreprises qui ne sont pas de premier ordre. Étape 2 : les survivantes sont "
           "classées sur la moyenne pondérée de plusieurs analyses, chacune sur 100 : le bloc des quatre piliers, la valorisation "
           "(comptée aussi à part, pour qu'elle pèse vraiment), les quatre regards, Piotroski, Altman et Beneish.")

with st.expander("Pondération des piliers", icon=":material/tune:"):
    base = strat["poids_piliers"]
    c = st.columns(4)
    poids = {
        "qualite": c[0].slider("Qualité", 0, 100, int(base["qualite"] * 100), 5),
        "croissance": c[1].slider("Croissance", 0, 100, int(base["croissance"] * 100), 5),
        "valorisation": c[2].slider("Valorisation", 0, 100, int(base["valorisation"] * 100), 5),
        "momentum": c[3].slider("Momentum", 0, 100, int(base["momentum"] * 100), 5),
    }
    st.caption("Ces curseurs règlent le bloc « Piliers », l'une des analyses du score. Les poids sont normalisés. Par défaut : "
               "qualité 35, valorisation 25, croissance 20, momentum 20. "
               "Le poids de chaque analyse se règle dans config/strategie.json (poids_score).")
if sum(poids.values()) == 0:
    poids = {k: 1 for k in poids}
sc = ui.screener(tuple(sorted((k, v / 100) for k, v in poids.items())))

# Deux lignes de filtres : sur une seule, les choix (« Exclu », « Étroit ») et les libellés étaient coupés.
f = st.columns([1.1, 1.4, 1.9, 2.6])
env = f[0].segmented_control("Compte", ["PEA", "CTO"], selection_mode="multi", default=["PEA", "CTO"])
statut = f[1].segmented_control("Statut", ["Éligible", "Exclu"], selection_mode="multi", default=["Éligible"])
moat = f[2].segmented_control("Moat estimé", ["Large", "Étroit", "Faible"], selection_mode="multi",
                              help="Traces d'un avantage concurrentiel dans les comptes. Ce n'est pas le moat de Morningstar.")
recherche = f[3].text_input("Recherche", placeholder="Nom ou ticker")
g = st.columns([2, 2, 1.2, 1.2, 1.5])
secteurs = g[0].multiselect("Secteurs", sorted(sc["secteur"].dropna().unique()), placeholder="Tous les secteurs")
pays = g[1].multiselect("Pays", sorted(sc["pays"].dropna().unique()), placeholder="Tous les pays")
pfcf_max = g[2].number_input("P/FCF maximum", min_value=0, max_value=200, value=0, step=5,
                             help="Prix / flux de trésorerie disponible des 12 derniers mois. 0 : pas de limite. Écarte aussi les valeurs "
                                  "sans FCF positif, ainsi que les banques et assureurs, pour qui ce ratio n'a pas de sens.")
crit_min = g[3].number_input("Critères min.", min_value=0, max_value=6, value=0, step=1,
                             help="Nombre minimal de critères de qualité remplis, sur six : croissance du CA et du free cash flow, ROCE, "
                                  "dette nette / FCF, nombre d'actions, marge de FCF. Détail et seuils sur la fiche de chaque valeur.")
g[4].markdown('<div style="height:1.9rem"></div>', unsafe_allow_html=True)  # aligne l'interrupteur sur les champs
sous_histoire = g[4].toggle("P/FCF décoté", value=False,
                            help="Ne garder que les actions dont le P/FCF est inférieur à leur niveau médian des dernières clôtures "
                                 "annuelles (six au plus).")

view = sc.copy()
if env:
    view = view[view["enveloppe"].isin(env)]
if statut:
    view = view[view["statut"].isin(statut)]
if moat:
    view = view[view["moat"].isin(moat)]
if secteurs:
    view = view[view["secteur"].isin(secteurs)]
if pays:
    view = view[view["pays"].isin(pays)]
if pfcf_max:
    view = view[view["p_fcf"] <= pfcf_max]
if sous_histoire:
    view = view[view["ecart_p_fcf_historique"] < 0]
if crit_min:
    view = view[view["criteres_ok"].fillna(0) >= crit_min]
if recherche:
    q = recherche.lower()
    view = view[view["nom"].str.lower().str.contains(q, na=False, regex=False) | view.index.str.lower().str.contains(q, regex=False)]

st.markdown(f"**{len(view)} valeurs**")
st.caption("Cliquez sur une valeur pour ouvrir sa fiche. La case à gauche d'une ligne l'ajoute à la watchlist "
           "(cochée = suivie) ; décochez-la pour la retirer.")
cols = ["rang", "nom", "enveloppe", "secteur", "score", "score_piliers", "moat", "criteres", "exercices_historique",
        "ecart_per_historique", "p_fcf", "p_fcf_net", "ecart_p_fcf_historique", "regards_total", "buffett", "munger", "fisher", "smith",
        "piotroski", "altman_z", "beneish_m", "verif_sec",
        "qualite", "croissance", "valorisation", "momentum", "rentabilite",
        "marge_operationnelle", "croissance_attendue", "per_prospectif", "rendement_fcf",
        "croissance_implicite", "tri_implicite", "mom_12_1", "volatilite",
        "crit_ca", "crit_fcf", "crit_roce", "crit_dette", "crit_actions", "crit_marge", "capitalisation_eur", "alertes", "motifs_exclusion"]
show = view.reindex(columns=cols).copy()  # une colonne pas encore calculée reste vide
show["capitalisation_eur"] = show["capitalisation_eur"] / 1e9
show = ui.as_pct_cols(show, ["rentabilite", "marge_operationnelle", "croissance_attendue", "rendement_fcf",
                             "croissance_implicite", "tri_implicite", "mom_12_1", "volatilite", "ecart_per_historique",
                             "ecart_p_fcf_historique", "crit_ca", "crit_fcf", "crit_roce", "crit_actions", "crit_marge"])
# Un clic sur une cellule ouvre la fiche ; la case de chaque ligne dit si la valeur est dans la watchlist. Le
# ticker est une colonne ordinaire : Streamlit ne signale pas les clics sur l'index.
show.insert(0, "symbole", show.index)
cle = "scr_tableau"
MAX_D_UN_COUP = 20
cle_tableau = f"{cle}_{st.session_state.get(cle, 0)}"
# 1. Cases changées par l'utilisateur au dernier affichage -> watchlist. Les positions se lisent dans la liste
#    des valeurs alors affichées (les filtres ont pu changer depuis).
affichees = st.session_state.get("scr_affichees", [])
etat = st.session_state.get(cle_tableau)
suivies = set(wl.load_watchlist().index)
if etat and affichees:
    cochees = {affichees[i] for i in etat["selection"]["rows"] if i < len(affichees)}
    a_ajouter, retirees = sorted(cochees - suivies), sorted((suivies & set(affichees)) - cochees)
    if len(a_ajouter) > MAX_D_UN_COUP or len(retirees) > MAX_D_UN_COUP:
        # Case de l'en-tête : elle cocherait (ou décocherait) toutes les lignes affichées d'un seul clic.
        st.warning(f"Plus de {MAX_D_UN_COUP} valeurs cochées ou décochées d'un coup : la watchlist n'a pas été modifiée. "
                   "Filtrez d'abord le screener, ou cochez les lignes une par une.", icon=":material/block:")
        a_ajouter, retirees = [], []
    ajoutees = ui.ajouter_watchlist(a_ajouter)
    for t in retirees:
        wl.retirer(t)
    for t in ajoutees:
        st.toast(f"{sc['nom'].get(t, t)} ajoutée à la watchlist.", icon=":material/star:")
    for t in retirees:
        st.toast(f"{sc['nom'].get(t, t)} retirée de la watchlist.", icon=":material/star_border:")
    suivies = (suivies | set(ajoutees)) - set(retirees)
    # Clic sur une cellule : la fiche, avant que l'étape 2 ne remette la sélection à zéro.
    cellules = [i for i, _ in etat["selection"]["cells"] if i < len(affichees)]
    if cellules:
        st.session_state["fiche_ticker"] = affichees[cellules[0]]
        st.session_state[cle] = st.session_state.get(cle, 0) + 1
        st.session_state.pop("scr_affichees", None)
        st.switch_page("vues/fiche.py")
# 2. Cases cochées = valeurs suivies, dans l'ordre de l'affichage actuel.
st.session_state["scr_affichees"] = list(show.index)
st.session_state[cle_tableau] = {"selection": {"rows": [i for i, t in enumerate(show.index) if t in suivies],
                                               "columns": [], "cells": []}}
ui.tableau(
    show, width="stretch", height=560, on_select="rerun", selection_mode=["single-cell", "multi-row"],
    key=cle_tableau, hide_index=True,
    column_config={
        "symbole": st.column_config.TextColumn("Ticker", pinned=True),
        "rang": st.column_config.NumberColumn("Rang", format="%d", pinned=True),
        "nom": st.column_config.TextColumn("Valeur", pinned=True),
        "enveloppe": "Compte", "secteur": "Secteur",
        "score": ui.SCORE("Score", "Moyenne pondérée des analyses, chacune sur 100 : piliers, valorisation, "
                                   "quatre regards, Piotroski, Altman, Beneish"),
        "score_piliers": ui.SCORE("Piliers", "Qualité, croissance, valorisation et momentum"),
        "moat": st.column_config.TextColumn("Moat estimé", help="Rentabilité élevée et tenue, prix défendus. "
                                                                "Estimation chiffrée, pas le moat de Morningstar."),
        "p_fcf": st.column_config.NumberColumn("P/FCF", format="%.1f", help="Capitalisation / flux de trésorerie disponible des 12 derniers mois"),
        "p_fcf_net": st.column_config.NumberColumn("P/FCF hors SBC", format="%.1f",
                                                   help="Capitalisation / (flux de trésorerie disponible − rémunérations en actions)"),
        "ecart_p_fcf_historique": ui.PCT("P/FCF / histoire", "P/FCF actuel comparé à son niveau médian aux 4 dernières clôtures annuelles", 0),
        "ecart_per_historique": ui.PCT("PER / histoire", "PER actuel comparé à son niveau médian aux 4 dernières clôtures annuelles", 0),
        "regards_total": st.column_config.NumberColumn("Regards / 20", format="%d", help="Total des quatre regards, voir la page du même nom"),
        "buffett": st.column_config.NumberColumn("Buffett", format="%d"), "munger": st.column_config.NumberColumn("Munger", format="%d"),
        "fisher": st.column_config.NumberColumn("Fisher", format="%d"), "smith": st.column_config.NumberColumn("Smith", format="%d"),
        "piotroski": st.column_config.NumberColumn("Piotroski", format="%d",
                                                   help="De 0 à 9 : la situation s'améliore-t-elle ? 0 à 2 : faible, 8 ou 9 : forte."),
        "altman_z": st.column_config.NumberColumn("Altman", format="%.1f",
                                                  help="Risque de faillite : sous 1,8 zone fragile, au-dessus de 3 zone sûre."),
        "beneish_m": st.column_config.NumberColumn("Beneish", format="%.2f", help="Au-dessus de -1,78 : comptes à examiner, ou forte croissance."),
        "verif_sec": st.column_config.TextColumn("Vérif. SEC", help="Sociétés américaines : comptes Yahoo recoupés avec ceux déposés à la SEC "
                                                 "(CA, résultat net, flux d'exploitation, fonds propres, bilan ; tolérance 3 %)."),
        "qualite": ui.SCORE("Qualité"), "croissance": ui.SCORE("Croiss."),
        "valorisation": ui.SCORE("Valo."), "momentum": ui.SCORE("Mom."),
        "rentabilite": ui.PCT("ROIC/ROE", "ROIC moyen (ROE pour banques, assureurs et holdings)"),
        "marge_operationnelle": ui.PCT("Marge op."), "croissance_attendue": ui.PCT("Croiss. att."),
        "per_prospectif": st.column_config.NumberColumn("PER prosp.", format="%.1f"),
        "rendement_fcf": ui.PCT("Rdt FCF"),
        "croissance_implicite": ui.PCT("Croiss. implicite", "Croissance annuelle (5 ans) que suppose le cours actuel"),
        "tri_implicite": ui.PCT("TRI implicite", "Rendement annuel si la croissance attendue se réalise"),
        "mom_12_1": ui.PCT("Mom. 12-1"), "volatilite": ui.PCT("Volatilité"),
        "exercices_historique": st.column_config.NumberColumn(
            "Historique", format="%d ex.", help="Exercices disponibles : 4 = Yahoo seul (3 ans de croissance, fréquent hors "
                                                "des États-Unis sans rapport ESEF raccordé) ; 5 ou plus = prolongé par les "
                                                "comptes SEC ou ESEF. Comparez les croissances à historique égal."),
        "criteres": st.column_config.TextColumn("Critères", help="Critères de qualité remplis sur critères évalués (six au plus). "
                                                "Banques, assureurs et holdings ne sont évalués que sur deux d'entre eux."),
        "crit_ca": ui.PCT("CA / an (5 ans)", "Croissance annuelle du chiffre d'affaires sur 5 ans (3 ans quand l'historique est plus court)"),
        "crit_fcf": ui.PCT("FCF / an (5 ans)", "Croissance annuelle du free cash flow sur 5 ans (3 ans quand l'historique est plus court)"),
        "crit_roce": ui.PCT("ROCE moyen", "Résultat opérationnel / (total du bilan − dettes courantes), moyenne sur 5 ans au plus"),
        "crit_dette": st.column_config.NumberColumn("Dette nette / FCF", format="%.2f",
                                                    help="Dette nette au dernier trimestre / free cash flow des 12 derniers mois. "
                                                         "Négatif : trésorerie nette."),
        "crit_actions": ui.PCT("Actions (5 ans)", "Évolution du nombre d'actions diluées sur 5 ans (3 ans quand l'historique est plus court)"),
        "crit_marge": ui.PCT("Marge FCF", "Free cash flow / chiffre d'affaires, moyenne sur 5 ans au plus"),
        "capitalisation_eur": st.column_config.NumberColumn("Capi. (Md€)", format="%.1f"),
        "alertes": st.column_config.TextColumn("Alertes", width="large"),
        "motifs_exclusion": st.column_config.TextColumn("Motifs d'exclusion", width="large"),
    })

st.download_button("Exporter la sélection (CSV)", view.drop(columns=["profil"], errors="ignore").to_csv(sep=";", decimal=",").encode("utf-8-sig"),
                   file_name=f"screener-{ui.stamp()}.csv", mime="text/csv", icon=":material/download:")

st.subheader("Qualité et valorisation")
st.caption("En haut à droite : entreprises de qualité à prix raisonnable. Taille : capitalisation. Survolez un point pour le détail.")
fig = go.Figure()
for i, e in enumerate(["PEA", "CTO"]):
    d = view[view["enveloppe"] == e]
    if d.empty:
        continue
    size = (d["capitalisation_eur"].fillna(1e10) / 1e9) ** 0.5
    fig.add_trace(go.Scatter(
        x=d["valorisation"], y=d["qualite"], mode="markers", name=e,
        marker=dict(size=(size / size.max() * 28).clip(lower=8), color=ui.couleurs()["series"][i], opacity=0.85,
                    line=dict(width=2, color=ui.couleurs()["surface"])),
        text=d["nom"], customdata=d[["score", "tri_implicite"]].values,
        hovertemplate="<b>%{text}</b><br>Qualité %{y:.0f} · Valorisation %{x:.0f}<br>Score %{customdata[0]:.0f}"
                      " · TRI %{customdata[1]:.1%}<extra>" + e + "</extra>"))
ui.style(fig, 520)
fig.update_xaxes(title="Valorisation (rang centile, 100 = la moins chère)", range=[0, 102], showgrid=True, gridcolor=ui.TRAIT)
fig.update_yaxes(title="Qualité (rang centile)", range=[0, 102])
ui.show(fig)
