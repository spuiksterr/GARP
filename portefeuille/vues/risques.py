"""Risques & équilibre : répartition, concentration, chocs, corrélations, équilibre d'apport, poids cibles et simulation."""
import re
import shutil
from datetime import date

import pandas as pd
import streamlit as st

from pf import portfolio as pfo
from pf import positions, risques, simulation, tracker, ui
from pf.config import BENCHMARKS, chemin_modele, load_strategy, write_csv_fr

sc = ui.require_data()
mp = ui.model()
w_cibles = pfo.model_weights()
strat = load_strategy()
st.title("Risques & équilibre")

w, source = risques.poids_actuels()
if w.empty:
    st.info("Ce portefeuille ne contient encore aucune ligne : importez-le ou ajoutez des opérations.", icon=":material/info:")
    st.stop()
bench = strat.get("suivi", {}).get("benchmark", "IWDA.AS")
noms = {t: str(sc["nom"].get(t, t)) for t in w.index}
names_sc = sc["nom"].astype(str).to_dict()
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

# --------------------------------------------------------------------------- chiffres clés & garde-fous
k = st.columns(5)
k[0].metric("Plus grosse ligne", ui.pct(conc["poids_plus_grosse"], 0), noms[conc["plus_grosse"]], delta_color="off", delta_arrow="off")
k[1].metric("Trois premières lignes", ui.pct(conc["trois_premieres"], 0), f"{len(w)} lignes au total", delta_color="off", delta_arrow="off")
k[2].metric("Nombre effectif de lignes", ui.num(conc["nombre_effectif"], 1),
            help="Diversification réelle : un portefeuille de 10 lignes égales vaut 10 ; s'il est dominé par une ligne, "
                 "il vaut bien moins.", delta="lignes « équivalentes »", delta_color="off", delta_arrow="off")
k[3].metric("Volatilité", ui.pct(profil.get("volatilite"), 0),
            f"diversification : {ui.num(profil.get('ratio_diversification'), 2)}" if profil.get("ratio_diversification")
            else "annuelle, sur 3 ans", delta_color="off", delta_arrow="off",
            help="Volatilité annuelle sur 3 ans (MSCI World ~14-16 %). Ratio de diversification = volatilité moyenne "
                 "des lignes / volatilité du portefeuille : plus il est élevé, plus les lignes se compensent.")
k[4].metric("Perte maximale", ui.pct(risques.perte_maximale(r_p), 0),
            f"pire mois : {ui.pct(pire, 0)}" + (f" ({date_pire:%m/%Y})" if date_pire is not None else ""),
            delta_color="off", delta_arrow="off", help="Plus forte baisse depuis un sommet sur 3 ans, avec les poids d'aujourd'hui.")
alertes_conc = risques.garde_fous(w, sc["secteur"], r)
for t, message in alertes_conc:
    st.warning(f"{noms[t]} {message}" if t else message, icon=":material/warning:")
if alertes_conc:
    st.caption("Seuils réglables dans config/strategie.json (suivi, garde_fous).")

fonds_or = {t: "or" for t in w.index if re.search(r"\bgold\b|\bor\b", noms[t], re.I)}
tab_rep, tab_eq, tab_cibles, tab_sim = st.tabs(
    ["Répartition & risques", "Équilibre & apport", "Poids cibles", "Simuler un changement"])

