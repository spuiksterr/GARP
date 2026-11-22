"""Construction de portefeuille : un portefeuille construit par des règles, comme source d'idées et point de comparaison."""
import pandas as pd
import streamlit as st

from pf import dirigeants, ui
from pf import investisseurs as inv
from pf import portfolio as pfo
from pf import watchlist as wl
from pf.config import load_strategy, save_strategy

sc = ui.require_data()
strat = load_strategy()
cfg = strat["construction"]
version = ui.data_version()

st.title("Construction de portefeuille")
st.caption("Un portefeuille diversifié construit uniquement par des règles, à partir de la méthode de notation de votre "
           "choix. Il sert de point de comparaison et de liste d'idées à étudier : un bon classement n'est pas une "
           "recommandation, seule l'analyse d'une valeur (/analyse-valeur) peut justifier un achat.")

# --------------------------------------------------------------------------- méthode de notation
PERSO = "perso"
libelles = {k: v[0] for k, v in pfo.NOTATIONS.items()} | {PERSO: "Personnalisée"}
poids_cfg = {k: float(v) for k, v in (cfg.get("notation") or {"score": 1}).items()}
defaut = next((k for k, v in pfo.NOTATIONS.items() if v[2] == poids_cfg), PERSO)

with st.container(border=True):
    choix = st.segmented_control("Méthode de notation mise en avant", list(libelles), format_func=libelles.get,
                                 default=defaut, key="cp_notation") or defaut
    if choix != PERSO:
        poids = pfo.NOTATIONS[choix][2]
        st.caption(pfo.NOTATIONS[choix][1])
    else:
        st.caption("Composez votre propre note : chaque curseur fixe le poids d'une composante. Toutes sont ramenées à "
                   "leur rang dans l'univers (0 à 100), donc comparables.")
        cols = st.columns(4)
        poids = {}
        for i, (cle, lib) in enumerate(pfo.COMPOSANTES.items()):
            poids[cle] = cols[i % 4].slider(lib, 0, 100, int(round(poids_cfg.get(cle, 0) * 100)), 5,
                                            key=f"cp_poids_{cle}", format="%d %%") / 100
        if sum(poids.values()) == 0:
            st.warning("Tous les poids sont à zéro : le score composite est utilisé.")
            poids = {"score": 1.0}

# --------------------------------------------------------------------------- réglages, repliés
g, d = st.columns(2)
with g.expander("Garde-fous de qualité", icon=":material/verified:"):
    crit_min = st.slider("Critères de qualité minimum", 0, 6, int(cfg.get("criteres_min", 4)), format="%d sur 6",
                         help="Part des six critères remplie au moins égale à ce seuil, sur les critères évalués (une "
                              "banque n'en a que deux : elle doit les remplir tous les deux pour un seuil de 4 sur 6).")
    sans_faible = st.toggle("Écarter les moats estimés faibles", value=bool(cfg.get("exclure_moat_faible", True)))
    cyc = st.slider("Part maximale des secteurs cycliques", 0, 100, int(round((cfg.get("cycliques_max") or 1) * 100)), 5,
                    format="%d %%", help="Énergie et infrastructures, matériaux et chimie, banques : leurs résultats "
                                         "suivent le cycle, et au sommet ils paraissent bon marché. Plafond en nombre de "
                                         "lignes et en poids ; 100 % : pas de plafond.") / 100
    exclure = st.multiselect("Valeurs à écarter", sorted(sc.index), placeholder="Aucune",
                             format_func=lambda t: f"{sc.loc[t, 'nom']} ({t})")
