"""Screener unifié : filtres de qualité, note GARP, prix juste / prix d'achat, verdicts et suivi watchlist."""
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pf import prix_achat as pa
from pf import ui
from pf import watchlist as wl
from pf.config import load_strategy

ui.require_data()
strat = load_strategy()
vcfg = strat["valorisation"]
regl = pa.reglages(strat)
sc = ui.screener()
mp = ui.model()
suivies_df = wl.load_watchlist()

st.title("Screener")
st.caption("Les entreprises qui passent les filtres de qualité sont classées par la note GARP (croissance, valorisation, "
           "qualité), avec leur prix d'achat au rendement exigé et votre marge de sécurité. Quatre regards, six critères "
           "et signaux de santé restent affichés comme repères, hors note.")

# Pré-filtre éventuel depuis le bouton « Voir la sélection » du tableau de bord.
if pre := st.session_state.pop("scr_prefiltre_verdict", None):
    st.session_state["scr_verdicts"] = pre

# --------------------------------------------------------------------------- filtres principaux
f1 = st.columns([2.4, 1.1, 2.5, 1.8])
perimetre = f1[0].segmented_control(
    "Périmètre", ["Actions de qualité", "Exclues", "Mon portefeuille", "Ma watchlist"],
    default="Actions de qualité", key="scr_perimetre",
) or "Actions de qualité"
env = f1[1].segmented_control("Compte", ["PEA", "CTO"], selection_mode="multi", default=["PEA", "CTO"], key="scr_env")
verdicts = f1[2].segmented_control(
    "Verdict", list(pa.VERDICTS.values()), selection_mode="multi", key="scr_verdicts",
    help="Filtre sur le verdict de prix (Au bon prix = cours sous votre prix d'achat). Vide = tous.",
)
recherche = f1[3].text_input("Recherche", placeholder="Nom ou ticker", key="scr_q")

actifs = sum(bool(st.session_state.get(k)) for k in ("scr_moat", "scr_secteurs", "scr_pays", "scr_pfcf", "scr_crit",
                                                     "scr_decote"))
label_exp = (f"Prix d'achat ({ui.pct(regl['rendement'], 1)} · marge {ui.pct(regl['marge'], 0)}) & plus de filtres"
             + (f" ({actifs} actif{'s' if actifs > 1 else ''})" if actifs else ""))
with st.expander(label_exp, icon=":material/tune:"):
    p_cols = st.columns([1.4, 1.4, 2.2])
    rendement = p_cols[0].slider(
        "Rendement exigé (par an)", 5.0, 15.0, regl["rendement"] * 100, 0.5, format="%.1f %%", key="scr_rendement",
        help="Rendement annuel souhaité. Plus il est élevé, plus le prix juste et le prix d'achat sont bas.",
    )
    marge = p_cols[1].slider(
        "Marge de sécurité", 0, 40, round(regl["marge"] * 100), 5, format="%d %%", key="scr_marge",
        help="Rabais demandé sous le prix juste avant d'acheter : il couvre l'erreur d'estimation.",
    )
    p_cols[2].caption("Ces réglages sont retenus pour vos prochaines visites et servent aussi sur la Fiche valeur, "
                      "le Tableau de bord et Mon portefeuille.")
    if (rendement / 100, marge / 100) != (regl["rendement"], regl["marge"]):
        pa.enregistrer_reglages(rendement / 100, marge / 100)

    g = st.columns([1.6, 2, 2])
    moat = g[0].segmented_control("Moat estimé", ["Large", "Étroit", "Faible"], selection_mode="multi", key="scr_moat",
                                  help="Traces d'un avantage concurrentiel dans les comptes. Ce n'est pas le moat de "
                                       "Morningstar.")
    secteurs = g[1].multiselect("Secteurs", sorted(sc["secteur"].dropna().unique()), placeholder="Tous les secteurs",
                                key="scr_secteurs")
    pays = g[2].multiselect("Pays", sorted(sc["pays"].dropna().unique()), placeholder="Tous les pays", key="scr_pays")
    h = st.columns([1.2, 1.2, 1.5, 2])
    pfcf_max = h[0].number_input("P/FCF maximum", min_value=0, max_value=200, value=0, step=5, key="scr_pfcf",
                                 help="Prix / flux de trésorerie disponible des 12 derniers mois. 0 : pas de limite.")
    crit_min = h[1].number_input("Critères min.", min_value=0, max_value=6, value=0, step=1, key="scr_crit",
                                 help="Nombre minimal de critères de qualité remplis, sur six.")
    h[2].markdown('<div style="height:1.9rem"></div>', unsafe_allow_html=True)
    sous_histoire = h[2].toggle("P/FCF décoté", value=False, key="scr_decote",
                                help="Ne garder que les actions dont le P/FCF est inférieur à leur médiane historique.")