# --------------------------------------------------------------------------- 1. Répartition & risques
with tab_rep:
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
        st.markdown("**Secteurs**")
        secteurs = w.groupby(lambda t: sc["secteur"].get(t, "Autre")).sum()
        ui.show(ui.hbar(secteurs, fmt=".0%"), key="risques_secteurs")
    with d.container(border=True):
        st.markdown("**Pays du siège**")
        pays = w.groupby(lambda t: sc["pays"].get(t, "Autre")).sum()
        ui.show(ui.hbar(pays, fmt=".0%"), key="risques_pays")

    g, d = st.columns(2)
    with g.container(border=True):
        st.markdown("**Devises de cotation**")
        ui.show(ui.hbar(risques.devises(w), fmt=".0%"), key="risques_devises")
    with d.container(border=True):
        st.markdown("**Comptes et poches**")
        cartes = []
        if not mp.empty and "enveloppe" in mp.columns:
            env_map = mp["enveloppe"].to_dict()
            env = w.groupby(lambda t: env_map.get(t, sc["enveloppe"].get(t, "CTO"))).sum().sort_values(ascending=False)
            cartes += [({"PEA": "PEA", "CTO": "Compte-titres"}.get(e, e), v) for e, v in env.items()]
        if not mp.empty and "poche" in mp.columns:
            poche_map = mp["poche"].to_dict()
            poches = w.groupby(lambda t: poche_map.get(t, "Autre")).sum().sort_values(ascending=False)
            cartes += [(f"Poche {str(p).lower()}", v) for p, v in poches.items() if p]
        if cartes:
            for col, (label, v) in zip(st.columns(len(cartes)), cartes):
                col.metric(label, ui.pct(v), border=True)
        else:
            st.caption("Importez votre portefeuille pour voir la répartition par compte et par poche.")

    st.subheader("Scénarios de choc")
    sce = risques.scenarios(w, r, bench, fonds_or)
    tickers_sce = sce["ligne"].copy()
    sce["ligne"] = sce["ligne"].map(lambda t: noms.get(t, t) if isinstance(t, str) else "—")
    ev_sce = ui.tableau(ui.as_pct_cols(sce, ["impact", "effet_ligne"]), hide_index=True, width="stretch",
                        on_select="rerun", selection_mode="single-cell", key=ui.cle_tableau("risques_sce"), column_config={
        "scenario": "Scénario", "impact": ui.PCT("Effet sur le portefeuille"),
        "ligne": st.column_config.TextColumn("Ligne la plus touchée"), "effet_ligne": ui.PCT("Dont cette ligne"),
    })
    cellules_sce = ev_sce.selection.cells if ev_sce and ev_sce.selection else []
    if cellules_sce:
        tk = tickers_sce.iloc[cellules_sce[0][0]]
        st.session_state["risques_sce"] = st.session_state.get("risques_sce", 0) + 1
        if isinstance(tk, str) and tk in sc.index:
            st.session_state["fiche_ticker"] = tk
            st.switch_page("vues/fiche.py")
    st.caption(f"Marché : chaque ligne bouge selon sa sensibilité passée à l'indice ({BENCHMARKS.get(bench, bench)}) ; "
               "une ligne sans historique suffisant compte pour 1. Dollar : les lignes cotées en dollar perdent 10 % en euros "
               "(l'or et l'uranium, cotés en euros, dépendent aussi du dollar : l'effet réel est plus large). Ordres de "
               "grandeur, pas des prévisions.")

    st.subheader("Corrélations")
    corr = profil.get("correlation")
    if corr is not None and len(corr) > 1:
        st.caption(f"Corrélation moyenne entre vos lignes : {ui.num(risques.correlation_moyenne(r, list(w.index)), 2)} "
                   "(0 : indépendantes, 1 : elles montent et baissent ensemble). Rendements quotidiens en euros sur 3 ans.")
        ui.show(ui.corr_heatmap(corr, labels=noms, height=420), key="risques_corr")

