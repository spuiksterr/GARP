import pandas as pd
import streamlit as st

from pf import actualites as act
from pf import backtest as bt
from pf import dirigeants, photos, regles, risques, scenarios, tracker, ui
from pf import portfolio as pfo
from pf import watchlist as wl
from pf.config import BENCHMARKS, load_strategy
from pf.sante import health_alerts

sc = ui.require_data()
mp = ui.model()
w = pfo.model_weights()
strat = load_strategy()
bench = strat["suivi"]["benchmark"]

st.title("Tableau de bord")
st.caption(f"Cours au {ui.data_date()} · univers de {len(sc)} valeurs dont {int((sc['statut'] == 'Éligible').sum())} "
           f"passent les filtres de qualité · portefeuille de {len(w)} lignes")

# ------------------------------------------------------------------ portefeuille réel
tx = tracker.load_transactions()
if not tx.empty:
    pos = tracker.positions(tx)
    hist = tracker.history(tx)
    perf = tracker.twr(hist)
    shadow = tracker.benchmark_shadow(hist, bench)
    value = hist["valeur_totale"].iloc[-1]
    st.subheader("Mon portefeuille")
    c = st.columns(4)
    c[0].metric("Valeur totale", ui.eur(value), border=True)
    cost = pos["cout_eur"].sum()
    c[1].metric("Plus-values latentes", ui.eur(pos["pv_latente_eur"].sum()),
                delta=ui.pct(pos["pv_latente_eur"].sum() / cost, signe=True) if cost else None, border=True)
    c[2].metric("Performance du suivi", ui.pct(perf.iloc[-1] / 100 - 1, signe=True),
                help="Performance pondérée par le temps : neutralise le calendrier de vos versements. Les lignes "
                     "reprises d'un courtier y entrent à leur valeur du jour de reprise.", border=True)
    if not shadow.empty:
        gap = value - shadow.iloc[-1]
        c[3].metric("Écart vs l'indice", ui.eur(gap), delta=ui.pct(gap / shadow.iloc[-1], signe=True),
                    help=f"Différence avec le même argent, versé aux mêmes dates, dans l'ETF de référence : "
                         f"{BENCHMARKS.get(bench, bench)}.", border=True)
else:
    st.info("Aucune opération saisie : ce tableau de bord suit les poids cibles. "
            "Enregistrez vos achats dans « Mon portefeuille » pour suivre votre performance réelle.",
            icon=":material/info:")

# ------------------------------------------------------------------ portefeuille modèle
st.subheader("Profil du portefeuille")
ch = pfo.characteristics(w, sc)
risk = pfo.risk_profile(w)
c = st.columns(4)
c[0].metric("TRI implicite moyen", ui.pct(ch.get("TRI implicite")), border=True,
            help="Rendement annuel attendu si la croissance prévue se réalise, au prix actuel (modèle de flux actualisés). "
                 "Moyenne sur les actions bénéficiaires : fonds et sociétés en perte n'en ont pas.")
c[1].metric("Croissance attendue", ui.pct(ch.get("Croissance attendue")), border=True,
            help="Médiane, par ligne, du consensus (BPA, CA) et de la croissance historique, pondérée par les poids.")
c[2].metric("PER prospectif", ui.num(ch.get("PER prospectif"), 1, "x"), border=True,
            help="Moyenne harmonique pondérée des PER sur les bénéfices attendus.")
c[3].metric("Volatilité attendue", ui.pct(risk.get("volatilite")), border=True,
            help="Écart-type annualisé des rendements en euros sur 3 ans, corrélations comprises.")