# --------------------------------------------------------------------------- périmètre & prix d'achat
if perimetre == "Actions de qualité":
    base_idx = sc.index[sc["statut"] == "Éligible"]
elif perimetre == "Exclues":
    base_idx = sc.index[sc["statut"] == "Exclu"]
elif perimetre == "Mon portefeuille":
    base_idx = sc.index[sc.index.isin(mp.index)]
else:
    base_idx = sc.index[sc.index.isin(suivies_df.index)]

prix_vises = {t: float(v) for t, v in suivies_df["prix_cible"].items()
              if isinstance(v, (int, float)) and math.isfinite(v)}
tab_prix = pa.tableau(sc, {t: perimetre for t in base_idx}, vcfg, rendement / 100, marge / 100, prix_vises)

view = sc.loc[base_idx].copy()
if not tab_prix.empty:
    view = view.join(tab_prix[["verdict", "prix_achat", "prix_juste", "ecart_achat", "prix_vise", "vise_atteint"]])
else:
    for col in ("verdict", "prix_achat", "prix_juste", "ecart_achat", "prix_vise", "vise_atteint"):
        view[col] = None

# Compteurs de verdicts sur le périmètre (avant filtrage par verdict).
nb_verdicts = view["verdict"].value_counts() if "verdict" in view.columns else {}
m = st.columns(4)
for col, v in zip(m, pa.VERDICTS.values()):
    col.metric(v, int(nb_verdicts.get(v, 0)), border=True, help=pa.EXPLICATIONS[v])

# Filtres sur la vue.
if env:
    view = view[view["enveloppe"].isin(env) | view["enveloppe"].isna()]
if verdicts:
    view = view[view["verdict"].isin(verdicts)]
if moat:
    view = view[view["moat"].isin(moat)]
if secteurs:
    view = view[view["secteur"].isin(secteurs)]
if pays:
    view = view[view["pays"].isin(pays)]
if pfcf_max:
    view = view[view["p_fcf"] <= pfcf_max]
if sous_histoire:
    view = view[view["ecart_p_fcf_historique"] < 0]
if crit_min:
    view = view[view["criteres_ok"].fillna(0) >= crit_min]
if recherche:
    q = recherche.lower()
    view = view[view["nom"].str.lower().str.contains(q, na=False, regex=False)
                | view.index.str.lower().str.contains(q, regex=False)]

if view.empty:
    st.info("Aucune valeur ne correspond à ces filtres.", icon=":material/info:")
    st.stop()

# --------------------------------------------------------------------------- tableau unifié
t_head = st.columns([3, 1], vertical_alignment="bottom")
t_head[0].markdown(f"**{len(view)} valeurs**")
avancees = t_head[1].toggle("Colonnes avancées", key="scr_avancees",
                            help="Toutes les mesures : prix juste, prix visé, piliers, quatre regards, signaux de "
                                 "santé, six critères, P/FCF, volatilité, risque homme-clé…")

ESSENTIELLES = ["rang", "nom", "verdict", "ecart_achat", "cours", "prix_achat", "devise", "score", "moat",
                "criteres", "tri_implicite", "per_prospectif", "enveloppe", "secteur"]
AVANCEES = [
    "rang", "nom", "verdict", "ecart_achat", "cours", "prix_achat", "prix_juste", "devise", "prix_vise",
    "score", "moat", "criteres", "enveloppe", "secteur", "exercices_historique",
    "ecart_per_historique", "p_fcf", "p_fcf_net", "ecart_p_fcf_historique",
    "regards_total", "buffett", "munger", "fisher", "smith",
    "piotroski", "altman_z", "beneish_m", "verif_sec", "homme_cle",
    "qualite", "croissance", "valorisation", "momentum", "rentabilite",
    "marge_operationnelle", "croissance_attendue", "per_prospectif", "rendement_fcf",
    "croissance_implicite", "tri_implicite", "mom_12_1", "volatilite",
    "crit_ca", "crit_fcf", "crit_roce", "crit_dette", "crit_actions", "crit_marge",
    "capitalisation_eur", "alertes", "motifs_exclusion",
]
cols = AVANCEES if avancees else ESSENTIELLES
show = view.reindex(columns=cols).copy()
if "capitalisation_eur" in show.columns:
    show["capitalisation_eur"] = show["capitalisation_eur"] / 1e9
