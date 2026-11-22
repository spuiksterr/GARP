"""Interface : streamlit run app.py  (ou double-clic sur lancer.bat)."""
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", module=r"yfinance")  # dépréciations pandas en rafale, propres à yfinance

import streamlit as st  # noqa: E402

from pf.ui import sidebar  # noqa: E402

# L'icône sert aussi d'icône d'application quand on ajoute la page à l'écran d'accueil du téléphone.
ICONE = str(Path(__file__).resolve().parent / "assets" / "garp.png")
st.set_page_config(page_title="G.A.R.P", page_icon=ICONE, layout="wide")
# En-tête de la barre latérale : l'icône et « G.A.R.P » en grand (assets/entete.png, composer_icones.py), l'icône
# seule quand la barre est repliée. st.logo les place au-dessus des rubriques ; la règle de style les agrandit.
st.logo(str(Path(__file__).resolve().parent / "assets" / "entete.png"), size="large", icon_image=ICONE)
st.html("""<style>
[data-testid="stSidebarHeader"] { height: auto; padding-top: 1.5rem; padding-bottom: 1rem; align-items: center; }
[data-testid="stSidebarLogo"] { height: 4.4rem; max-width: 100%; }
/* Barre du haut épurée : ni bonhomme animé ni bouton « Stop » pendant les calculs. */
[data-testid="stStatusWidget"] { display: none; }
/* Chiffre principal des blocs du tableau de bord, en ocre de la marque (lisible sur les deux thèmes en grand). */
.garp-chiffre { font-family: Manrope, sans-serif; font-weight: 800; font-size: 3rem; line-height: 1.05;
                color: #b9781f; margin: 0.25rem 0 0.5rem; }
/* Verdict de prix : le mot, en couleur, sur une pastille légèrement teintée. */
.garp-verdict { display: inline-block; font-family: Manrope, sans-serif; font-weight: 700; font-size: 1.5rem;
                padding: 0.15rem 0.7rem; border-radius: 0.6rem; margin-bottom: 0.2rem; }
.garp-verdict-green { color: #1f9d55; background: rgba(31, 157, 85, 0.14); }
.garp-verdict-orange { color: #c98500; background: rgba(201, 133, 0, 0.14); }
.garp-verdict-gray { color: #898781; background: rgba(137, 135, 129, 0.16); }
</style>""")

# L'outil sert d'abord à trouver la bonne action au bon prix ; votre portefeuille, importé du courtier, est analysé
# avec les mêmes outils (l'équilibre n'y est qu'un onglet de propositions), avec ses risques et votre style
# d'investisseur, qui classe « La bonne action au bon prix ». « Explorer » pour le reste. Tout est
# affiché : rien n'est caché derrière « View more ».
pages = {
    "": [
        st.Page("vues/accueil.py", title="Tableau de bord", icon=":material/dashboard:", default=True),
    ],
    "Trouver": [
        st.Page("vues/prix_achat.py", title="La bonne action au bon prix", icon=":material/sell:"),
        st.Page("vues/screener.py", title="Screener", icon=":material/filter_alt:"),
        st.Page("vues/fiche.py", title="Fiche valeur", icon=":material/query_stats:"),
        st.Page("vues/watchlist.py", title="Watchlist", icon=":material/star:"),
    ],
    "Mon portefeuille": [
        st.Page("vues/modele.py", title="Analyse de mon portefeuille", icon=":material/pie_chart:"),
        st.Page("vues/risques.py", title="Risques", icon=":material/shield:"),
        st.Page("vues/importer.py", title="Importer mon portefeuille", icon=":material/upload_file:"),
        st.Page("vues/style.py", title="Mon style d'investisseur", icon=":material/psychology:"),
    ],
    "Explorer": [
        st.Page("vues/actualites.py", title="Actualités", icon=":material/newspaper:"),
        st.Page("vues/regards.py", title="Quatre regards", icon=":material/visibility:"),
        st.Page("vues/investisseurs.py", title="Grands investisseurs", icon=":material/groups:"),
        st.Page("vues/construction.py", title="Construction automatique", icon=":material/tune:"),
        st.Page("vues/backtest.py", title="Backtest", icon=":material/history:"),
        st.Page("vues/methode.py", title="Méthode et routine", icon=":material/menu_book:"),
    ],
}

nav = st.navigation(pages, expanded=True)
sidebar()
nav.run()