with d.expander("Diversification et pondération", icon=":material/tune:"):
    c = st.columns(2)
    n = c[0].slider("Nombre de lignes", 10, 40, int(cfg["nb_lignes"]))
    max_sec = c[1].slider("Lignes maximum par secteur", 2, 10, int(cfg["max_par_secteur"]))
    sect_max = c[0].slider("Poids maximal par secteur", 10, 50, int(cfg["secteur_max"] * 100), 5, format="%d %%") / 100
    methode = c[1].selectbox("Pondération", list(pfo.METHODES), index=list(pfo.METHODES).index(cfg["methode"]),
                             format_func=pfo.METHODES.get, help="« Note » : la note de la méthode choisie × 1/volatilité.")
    w_min = c[0].slider("Poids minimal par ligne", 0.5, 5.0, cfg["poids_min"] * 100, 0.5, format="%.1f %%") / 100
    w_max = c[1].slider("Poids maximal par ligne", 3.0, 15.0, cfg["poids_max"] * 100, 0.5, format="%.1f %%") / 100
    imposer_pea = st.toggle("Imposer une part PEA", value=cfg.get("part_pea") not in (None, 0, 1),
                            help="Sinon, la répartition entre PEA et compte-titres découle des notes.")
    part_pea = st.slider("Part du PEA", 5, 95, int((cfg.get("part_pea") or 0.5) * 100), 5, format="%d %%") / 100 \
        if imposer_pea else None

cycliques_max = cyc if cyc < 1 else None
resume = [f"{n} lignes", f"critères ≥ {crit_min}/6" if crit_min else "sans plancher de critères",
          "moats faibles écartés" if sans_faible else "moats faibles admis",
          f"cycliques ≤ {ui.pct(cyc, 0)}" if cycliques_max is not None else "cycliques libres",
          f"{ui.pct(sect_max, 0)} max. par secteur", pfo.METHODES[methode].split(" (")[0],
          f"PEA {ui.pct(part_pea, 0)}" if part_pea is not None else "PEA libre"]
st.caption(" · ".join(resume))


# --------------------------------------------------------------------------- calculs (en cache)
@st.cache_data(show_spinner=False)
def construire(version, poids_items, n, max_sec, part_pea, exclure, crit_min, sans_faible, cycliques_max, methode,
               w_min, w_max, sect_max):
    note = pfo.note_construction(sc, dict(poids_items))
    tickers = pfo.select(sc, n, max_sec, part_pea, exclude=list(exclure), criteres_min=crit_min,
                         exclure_moat_faible=sans_faible, cycliques_max=cycliques_max, note=note)
    if not tickers:
        return pd.Series(dtype=float), note
    w = pfo.weight(tickers, sc, methode, w_min, w_max, sect_max, cycliques_max=cycliques_max, note=note)
    if part_pea is not None:
        env = sc.reindex(w.index)["enveloppe"]
        for e, cible in (("PEA", part_pea), ("CTO", 1 - part_pea)):
            m = env == e
            if m.any():
                w[m] = w[m] / w[m].sum() * cible
        w = w / w.sum()
    return w.sort_values(ascending=False), note


@st.cache_data(show_spinner=False)
def profil_risque(version, poids_items):
    return pfo.risk_profile(pd.Series(dict(poids_items)))


@st.cache_data(ttl=600, show_spinner=False)
def detenteurs(version):
    return inv.detenteurs_par_ticker()


@st.cache_data(show_spinner=False)
def comparer_methodes(version, n, max_sec, part_pea, exclure, crit_min, sans_faible, cycliques_max):
    """Valeurs retenues par chaque méthode proposée, avec les mêmes garde-fous."""
    out = {}
    for lib, _, p in pfo.NOTATIONS.values():
        note = pfo.note_construction(sc, p)
        out[lib] = pfo.select(sc, n, max_sec, part_pea, exclude=list(exclure), criteres_min=crit_min,
                              exclure_moat_faible=sans_faible, cycliques_max=cycliques_max, note=note)
    return out


reglages = dict(n=n, max_sec=max_sec, part_pea=part_pea, exclure=tuple(exclure), crit_min=crit_min,
                sans_faible=sans_faible, cycliques_max=cycliques_max)
with st.spinner("Construction…"):
    w, note = construire(version, tuple(sorted(poids.items())), methode=methode, w_min=w_min, w_max=w_max,
                         sect_max=sect_max, **reglages)
