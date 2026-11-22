import plotly.graph_objects as go
import streamlit as st

from pf import ui
from pf import watchlist as wl
from pf.config import load_strategy

ui.require_data()
strat = load_strategy()

st.title("Screener")
st.caption("Étape 1 : les filtres d'exclusion écartent les entreprises qui ne sont pas de premier ordre. Étape 2 : "
           "les survivantes sont classées par la note GARP, la croissance sans la surpayer : croissance 40 %, "
           "valorisation 35 %, qualité 25 %, chaque pilier en rang centile dans l'univers. Quatre regards, six critères "
           "et signaux de santé restent affichés comme repères, hors note.")
sc = ui.screener()

# Les filtres courants en tête ; les autres dans un volet, pour que le tableau arrive vite à l'écran.
f = st.columns([1.1, 1.4, 3])
env = f[0].segmented_control("Compte", ["PEA", "CTO"], selection_mode="multi", default=["PEA", "CTO"])
statut = f[1].segmented_control("Statut", ["Éligible", "Exclu"], selection_mode="multi", default=["Éligible"])
recherche = f[2].text_input("Recherche", placeholder="Nom ou ticker")
actifs = sum(bool(st.session_state.get(k)) for k in ("scr_moat", "scr_secteurs", "scr_pays", "scr_pfcf", "scr_crit",
                                                     "scr_decote"))
with st.expander("Plus de filtres" + (f" ({actifs} actif{'s' if actifs > 1 else ''})" if actifs else ""),
                 icon=":material/filter_list:"):
    g = st.columns([1.6, 2, 2])
    moat = g[0].segmented_control("Moat estimé", ["Large", "Étroit", "Faible"], selection_mode="multi", key="scr_moat",
                                  help="Traces d'un avantage concurrentiel dans les comptes. Ce n'est pas le moat de "
                                       "Morningstar.")
    secteurs = g[1].multiselect("Secteurs", sorted(sc["secteur"].dropna().unique()), placeholder="Tous les secteurs",
                                key="scr_secteurs")
    pays = g[2].multiselect("Pays", sorted(sc["pays"].dropna().unique()), placeholder="Tous les pays", key="scr_pays")
    h = st.columns([1.2, 1.2, 1.5, 2])
    pfcf_max = h[0].number_input("P/FCF maximum", min_value=0, max_value=200, value=0, step=5, key="scr_pfcf",
                                 help="Prix / flux de trésorerie disponible des 12 derniers mois. 0 : pas de limite. Écarte "
                                      "aussi les valeurs sans FCF positif, ainsi que les banques et assureurs, pour qui ce "
                                      "ratio n'a pas de sens.")
    crit_min = h[1].number_input("Critères min.", min_value=0, max_value=6, value=0, step=1, key="scr_crit",
                                 help="Nombre minimal de critères de qualité remplis, sur six : croissance du CA et du free "
                                      "cash flow, ROCE, dette nette / FCF, nombre d'actions, marge de FCF. Détail et seuils "
                                      "sur la fiche de chaque valeur.")
    h[2].markdown('<div style="height:1.9rem"></div>', unsafe_allow_html=True)  # aligne l'interrupteur sur les champs
    sous_histoire = h[2].toggle("P/FCF décoté", value=False, key="scr_decote",
                                help="Ne garder que les actions dont le P/FCF est inférieur à leur niveau médian des "
                                     "dernières clôtures annuelles (six au plus).")

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

t = st.columns([3, 1], vertical_alignment="bottom")
t[0].markdown(f"**{len(view)} valeurs**")
avancees = t[1].toggle("Colonnes avancées", key="scr_avancees",
                       help="Toutes les mesures : piliers, quatre regards, signaux de santé, six critères, P/FCF, "
                            "volatilité, risque homme-clé…")
st.caption("Cliquez sur une valeur pour ouvrir sa fiche. La case à gauche d'une ligne l'ajoute à la watchlist "
           "(cochée = suivie) ; décochez-la pour la retirer.")
# Les colonnes utiles pour juger « de la croissance à un prix raisonnable » ; le reste sur demande.
ESSENTIELLES = ["rang", "nom", "enveloppe", "secteur", "score", "moat", "criteres", "croissance_attendue",
                "per_prospectif", "ecart_per_historique", "tri_implicite"]
cols = ["rang", "nom", "enveloppe", "secteur", "score", "moat", "criteres", "exercices_historique",
        "ecart_per_historique", "p_fcf", "p_fcf_net", "ecart_p_fcf_historique", "regards_total", "buffett", "munger", "fisher", "smith",
        "piotroski", "altman_z", "beneish_m", "verif_sec", "homme_cle",
        "qualite", "croissance", "valorisation", "momentum", "rentabilite",
        "marge_operationnelle", "croissance_attendue", "per_prospectif", "rendement_fcf",
        "croissance_implicite", "tri_implicite", "mom_12_1", "volatilite",
        "crit_ca", "crit_fcf", "crit_roce", "crit_dette", "crit_actions", "crit_marge", "capitalisation_eur", "alertes", "motifs_exclusion"]
if not avancees:
    cols = ESSENTIELLES
show = view.reindex(columns=cols).copy()  # une colonne pas encore calculée reste vide
if "capitalisation_eur" in show.columns:
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
        "score": ui.SCORE("Note GARP", "Croissance 40 %, valorisation 35 %, qualité 25 % : rangs dans l'univers, sur 100"),
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
        "homme_cle": st.column_config.NumberColumn(
            "Homme-clé / 10", format="%.1f",
            help="Risque homme-clé : dépendance à une personne (fondateur aux commandes, PDG, âge du dirigeant, part des "
                 "initiés, conseil peu indépendant). 6 ou plus : élevé. Détail dans la fiche, section Résumé."),
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

st.subheader("Croissance et valorisation")
st.caption("En haut à droite : la croissance à prix raisonnable, le cœur de la note GARP. Taille : capitalisation. "
           "Survolez un point pour le détail (qualité et note GARP).")
fig = go.Figure()
for i, e in enumerate(["PEA", "CTO"]):
    d = view[view["enveloppe"] == e]
    if d.empty:
        continue
    size = (d["capitalisation_eur"].fillna(1e10) / 1e9) ** 0.5
    fig.add_trace(go.Scatter(
        x=d["valorisation"], y=d["croissance"], mode="markers", name=e,
        marker=dict(size=(size / size.max() * 28).clip(lower=8), color=ui.couleurs()["series"][i], opacity=0.85,
                    line=dict(width=2, color=ui.couleurs()["surface"])),
        text=d["nom"], customdata=d[["score", "tri_implicite", "qualite"]].values,
        hovertemplate="<b>%{text}</b><br>Croissance %{y:.0f} · Valorisation %{x:.0f} · Qualité %{customdata[2]:.0f}"
                      "<br>Note GARP %{customdata[0]:.0f} · TRI %{customdata[1]:.1%}<extra>" + e + "</extra>"))
ui.style(fig, 520)
fig.update_xaxes(title="Valorisation (rang centile, 100 = la moins chère)", range=[0, 102], showgrid=True, gridcolor=ui.TRAIT)
fig.update_yaxes(title="Croissance (rang centile)", range=[0, 102])
ui.show(fig)
