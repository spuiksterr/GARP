import pandas as pd
import streamlit as st

from pf import prix_juste, ui
from pf import watchlist as wl

sc = ui.require_data()
mp = ui.model()
names = ui.label_map(sc)

st.title("Watchlist")
st.caption("Cliquez sur une valeur pour ouvrir sa fiche. Cochez une ligne pour la retirer ou la déplacer dans la liste. "
           "On ajoute une valeur ici, depuis sa fiche ou depuis le screener. Le prix visé se fixe dans la fiche, "
           "section « Prix juste ».")

CLE = "wl_tableau"


def _cle_tableau() -> str:
    return f"{CLE}_{st.session_state.get(CLE, 0)}"


def _cocher(positions: list[int]) -> None:
    """Coche les lignes données au prochain affichage (aucune si la liste est vide)."""
    st.session_state[_cle_tableau()] = {"selection": {"rows": positions, "columns": [], "cells": []}}


def _placer(ticker: str, position: int) -> None:
    _cocher([wl.placer(ticker, position)])  # la ligne déplacée reste cochée : on peut enchaîner


def _nouveau_tableau() -> None:
    """Tableau neuf quand la liste change de taille : avec la même clé, le premier clic suivant serait perdu."""
    st.session_state[CLE] = st.session_state.get(CLE, 0) + 1


def _retirer_cochees(tickers: list[str]) -> None:
    for t in tickers:
        wl.retirer(t)
    _nouveau_tableau()


def _ajouter() -> None:
    t, st.session_state["wl_ajout"] = st.session_state.get("wl_ajout"), None
    if t:
        ui.ajouter_watchlist([t])
        _nouveau_tableau()


liste = wl.load_watchlist()
onglet_wl, onglet_surv = st.tabs([f"Ma watchlist ({len(liste)})", "Surveillance : conditions d'entrée"])

