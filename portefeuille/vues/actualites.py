"""Actualités de vos lignes et de votre watchlist : presse, déclarations officielles, signaux de l'outil."""
import pandas as pd
import streamlit as st

from pf import actualites as act
from pf import ui

sc = ui.require_data()

st.title("Actualités")
st.caption("Vos lignes (hors fonds) et votre watchlist. Presse française (Google Actualités), déclarations officielles à "
           "la SEC pour les sociétés américaines, dates de résultats, et signaux de l'outil. Les titres seuls : cliquez "
           "pour lire l'article. Une nouvelle n'est pas une raison d'agir : relisez d'abord la thèse.")

precedente = act.derniere_visite()
c1, c2 = st.columns([3, 1], vertical_alignment="center")
lus = [(act.lire_json(act.path_of(t)) or {}).get("lu") for t in act.suivis()]
lus = [x for x in lus if x]
c1.caption(f"Lues le {pd.Timestamp(min(lus)):%d/%m/%Y à %H:%M}" if lus else "Jamais lues : cliquez sur « Rafraîchir ».")
if c2.button("Rafraîchir", icon=":material/refresh:", width="stretch",
             help="Relit les sources pour toutes les valeurs suivies (une vingtaine de secondes). Aussi fait par les "
                  "mises à jour."):
    with st.spinner("Lecture des actualités…"):
        act.mettre_a_jour(sc["nom"].to_dict(), force=True)
    st.rerun()

f = act.fil(sc)
if f.empty:
    st.info("Aucune actualité pour l'instant : cliquez sur « Rafraîchir ».")
    st.stop()

# --------------------------------------------------------------------------- à surveiller
etat = f[f["type"] == "À surveiller"]
if len(etat):
    with st.container(border=True):
        st.markdown("**À surveiller**")
        for _, x in etat.sort_values(["nom", "source"]).iterrows():
            detail = f" — {x['detail']}" if isinstance(x["detail"], str) and x["detail"] else ""
            st.markdown(f"- **{x['nom']}** · {x['titre']}{detail}")

# --------------------------------------------------------------------------- fil
fil = f[f["type"] != "À surveiller"]
g = st.columns([2, 2])
valeurs = g[0].multiselect("Valeurs", sorted(fil["nom"].unique()), placeholder="Toutes les valeurs suivies",
                           key="act_valeurs")
types = g[1].segmented_control("Type", ["Presse", "Déclaration officielle", "Signal"], selection_mode="multi",
                               default=["Presse", "Déclaration officielle", "Signal"], key="act_types")
if valeurs:
    fil = fil[fil["nom"].isin(valeurs)]
fil = fil[fil["type"].isin(types or [])].head(200)

nouveaux = int((fil["date"] > precedente).sum()) if precedente else 0
if precedente:
    st.caption(f"{nouveaux} nouveauté(s) depuis votre dernière visite ({pd.Timestamp(precedente):%d/%m à %H:%M}).")

aujourdhui = pd.Timestamp.today().normalize()
icones = {"Presse": ":material/article:", "Déclaration officielle": ":material/gavel:", "Signal": ":material/insights:"}
for jour, groupe in fil.groupby(fil["date"].str[:10], sort=False):
    d = pd.Timestamp(jour)
    libelle = ("Aujourd'hui" if d == aujourdhui else "Hier" if d == aujourdhui - pd.Timedelta(days=1)
               else f"{d:%d/%m/%Y}")
    st.markdown(f"##### {libelle}")
    for _, x in groupe.iterrows():
        neuf = " :blue-badge[Nouveau]" if precedente and x["date"] > precedente else ""
        titre = x["titre"].replace("[", "(").replace("]", ")")
        lien = f"[{titre}]({x['lien']})" if isinstance(x["lien"], str) and x["lien"] else titre
        detail = f" — {x['detail']}" if isinstance(x["detail"], str) and x["detail"] else ""
        st.markdown(f"{icones.get(x['type'], '')} **{x['nom']}** · {x['source']} · {lien}{detail}{neuf}")

act.marquer_vu()
