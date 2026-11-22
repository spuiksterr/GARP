import math

import pandas as pd
import streamlit as st

from pf import actualites as act
from pf import backtest as bt
from pf import dirigeants, photos, positions, regles, scenarios, ui
from pf import portfolio as pfo
from pf import prix_achat as pa
from pf import watchlist as wl
from pf.config import BENCHMARKS, load_strategy
from pf.sante import health_alerts

sc = ui.require_data()
mp = ui.model()
w = pfo.model_weights()
strat = load_strategy()
bench = strat["suivi"]["benchmark"]
names = sc["nom"].to_dict()
suivies_wl = wl.load_watchlist()

st.title("Tableau de bord")
st.caption(f"Cours au {ui.data_date()} · univers de {len(sc)} valeurs dont {int((sc['statut'] == 'Éligible').sum())} "
           f"passent les filtres de qualité · portefeuille de {len(w)} lignes")

# ------------------------------------------------------------------ portefeuille importé (photo du dernier import)
pos = positions.positions()
if not pos.empty:
    valeur = float(pos["valeur_eur"].sum())
    par_compte = pos.groupby("compte")["valeur_eur"].sum()
    quand = positions.date_photo()
    c = st.columns(4)
    c[0].metric("Valeur du portefeuille", ui.eur(valeur, 0), border=True,
                help="Quantités du dernier import × derniers cours, en euros." + (
                    f" Quantités importées le {pd.Timestamp(quand):%d/%m/%Y} : réimportez pour les mettre à jour."
                    if quand else ""))
    c[1].metric("Lignes détenues", int(pos["ticker"].nunique()), border=True)
    for col, compte in zip(c[2:], ["PEA", "CTO"]):
        part = par_compte.get(compte, 0.0) / valeur if valeur else 0.0
        col.metric({"PEA": "Sur le PEA", "CTO": "Sur le compte-titres"}[compte], ui.pct(part, 0), border=True)

# ------------------------------------------------------------------ points de vigilance (calculés d'abord)
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
    niveau_hc = r.get("homme_cle_niveau")  # vide (NA) pour un fonds ou une valeur pas encore relue
    if pd.notna(niveau_hc) and niveau_hc == "Élevé" and w.get(t, 0) >= 0.05:
        rows.append(("Homme-clé", t, f"Risque homme-clé de {ui.num(r['homme_cle'], 1)} / 10 ({r['homme_cle_facteurs']}) : "
                                     "la thèse dit-elle ce qui se passerait sans cette personne ?"))
# Écarts aux poids cibles et concentration relèvent de l'équilibre : ils sont proposés dans l'onglet « Équilibre »
# de « Analyse de mon portefeuille », pas signalés ici.
# Statut changé entre les deux dernières photos du screener (lignes détenues et watchlist).
suivies = list(dict.fromkeys(list(w.index) + list(suivies_wl.index)))
for t, ancien, nouveau, depuis in photos.changements_de_statut(suivies):
    rows.append(("Changement de statut", t, f"{ancien} → {nouveau} depuis la photo du {depuis:%d/%m/%Y}. "
                 "Relire la thèse."))
# Achats groupés de dirigeants (déclarations déjà lues depuis la fiche : aucun accès réseau ici).
for t in suivies:
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

# ------------------------------------------------------------------ la bonne action au bon prix, mon portefeuille
regl = pa.reglages(strat)
vises = {t: float(v) for t, v in suivies_wl["prix_cible"].items() if isinstance(v, (int, float)) and math.isfinite(v)}
reglages_txt = (f"au rendement exigé de {ui.pct(regl['rendement'], 1)} et avec une marge de sécurité de "
                f"{ui.pct(regl['marge'], 0)}, réglables dans « La bonne action au bon prix »")
occasions = pa.tableau(sc, {t: "Univers" for t in sc.index[sc["statut"] == "Éligible"]}, strat["valorisation"],
                       regl["rendement"], regl["marge"], vises)
occasions = occasions[occasions["verdict"] == pa.VERDICTS["bon"]] if not occasions.empty else occasions
lignes = pa.tableau(sc, {t: "Portefeuille" for t in w.index}, strat["valorisation"], regl["rendement"],
                    regl["marge"], vises)

b = st.columns(3)
def chiffre(valeur, libelle: str, aide: str | None = None) -> None:
    """Grand chiffre en ocre, puis son libellé : le même gabarit dans les trois blocs."""
    st.markdown(f'<div class="garp-chiffre">{valeur}</div>', unsafe_allow_html=True)
    st.markdown(libelle, help=aide)


with b[0].container(border=True, height="stretch"):
    st.markdown("##### :material/sell: Au bon prix")
    chiffre(len(occasions), "actions de qualité sous votre prix d'achat",
            f"Parmi les valeurs qui passent les filtres de qualité, {reglages_txt}.")
    if len(occasions):
        st.caption("Les mieux notées (note GARP) : " + " · ".join(
            f"{x['nom']} ({ui.pct(x['ecart_achat'], 0, signe=True)})" for _, x in occasions.head(4).iterrows()))
    if st.button("Voir la sélection", icon=":material/arrow_forward:", key="aller_prix"):
        st.switch_page("vues/prix_achat.py")
