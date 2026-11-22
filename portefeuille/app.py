"""Interface : streamlit run app.py  (ou double-clic sur lancer.bat)."""
import warnings

warnings.filterwarnings("ignore", module=r"yfinance")  # dépréciations pandas en rafale, propres à yfinance

import streamlit as st  # noqa: E402

from pf.ui import sidebar  # noqa: E402

st.set_page_config(page_title="Portefeuille long terme", page_icon=":material/monitoring:", layout="wide")

pages = {
    "Investir": [
        st.Page("vues/accueil.py", title="Tableau de bord", icon=":material/dashboard:", default=True),
        st.Page("vues/actualites.py", title="Actualités", icon=":material/newspaper:"),
        st.Page("vues/modele.py", title="Composition", icon=":material/pie_chart:"),
        st.Page("vues/apport.py", title="Apport du mois", icon=":material/savings:"),
        st.Page("vues/suivi.py", title="Mon portefeuille", icon=":material/account_balance_wallet:"),
        st.Page("vues/risques.py", title="Risques", icon=":material/shield:"),
    ],
    "Analyser": [
        st.Page("vues/screener.py", title="Screener", icon=":material/filter_alt:"),
        st.Page("vues/watchlist.py", title="Watchlist", icon=":material/star:"),
        st.Page("vues/fiche.py", title="Fiche valeur", icon=":material/query_stats:"),
        st.Page("vues/regards.py", title="Quatre regards", icon=":material/visibility:"),
        st.Page("vues/investisseurs.py", title="Grands investisseurs", icon=":material/groups:"),
        st.Page("vues/construction.py", title="Construction de portefeuille", icon=":material/tune:"),
        st.Page("vues/backtest.py", title="Backtest", icon=":material/history:"),
    ],
    "Comprendre": [
        st.Page("vues/methode.py", title="Méthode et routine", icon=":material/menu_book:"),
    ],
}

nav = st.navigation(pages)
sidebar()
nav.run()