with onglet_wl:
    ordre = sorted(sc.index, key=lambda t: str(sc.loc[t, "nom"]).lower())
    st.selectbox("Ajouter une valeur", [t for t in ordre if t not in liste.index], index=None, key="wl_ajout",
                 on_change=_ajouter, format_func=lambda t: names.get(t, t), placeholder="Nom ou ticker")
    if liste.empty:
        st.info("Watchlist vide. Ajoutez une valeur ci-dessus, avec le bouton « Ajouter à la watchlist » de sa fiche, "
                "ou en cochant sa ligne dans le screener.", icon=":material/star:")
    else:
        cols = ["nom", "secteur", "statut", "rang", "score", "criteres", "moat", "cours", "devise", "perf_1m", "perf_12m",
                "per", "ecart_per_historique", "p_fcf", "tri_implicite", "alertes"]
        t = liste.join(sc.reindex(columns=cols), how="left")  # ordre de la liste, celui que vous avez choisi
        t["nom"] = t["nom"].fillna(pd.Series(t.index, index=t.index))
        t["cours"] = pd.to_numeric(t["cours"], errors="coerce")
        t["depuis_ajout"] = t["cours"] / pd.to_numeric(t["cours_ajout"], errors="coerce") - 1
        t["ecart_prix_vise"] = [prix_juste.ecart(p, c) for p, c in zip(t["prix_cible"], t["cours"])]
        atteints = wl.prix_vises_atteints(t["cours"], liste)
        if len(atteints):
            st.success("Prix visé atteint : " + ", ".join(
                f"**{t.loc[x, 'nom']}** ({ui.num(a['cours'], 2)} {t.loc[x, 'devise']} pour {ui.num(a['prix_cible'], 2)} "
                f"{t.loc[x, 'devise']} visé"
                f"{', ' + a['objectif'] if a['objectif'] else ''})" for x, a in atteints.iterrows())
                + ". Relisez la thèse avant toute décision : un prix bas ne suffit pas, il peut refléter un problème nouveau.",
                icon=":material/flag:")
        show = ui.as_pct_cols(t[["nom", "cours", "devise", "prix_cible", "ecart_prix_vise", "objectif", "statut", "rang", "score",
                                 "criteres", "moat", "depuis_ajout", "perf_1m", "perf_12m", "per", "ecart_per_historique",
                                 "p_fcf", "tri_implicite", "secteur", "ajoute_le", "alertes"]],
                              ["ecart_prix_vise", "depuis_ajout", "perf_1m", "perf_12m", "ecart_per_historique", "tri_implicite"])
        show.insert(0, "position", range(1, len(show) + 1))
        show.insert(2, "symbole", show.index)  # colonne ordinaire : un clic sur l'index ne renvoie rien
        event = ui.tableau(
            show, width="stretch", height=min(700, 35 * len(show) + 38), on_select="rerun",
            selection_mode=["single-cell", "multi-row"], key=_cle_tableau(), hide_index=True,
            column_config={
                "position": st.column_config.NumberColumn("N°", format="%d", pinned=True, width="small"),
                "nom": st.column_config.TextColumn("Valeur", pinned=True), "symbole": "Ticker", "statut": "Statut",
                "cours": st.column_config.NumberColumn("Cours", format="%.2f", help="Dernier cours, devise de cotation"),
                "devise": st.column_config.TextColumn("Devise", width="small"),
                "prix_cible": st.column_config.NumberColumn(
                    "Prix visé", format="%.2f", help="Prix d'achat fixé dans la fiche, section « Prix juste »"),
                "ecart_prix_vise": ui.PCT("Écart au prix visé", "Variation du cours qui mènerait au prix visé : −20 % = il "
                                          "faut une baisse de 20 %. Positif : le cours est déjà sous le prix visé."),
                "objectif": st.column_config.TextColumn("Objectif", help="Le ratio et la cible qui ont fixé le prix visé"),
                "rang": st.column_config.NumberColumn("Rang", format="%d"), "score": ui.SCORE("Score"),
                "criteres": st.column_config.TextColumn("Critères", help="Critères de qualité remplis sur critères évalués"),
                "moat": "Moat estimé",
                "depuis_ajout": ui.PCT("Depuis l'ajout", "Évolution du cours depuis l'ajout à la watchlist (devise de cotation)"),
                "perf_1m": ui.PCT("1 mois"), "perf_12m": ui.PCT("12 mois"),
                "per": st.column_config.NumberColumn("PER", format="%.1f"),
                "ecart_per_historique": ui.PCT("PER / histoire", "PER actuel comparé à son niveau habituel", 0),
                "p_fcf": st.column_config.NumberColumn("P/FCF", format="%.1f"),
                "tri_implicite": ui.PCT("TRI implicite"), "secteur": "Secteur",
                "ajoute_le": st.column_config.TextColumn("Ajoutée le"),
                "alertes": st.column_config.TextColumn("Alertes", width="large"),
            })
        ui.fiche_au_clic(show, event, CLE, lignes=False)  # clic sur une cellule : la fiche

        # Lignes cochées : retirer, ou déplacer (une seule à la fois).
        cochees = [show.index[i] for i in (event.selection.rows if event and event.selection else [])]
        if cochees:
            noms = ", ".join(str(show.loc[x, "nom"]) for x in cochees)
            with st.container(border=True):
                st.markdown(f"**{noms}**")
                b = st.columns([1, 1, 1, 1, 1.4])
                if len(cochees) == 1:
                    x, pos, dernier = cochees[0], list(show.index).index(cochees[0]), len(show) - 1
                    b[0].button("Monter", icon=":material/arrow_upward:", on_click=_placer, args=(x, pos - 1),
                                disabled=pos == 0, width="stretch")
                    b[1].button("Descendre", icon=":material/arrow_downward:", on_click=_placer, args=(x, pos + 1),
                                disabled=pos == dernier, width="stretch")
                    b[2].button("En tête", icon=":material/vertical_align_top:", on_click=_placer, args=(x, 0),
                                disabled=pos == 0, width="stretch")
                    b[3].button("En dernier", icon=":material/vertical_align_bottom:", on_click=_placer, args=(x, dernier),
                                disabled=pos == dernier, width="stretch")
                else:
                    b[0].caption("Cochez une seule ligne pour la déplacer.")
                b[4].button(f"Retirer de la watchlist ({len(cochees)})", icon=":material/delete:", on_click=_retirer_cochees,
                            args=(cochees,), width="stretch")

with onglet_surv:
    sv = ui.surveillance()
    if sv.empty:
        st.info("Aucune valeur en surveillance.")
    else:
        detenues = [t for t in sv.index if t in mp.index]
        if detenues:
            st.caption("Déjà en portefeuille, donc retirées de cette liste : " + ", ".join(sc["nom"].get(t, t) for t in detenues)
                       + ". Supprimez la ligne de profil/surveillance.csv quand vous le souhaitez.")
            sv = sv.drop(index=detenues)
        st.markdown("Valeurs de qualité écartées **pour l'instant**, avec la condition qui justifierait de les acheter "
                    "(fichier profil/surveillance.csv, rempli lors des analyses).")
        sv = sv.join(sc.reindex(columns=["score", "tri_implicite", "per_prospectif", "mom_12_1"]))
        sv = ui.as_pct_cols(sv, ["tri_implicite", "mom_12_1"])
        sv.insert(1, "symbole", sv.index)
        cle = "surv_tableau"
        event = ui.tableau(
            sv, width="stretch", on_select="rerun", selection_mode="single-cell", key=f"{cle}_{st.session_state.get(cle, 0)}",
            hide_index=True,
            column_config={
                "nom": st.column_config.TextColumn("Valeur", pinned=True), "symbole": "Ticker",
                "raison": st.column_config.TextColumn("Pourquoi pas maintenant", width="large"),
                "condition_entree": st.column_config.TextColumn("Condition d'entrée", width="large"),
                "score": ui.SCORE("Score"), "tri_implicite": ui.PCT("TRI implicite"),
                "per_prospectif": st.column_config.NumberColumn("PER prosp.", format="%.1f"), "mom_12_1": ui.PCT("Momentum"),
            })
        ui.fiche_au_clic(sv, event, cle)
