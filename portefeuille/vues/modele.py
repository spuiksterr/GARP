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

tab_lignes, tab_repartition, tab_equilibre, tab_operations, tab_modifier, tab_theses = st.tabs(
    ["Analyse des lignes", "Répartition et risques", "Équilibre (proposition)", "Opérations", "Modifier les poids", "Thèses"])

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
                       + " ; ".join(f"{names.get(t, t)}, {r}" for t, r in ecartees.items()) + ".")
        st.caption("Une ligne trop lourde n'a pas besoin d'être vendue : les apports suivants peuvent aller aux autres. "
                   "Proposition indicative, pas un conseil en investissement.")

with tab_operations:
    st.caption("Enregistrez vos positions de départ (`REPRISE`) ainsi que vos achats ou ventes ponctuels (`ACHAT`, "
               "`VENTE`) à leur date exacte. Chaque opération met à jour votre coût moyen (PRU) et n'entre dans la "
               "courbe du tableau de bord qu'à compter de sa date.")
    noms_op = sc["nom"].astype(str).to_dict()
    choix_tickers = list(dict.fromkeys(list(w.index) + sorted(sc.index, key=lambda t: noms_op[t].lower())))
    with st.form("form_operation", clear_on_submit=True):
        st.markdown("**Ajouter un achat ou une vente**")
        r1 = st.columns([1.1, 1.2, 0.9, 2.3])
        op_type = r1[0].selectbox("Opération", ["ACHAT", "VENTE", "REPRISE"],
                                  help="ACHAT : nouvel achat ou renforcement ; VENTE : allègement ou cession ; "
                                       "REPRISE : position déjà détenue au départ.")
        op_date = r1[1].date_input("Date", value=date.today(), min_value=date(2000, 1, 1), max_value=date.today())
        op_compte = r1[2].selectbox("Compte", tracker.COMPTES)
        op_ticker = r1[3].selectbox("Valeur", choix_tickers, index=None, placeholder="Nom ou ticker…",
                                    format_func=lambda t: f"{noms_op.get(t, t)} ({t})")
        r2 = st.columns([1.1, 1.2, 1.3, 1.0])
        op_qte = r2[0].number_input("Quantité", min_value=0.0, value=0.0, step=1.0, format="%.4f")
        op_prix = r2[1].number_input("Prix unitaire", min_value=0.0, value=0.0, step=1.0, format="%.4f",
                                     help="Dans la devise de cotation de la valeur (facultatif si le montant en € est saisi).")
        op_montant = r2[2].number_input("Montant total (€, facultatif)", min_value=0.0, value=0.0, step=100.0,
                                        format="%.2f", help="Montant réellement débité/crédité frais inclus. "
                                                            "Si 0, calculé depuis quantité × prix unitaire + frais.")
        op_frais = r2[3].number_input("Frais (€)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        r3 = st.columns([3, 1.3], vertical_alignment="bottom")
        op_note = r3[0].text_input("Note (facultative)", placeholder="Ex. Renforcement post-résultats")
        valide = r3[1].form_submit_button("Enregistrer l'opération", type="primary", icon=":material/add:",
                                          width="stretch")
        if valide:
            if not op_ticker:
                st.error("Choisissez une valeur.")
            elif op_qte <= 0:
                st.error("La quantité doit être strictement positive.")
            elif op_prix <= 0 and op_montant <= 0:
                st.error("Renseignez le prix unitaire ou le montant total en euros.")
            else:
                devise_op = (str(sc.loc[op_ticker, "devise"])
                             if op_ticker in sc.index and pd.notna(sc.loc[op_ticker, "devise"]) else "EUR")
                tracker.append_transaction({
                    "date": op_date.isoformat(),
                    "compte": op_compte,
                    "type": op_type,
                    "ticker": op_ticker,
                    "quantite": op_qte,
                    "prix_unitaire": op_prix if op_prix > 0 else "",
                    "devise": devise_op,
                    "frais_eur": op_frais if op_frais > 0 else "",
                    "montant_eur": op_montant if op_montant > 0 else "",
                    "taux_change": "",
                    "note": op_note.replace(";", ",").strip(),
                })
                st.cache_data.clear()
                st.toast(f"{op_type} enregistré : {op_qte:g} {noms_op.get(op_ticker, op_ticker)} le {op_date:%d/%m/%Y}.",
                         icon=":material/check:")
                st.rerun()

    tx_journal = tracker.load_transactions()
    if tx_journal.empty:
        st.info("Aucune opération enregistrée dans le journal (`data/transactions.csv`). Ajoutez vos positions "
                "ci-dessus pour suivre votre coût moyen (PRU) et votre performance réelle à compter de chaque achat.",
                icon=":material/info:")
    else:
        _, anomalies_tx = tracker.controle_ventes(tx_journal)
        for msg in anomalies_tx:
            st.warning(msg, icon=":material/warning:")
        pos_tx = tracker.positions(tx_journal)
        pos_act = pos_tx[pos_tx["quantite"] > 0].copy() if not pos_tx.empty else pd.DataFrame()
        if not pos_act.empty:
            st.markdown("**Positions et coût moyen (PRU) issus de vos opérations**")
            pos_act["nom"] = [noms_op.get(t, t) for t in pos_act["ticker"]]
            pos_act["premier_achat"] = pd.to_datetime(pos_act["premier_achat"]).dt.strftime("%d/%m/%Y")
            vue_pos = ui.as_pct_cols(
                pos_act[["ticker", "nom", "compte", "quantite", "pru_eur", "cours_eur", "valeur_eur",
                         "pv_latente_eur", "pv_latente_pct", "premier_achat"]],
                ["pv_latente_pct"],
            )
            ev_pos = ui.tableau(
                vue_pos, hide_index=True, width="stretch", height=min(520, 35 * len(vue_pos) + 38),
                on_select="rerun", selection_mode="single-cell", key=ui.cle_tableau("mp_op_pos"),
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker", pinned=True),
                    "nom": st.column_config.TextColumn("Valeur", pinned=True),
                    "compte": "Compte",
                    "quantite": st.column_config.NumberColumn("Quantité", format="%.4g"),
                    "pru_eur": st.column_config.NumberColumn("PRU (€)", format="%.2f"),
                    "cours_eur": st.column_config.NumberColumn("Cours (€)", format="%.2f"),
                    "valeur_eur": st.column_config.NumberColumn("Valeur (€)", format="%.0f"),
                    "pv_latente_eur": st.column_config.NumberColumn("Plus-value (€)", format="%+.0f"),
                    "pv_latente_pct": ui.PCT("Plus-value (%)"),
                    "premier_achat": "1er achat",
                })
            ui.fiche_au_clic(pos_act.set_index("ticker"), ev_pos, "mp_op_pos")

        with st.expander(f"Journal des opérations ({len(tx_journal)})", icon=":material/receipt_long:"):
            st.caption("Modifiez une ligne ou supprimez-en une (case à gauche puis corbeille), puis enregistrez.")
            tx_edit = tx_journal.copy()
            tx_edit["date"] = pd.to_datetime(tx_edit["date"]).dt.date
            edite_tx = st.data_editor(
                tx_edit, key="tx_journal_edition", num_rows="dynamic", hide_index=True, width="stretch",
                column_config={
                    "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY", required=True),
                    "compte": st.column_config.SelectboxColumn("Compte", options=tracker.COMPTES, required=True),
                    "type": st.column_config.SelectboxColumn("Type", options=tracker.TYPES, required=True),
                    "ticker": st.column_config.TextColumn("Ticker"),
                    "quantite": st.column_config.NumberColumn("Quantité", format="%.4g"),
                    "prix_unitaire": st.column_config.NumberColumn("Prix unit.", format="%.4g"),
                    "devise": "Devise",
                    "frais_eur": st.column_config.NumberColumn("Frais €", format="%.2f"),
                    "montant_eur": st.column_config.NumberColumn("Montant €", format="%.2f"),
                    "taux_change": st.column_config.NumberColumn("Change", format="%.4f"),
                    "note": "Note",
                })
            if st.button("Enregistrer les modifications du journal", icon=":material/save:", key="save_tx_journal"):
                propre = edite_tx.dropna(subset=["date", "type"]).copy()
                if "note" in propre.columns:
                    propre["note"] = propre["note"].fillna("").astype(str).str.replace(";", ",", regex=False)
                tracker.save_transactions(propre)
                st.cache_data.clear()
                st.toast(f"Journal enregistré ({len(propre)} opération(s)).", icon=":material/check:")
                st.rerun()

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