created = pd.Timestamp(strat["suivi"].get("date_creation_modele") or "2026-10-29")
px = ui.eur_prices(tuple(w.index) + (bench,))
# Suivi réel dès 5 séances après la création du modèle ; avant, simulation sur un an (poids actuels).
debut = created if len(px[px.index >= created]) >= 5 else px.index.max() - pd.Timedelta(days=365)
curve = bt.run_backtest(w, debut, rebalance=None, prices=px[list(w.index)], cost_bps=0)["valeur"]
b = bt.benchmark_curve(bench, debut)
resume = (f"portefeuille {ui.pct(curve.iloc[-1] / 100 - 1, signe=True)}, "
          f"{BENCHMARKS.get(bench, bench)} {ui.pct(b.iloc[-1] / 100 - 1, signe=True)}")
if debut == created:
    st.markdown(f"**Depuis le début du suivi ({created:%d/%m/%Y}, poids cibles)** : {resume}")
else:
    st.markdown(f"**Sur un an glissant (simulation, poids actuels)** : {resume}. Le suivi réel démarre le {created:%d/%m/%Y}.")
ui.show(ui.lines(pd.DataFrame({"Portefeuille": curve, BENCHMARKS.get(bench, bench): b}).dropna(),
                 yfmt=",.1f", height=300))

# ------------------------------------------------------------------ alertes
st.subheader("Points de vigilance")
rows = []
for t in w.index:
    if t not in sc.index:
        rows.append(("Données", t, "Valeur absente des données : lancez une mise à jour."))
        continue
    r = sc.loc[t]
    if r["statut"] == "Exclu":
        rows.append(("Thèse à revoir", t, f"Ne passe plus les filtres de qualité : {r['motifs_exclusion']}"))
    p1 = r.get("perf_1m")
    if pd.notna(p1) and p1 <= -0.15:
        rows.append(("Forte baisse", t, f"{ui.pct(p1, signe=True)} sur un mois : vérifier si la thèse est touchée."))
    if pd.notna(p1) and p1 >= 0.25:
        rows.append(("Forte hausse", t, f"{ui.pct(p1, signe=True)} sur un mois : le poids dérive au-dessus de la cible."))
    tri = r.get("tri_implicite")
    if pd.notna(tri) and tri < 0.06:
        rows.append(("Valorisation", t, f"TRI implicite de {ui.pct(tri)} : l'action intègre déjà beaucoup de croissance."))
    rows += [("Santé financière", t, msg) for msg in health_alerts(r)]
if not tx.empty:
    drift = tracker.drift_alerts(pos, w, strat["suivi"]["seuil_reequilibrage"])
    for t, d in drift[drift["action"] != "Dans la cible"].iterrows():
        rows.append(("Écart de poids", t, f"{d['action']} : {ui.pct(d['poids_reel'])} détenu pour {ui.pct(d['poids_cible'])} visé."))
# Garde-fous de concentration (seuils de config/strategie.json, suivi.garde_fous), sur les poids réels.
poids_reels, _ = risques.poids_actuels()
for t, message in risques.garde_fous(poids_reels, sc["secteur"]):
    rows.append(("Concentration", t or "Portefeuille", message[0].upper() + message[1:]))
# Statut changé entre les deux dernières photos du screener (lignes détenues et watchlist).
suivies = list(dict.fromkeys(list(w.index) + list(wl.load_watchlist().index)))
for t, ancien, nouveau, depuis in photos.changements_de_statut(suivies):
    rows.append(("Changement de statut", t, f"{ancien} → {nouveau} depuis la photo du {depuis:%d/%m/%Y}. "
                 "Relire la thèse."))
# Achats groupés de dirigeants (déclarations déjà lues depuis la fiche : aucun accès réseau ici).
for t in dict.fromkeys(list(w.index) + list(wl.load_watchlist().index)):
    syn = dirigeants.synthese(dirigeants.en_cache(t))
    if syn["acheteurs"] >= dirigeants.GROUPES_MIN:
        rows.append(("Achats de dirigeants", t, f"{syn['acheteurs']} dirigeants ou administrateurs ont acheté en bourse "
                     f"sur 12 mois ({ui.num(syn['montant_achats'] / 1e6, 1)} M {sc['devise'].get(t, 'USD')}) : "
                     "voir la fiche."))