if w.empty:
    st.warning("Aucune valeur ne passe ces règles : assouplissez les garde-fous de qualité.")
    st.stop()
if len(w) < n:
    st.info(f"Seules {len(w)} valeurs passent ces règles (sur {n} demandées).", icon=":material/info:")

model_w = pfo.model_weights()
fonds = sc.reindex(model_w.index)["statut"].eq("Fonds")
actions_w = model_w[~fonds]
actions_w = actions_w / actions_w.sum() if actions_w.sum() > 0 else actions_w
risque = profil_risque(version, tuple(w.items()))
secteurs = sc.reindex(w.index)["secteur"]
communes = w.index.intersection(model_w.index)

# --------------------------------------------------------------------------- chiffres clés
k = st.columns(5)
k[0].metric("Lignes", len(w), f"{len(communes)} déjà détenue(s)" if len(communes) else "aucune déjà détenue",
            delta_color="off")
k[1].metric(f"Note « {libelles[choix]} »", ui.num(float((note.reindex(w.index).clip(upper=100) * w).sum()), 0),
            "sur 100 (rang)", delta_color="off")
tri = pd.to_numeric(sc.reindex(w.index)["tri_implicite"], errors="coerce")
k[2].metric("TRI implicite", ui.pct(float((tri * w).sum() / w[tri.notna()].sum())) if tri.notna().any() else "—",
            "par an, au prix actuel", delta_color="off")
k[3].metric("Volatilité attendue", ui.pct(risque.get("volatilite")), "sur 3 ans de cours", delta_color="off")
k[4].metric("Secteurs cycliques", ui.pct(float(w[secteurs.isin(pfo.CYCLIQUES)].sum()), 0),
            f"{secteurs.nunique()} secteurs", delta_color="off")

onglet_sel, onglet_meth, onglet_comp = st.tabs(["Sélection", "Comparer les méthodes", "Face à mon portefeuille"])