if "prix_vise" in show.columns:
    show["prix_vise"] = [
        ("—" if not (isinstance(v, (int, float)) and math.isfinite(v))
         else ui.num(v, 2) + (" · atteint" if a else ""))
        for v, a in zip(view["prix_vise"], view["vise_atteint"].fillna(False))
    ]
show = ui.as_pct_cols(show, [
    "ecart_achat", "rentabilite", "marge_operationnelle", "croissance_attendue", "rendement_fcf",
    "croissance_implicite", "tri_implicite", "mom_12_1", "volatilite", "ecart_per_historique",
    "ecart_p_fcf_historique", "crit_ca", "crit_fcf", "crit_roce", "crit_actions", "crit_marge",
])
show["verdict"] = ui.pastilles_verdict(show["verdict"])
show.insert(0, "symbole", show.index)

barre = st.container()
cle = f"scr_tableau_{perimetre}"
selection = ui.tableau(
    show, width="stretch", height=580, on_select="rerun", selection_mode=["single-cell", "multi-row"],
    key=ui.cle_tableau(cle), hide_index=True,
    column_config={
        "symbole": st.column_config.TextColumn("Ticker", pinned=True),
        "rang": st.column_config.NumberColumn("Rang", format="%d", pinned=True),
        "nom": st.column_config.TextColumn("Valeur", pinned=True, width="medium"),
        "verdict": ui.colonne_verdict(),
        "ecart_achat": ui.PCT("Cours / prix d'achat", "Négatif : le cours est sous votre prix d'achat.", 0),
        "cours": st.column_config.NumberColumn("Cours", format="%.2f"),
        "prix_achat": st.column_config.NumberColumn("Prix d'achat", format="%.2f",
                                                    help="Prix juste moins votre marge de sécurité."),
        "prix_juste": st.column_config.NumberColumn("Prix juste", format="%.2f"),
        "devise": "Devise",
        "prix_vise": st.column_config.TextColumn("Votre prix visé", help="Fixé dans la watchlist."),
        "enveloppe": "Compte", "secteur": "Secteur",
        "score": ui.SCORE("Note GARP", "Croissance, valorisation, qualité : rangs centiles parmi les éligibles, sur 100"),
        "moat": st.column_config.TextColumn("Moat estimé", help="Rentabilité élevée et tenue, prix défendus."),
        "p_fcf": st.column_config.NumberColumn("P/FCF", format="%.1f", help="Capitalisation / FCF 12 mois"),
        "p_fcf_net": st.column_config.NumberColumn("P/FCF hors SBC", format="%.1f",
                                                   help="Capitalisation / (FCF − rémunérations en actions)"),
        "ecart_p_fcf_historique": ui.PCT("P/FCF / histoire", "P/FCF actuel comparé à sa médiane historique", 0),
        "ecart_per_historique": ui.PCT("PER / histoire", "PER actuel comparé à sa médiane historique", 0),
        "regards_total": st.column_config.NumberColumn("Regards / 20", format="%d"),
        "buffett": st.column_config.NumberColumn("Buffett", format="%d"),
        "munger": st.column_config.NumberColumn("Munger", format="%d"),
        "fisher": st.column_config.NumberColumn("Fisher", format="%d"),
        "smith": st.column_config.NumberColumn("Smith", format="%d"),
        "piotroski": st.column_config.NumberColumn("Piotroski", format="%d"),
        "altman_z": st.column_config.NumberColumn("Altman", format="%.1f"),
        "beneish_m": st.column_config.NumberColumn("Beneish", format="%.2f"),
        "homme_cle": st.column_config.NumberColumn("Homme-clé / 10", format="%.1f"),
        "verif_sec": st.column_config.TextColumn("Vérif. SEC"),
        "qualite": ui.SCORE("Qualité"), "croissance": ui.SCORE("Croiss."),
        "valorisation": ui.SCORE("Valo."), "momentum": ui.SCORE("Mom."),
        "rentabilite": ui.PCT("ROIC/ROE"), "marge_operationnelle": ui.PCT("Marge op."),
        "croissance_attendue": ui.PCT("Croiss. att."),
        "per_prospectif": st.column_config.NumberColumn("PER prosp.", format="%.1f"),
        "rendement_fcf": ui.PCT("Rdt FCF"), "croissance_implicite": ui.PCT("Croiss. implicite"),
        "tri_implicite": ui.PCT("TRI implicite"), "mom_12_1": ui.PCT("Mom. 12-1"),
        "volatilite": ui.PCT("Volatilité"),
        "exercices_historique": st.column_config.NumberColumn("Historique", format="%d ex."),
        "criteres": st.column_config.TextColumn("Critères"),
        "crit_ca": ui.PCT("CA / an (5 ans)"), "crit_fcf": ui.PCT("FCF / an (5 ans)"),
        "crit_roce": ui.PCT("ROCE moyen"), "crit_dette": st.column_config.NumberColumn("Dette nette / FCF", format="%.2f"),
        "crit_actions": ui.PCT("Actions (5 ans)"), "crit_marge": ui.PCT("Marge FCF"),
        "capitalisation_eur": st.column_config.NumberColumn("Capi. (Md€)", format="%.1f"),
        "alertes": st.column_config.TextColumn("Alertes", width="large"),
        "motifs_exclusion": st.column_config.TextColumn("Motifs d'exclusion", width="large"),
    })