# --------------------------------------------------------------------------- 2. Équilibre & apport
with tab_eq:
    st.caption("Une proposition, pas une consigne : comparer vos poids réels à vos poids cibles, et voir comment un "
               "apport rapprocherait le portefeuille de sa cible sans rien vendre. Rien n'est enregistré ici.")
    pos = positions.positions()
    if pos.empty or w_cibles.empty:
        st.info("Pour comparer poids réels et cibles, G.A.R.P a besoin de vos quantités : importez votre portefeuille "
                "avec quantités, ou enregistrez vos opérations dans « Opérations ».", icon=":material/info:")
    else:
        seuil = float(strat["suivi"]["seuil_reequilibrage"])
        ecarts = tracker.drift_alerts(pos, w_cibles, seuil)
        total = float(pos["valeur_eur"].sum())
        ecarts["nom"] = [names_sc.get(t, t) for t in ecarts.index]
        ecarts["a_ajuster_eur"] = -ecarts["ecart"] * total
        hors = ecarts[ecarts["action"] != "Dans la cible"]
        km = st.columns(3)
        km[0].metric("Valeur du portefeuille", ui.eur(total, 0), border=True)
        km[1].metric("Lignes loin de leur cible", len(hors), border=True,
                     help=f"Écart de plus de {ui.num(seuil * 100, 0)} points entre poids réel et poids cible.")
        km[2].metric("Écart le plus fort", f"{ui.num(ecarts['ecart'].abs().max() * 100, 1)} pts", border=True)
        vue = ecarts.sort_values("ecart")[["nom", "poids_reel", "poids_cible", "ecart", "a_ajuster_eur", "action"]].copy()
        vue.insert(0, "symbole", vue.index)
        ev_eq = ui.tableau(ui.as_pct_cols(vue, ["poids_reel", "poids_cible", "ecart"]), hide_index=True, width="stretch",
                           height=min(520, 35 * len(vue) + 38), on_select="rerun", selection_mode="single-cell",
                           key=ui.cle_tableau("mp_eq_ecarts"), column_config={
                               "symbole": st.column_config.TextColumn("Ticker", pinned=True),
                               "nom": st.column_config.TextColumn("Valeur", pinned=True),
                               "poids_reel": ui.PCT("Poids réel"), "poids_cible": ui.PCT("Poids cible"),
                               "ecart": ui.PCT("Écart (points)", d=1),
                               "a_ajuster_eur": st.column_config.NumberColumn(
                                   "Pour revenir à la cible (€)", format="%.0f",
                                   help="Positif : montant qu'il faudrait acheter. Négatif : montant au-dessus de la cible."),
                               "action": "Proposition"})
        ui.fiche_au_clic(vue, ev_eq, "mp_eq_ecarts")
        st.markdown("**Si vous faites un apport**")
        compte_principal = pfo.compte_principal(w_cibles, mp)
        ca = st.columns([1.2, 1, 1.2])
        montant = ca[0].number_input("Montant (€)", min_value=0.0, value=1000.0, step=100.0, key="eq_montant")
        compte = ca[1].segmented_control("Compte", tracker.COMPTES, default=compte_principal,
                                         key="eq_compte") or compte_principal
        min_order = ca[2].number_input("Ordre minimum (€)", min_value=0.0,
                                       value=float(strat["suivi"]["ordre_min_eur"]), step=50.0, key="eq_min")
        ecartees = pfo.lignes_a_ecarter(sc, w_cibles.index)
        plan = tracker.contribution_plan(montant, compte, w_cibles.drop(index=list(ecartees)), mp["enveloppe"], pos=pos,
                                         min_order=min_order)
        if plan.empty:
            st.caption("Aucune répartition proposée : montant trop faible face à l'ordre minimum, ou lignes du compte "
                       "déjà au-dessus de leur cible.")
        else:
            plan.insert(1, "nom", plan["ticker"].map(lambda t: names_sc.get(t, t)))
            ev_plan = ui.tableau(ui.as_pct_cols(plan, ["poids_cible_compte", "poids_apres"]).drop(columns=["ticker"]),
                                 hide_index=True, width="stretch", on_select="rerun", selection_mode="single-cell",
                                 key=ui.cle_tableau("mp_eq_plan"), column_config={
                                     "nom": "Valeur", "quantite": st.column_config.NumberColumn("Quantité", format="%.4g"),
                                     "cours_eur": st.column_config.NumberColumn("Cours €", format="%.2f"),
                                     "montant_eur": st.column_config.NumberColumn("Montant €", format="%.2f"),
                                     "poids_cible_compte": ui.PCT("Cible dans le compte"),
                                     "valeur_avant": st.column_config.NumberColumn("Détenu avant €", format="%.0f"),
                                     "poids_apres": ui.PCT("Poids après achat")})
            ui.fiche_au_clic(plan.set_index("ticker"), ev_plan, "mp_eq_plan")
        if ecartees:
            st.caption("Laissées de côté, le temps de revoir leur thèse : "
                       + " ; ".join(f"{names_sc.get(t, t)}, {r_}" for t, r_ in ecartees.items()) + ".")
        st.caption("Une ligne trop lourde n'a pas besoin d'être vendue : les apports suivants peuvent aller aux autres. "
                   "Proposition indicative, pas un conseil en investissement.")

