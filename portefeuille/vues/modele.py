"""Mon portefeuille : importé de votre courtier, analysé avec les outils de G.A.R.P. Chaque ligne est-elle une
bonne action, et à un bon prix ? L'équilibre n'est qu'une proposition, dans son propre onglet."""
import math
import shutil
from datetime import date

import pandas as pd
import streamlit as st

from pf import portfolio as pfo
from pf import positions, risques, tracker, ui
from pf import prix_achat as pa
from pf import watchlist as wl
from pf.config import MODELE_CSV, SELECTION_CLAUDE_CSV, load_strategy, write_csv_fr
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
            "Excel), ou ajoutez des lignes dans l'onglet « Modifier les poids ».", icon=":material/upload_file:")
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

tab_lignes, tab_repartition, tab_equilibre, tab_modifier, tab_theses = st.tabs(
    ["Analyse des lignes", "Répartition et risques", "Équilibre (proposition)", "Modifier les poids", "Thèses"])

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
            selection_mode="single-row", key="mp_lignes",
            column_config={
                "symbole": st.column_config.TextColumn("Ticker", pinned=True),
                "nom": st.column_config.TextColumn("Valeur", pinned=True), "poids": ui.PCT("Poids"),
                "verdict": ui.colonne_verdict(), "ecart_achat": ui.PCT("Cours / prix d'achat", "Négatif : sous votre prix d'achat.", 0),
                "cours": st.column_config.NumberColumn("Cours", format="%.2f"),
                "prix_achat": st.column_config.NumberColumn("Prix d'achat", format="%.2f"), "devise": "Devise",
                "score": ui.SCORE("Note GARP"), "moat": "Moat estimé",
                "criteres": st.column_config.TextColumn("Critères", help="Critères de qualité remplis sur évalués."),
                "tri_implicite": ui.PCT("TRI implicite"), "perf_12m": ui.PCT("12 mois"),
                "homme_cle": st.column_config.NumberColumn("Homme-clé / 10", format="%.1f"),
                "statut": "Filtres", "alerte": st.column_config.TextColumn("Alerte", width="large"),
            })
        lignes_choisies = selection.selection.rows if selection else []
        if st.button("Ouvrir la fiche de la ligne choisie", icon=":material/query_stats:",
                     disabled=not lignes_choisies):
            st.session_state["fiche_ticker"] = t.index[lignes_choisies[0]]
            st.switch_page("vues/fiche.py")
        st.caption(f"Prix d'achat au rendement exigé de {ui.pct(regl['rendement'], 1)} et avec une marge de "
                   f"{ui.pct(regl['marge'], 0)} (réglables dans « La bonne action au bon prix »). Choisissez une ligne "
                   "pour ouvrir sa fiche. Outil d'aide à la décision, pas un conseil.")
    st.download_button("Exporter la composition (CSV)", mp.to_csv(sep=";").encode("utf-8-sig"),
                       file_name="portefeuille_modele.csv", mime="text/csv", icon=":material/download:")

with tab_repartition:
    st.subheader("Répartition")
    a, b = st.columns(2)
    with a:
        st.markdown("**Par secteur**")
        ui.show(ui.hbar(pfo.breakdown(w, sc, "secteur"), color=ui.accent()))
    with b:
        st.markdown("**Par pays du siège**")
        ui.show(ui.hbar(pfo.breakdown(w, sc, "pays"), color=ui.accent()))
    env = w.groupby(mp["enveloppe"]).sum().sort_values(ascending=False)  # le compte où la ligne est réellement détenue
    poches = w.groupby(mp["poche"]).sum()
    cartes = [({"PEA": "PEA", "CTO": "Compte-titres"}.get(e, e), v) for e, v in env.items()]
    cartes += [(f"Poche {p.lower()}", v) for p, v in poches.sort_values(ascending=False).items()]
    for col, (label, v) in zip(st.columns(len(cartes)), cartes):
        col.metric(label, ui.pct(v), border=True)

    if risk:
        st.subheader("Risque et corrélations")
        c = st.columns(3)
        c[0].metric("Volatilité attendue", ui.pct(risk["volatilite"]), border=True,
                    help="Sur 3 ans de rendements quotidiens en euros. À comparer à ~14-16 % pour le MSCI World.")
        c[1].metric("Ratio de diversification", ui.num(risk["ratio_diversification"], 2), border=True,
                    help="Volatilité moyenne des lignes / volatilité du portefeuille. Plus il est élevé, plus les lignes se compensent.")
        c[2].metric("Nombre effectif", ui.num(risk["nombre_effectif"], 1), border=True)
        st.markdown("**Contribution de chaque ligne au risque total**")
        contrib = risk["contribution_risque"].rename(index=sc["nom"].to_dict())
        ui.show(ui.hbar(contrib, color=ui.accent()))
        st.markdown("**Corrélations des rendements hebdomadaires (3 ans)**")
        names = sc["nom"].to_dict()
        rets = pfo.returns_eur(list(w.index))
        weekly = (1 + rets).resample("W-FRI").prod() - 1
        ui.show(ui.corr_heatmap(weekly.corr(), labels=names))
        st.caption("Bleu : les deux valeurs évoluent en sens opposé. Rouge : elles évoluent ensemble. "
                   "Un bloc rouge signale un risque commun aux lignes concernées.")

