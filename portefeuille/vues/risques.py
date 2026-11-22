"""Risques du portefeuille : concentration, devises, corrélations, pertes passées, scénarios de choc."""
import re

import pandas as pd
import streamlit as st

from pf import portfolio as pfo
from pf import risques, simulation, ui
from pf.config import BENCHMARKS, load_strategy

sc = ui.require_data()
st.title("Risques du portefeuille")

w, source = risques.poids_actuels()
bench = load_strategy().get("suivi", {}).get("benchmark", "IWDA.AS")
noms = {t: str(sc["nom"].get(t, t)) for t in w.index}
st.caption(f"Calculé sur vos {source}, avec 3 ans de cours en euros aux poids d'aujourd'hui. Mesures du passé et "
           "scénarios simplifiés : ils montrent où sont les risques, pas ce qui arrivera.")


@st.cache_data(ttl=3600, show_spinner=False)
def calculs(version, poids_items, bench):
    poids = pd.Series(dict(poids_items))
    r_p, r = risques.rendements(poids, benchmark=bench)
    return r_p, r, pfo.risk_profile(poids, returns=r)


with st.spinner("Calcul des risques…"):
    r_p, r, profil = calculs(ui.data_version(), tuple(w.items()), bench)
conc = risques.concentration(w)
date_pire, pire = risques.pire_mois(r_p)

# --------------------------------------------------------------------------- chiffres clés
k = st.columns(5)
k[0].metric("Plus grosse ligne", ui.pct(conc["poids_plus_grosse"], 0), noms[conc["plus_grosse"]], delta_color="off")
k[1].metric("Trois premières lignes", ui.pct(conc["trois_premieres"], 0), f"{len(w)} lignes au total", delta_color="off")
k[2].metric("Nombre effectif de lignes", ui.num(conc["nombre_effectif"], 1),
            help="Diversification réelle : un portefeuille de 10 lignes égales vaut 10 ; s'il est dominé par une ligne, "
                 "il vaut bien moins.", delta="lignes « équivalentes »", delta_color="off")
k[3].metric("Volatilité", ui.pct(profil.get("volatilite"), 0), "annuelle, sur 3 ans", delta_color="off")
k[4].metric("Perte maximale", ui.pct(risques.perte_maximale(r_p), 0),
            f"pire mois : {ui.pct(pire, 0)}" + (f" ({date_pire:%m/%Y})" if date_pire is not None else ""),
            delta_color="off", help="Plus forte baisse depuis un sommet sur 3 ans, avec les poids d'aujourd'hui.")
for t, message in risques.garde_fous(w, sc["secteur"], r):
    st.warning(f"{noms[t]} {message}" if t else message, icon=":material/warning:")
if risques.garde_fous(w, sc["secteur"], r):
    st.caption("Seuils réglables dans config/strategie.json (suivi, garde_fous).")

# --------------------------------------------------------------------------- scénarios
st.subheader("Scénarios de choc")
fonds_or = {t: "or" for t in w.index if re.search(r"\bgold\b|\bor\b", noms[t], re.I)}
sce = risques.scenarios(w, r, bench, fonds_or)
sce["ligne"] = sce["ligne"].map(lambda t: noms.get(t, t) if isinstance(t, str) else "—")
ui.tableau(ui.as_pct_cols(sce, ["impact", "effet_ligne"]), hide_index=True, width="stretch", column_config={
    "scenario": "Scénario", "impact": ui.PCT("Effet sur le portefeuille"),
    "ligne": st.column_config.TextColumn("Ligne la plus touchée"), "effet_ligne": ui.PCT("Dont cette ligne"),
})
st.caption(f"Marché : chaque ligne bouge selon sa sensibilité passée à l'indice ({BENCHMARKS.get(bench, bench)}) ; "
           "une ligne sans historique suffisant compte pour 1. Dollar : les lignes cotées en dollar perdent 10 % en euros "
           "(l'or et l'uranium, cotés en euros, dépendent aussi du dollar : l'effet réel est plus large). Ordres de "
           "grandeur, pas des prévisions.")

# --------------------------------------------------------------------------- répartitions
g, d = st.columns(2)
with g.container(border=True):
    st.markdown("**Poids par ligne**")
    ui.show(ui.hbar(pd.Series(w.values, index=[noms[t] for t in w.index]), fmt=".1%"), key="risques_poids")
with d.container(border=True):
    st.markdown("**Part du risque**")
    contrib = profil.get("contribution_risque", pd.Series(dtype=float))
    if len(contrib):
        ui.show(ui.hbar(pd.Series(contrib.values, index=[noms.get(t, t) for t in contrib.index]), fmt=".1%"),
                key="risques_contrib")
        st.caption("Part de la volatilité du portefeuille due à chaque ligne : poids, volatilité propre et "
                   "corrélation avec les autres.")
g, d = st.columns(2)
with g.container(border=True):
    st.markdown("**Devises de cotation**")
    ui.show(ui.hbar(risques.devises(w), fmt=".0%"), key="risques_devises")
with d.container(border=True):
    st.markdown("**Secteurs**")
    secteurs = w.groupby(lambda t: sc["secteur"].get(t, "Autre")).sum()
    ui.show(ui.hbar(secteurs, fmt=".0%"), key="risques_secteurs")