ui.fiche_au_clic(show, selection, cle, lignes=False)

choisies = [show.index[i] for i in (selection.selection.rows if selection and selection.selection else [])]
with barre:
    b = st.columns([1.4, 1.7, 1.4, 2.5], vertical_alignment="center")
    nouvelles = [t for t in choisies if not wl.contient(t)]
    if b[0].button(f"Ajouter à la watchlist ({len(nouvelles)})", icon=":material/star:", disabled=not nouvelles,
                   width="stretch", help="Ajoute les lignes cochées à la watchlist, sans prix visé."):
        ui.ajouter_watchlist(nouvelles)
        st.toast(f"{len(nouvelles)} valeur(s) ajoutée(s) à la watchlist.", icon=":material/star:")
        st.rerun()
    fixables = [t for t in choisies if isinstance(view.loc[t, "prix_achat"], (int, float))
                and math.isfinite(view.loc[t, "prix_achat"])]
    if b[1].button(f"Suivre au prix d'achat ({len(fixables)})", icon=":material/flag:", disabled=not fixables,
                   width="stretch", help="Inscrit le prix d'achat comme prix visé dans la watchlist."):
        for t in fixables:
            wl.fixer_cible(t, float(view.loc[t, "prix_achat"]),
                           f"Prix d'achat : rendement {ui.num(rendement, 1)} %, marge {marge} %",
                           cours=float(view.loc[t, "cours"]) if pd.notna(view.loc[t, "cours"]) else None)
        st.toast(f"{len(fixables)} valeur(s) suivie(s) au prix d'achat.", icon=":material/flag:")
        st.rerun()
    deja_wl = [t for t in choisies if wl.contient(t)]
    if b[2].button(f"Retirer watchlist ({len(deja_wl)})", icon=":material/star_border:", disabled=not deja_wl,
                   width="stretch"):
        for t in deja_wl:
            wl.retirer(t)
        st.toast(f"{len(deja_wl)} valeur(s) retirée(s) de la watchlist.", icon=":material/star_border:")
        st.rerun()
    b[3].caption("Cliquez sur une valeur pour ouvrir sa fiche, ou cochez des lignes (à gauche) pour les ajouter à la "
                 "watchlist." if not choisies else f"{len(choisies)} ligne(s) cochée(s).")

st.download_button(
    "Exporter la sélection (CSV)",
    view.drop(columns=["profil"], errors="ignore").to_csv(sep=";", decimal=",").encode("utf-8-sig"),
    file_name=f"screener-{ui.stamp()}.csv", mime="text/csv", icon=":material/download:",
)

st.subheader("Croissance et valorisation")
st.caption("En haut à droite : la croissance à prix raisonnable, le cœur de la note GARP. Taille : capitalisation. "
           "Survolez un point pour le détail (qualité et note GARP).")
fig = go.Figure()
for i, e in enumerate(["PEA", "CTO"]):
    d = view[view["enveloppe"] == e]
    if d.empty:
        continue
    size = (d["capitalisation_eur"].fillna(1e10) / 1e9) ** 0.5
    fig.add_trace(go.Scatter(
        x=d["valorisation"], y=d["croissance"], mode="markers", name=e,
        marker=dict(size=(size / size.max() * 28).clip(lower=8), color=ui.couleurs()["series"][i], opacity=0.85,
                    line=dict(width=2, color=ui.couleurs()["surface"])),
        text=d["nom"], customdata=d[["score", "tri_implicite", "qualite"]].values,
        hovertemplate="<b>%{text}</b><br>Croissance %{y:.0f} · Valorisation %{x:.0f} · Qualité %{customdata[2]:.0f}"
                      "<br>Note GARP %{customdata[0]:.0f} · TRI %{customdata[1]:.1%}<extra>" + e + "</extra>"))
ui.style(fig, 520)
fig.update_xaxes(title="Valorisation (rang centile, 100 = la moins chère)", range=[0, 102], showgrid=True, gridcolor=ui.TRAIT)
fig.update_yaxes(title="Croissance (rang centile)", range=[0, 102])
ui.show(fig)
