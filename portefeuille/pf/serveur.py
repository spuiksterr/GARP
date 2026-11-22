"""Serveur Streamlit de la fenêtre G.A.R.P (pf/bureau.py) : `python -m pf.serveur <app.py> <options de streamlit run>`.

Il charge d'abord les modules de l'outil (pandas, plotly, Streamlit, pf.ui), puis démarre Streamlit dans le même
processus : la première page les trouve déjà en mémoire et s'ouvre sans attendre. Pendant ce chargement, le serveur
ne répond pas encore, et la fenêtre garde son écran d'attente, qui dit où en est l'ouverture. Streamlit ne crée ses
caches qu'au premier appel d'une fonction, pas à l'import : charger les modules avant lui ne change rien aux caches.
"""
import sys
import warnings


def main() -> None:
    warnings.filterwarnings("ignore", module=r"yfinance")
    from streamlit.web import cli

    import pf.ui  # noqa: F401  (préchargement)

    sys.argv = ["streamlit", "run", *sys.argv[1:]]
    cli.main()


if __name__ == "__main__":
    main()