with tab_equilibre:
    st.caption("Une proposition, pas une consigne : comparer vos poids réels à vos poids cibles, et voir comment un "
               "apport rapprocherait le portefeuille de sa cible sans rien vendre. Rien n'est enregistré ici.")
    # Garde-fous de concentration (seuils de config/strategie.json, suivi.garde_fous), sur les poids réels.
    poids_reels, _ = risques.poids_actuels()
    concentration = risques.garde_fous(poids_reels, sc["secteur"])
    if concentration:
        st.markdown("**Concentration**")
        for t, message in concentration:
            st.markdown(f"- {names.get(t, t) + ' : ' if t else ''}{message}")
    pos = positions.positions()  # photo du dernier import avec quantités
    if pos.empty or w.empty:
        st.info("Pour comparer poids réels et cibles, G.A.R.P a besoin de vos quantités : importez votre portefeuille "
                "en laissant cochée l'option « Enregistrer aussi mes quantités ».", icon=":material/info:")
    else:
        seuil = float(strat["suivi"]["seuil_reequilibrage"])
        ecarts = tracker.drift_alerts(pos, w, seuil)
        total = float(pos["valeur_eur"].sum())
        ecarts["nom"] = [names.get(t, t) for t in ecarts.index]
        ecarts["a_ajuster_eur"] = -ecarts["ecart"] * total
        hors = ecarts[ecarts["action"] != "Dans la cible"]
        k = st.columns(3)
        k[0].metric("Valeur du portefeuille", ui.eur(total, 0), border=True)
        k[1].metric("Lignes loin de leur cible", len(hors), border=True,
                    help=f"Écart de plus de {ui.num(seuil * 100, 0)} points entre poids réel et poids cible.")
        k[2].metric("Écart le plus fort", f"{ui.num(ecarts['ecart'].abs().max() * 100, 1)} pts", border=True)
        vue = ecarts.sort_values("ecart")[["nom", "poids_reel", "poids_cible", "ecart", "a_ajuster_eur", "action"]]
        ui.tableau(ui.as_pct_cols(vue, ["poids_reel", "poids_cible", "ecart"]), width="stretch",
                   height=min(520, 35 * len(vue) + 38), column_config={
                       "nom": "Valeur", "poids_reel": ui.PCT("Poids réel"), "poids_cible": ui.PCT("Poids cible"),
                       "ecart": ui.PCT("Écart (points)", d=1),
                       "a_ajuster_eur": st.column_config.NumberColumn(
                           "Pour revenir à la cible (€)", format="%.0f",
                           help="Positif : montant qu'il faudrait acheter. Négatif : montant au-dessus de la cible."),
                       "action": "Proposition"})
        st.markdown("**Si vous faites un apport**")
        compte_principal = pfo.compte_principal(w, mp)
        c = st.columns([1.2, 1, 1.2])
        montant = c[0].number_input("Montant (€)", min_value=0.0, value=1000.0, step=100.0, key="eq_montant")
        compte = c[1].segmented_control("Compte", tracker.COMPTES, default=compte_principal,
                                        key="eq_compte") or compte_principal
        min_order = c[2].number_input("Ordre minimum (€)", min_value=0.0,
                                      value=float(strat["suivi"]["ordre_min_eur"]), step=50.0, key="eq_min")
        ecartees = pfo.lignes_a_ecarter(sc, w.index)
        plan = tracker.contribution_plan(montant, compte, w.drop(index=list(ecartees)), mp["enveloppe"], pos=pos,
                                         min_order=min_order)
        if plan.empty:
            st.caption("Aucune répartition proposée : montant trop faible face à l'ordre minimum, ou lignes du compte "
                       "déjà au-dessus de leur cible.")
        else:
            plan.insert(1, "nom", plan["ticker"].map(lambda t: names.get(t, t)))
            ui.tableau(ui.as_pct_cols(plan, ["poids_cible_compte", "poids_apres"]).drop(columns=["ticker"]),
                       hide_index=True, width="stretch", column_config={
                           "nom": "Valeur", "quantite": st.column_config.NumberColumn("Quantité", format="%.4g"),
                           "cours_eur": st.column_config.NumberColumn("Cours €", format="%.2f"),
                           "montant_eur": st.column_config.NumberColumn("Montant €", format="%.2f"),
                           "poids_cible_compte": ui.PCT("Cible dans le compte"),
                           "valeur_avant": st.column_config.NumberColumn("Détenu avant €", format="%.0f"),
                           "poids_apres": ui.PCT("Poids après achat")})
        if ecartees:
            st.caption("Laissées de côté, le temps de revoir leur thèse : "
                       + " ; ".join(f"{names.get(t, t)}, {r}" for t, r in ecartees.items()) + ".")
        st.caption("Une ligne trop lourde n'a pas besoin d'être vendue : les apports suivants peuvent aller aux autres. "
                   "Proposition indicative, pas un conseil en investissement.")

