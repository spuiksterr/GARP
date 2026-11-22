from datetime import date

import pandas as pd
import streamlit as st

from pf import portfolio as pfo
from pf import tracker, ui
from pf.config import BENCHMARKS, load_strategy, save_strategy
from pf.data import currency_of, load_fundamentals

sc = ui.require_data()
strat = load_strategy()
names = ui.label_map(sc)
w_model = pfo.model_weights()
bench = strat["suivi"]["benchmark"]
mp = ui.model()
compte_principal = pfo.compte_principal(w_model, mp)

st.title("Mon portefeuille")
tx = tracker.load_transactions()
for anomalie in tracker.controle_ventes(tx)[1] if not tx.empty else []:
    st.warning(f"Journal à corriger : {anomalie}.", icon=":material/error:")
tabs = st.tabs(["Positions", "Performance", "Saisir une opération", "Journal des opérations", "Fiscalité"])

# ------------------------------------------------------------------ saisie
with tabs[2]:
    kind = st.segmented_control("Type d'opération", tracker.TYPES, default="ACHAT")
    titres = kind in tracker.TITRES
    options = list(dict.fromkeys(list(w_model.index) + sorted(sc.index, key=lambda t: str(sc.loc[t, "nom"]).lower())))
    with st.form("saisie", clear_on_submit=False):
        c = st.columns(3)
        d = c[0].date_input("Date", value=date.today(), format="DD/MM/YYYY")
        compte = c[1].segmented_control("Compte", tracker.COMPTES, default=compte_principal)
        ticker = c[2].selectbox("Valeur", [""] + options, format_func=lambda t: names.get(t, t) if t else "—",
                                accept_new_options=True, help="Valeur hors univers : saisissez son ticker Yahoo (ex. : AI.PA).")
        if titres:
            c = st.columns(4)
            qte = c[0].number_input("Quantité", min_value=0.0, step=1.0, format="%.4f")
            prix = c[1].number_input("Prix unitaire (devise de cotation)", min_value=0.0, step=0.01, format="%.4f",
                                     help="Pour Londres, Yahoo cote en pence (GBp) : saisissez le prix en pence.")
            frais = c[2].number_input("Frais (€)", min_value=0.0, step=0.5, format="%.2f")
            montant = c[3].number_input("Montant débité/crédité (€), facultatif", min_value=0.0, step=1.0, format="%.2f",
                                        help="Si renseigné, il fait foi (frais et change inclus). Sinon il est calculé.")
            taux = st.number_input("Taux de change appliqué (unités de devise pour 1 €), facultatif", min_value=0.0,
                                   step=0.0001, format="%.4f")
        else:
            montant = st.number_input("Montant (€)", min_value=0.0, step=1.0, format="%.2f",
                                      help="Dividende net reçu, versement, retrait ou frais de tenue de compte.")
            qte = prix = frais = taux = 0.0
        note = st.text_input("Note", placeholder="Facultatif")
        ok = st.form_submit_button("Enregistrer l'opération", type="primary", icon=":material/add:")
    if ok:
        if titres and (not ticker or qte <= 0 or prix <= 0):
            st.error("Pour un achat, une vente ou une reprise : valeur, quantité et prix sont obligatoires.")
        elif kind == "VENTE" and qte > tracker.quantite_detenue(tx, compte or compte_principal, ticker, d) + 1e-9:
            st.error(f"Vente refusée : vous détenez {ui.num(tracker.quantite_detenue(tx, compte or compte_principal, ticker, d), 4)} "
                     f"{ticker} sur le {compte or compte_principal} à cette date.")
        elif kind == "DIVIDENDE" and not ticker:
            st.error("Indiquez la valeur qui a versé le dividende.")
        elif not titres and montant <= 0:
            st.error("Indiquez le montant.")
        else:
            devise = currency_of(ticker, load_fundamentals(ticker)) if ticker else "EUR"
            tracker.append_transaction({
                "date": pd.Timestamp(d), "compte": compte or compte_principal, "type": kind, "ticker": ticker or "",
                "quantite": qte or "", "prix_unitaire": prix or "", "devise": devise if titres else "EUR",
                "frais_eur": frais or "", "montant_eur": montant or "", "taux_change": taux or "", "note": note,
            })
            st.success(f"Opération enregistrée : {kind} {names.get(ticker, ticker)}")
            st.rerun()