with b[1].container(border=True, height="stretch"):
    st.markdown("##### :material/pie_chart: Mon portefeuille")
    if lignes.empty:
        chiffre("—", "aucune ligne pour l'instant")
        st.caption("Importez votre portefeuille pour l'analyser avec les outils de G.A.R.P.")
    else:
        nb = lignes["verdict"].value_counts()
        chiffre(int(nb.get(pa.VERDICTS["bon"], 0)), f"lignes au bon prix, sur {len(lignes)}",
                f"Sur {len(lignes)} lignes, {reglages_txt}.")
        with st.container(horizontal=True, gap="small"):
            for v in (pa.VERDICTS["correct"], pa.VERDICTS["attendre"]):
                if nb.get(v, 0):
                    st.badge(f"{v} : {int(nb[v])}", color=ui.COULEURS_VERDICT[v])
            exclues = int((lignes["statut"] == "Exclu").sum())
            if exclues:
                st.badge(f"Hors des filtres : {exclues}", color="red")
    if st.button("Analyser mon portefeuille", icon=":material/arrow_forward:", key="aller_portefeuille"):
        st.switch_page("vues/modele.py")
with b[2].container(border=True, height="stretch"):
    st.markdown("##### :material/notifications: Vigilance")
    chiffre(len(rows), "points à regarder")
    if rows:
        types = pd.Series([r[0] for r in rows]).value_counts()
        st.caption(" · ".join(f"{k} ({v})" for k, v in types.head(4).items()))
    else:
        st.caption("Aucun : toutes les lignes passent les filtres, sans mouvement extrême.")

st.divider()
if rows:
    st.markdown("#### Points de vigilance")
    al = pd.DataFrame(rows, columns=["Type", "ticker", "Détail"])
    al.insert(1, "Valeur", al["ticker"].map(lambda t: names.get(t, t)))
    ui.tableau(al.drop(columns="ticker"), hide_index=True, width="stretch")
if pos.empty:
    st.caption("Sans quantités importées, ce tableau de bord suit les poids de votre portefeuille. Importez-le avec ses "
               "quantités (page « Importer mon portefeuille ») pour voir sa valeur et ses poids réels.")

# ------------------------------------------------------------------ portefeuille modèle
st.markdown("#### Profil du portefeuille")
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
bcurve = bt.benchmark_curve(bench, debut)
resume = (f"portefeuille {ui.pct(curve.iloc[-1] / 100 - 1, signe=True)}, "
          f"{BENCHMARKS.get(bench, bench)} {ui.pct(bcurve.iloc[-1] / 100 - 1, signe=True)}")
if debut == created:
    st.markdown(f"**Depuis le début du suivi ({created:%d/%m/%Y}, poids cibles)** : {resume}")
else:
    st.markdown(f"**Sur un an glissant (simulation, poids actuels)** : {resume}. Le suivi réel démarre le {created:%d/%m/%Y}.")
ui.show(ui.lines(pd.DataFrame({"Portefeuille": curve, BENCHMARKS.get(bench, bench): bcurve}).dropna(),
                 colors={"Portefeuille": ui.accent(), BENCHMARKS.get(bench, bench): ui.GRIS},
                 yfmt=",.1f", height=300))

# ------------------------------------------------------------------ lignes du modèle
st.markdown("#### Lignes du portefeuille")
t = mp[["nom", "enveloppe", "poche"]].copy()
t["poids"] = w
t = t.join(sc[["score", "perf_1m", "perf_12m", "tri_implicite", "per_prospectif"]])
t = ui.as_pct_cols(t, ["poids", "perf_1m", "perf_12m", "tri_implicite"]).sort_values("poids", ascending=False)
ui.tableau(t, width="stretch", column_config={
    "nom": "Valeur", "enveloppe": "Compte", "poche": "Poche",
    "poids": ui.PCT("Poids"),
    "score": ui.SCORE("Note GARP", "Croissance 40 %, valorisation 35 %, qualité 25 % : rangs dans l'univers, "
                                   "sur 100"),
    "perf_1m": ui.PCT("1 mois"), "perf_12m": ui.PCT("12 mois"),
    "tri_implicite": ui.PCT("TRI implicite"), "per_prospectif": st.column_config.NumberColumn("PER prosp.", format="%.1f"),
})

# ------------------------------------------------------------------ actualités
dernieres = act.fil(sc)
dernieres = dernieres[dernieres["type"] != "À surveiller"].head(5) if not dernieres.empty else dernieres
if len(dernieres):
    st.markdown("#### Dernières actualités")
    for _, x in dernieres.iterrows():
        titre = x["titre"].replace("[", "(").replace("]", ")")
        lien = f"[{titre}]({x['lien']})" if isinstance(x["lien"], str) and x["lien"] else titre
        st.markdown(f"**{x['nom']}** · {pd.Timestamp(x['date']):%d/%m} · {x['source']} · {lien}")
    try:  # le lien n'existe que dans l'application complète (menu de navigation)
        st.page_link("vues/actualites.py", label="Toutes les actualités", icon=":material/newspaper:")
    except Exception:
        st.caption("Toutes les actualités : page « Actualités » du menu.")