# Cours qui ne suivent plus le marché (ticker changé, valeur suspendue) : les indicateurs de la ligne sont faux.
prix_tous = ui.load_prices()
if not prix_tous.empty:
    fin_marche = prix_tous.index.max()
    for t in w.index:
        if t in prix_tous.columns and prix_tous[t].last_valid_index() is not None:
            dernier = prix_tous[t].last_valid_index()
            if (fin_marche - dernier).days > 4:
                rows.append(("Données anciennes", t, f"Dernier cours du {dernier:%d/%m/%Y} (marché au "
                             f"{fin_marche:%d/%m/%Y}) : vérifier le ticker chez Yahoo."))
for t, message in scenarios.alertes(sc):
    rows.append(("Scénarios à 5 ans", t, message + " Relire la thèse."))
for _, x in regles.evaluer(sc).query("statut == 'Atteinte'").iterrows():
    rows.append(("Condition de vente atteinte", x["ticker"], f"{x['regle']} (actuellement {x['valeur']})"
                 + (f" — {x['note']}" if x["note"] else "") + ". Relire la thèse avant toute décision."))
for t, a in wl.prix_vises_atteints(sc["cours"]).iterrows():
    dev = sc["devise"].get(t, "")
    rows.append(("Prix visé atteint", t, f"Watchlist : cours {ui.num(a['cours'], 2)} {dev} pour un prix visé de "
                 f"{ui.num(a['prix_cible'], 2)} {dev}{' (' + a['objectif'] + ')' if a['objectif'] else ''}. "
                 "Relire la thèse avant toute décision."))
if rows:
    names = sc["nom"].to_dict()
    al = pd.DataFrame(rows, columns=["Type", "ticker", "Détail"])
    al.insert(1, "Valeur", al["ticker"].map(lambda t: names.get(t, t)))
    ui.tableau(al.drop(columns="ticker"), hide_index=True, width="stretch")
else:
    st.success("Aucune alerte : toutes les lignes passent les filtres, sans mouvement extrême.", icon=":material/check_circle:")

# ------------------------------------------------------------------ actualités
dernieres = act.fil(sc)
dernieres = dernieres[dernieres["type"] != "À surveiller"].head(5) if not dernieres.empty else dernieres
if len(dernieres):
    st.subheader("Dernières actualités")
    for _, x in dernieres.iterrows():
        titre = x["titre"].replace("[", "(").replace("]", ")")
        lien = f"[{titre}]({x['lien']})" if isinstance(x["lien"], str) and x["lien"] else titre
        st.markdown(f"**{x['nom']}** · {pd.Timestamp(x['date']):%d/%m} · {x['source']} · {lien}")
    try:  # le lien n'existe que dans l'application complète (menu de navigation)
        st.page_link("vues/actualites.py", label="Toutes les actualités", icon=":material/newspaper:")
    except Exception:
        st.caption("Toutes les actualités : page « Actualités » du menu.")

# ------------------------------------------------------------------ lignes du modèle
st.subheader("Lignes du portefeuille")
t = mp[["nom", "enveloppe", "poche"]].copy()
t["poids"] = w
t = t.join(sc[["score", "perf_1m", "perf_12m", "tri_implicite", "per_prospectif"]])
t = ui.as_pct_cols(t, ["poids", "perf_1m", "perf_12m", "tri_implicite"]).sort_values("poids", ascending=False)
ui.tableau(t, width="stretch", column_config={
    "nom": "Valeur", "enveloppe": "Compte", "poche": "Poche",
    "poids": ui.PCT("Poids"),
    "score": ui.SCORE("Score", "Moyenne pondérée des analyses, chacune sur 100 : piliers, valorisation, "
                               "quatre regards, Piotroski, Altman, Beneish"),
    "perf_1m": ui.PCT("1 mois"), "perf_12m": ui.PCT("12 mois"),
    "tri_implicite": ui.PCT("TRI implicite"), "per_prospectif": st.column_config.NumberColumn("PER prosp.", format="%.1f"),
})
