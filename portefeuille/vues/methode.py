from pathlib import Path

import streamlit as st

from pf import ui
from pf.data import load_controles

doc = Path(__file__).resolve().parent.parent / "docs" / "METHODE.md"

with st.expander("État des sources et des recoupements", expanded=True):
    ctl = load_controles()
    fx = ctl.get("change", {})
    res = fx.get("resultat", {})
    ecarts = res.get("ecart_median_yahoo", {})
    pire = max(ecarts.items(), key=lambda kv: kv[1]) if ecarts else None
    st.markdown(
        "- **Cours, fondamentaux, consensus des analystes** : Yahoo Finance.\n"
        "- **Secteurs** : classification GICS publiée par iShares, affinée par l'industrie indiquée par Yahoo.\n"
        f"- **Taux de change** : {res.get('source', 'non mis à jour depuis le passage à la BCE')}"
        + (f", recoupés avec Yahoo (écart médian maximal {ui.pct(pire[1], 2)} sur {pire[0]})" if pire else "")
        + (f". Hors BCE, pris chez Yahoo : {', '.join(res['absentes_bce'])}" if res.get("absentes_bce") else "") + ".\n"
        "- **Composition des indices** : iShares (fonds répliquant le S&P 500 et le STOXX Europe 600)."
    )
    try:
        sc = ui.screener()
        us = sc[~sc.index.str.contains(".", regex=False) & (sc["statut"] != "Fonds")]
        v = us["verif_sec"].value_counts()
        retard = int(us["sec_retard"].fillna(False).astype(bool).sum())
        if v.sum():
            st.markdown(
                f"- **Comptes des sociétés américaines** : recoupés avec la SEC pour {int(v.sum())} valeurs sur {len(us)} : "
                f"{v.get('Confirmé', 0)} confirmées, {v.get('Écart', 0)} avec un écart de plus de 3 %, "
                f"{v.get('Non comparable', 0)} non comparables ; Yahoo en retard d'un exercice pour {retard}."
            )
        else:
            st.markdown("- **Comptes des sociétés américaines** : pas encore recoupés avec la SEC "
                        "(renseigner « contact_sec » dans profil/prive.json, puis mettre à jour).")
    except Exception as exc:  # l'encadré ne doit pas empêcher d'afficher la méthode
        st.caption(f"État du recoupement SEC indisponible : {exc}")
    st.caption("Les sociétés européennes n'ont pas de seconde source gratuite et à jour : leurs chiffres clés "
               "se vérifient dans le rapport annuel lors d'une analyse approfondie.")

st.markdown(doc.read_text(encoding="utf-8"))