with tab_modifier:
    st.caption("Changez un poids, ajoutez une valeur sur la ligne vide du bas, ou supprimez une ligne (case à gauche, "
               "puis la corbeille). Les poids sont ramenés à 100 % à l'enregistrement ; thèses et conditions de vente "
               "déjà écrites sont gardées.")
    noms_sc = sc["nom"].astype(str).to_dict()
    libelles = {t: f"{noms_sc[t]} ({t})" for t in sorted(sc.index, key=lambda t: noms_sc[t].lower())}
    for t in mp.index:  # une ligne hors des données reste modifiable sous son ticker
        libelles.setdefault(t, t)
    par_libelle = {v: k for k, v in libelles.items()}
    base = pd.DataFrame({
        "valeur": [libelles[t] for t in mp.index],
        "enveloppe": [mp["enveloppe"].get(t) or "CTO" for t in mp.index] if "enveloppe" in mp else "CTO",
        "poche": [mp["poche"].get(t) or "Cœur" for t in mp.index] if "poche" in mp else "Cœur",
        "poids": [round(float(w.get(t, 0)) * 100, 2) for t in mp.index],
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
    total = pd.to_numeric(edite["poids"], errors="coerce").fillna(0).sum()
    doublons = edite["valeur"].dropna()[edite["valeur"].dropna().duplicated()].tolist()
    c = st.columns([1, 3], vertical_alignment="center")
    c[0].metric("Total saisi", f"{ui.num(total, 1)} %", border=True,
                help="Il n'a pas besoin de faire 100 % : les poids sont ramenés à 100 % à l'enregistrement.")
    if doublons:
        c[1].caption(f"Cité deux fois, poids cumulés à l'enregistrement : {', '.join(doublons)}.")
    if c[1].button("Enregistrer la composition", type="primary", icon=":material/save:"):
        lignes = [(par_libelle.get(r["valeur"]), r["enveloppe"], r["poche"],
                   float(r["poids"]) if pd.notna(r["poids"]) else 0.0) for _, r in edite.iterrows()]
        try:
            nouveau = pfo.nouvelle_composition(mp, lignes, noms_sc)
        except ValueError as e:
            st.error(f"Composition non enregistrée : {e}.")
        else:
            if MODELE_CSV.exists():
                shutil.copy2(MODELE_CSV, MODELE_CSV.with_name(f"portefeuille_modele.avant-modif-{date.today():%Y-%m-%d}.csv"))
            write_csv_fr(nouveau, MODELE_CSV)
            st.cache_data.clear()
            st.session_state.pop("compo_edition", None)
            st.toast(f"Composition enregistrée : {len(nouveau)} lignes.", icon=":material/check:")
            st.rerun()

with tab_theses:
    choix = st.selectbox("Valeur", list(w.index), format_func=lambda t: f"{names.get(t, t)} ({t})")
    txt = read_thesis(choix)
    st.markdown(txt or "_Fiche absente : lancez une mise à jour pour la générer._")
