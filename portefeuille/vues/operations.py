"""Opérations : achats, ventes et positions initiales à date précise, coût moyen (PRU) et journal."""
import pandas as pd
import streamlit as st

from pf import positions, tracker, ui

sc = ui.require_data()
mp = ui.model()
noms = sc["nom"].astype(str).to_dict()

st.title("Opérations")
st.caption("Enregistrez vos positions de départ ainsi que vos achats ou ventes ponctuels à leur date exacte. "
           "Chaque opération met à jour votre coût moyen (PRU) et n'entre dans la performance du tableau de bord "
           "(face au S&P 500, MSCI World, STOXX 600 et Nasdaq 100) qu'à compter de sa date.")

if ui.formulaire_operation(sc, mp, cle="op"):
    st.rerun()

tx_journal = tracker.load_transactions()
if tx_journal.empty:
    st.info("Aucune opération enregistrée dans le journal (`data/transactions.csv`). Ajoutez vos positions "
            "ci-dessus pour suivre votre coût moyen (PRU) et votre performance réelle à compter de chaque achat.",
            icon=":material/info:")
    st.stop()

_, anomalies_tx = tracker.controle_ventes(tx_journal)
for msg in anomalies_tx:
    st.warning(msg, icon=":material/warning:")

pos_tx = tracker.positions(tx_journal)
pos_act = pos_tx[pos_tx["quantite"] > 0].copy() if not pos_tx.empty else pd.DataFrame()
manquantes = [t for t in pos_act["ticker"].unique() if t not in mp.index] if not pos_act.empty else []
if manquantes:
    lib_manq = ", ".join(noms.get(t, t) for t in manquantes)
    st.info(f"Ligne(s) dans vos opérations mais absente(s) de la composition affichée : **{lib_manq}**.",
            icon=":material/sync:")
    if st.button("Synchroniser Mon portefeuille avec mes opérations", type="primary", icon=":material/sync:",
                 key="sync_mp_depuis_op"):
        lignes = [{"ticker": r["ticker"], "compte": r["compte"], "quantite": float(r["quantite"])}
                  for _, r in pos_act.iterrows()]
        positions.enregistrer(lignes)
        n_sync = ui._synchroniser_modele(mp, noms)
        st.cache_data.clear()
        st.toast(f"Portefeuille synchronisé ({n_sync} lignes).", icon=":material/check:")
        st.rerun()

if not pos_act.empty:
    st.subheader("Positions et coût moyen (PRU)")
    pos_act["nom"] = [noms.get(t, t) for t in pos_act["ticker"]]
    pos_act["premier_achat"] = pd.to_datetime(pos_act["premier_achat"]).dt.strftime("%d/%m/%Y")
    vue_pos = ui.as_pct_cols(
        pos_act[["ticker", "nom", "compte", "quantite", "pru_eur", "cours_eur", "valeur_eur",
                 "pv_latente_eur", "pv_latente_pct", "premier_achat"]],
        ["pv_latente_pct"],
    )
    ev_pos = ui.tableau(
        vue_pos, hide_index=True, width="stretch", height=min(520, 35 * len(vue_pos) + 38),
        on_select="rerun", selection_mode="single-cell", key=ui.cle_tableau("op_pos"),
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
    ui.fiche_au_clic(pos_act.set_index("ticker"), ev_pos, "op_pos")
    st.caption("Cliquez sur une valeur pour ouvrir sa fiche.")

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
