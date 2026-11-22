"""La bonne action au bon prix : les entreprises de qualité (filtres), classées selon la note GARP, dont le cours
est sous votre prix d'achat (pf/prix_achat.py). Dans tout l'univers, dans votre portefeuille ou dans votre
watchlist."""
import math

import streamlit as st

from pf import prix_achat as pa
from pf import ui
from pf import watchlist as wl
from pf.config import load_strategy

sc = ui.require_data()
strat = load_strategy()
vcfg = strat["valorisation"]
regl = pa.reglages(strat)

st.title("La bonne action au bon prix")
st.markdown(
    "Deux questions. **La bonne action** : l'entreprise passe-t-elle les filtres de qualité, et quelle est sa "
    "**note GARP** (la croissance, sans la surpayer) ? **Au bon prix** : son cours est-il sous votre **prix "
    "d'achat**, c'est-à-dire le **prix juste** (le cours qui vous rapporterait votre rendement exigé si la "
    "croissance attendue se réalise) moins votre marge de sécurité ?")

c = st.columns([1.2, 1.2, 2.6])
rendement = c[0].slider("Rendement exigé (par an)", 5.0, 15.0, regl["rendement"] * 100, 0.5, format="%.1f %%",
                        help="Le rendement annuel que vous voulez obtenir. Plus il est élevé, plus le prix juste est bas.")
marge = c[1].slider("Marge de sécurité", 0, 40, round(regl["marge"] * 100), 5, format="%d %%",
                    help="Rabais demandé sous le prix juste avant d'acheter : il couvre l'erreur d'estimation.")
ou = c[2].segmented_control("Où chercher", ["Toutes les actions de qualité", "Mon portefeuille", "Ma watchlist"],
                            default="Toutes les actions de qualité", key="bon_prix_perimetre",
                            ) or "Toutes les actions de qualité"
if (rendement / 100, marge / 100) != (regl["rendement"], regl["marge"]):
    pa.enregistrer_reglages(rendement / 100, marge / 100)  # retenus pour les prochaines ouvertures

suivies = wl.load_watchlist()
univers = ou == "Toutes les actions de qualité"
if univers:
    sources = {t: "Univers" for t in sc.index[sc["statut"] == "Éligible"]}
elif ou == "Mon portefeuille":
    sources = {t: "Portefeuille" for t in ui.model().index}
else:
    sources = {t: "Watchlist" for t in suivies.index}
prix_vises = {t: float(v) for t, v in suivies["prix_cible"].items() if isinstance(v, (int, float)) and math.isfinite(v)}
tab = pa.tableau(sc, sources, vcfg, rendement / 100, marge / 100, prix_vises)
if tab.empty:
    st.info("Aucune valeur à évaluer : importez votre portefeuille, ou ajoutez des valeurs à la watchlist depuis le "
            "screener ou une fiche.", icon=":material/info:")
    st.stop()

# Filtres : par défaut, dans l'univers, les seules actions au bon prix ou à un prix correct.
f = st.columns([0.9, 3.1, 0.9, 1.9])
comptes = f[0].segmented_control("Compte", ["PEA", "CTO"], selection_mode="multi", default=["PEA", "CTO"],
                                 key="bon_prix_comptes")
verdicts = f[1].segmented_control("Verdict", list(pa.VERDICTS.values()), selection_mode="multi",
                                  default=["Au bon prix", "Prix correct"] if univers else list(pa.VERDICTS.values()),
                                  key=f"bon_prix_verdicts_{univers}")
crit_min = f[2].number_input("Critères min.", 0, 6, 0, 1, key="bon_prix_crit",
                             help="Nombre minimal de critères de qualité remplis, sur six (détail dans la fiche).")
moat = f[3].segmented_control("Moat estimé", ["Large", "Étroit", "Faible"], selection_mode="multi",
                              key="bon_prix_moat", help="Traces d'un avantage concurrentiel dans les comptes.")
vue = tab.copy()
if comptes:
    vue = vue[vue["enveloppe"].isin(comptes) | vue["enveloppe"].isna()]
if verdicts:
    vue = vue[vue["verdict"].isin(verdicts)]
if crit_min:
    vue = vue[vue["criteres_ok"].astype(float).fillna(0) >= crit_min]
if moat:
    vue = vue[vue["moat"].isin(moat)]

nb = tab["verdict"].value_counts()
m = st.columns(4)
for col, v in zip(m, pa.VERDICTS.values()):
    col.metric(v, int(nb.get(v, 0)), border=True, help=pa.EXPLICATIONS[v])
MAX = 150
st.markdown(f"**{len(vue)} valeurs** retenues par les filtres" + (f", les {MAX} premières affichées" if len(vue) > MAX
                                                                    else "") + " : au bon prix d'abord, puis par "
            "note GARP.")

vue = vue.head(MAX).copy()
vue.insert(0, "symbole", vue.index)
vue["ecart_achat"] = vue["ecart_achat"] * 100
vue["croissance_attendue"] = vue["croissance_attendue"].astype(float) * 100
vue["tri_implicite"] = vue["tri_implicite"].astype(float) * 100
# Prix visé en texte : « — » plutôt qu'une case « None », et « atteint » dans la même colonne.
vue["prix_vise"] = [("—" if not math.isfinite(v) else ui.num(v, 2) + (" · atteint" if a else ""))
                    for v, a in zip(vue["prix_vise"], vue["vise_atteint"])]
