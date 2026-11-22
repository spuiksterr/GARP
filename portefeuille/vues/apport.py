from datetime import date

import pandas as pd
import streamlit as st

from pf import portfolio as pfo
from pf import tracker, ui
from pf.config import load_strategy
from pf.data import currency_of, load_fundamentals

sc = ui.require_data()
strat = load_strategy()
mp = ui.model()
w = pfo.model_weights()
names = ui.label_map(sc)
compte_principal = pfo.compte_principal(w, mp)

st.title("Apport du mois")
st.markdown("Investir régulièrement, sans jamais vendre pour rééquilibrer : chaque apport va aux lignes **les plus en "
            "retard sur leur poids cible**. Sur le compte-titres, cela évite de payer l'impôt sur les plus-values ; "
            "sur le PEA, cela évite des frais inutiles.")

c = st.columns(5)
montant = c[0].number_input("Montant à investir (€)", min_value=0.0, value=1000.0, step=100.0)
compte = c[1].segmented_control("Compte", tracker.COMPTES, default=compte_principal)
min_order = c[2].number_input("Ordre minimum (€)", min_value=0.0, value=float(strat["suivi"]["ordre_min_eur"]), step=50.0,
                              help="En dessous, les frais de courtage pèsent trop (ex. : 2 € sur 300 € = 0,7 %).")
max_orders = c[3].number_input("Nombre d'ordres maximum", min_value=0, value=0, step=1,
                               help="0 = pas de limite. Limiter le nombre d'ordres réduit les frais fixes.")
fractions = c[4].toggle("Fractions d'action", value=False, help="Si votre courtier permet d'acheter des fractions.")
ecarter = st.toggle("Écarter les lignes sorties des filtres ou en forte baisse", value=True,
                    help="Leur part de l'apport va aux autres lignes du compte, le temps de réexaminer leur thèse "
                         "(commande /revue-portefeuille).")
compte = compte or compte_principal

tx = tracker.load_transactions()
pos = tracker.positions(tx) if not tx.empty else pd.DataFrame()
ecartees = pfo.lignes_a_ecarter(sc, w.index) if ecarter else {}
if ecartees:
    st.caption("Écartées de cet apport : " + " ; ".join(f"{names.get(t, t)}, {r}" for t, r in ecartees.items()) + ".")
plan = tracker.contribution_plan(montant, compte, w.drop(index=list(ecartees)), mp["enveloppe"], pos=pos, min_order=min_order,
                                 fractional=fractions, max_orders=int(max_orders) or None)
if plan.empty:
    st.info("Aucun ordre proposé : montant trop faible face à l'ordre minimum, ou lignes déjà au-dessus de leur cible.")
    st.stop()

plan.insert(1, "nom", plan["ticker"].map(lambda t: names.get(t, t)))
investi = plan["montant_eur"].sum()
k = st.columns(3)
k[0].metric("Ordres", len(plan), border=True)
k[1].metric("Montant investi", ui.eur(investi, 2), border=True)
k[2].metric("Reste en espèces", ui.eur(plan.attrs.get("reste", montant - investi), 2), border=True,
            help="Ce qui ne permet pas d'acheter une action entière de plus : il servira au prochain apport.")
show = ui.as_pct_cols(plan, ["poids_cible_compte", "poids_apres"])
ui.tableau(show.drop(columns=["ticker"]), hide_index=True, width="stretch", column_config={
    "nom": "Valeur", "quantite": st.column_config.NumberColumn("Quantité", format="%.4g"),
    "cours_eur": st.column_config.NumberColumn("Cours €", format="%.2f"),
    "montant_eur": st.column_config.NumberColumn("Montant €", format="%.2f"),
    "poids_cible_compte": ui.PCT("Cible dans le compte"),
    "valeur_avant": st.column_config.NumberColumn("Détenu avant €", format="%.0f"),
    "poids_apres": ui.PCT("Poids après achat"),
})
st.caption("Cours de clôture convertis en euros au taux du jour : le prix d'exécution sera un peu différent. "
           "Passez des ordres à cours limité proches du dernier cours.")

# Un second clic, ou un rechargement de la page, ne doit pas enregistrer deux fois les mêmes ordres.
deja = tracker.ordres_deja_saisis(tx, plan, compte, date.today())
if deja:
    st.info("Déjà enregistrés aujourd'hui dans le journal : " + ", ".join(names.get(t, t) for t in sorted(deja)) + ".")
nouveaux = plan[~plan["ticker"].isin(deja)]
if not nouveaux.empty and st.button("J'ai passé ces ordres : les enregistrer dans le journal", icon=":material/playlist_add_check:"):
    lignes = []
    for _, o in nouveaux.iterrows():
        t = o["ticker"]
        local = ui.local_prices(t)
        lignes.append({
            "date": pd.Timestamp(date.today()), "compte": compte, "type": "ACHAT", "ticker": t,
            "quantite": o["quantite"], "prix_unitaire": round(float(local.iloc[-1]), 4) if not local.empty else "",
            "devise": currency_of(t, load_fundamentals(t)), "frais_eur": "", "montant_eur": round(float(o["montant_eur"]), 2),
            "taux_change": "", "note": f"{tracker.NOTE_APPORT} (prix de clôture, à corriger avec l'avis d'opéré)",
        })
    tracker.append_transactions(lignes)
    st.success("Ordres ajoutés au journal. Corrigez les prix et frais réels dans « Mon portefeuille » > « Journal ».")
    st.rerun()