# --------------------------------------------------------------------------- sélection
with onglet_sel:
    qui = detenteurs(version)
    suivies = set(wl.load_watchlist().index)
    t = sc.reindex(w.index).copy()
    t["poids"] = w
    t["note"] = note.reindex(w.index).clip(upper=100)
    t["investisseurs"] = [len(qui.get(x, [])) for x in t.index]

    def signal_dirigeants(ticker: str) -> str:
        """Signal des déclarations déjà lues depuis la fiche (aucun accès réseau ici)."""
        tx = dirigeants.en_cache(ticker)
        if tx is None:
            return ""
        signal = dirigeants.synthese(tx)["signal"]
        return {"Aucune transaction en bourse": "", "Ventes seulement": "Ventes"}.get(signal, signal)

    t["dirigeants"] = [signal_dirigeants(x) for x in t.index]
    t["detenue"] = t.index.isin(model_w.index)
    show = ui.as_pct_cols(t, ["poids", "ecart_p_fcf_historique", "tri_implicite"])
    show = show[["nom", "poids", "note", "score", "buffett", "munger", "fisher", "smith", "criteres", "moat",
                 "ecart_p_fcf_historique", "tri_implicite", "investisseurs", "dirigeants", "detenue", "secteur",
                 "enveloppe"]]
    show.insert(0, "symbole", show.index)

    # Cases cochées = valeurs de la watchlist (comme dans le screener), clic sur une cellule = fiche.
    cle = "idees_tableau"
    cle_tableau = f"{cle}_{st.session_state.get(cle, 0)}"
    affichees = st.session_state.get("idees_affichees", [])
    etat = st.session_state.get(cle_tableau)
    if etat and affichees:
        cochees = {affichees[i] for i in etat["selection"]["rows"] if i < len(affichees)}
        a_ajouter, retirees = sorted(cochees - suivies), sorted((suivies & set(affichees)) - cochees)
        if len(a_ajouter) > 15 or len(retirees) > 15:
            st.warning("Trop de valeurs cochées ou décochées d'un coup : la watchlist n'a pas été modifiée. "
                       "Cochez les lignes une par une.", icon=":material/block:")
            a_ajouter, retirees = [], []
        for x in ui.ajouter_watchlist(a_ajouter):
            st.toast(f"{sc['nom'].get(x, x)} ajoutée à la watchlist.", icon=":material/star:")
            suivies.add(x)
        for x in retirees:
            wl.retirer(x)
            suivies.discard(x)
            st.toast(f"{sc['nom'].get(x, x)} retirée de la watchlist.", icon=":material/star_border:")
        cellules = [i for i, _ in etat["selection"]["cells"] if i < len(affichees)]
        if cellules:
            st.session_state["fiche_ticker"] = affichees[cellules[0]]
            st.session_state[cle] = st.session_state.get(cle, 0) + 1
            st.session_state.pop("idees_affichees", None)
            st.switch_page("vues/fiche.py")
    st.session_state["idees_affichees"] = list(show.index)
    st.session_state[cle_tableau] = {"selection": {"rows": [i for i, x in enumerate(show.index) if x in suivies],
                                                   "columns": [], "cells": []}}
    regard = lambda nom, aide: st.column_config.NumberColumn(nom, format="%d", width="small", help=aide)  # noqa: E731
    ui.tableau(show, width="stretch", height=min(820, 35 * len(show) + 38), on_select="rerun",
               selection_mode=["single-cell", "multi-row"], key=cle_tableau, hide_index=True, column_config={
                   "symbole": st.column_config.TextColumn("Ticker", pinned=True),
                   "nom": st.column_config.TextColumn("Valeur", pinned=True), "poids": ui.PCT("Poids"),
                   "note": ui.SCORE(f"Note {libelles[choix]}", "Note de la méthode choisie : rang dans l'univers, sur 100"),
                   "score": ui.SCORE("Score", "Score composite de l'outil"),
                   "buffett": regard("Buffett", "Regard de Buffett, de 1 à 5"),
                   "munger": regard("Munger", "Regard de Munger, de 1 à 5"),
                   "fisher": regard("Fisher", "Regard de Fisher, de 1 à 5"),
                   "smith": regard("Smith", "Regard de Terry Smith, de 1 à 5"),
                   "criteres": st.column_config.TextColumn("Critères", help="Critères de qualité remplis sur évalués"),
                   "moat": "Moat", "ecart_p_fcf_historique": ui.PCT(
                       "P/FCF / habituel", "P/FCF actuel comparé à sa médiane historique : négatif = moins cher", 0),
                   "tri_implicite": ui.PCT("TRI implicite"),
                   "investisseurs": st.column_config.NumberColumn(
                       "Grands inv.", format="%d", help="Grands investisseurs suivis qui la détiennent (page « Grands "
                                                        "investisseurs »)"),
                   "dirigeants": st.column_config.TextColumn(
                       "Dirigeants", help="Achats ou ventes en bourse des dirigeants sur 12 mois (sociétés américaines "
                                          "dont la fiche a déjà lu les déclarations)"),
                   "detenue": st.column_config.CheckboxColumn("Détenue", help="Dans votre portefeuille"),
                   "secteur": "Secteur", "enveloppe": "Compte",
               })
    st.caption("Cochez une ligne pour l'ajouter à la watchlist, cliquez sur une cellule pour ouvrir la fiche. Regards de "
               "1 (faible) à 5 (excellent) : détail et corrections dans la page « Quatre regards ».")

