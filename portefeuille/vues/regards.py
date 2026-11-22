import streamlit as st

from pf import ui
from pf.regards import compute_regards, load_adjustments

sc = ui.require_data()
mp = ui.model()

st.title("Quatre regards")
st.markdown(
    "Une note sur 5 par regard, pour toutes les actions de la base :\n\n"
    "- **Buffett** : une bonne entreprise à un prix qui laisse une marge.\n"
    "- **Munger** : ce qui peut faire perdre la moitié de la mise (plus la note est haute, moins c'est fragile).\n"
    "- **Fisher** : la croissance à venir et l'usage du capital.\n"
    "- **Smith** : une rentabilité durable, transformée en cash."
)
st.caption(f"Notes issues de règles fixes sur les indicateurs. Seules {len(load_adjustments())} valeurs ont en plus une correction "
           "manuelle (colonne « Correction »), pour ce que les chiffres ne voient pas ; celles datées ont été vérifiées sur les publications "
           "récentes. Sans correction, un pic de cycle ou un risque réglementaire n'est pas pris en compte. Les fonds ne sont pas notés. "
           "Ce crible désigne quoi analyser, pas quoi acheter : utilisez /analyse-valeur avant toute décision.")

c = st.columns([2, 3, 1])
statut = c[0].segmented_control("Statut", ["Éligible", "Exclu"], selection_mode="multi", default=["Éligible", "Exclu"])
q = c[1].text_input("Recherche", placeholder="Nom ou ticker").strip().lower()
detenues = c[2].toggle("Mes lignes", value=False)

t = compute_regards(sc, tous=True)
t.insert(2, "detenue", t.index.isin(mp.index))
if statut:
    t = t[t["statut"].isin(statut)]
if q:
    t = t[t["nom"].str.lower().str.contains(q, na=False, regex=False) | t.index.str.lower().str.contains(q, regex=False)]
if detenues:
    t = t[t["detenue"]]
st.markdown(f"**{len(t)} valeurs**")
note = lambda label: st.column_config.ProgressColumn(label, min_value=0, max_value=5, format="%d")  # noqa: E731
ui.tableau(t, width="stretch", height=640, column_config={
    "rang": st.column_config.NumberColumn("Rang", format="%d", pinned=True),
    "nom": st.column_config.TextColumn("Valeur", pinned=True), "detenue": st.column_config.CheckboxColumn("Détenue"),
    "statut": "Filtres", "score": ui.SCORE("Score"), "buffett": note("Buffett"), "munger": note("Munger"), "fisher": note("Fisher"),
    "smith": note("Smith"), "total": st.column_config.NumberColumn("Total / 20", format="%d"),
    "correction": st.column_config.TextColumn("Correction", width="large"),
})
st.download_button("Exporter (CSV)", t.to_csv(sep=";", decimal=",").encode("utf-8-sig"), file_name="quatre_regards.csv",
                   mime="text/csv", icon=":material/download:")