# --------------------------------------------------------------------------- corrélations
st.subheader("Corrélations")
corr = profil.get("correlation")
if corr is not None and len(corr) > 1:
    st.caption(f"Corrélation moyenne entre vos lignes : {ui.num(risques.correlation_moyenne(r, list(w.index)), 2)} "
               "(0 : indépendantes, 1 : elles montent et baissent ensemble). Rendements quotidiens en euros sur 3 ans.")
    ui.show(ui.corr_heatmap(corr, labels=noms, height=420), key="risques_corr")

# --------------------------------------------------------------------------- simulation
st.subheader("Simuler un changement")
st.caption("Et si j'ajoute une ligne, la retire ou change son poids ? Les autres lignes sont ajustées en proportion "
           "pour rester à 100 %. Mesures du passé : elles montrent où le risque se concentre, pas ce qui arrivera.")


@st.cache_data(ttl=3600, show_spinner=False)
def simuler(version, poids_items, cible, poids, bench, fonds_items):
    return simulation.simuler(pd.Series(dict(poids_items)), cible, poids, ui.screener(), bench, dict(fonds_items))


choix = list(dict.fromkeys(list(w.index) + list(sc.sort_values("rang").index)))
demande = st.session_state.pop("simulation_ticker", None)  # bouton « Simuler » de la fiche valeur
c1, c2 = st.columns([3, 1])
cible = c1.selectbox("Ligne à simuler", choix, index=choix.index(demande) if demande in choix else None,
                     format_func=lambda t: f"{sc['nom'].get(t, t)} ({t})" + (" · détenue" if t in w.index else ""),
                     placeholder="Choisir une valeur de l'univers ou une de vos lignes…")
if cible:
    actuel = float(w.get(cible, 0.0))
    poids = c2.number_input("Poids visé (%)", min_value=0.0, max_value=50.0, step=0.5,
                            value=round(actuel * 100, 1) if actuel else 5.0,
                            help="0 pour simuler la vente complète de la ligne.") / 100
    noms_sim = {t: str(sc["nom"].get(t, t)) for t in [*w.index, cible]}
    with st.spinner("Simulation…"):
        res = simuler(ui.data_version(), tuple(w.items()), cible, poids, bench, tuple(fonds_or.items()))
    m = res["mesures"]

    def texte(indicateur, v):
        if pd.isna(v):
            return "—"
        if indicateur.startswith("Nombre"):
            return ui.num(v, 1)
        if indicateur.startswith("Corrélation"):
            return ui.num(v, 2)
        return ui.pct(v, 1)

    def ecart(indicateur, a, b):
        if pd.isna(a) or pd.isna(b):
            return "—"
        if indicateur.startswith("Nombre"):
            return f"{b - a:+.1f}".replace(".", ",")
        if indicateur.startswith("Corrélation"):
            return f"{b - a:+.2f}".replace(".", ",")
        return f"{(b - a) * 100:+.1f} pt".replace(".", ",")

    tableau = pd.DataFrame([{"Indicateur": k, "Avant": texte(k, a), "Après": texte(k, b), "Écart": ecart(k, a, b)}
                            for k, (a, b) in m[["avant", "apres"]].iterrows()])
    titre = f"{noms_sim[cible]} : {ui.pct(actuel, 1)} → {ui.pct(poids, 1)}"
    st.markdown(f"**{titre}**")
    ui.tableau(tableau, hide_index=True, width="stretch")
    deja = {m for _, m in risques.garde_fous(w, sc["secteur"])}
    for t, message in risques.garde_fous(res["poids"]["apres"].loc[lambda x: x > 0], sc["secteur"]):
        if message not in deja:
            st.warning("Après ce changement : " + (f"{noms_sim.get(t, t)} {message}" if t else message),
                       icon=":material/warning:")
    corr_cible = res["correlations"]
    if len(corr_cible):
        proche = corr_cible.index[0]
        if corr_cible.iloc[0] >= 0.6:
            st.warning(f"{noms_sim[cible]} évolue comme {noms_sim.get(proche, proche)} (corrélation de "
                       f"{ui.num(corr_cible.iloc[0], 2)} sur 3 ans) : ce changement renforce un pari déjà présent "
                       "plutôt qu'il ne diversifie.", icon=":material/link:")
    g, d = st.columns(2)
    with g.container(border=True):
        st.markdown(f"**Corrélation de {noms_sim[cible]} avec vos lignes**")
        if len(corr_cible):
            ui.show(ui.hbar(pd.Series(corr_cible.values, index=[noms_sim.get(t, t) for t in corr_cible.index]),
                            fmt=".2f"), key="simulation_corr")
        else:
            st.caption("Pas assez d'historique commun pour la calculer.")
    with d.container(border=True):
        st.markdown("**Secteurs et devises, avant → après**")
        rep = pd.concat([res["secteurs"].assign(type="Secteur"), res["devises"].assign(type="Devise")])
        rep = rep[(rep["avant"] > 0.0005) | (rep["apres"] > 0.0005)].rename_axis("Répartition").reset_index()
        ui.tableau(ui.as_pct_cols(rep, ["avant", "apres"]), hide_index=True, width="stretch", column_config={
            "type": "Type", "avant": ui.PCT("Avant"), "apres": ui.PCT("Après")})
    st.caption("Ce simulateur ne dit pas s'il faut acheter : il montre ce que la ligne change au risque du "
               "portefeuille. La décision reste la vôtre, après lecture de la thèse.")