# ------------------------------------------------------------------ journal
with tabs[3]:
    if tx.empty:
        st.info("Journal vide. Les opérations sont stockées dans data/transactions.csv (modifiable aussi sous Excel).")
    else:
        edited = st.data_editor(tx, num_rows="dynamic", width="stretch", hide_index=True, column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
            "compte": st.column_config.SelectboxColumn("Compte", options=tracker.COMPTES),
            "type": st.column_config.SelectboxColumn("Type", options=tracker.TYPES),
            "quantite": st.column_config.NumberColumn("Quantité"), "prix_unitaire": st.column_config.NumberColumn("Prix"),
            "frais_eur": st.column_config.NumberColumn("Frais €"), "montant_eur": st.column_config.NumberColumn("Montant €"),
            "taux_change": st.column_config.NumberColumn("Change"),
        })
        if st.button("Enregistrer les modifications", icon=":material/save:",
                     help="Une copie de l'ancien journal est gardée dans data/sauvegardes (30 dernières)."):
            tracker.save_transactions(edited.dropna(subset=["date"]))
            st.success("Journal enregistré (ancienne version copiée dans data/sauvegardes).")
            st.rerun()

if tx.empty:
    with tabs[0]:
        st.info("Aucune position. Saisissez vos opérations dans l'onglet « Saisir une opération », "
                "ou utilisez la page « Apport du mois » pour préparer vos premiers achats.", icon=":material/info:")
    st.stop()

pos = tracker.positions(tx)
hist = tracker.history(tx)

# ------------------------------------------------------------------ positions
with tabs[0]:
    total = pos["valeur_eur"].sum()
    c = st.columns(4)
    c[0].metric("Valeur des titres", ui.eur(total), border=True)
    c[1].metric("Prix de revient", ui.eur(pos["cout_eur"].sum()), border=True)
    c[2].metric("Plus-values latentes", ui.eur(pos["pv_latente_eur"].sum()), border=True,
                delta=ui.pct(pos["pv_latente_eur"].sum() / pos["cout_eur"].sum(), signe=True) if pos["cout_eur"].sum() else None)
    c[3].metric("Dividendes reçus", ui.eur(pos["dividendes_eur"].sum()), border=True)
    p = pos[pos["quantite"] > 0].copy()
    p.insert(1, "nom", p["ticker"].map(lambda t: names.get(t, t)))
    p = ui.as_pct_cols(p, ["pv_latente_pct", "poids"])
    ui.tableau(p.drop(columns=["ticker", "premier_achat"]), hide_index=True, width="stretch", column_config={
        "compte": "Compte", "nom": "Valeur", "quantite": st.column_config.NumberColumn("Quantité", format="%.4g"),
        "pru_eur": st.column_config.NumberColumn("PRU €", format="%.2f"),
        "cout_eur": st.column_config.NumberColumn("Coût €", format="%.0f"),
        "cours_eur": st.column_config.NumberColumn("Cours €", format="%.2f"),
        "valeur_eur": st.column_config.NumberColumn("Valeur €", format="%.0f"),
        "pv_latente_eur": st.column_config.NumberColumn("+/- latente €", format="%+.0f"),
        "pv_latente_pct": ui.PCT("+/- latente"), "pv_realisee_eur": st.column_config.NumberColumn("+/- réalisée €", format="%+.0f"),
        "dividendes_eur": st.column_config.NumberColumn("Dividendes €", format="%.0f"), "poids": ui.PCT("Poids"),
    })
    drift = tracker.drift_alerts(pos, w_model, strat["suivi"]["seuil_reequilibrage"])
    if not drift.empty:
        st.markdown("**Poids réels et poids cibles**")
        comp = drift[["poids_reel", "poids_cible"]].rename(columns={"poids_reel": "Réel", "poids_cible": "Cible"})
        comp.index = [sc["nom"].get(t, t) for t in comp.index]
        ui.show(ui.grouped_bars(comp.sort_values("Cible", ascending=False), height=340))
        st.caption("Pour rééquilibrer sans payer d'impôt, orientez les nouveaux apports vers les lignes en retard "
                   "(page « Apport du mois ») plutôt que de vendre les gagnantes, surtout sur le compte-titres.")