# --------------------------------------------------------------------------- 3. Poids cibles
with tab_cibles:
    st.caption("Changez un poids cible, ajoutez une valeur sur la ligne vide du bas, ou supprimez une ligne (case à "
               "gauche, puis la corbeille). Les poids sont ramenés à 100 % à l'enregistrement ; thèses et conditions de "
               "vente déjà écrites sont gardées.")
    libelles = {t: f"{names_sc[t]} ({t})" for t in sorted(sc.index, key=lambda t: names_sc[t].lower())}
    for t in mp.index:  # une ligne hors des données reste modifiable sous son ticker
        libelles.setdefault(t, t)
    par_libelle = {v: k_ for k_, v in libelles.items()}
    base = pd.DataFrame({
        "valeur": [libelles[t] for t in mp.index],
        "enveloppe": [mp["enveloppe"].get(t) or "CTO" for t in mp.index] if "enveloppe" in mp else "CTO",
        "poche": [mp["poche"].get(t) or "Cœur" for t in mp.index] if "poche" in mp else "Cœur",
        "poids": [round(float(w_cibles.get(t, 0)) * 100, 2) for t in mp.index],
    })
    edite = st.data_editor(
        base, key="compo_edition", num_rows="dynamic", hide_index=True, width="stretch",
        column_config={
            "valeur": st.column_config.SelectboxColumn("Valeur", options=list(libelles.values()), required=True,
                                                       width="large"),
            "enveloppe": st.column_config.SelectboxColumn("Compte", options=["PEA", "CTO"], required=True,
                                                          default="CTO"),
            "poche": st.column_config.TextColumn("Poche", default="Cœur"),
            "poids": st.column_config.NumberColumn("Poids cible (%)", min_value=0.0, max_value=100.0, step=0.5,
                                                   format="%.1f", required=True),
        })
    total_cibles = pd.to_numeric(edite["poids"], errors="coerce").fillna(0).sum()
    doublons = edite["valeur"].dropna()[edite["valeur"].dropna().duplicated()].tolist()
    cc = st.columns([1, 3], vertical_alignment="center")
    cc[0].metric("Total saisi", f"{ui.num(total_cibles, 1)} %", border=True,
                 help="Il n'a pas besoin de faire 100 % : les poids sont ramenés à 100 % à l'enregistrement.")
    if doublons:
        cc[1].caption(f"Cité deux fois, poids cumulés à l'enregistrement : {', '.join(doublons)}.")
    if cc[1].button("Enregistrer la composition", type="primary", icon=":material/save:"):
        lignes = [(par_libelle.get(row["valeur"]), row["enveloppe"], row["poche"],
                   float(row["poids"]) if pd.notna(row["poids"]) else 0.0) for _, row in edite.iterrows()]
        try:
            nouveau = pfo.nouvelle_composition(mp, lignes, names_sc)
        except ValueError as e:
            st.error(f"Composition non enregistrée : {e}.")
        else:
            cible = chemin_modele()
            if cible.exists():
                shutil.copy2(cible, cible.with_name(f"portefeuille_modele.avant-modif-{date.today():%Y-%m-%d}.csv"))
            write_csv_fr(nouveau, cible)
            st.cache_data.clear()
            st.session_state.pop("compo_edition", None)
            st.toast(f"Composition enregistrée : {len(nouveau)} lignes.", icon=":material/check:")
            st.rerun()

# --------------------------------------------------------------------------- 4. Simuler un changement
with tab_sim:
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

        tableau = pd.DataFrame([{"Indicateur": k_, "Avant": texte(k_, a), "Après": texte(k_, b), "Écart": ecart(k_, a, b)}
                                for k_, (a, b) in m[["avant", "apres"]].iterrows()])
        titre = f"{noms_sim[cible]} : {ui.pct(actuel, 1)} → {ui.pct(poids, 1)}"
        st.markdown(f"**{titre}**")
        ui.tableau(tableau, hide_index=True, width="stretch")
        deja = {msg for _, msg in risques.garde_fous(w, sc["secteur"])}
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