vue["verdict"] = ui.pastilles_verdict(vue["verdict"])
# Barre d'actions au-dessus du tableau (remplie après lui, une fois la sélection connue).
barre = st.container()
colonnes = ["symbole", "nom", "verdict", "ecart_achat", "cours", "prix_achat", "prix_juste", "devise", "score",
            "moat",
            "criteres", "tri_implicite", "croissance_attendue", "secteur", "enveloppe", "prix_vise"]
selection = ui.tableau(
    vue[colonnes], hide_index=True, width="stretch", height=min(720, 35 * len(vue) + 38), on_select="rerun",
    selection_mode="multi-row", key=f"bon_prix_tableau_{ou}",
    column_config={
        "symbole": st.column_config.TextColumn("Ticker", pinned=True),
        "nom": st.column_config.TextColumn("Valeur", pinned=True),
        "verdict": ui.colonne_verdict(),
        "ecart_achat": ui.PCT("Cours / prix d'achat", "Négatif : le cours est sous votre prix d'achat.", 0),
        "cours": st.column_config.NumberColumn("Cours", format="%.2f"),
        "prix_achat": st.column_config.NumberColumn("Prix d'achat", format="%.2f",
                                                    help="Prix juste moins votre marge de sécurité."),
        "prix_juste": st.column_config.NumberColumn("Prix juste", format="%.2f"),
        "devise": "Devise",
        "score": ui.SCORE("Note GARP", "Croissance 40 %, valorisation 35 %, qualité 25 % : rangs dans l'univers, "
                                       "de 0 à 100 (100 : la mieux classée)."),
        "moat": st.column_config.TextColumn("Moat estimé"),
        "criteres": st.column_config.TextColumn("Critères", help="Critères de qualité remplis sur critères évalués."),
        "tri_implicite": ui.PCT("TRI au cours actuel", "Rendement annuel si la croissance retenue se réalise."),
        "croissance_attendue": ui.PCT("Croissance retenue", "Croissance annuelle des 5 prochaines années utilisée."),
        "secteur": "Secteur", "enveloppe": "Compte",
        "prix_vise": st.column_config.TextColumn("Votre prix visé", help="Fixé dans la watchlist."),
    })
choisies = [vue.index[i] for i in (selection.selection.rows if selection else [])]
with barre:
    b = st.columns([1.2, 1.5, 1.8, 2.5])
    if b[0].button("Ouvrir la fiche", icon=":material/query_stats:", disabled=len(choisies) != 1, width="stretch",
                   help="Cochez une seule ligne."):
        st.session_state["fiche_ticker"] = choisies[0]
        st.switch_page("vues/fiche.py")
    nouvelles = [t for t in choisies if not wl.contient(t)]
    if b[1].button(f"Ajouter à la watchlist ({len(nouvelles)})", icon=":material/star:", disabled=not nouvelles,
                   width="stretch", help="Ajoute les lignes cochées à la watchlist, sans prix visé."):
        for t in nouvelles:
            cours = tab.loc[t, "cours"]
            wl.ajouter(t, cours=cours if math.isfinite(cours) else None, note="Depuis « La bonne action au bon prix »")
        st.toast(f"{len(nouvelles)} valeur(s) ajoutée(s) à la watchlist.", icon=":material/star:")
        st.rerun()
    fixables = [t for t in choisies if math.isfinite(tab.loc[t, "prix_achat"])]
    if b[2].button(f"Suivre au prix d'achat ({len(fixables)})", icon=":material/flag:", disabled=not fixables,
                   width="stretch", help="Ajoute à la watchlist avec le prix d'achat comme prix visé : le tableau de "
                                         "bord vous prévient quand le cours y passe."):
        for t in fixables:
            wl.fixer_cible(t, tab.loc[t, "prix_achat"],
                           f"Prix d'achat : rendement {ui.num(rendement, 1)} %, marge {marge} %", cours=tab.loc[t, "cours"])
        st.toast(f"{len(fixables)} valeur(s) suivie(s) au prix d'achat.", icon=":material/flag:")
        st.rerun()
    b[3].caption("Cochez une ligne (case à gauche du tableau) pour ouvrir sa fiche, ou plusieurs pour les ajouter à la "
                 "watchlist." if not choisies else f"{len(choisies)} ligne(s) cochée(s).")
st.caption(
    f"Modèle : croissance retenue pendant {vcfg['annees_croissance']} ans, puis ralentissement en "
    f"{vcfg['annees_convergence']} ans vers {ui.pct(vcfg['croissance_terminale'], 0)} par an ; rentabilité des "
    "nouveaux investissements bornée. Une estimation, sensible à la croissance retenue : le détail et d'autres "
    "méthodes (multiples, scénarios) sont dans la fiche. Outil d'aide à la décision, pas un conseil en investissement.")