# --------------------------------------------------------------------------- comparer les méthodes
with onglet_meth:
    st.caption("La sélection de chaque méthode, avec vos garde-fous et votre diversification. Une valeur retenue par "
               "beaucoup de méthodes plaît sous plusieurs angles : c'est souvent la plus intéressante à étudier.")
    par_methode = comparer_methodes(version, **reglages)
    lignes = sorted({x for v in par_methode.values() for x in v})
    m = pd.DataFrame({lib: ["●" if x in v else "" for x in lignes] for lib, v in par_methode.items()}, index=lignes)
    m.insert(0, "methodes", (m == "●").sum(axis=1))
    m.insert(0, "nom", sc.reindex(m.index)["nom"])
    m["detenue"] = m.index.isin(model_w.index)
    m = m.sort_values(["methodes", "nom"], ascending=[False, True])
    m.insert(0, "symbole", m.index)
    compteur = "cp_meth"
    ev = ui.tableau(m, width="stretch", height=min(620, 35 * len(m) + 38), hide_index=True, on_select="rerun",
                    selection_mode="single-cell", key=f"{compteur}_{st.session_state.get(compteur, 0)}",
                    column_config={"symbole": st.column_config.TextColumn("Ticker", pinned=True),
                                   "nom": st.column_config.TextColumn("Valeur", pinned=True),
                                   "methodes": st.column_config.ProgressColumn(
                                       "Méthodes", min_value=0, max_value=len(par_methode), format="%d",
                                       help="Nombre de méthodes qui la retiennent"),
                                   "detenue": st.column_config.CheckboxColumn("Détenue")})
    ui.fiche_au_clic(m, ev, compteur, lignes=False)

# --------------------------------------------------------------------------- face à mon portefeuille
with onglet_comp:
    g, d = st.columns(2)
    with g:
        risque_m = profil_risque(version, tuple(actions_w.items())) if len(actions_w) else {}
        comp = pd.DataFrame({"Construction": pfo.characteristics(w, sc), "Mes actions": pfo.characteristics(actions_w, sc)})
        comp.loc["Volatilité attendue"] = [risque.get("volatilite"), risque_m.get("volatilite")]
        comp.loc["Nombre effectif de lignes"] = [risque.get("nombre_effectif"), risque_m.get("nombre_effectif")]
        fmt = comp.copy().astype(object)
        for idx in fmt.index:
            fmt.loc[idx] = [ui.num(v, 1) if idx in ("PER prospectif", "Nombre effectif de lignes") else ui.pct(v)
                            for v in comp.loc[idx]]
        st.markdown(f"**Indicateurs moyens** ({len(communes)} valeur(s) en commun)")
        ui.tableau(fmt, width="stretch")
        part_fonds = float(model_w[fonds].sum())
        if part_fonds > 0:
            st.caption(f"Vos ETF et ETC ({ui.pct(part_fonds, 0)} de vos poids cibles : "
                       f"{', '.join(sc['nom'].get(x, x) for x in model_w[fonds].index)}) sont laissés de côté : ils "
                       "n'ont pas ces indicateurs.")
    with d:
        st.markdown("**Par secteur**")
        repartition = pfo.breakdown(w, sc, "secteur")
        fig = ui.hbar(repartition, highlight={s: ui.GRIS for s in repartition.index if s in pfo.CYCLIQUES})
        fig.update_layout(margin=dict(r=60))  # place pour le pourcentage de la plus longue barre
        ui.show(fig, key="idees_secteurs")
        st.caption("En gris : secteurs cycliques.")

st.divider()
c = st.columns([1, 2])
if c[0].button("Enregistrer ces réglages par défaut", icon=":material/save:",
               help="Ils servent aussi au backtest du portefeuille systématique et à la commande « construire »."):
    strat["construction"].update({"nb_lignes": n, "methode": methode, "part_pea": part_pea, "secteur_max": sect_max,
                                  "poids_min": w_min, "poids_max": w_max, "max_par_secteur": max_sec,
                                  "criteres_min": crit_min, "exclure_moat_faible": sans_faible,
                                  "cycliques_max": cycliques_max, "notation": {k: v for k, v in poids.items() if v > 0}})
    save_strategy(strat)
    st.cache_data.clear()
    st.toast("Réglages enregistrés dans config/strategie.json")
c[1].caption("Ce portefeuille ne remplace pas vos poids cibles : vos apports restent guidés par "
             "profil/portefeuille_modele.csv. Pour faire entrer une idée : l'étudier (/analyse-valeur), fixer un prix "
             "visé dans sa fiche, puis modifier vos poids cibles.")