# ------------------------------------------------------------------ performance
with tabs[1]:
    perf = tracker.twr(hist)
    rdt, annualise = tracker.rendement_argent(hist)
    shadow = tracker.benchmark_shadow(hist, bench)
    c = st.columns(4)
    c[0].metric("Valeur totale", ui.eur(hist["valeur_totale"].iloc[-1]), border=True)
    c[1].metric("Apports nets", ui.eur(hist["apports_cumules"].iloc[-1]), border=True)
    c[2].metric("Performance (TWR)", ui.pct(perf.iloc[-1] / 100 - 1, signe=True), border=True,
                help="Neutralise le calendrier des versements : comparable à un fonds ou un indice.")
    if annualise:
        c[3].metric("TRI annualisé", ui.pct(rdt), border=True, help="Rendement annuel réellement obtenu sur votre argent, versements compris.")
    else:
        c[3].metric("Rendement de votre argent", ui.pct(rdt, signe=True), border=True,
                    help="Sur la période suivie, versements compris. Il sera annualisé au bout d'un an : sur quelques jours, "
                         "un rendement annualisé n'a pas de sens (+0,8 % en six jours ferait +64 % « par an »).")
    df = pd.DataFrame({"Valeur du portefeuille": hist["valeur_totale"], "Apports cumulés": hist["apports_cumules"]})
    if not shadow.empty:
        df[f"Même argent dans {BENCHMARKS.get(bench, bench)}"] = shadow
    ui.show(ui.lines(df, yfmt=",.0f", height=380, ytitle="€"))
    reprises = tx[tx["type"] == "REPRISE"]
    if not reprises.empty:
        st.caption(f"Lignes reprises du courtier le {reprises['date'].min():%d/%m/%Y} : elles entrent dans la performance à "
                   "leur valeur de ce jour-là. Les plus-values acquises avant figurent dans les plus-values latentes "
                   "(onglet Positions), calculées sur le PRU du courtier.")
    st.caption("La courbe de l'ETF répond à la seule question qui compte : le stock-picking fait-il mieux qu'un fonds "
               "indiciel à frais minimes ? Si l'écart reste négatif sur 3 à 5 ans, mieux vaut basculer vers l'ETF.")

# ------------------------------------------------------------------ fiscalité
with tabs[4]:
    real = tracker.realized_by_year(tx)
    if real.empty:
        st.info("Aucune cession ni dividende enregistré.")
    else:
        ui.tableau(real, hide_index=True, width="stretch", column_config={
            "annee": st.column_config.NumberColumn("Année", format="%d"), "compte": "Compte",
            "pv_realisee": st.column_config.NumberColumn("Plus-values réalisées €", format="%+.2f"),
            "dividendes": st.column_config.NumberColumn("Dividendes €", format="%.2f"),
            "cessions": st.column_config.NumberColumn("Montant des cessions €", format="%.2f"),
        })
    st.markdown("**Repères**")
    pea = strat["suivi"].get("date_ouverture_pea") or ""
    d_pea = st.date_input("Date d'ouverture de votre PEA", value=pd.Timestamp(pea) if pea else None, format="DD/MM/YYYY")
    if d_pea and str(d_pea) != pea:
        strat["suivi"]["date_ouverture_pea"] = str(d_pea)
        save_strategy(strat)
    if d_pea:
        five = pd.Timestamp(d_pea) + pd.DateOffset(years=5)
        st.markdown(f"Le PEA atteint 5 ans le **{five:%d/%m/%Y}** : au-delà, les retraits ne le clôturent plus et les gains "
                    "sont exonérés d'impôt sur le revenu (seuls les prélèvements sociaux restent dus). "
                    "Les arbitrages à l'intérieur du PEA ne sont jamais imposés.")
    st.markdown("Compte-titres : plus-values (calculées au prix moyen pondéré, comme ci-dessus) et dividendes relèvent "
                "du prélèvement forfaitaire unique, sauf option pour le barème. Les retenues à la source étrangères sur "
                "dividendes ouvrent droit à un crédit d'impôt dans la limite des conventions. Vérifiez les taux en vigueur "
                "sur impots.gouv.fr ; l'IFU de votre courtier fait foi pour la déclaration.")
