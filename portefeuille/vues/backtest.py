import pandas as pd
import streamlit as st

from pf import backtest as bt
from pf import portfolio as pfo
from pf import ui
from pf.config import BENCHMARKS, SELECTION_CLAUDE_CSV

sc = ui.require_data()
names = ui.label_map(sc)

st.title("Backtest")
MODES = ["Mon portefeuille : profil de risque", "Méthodes de notation : test à date"]
mode = st.segmented_control("Type de backtest", MODES, default=MODES[0], key="bt_mode",
                            label_visibility="collapsed") or MODES[0]

if mode == MODES[0]:
    st.warning(
        "**Biais rétrospectif.** Les valeurs testées sont celles détenues ou choisies aujourd'hui, en connaissant leur "
        "parcours : leur passé est souvent flatteur. Le backtest sert à comprendre le **profil de risque** (pertes "
        "maximales, volatilité, comportement en crise), pas à promettre une performance future. Le vrai juge : le suivi "
        "réel, sur le tableau de bord.", icon=":material/warning:")

    c = st.columns(4)
    options = ["Mon portefeuille (poids cibles)"]
    if SELECTION_CLAUDE_CSV.exists():
        options.append("Sélection Claude (octobre 2026)")
    choix = c[0].selectbox("Portefeuille", options + ["Systématique (paramètres enregistrés)", "Personnalisé"])
    start = c[1].date_input("Depuis", value=pd.Timestamp("2016-01-01"), min_value=pd.Timestamp("2010-01-04"),
                            max_value=pd.Timestamp.today() - pd.Timedelta(days=60), format="DD/MM/YYYY")
    freq_label = c[2].selectbox("Rééquilibrage", list(bt.FREQUENCES), index=1)
    cost = c[3].number_input("Frais par transaction (points de base)", 0, 100, 10, 5,
                             help="10 pb = 0,10 % du montant échangé à chaque rééquilibrage.")

    if choix.startswith("Mon portefeuille"):
        w = pfo.model_weights()
    elif choix.startswith("Sélection Claude"):
        w = pfo.model_weights(SELECTION_CLAUDE_CSV)
    elif choix.startswith("Systématique"):
        w = pfo.build_quant_portfolio(sc)
    else:
        picks = st.multiselect("Valeurs (équipondérées)", list(sc.index), default=list(pfo.model_weights().index[:10]),
                               format_func=lambda t: names.get(t, t))
        if not picks:
            st.stop()
        w = pd.Series(1 / len(picks), index=picks)

    benches = st.multiselect("Comparer à", list(BENCHMARKS), default=["IWDA.AS", "EXSA.DE"], format_func=BENCHMARKS.get)
    log = st.toggle("Échelle logarithmique", value=True)

    with st.spinner("Simulation…"):
        curve = bt.run_backtest(w, start, rebalance=bt.FREQUENCES[freq_label], cost_bps=cost)
    if curve.empty:
        st.error("Aucune donnée de cours sur la période.")
        st.stop()
    v = curve["valeur"]
    missing = [t for t in w.index if t not in ui.eur_prices(tuple(w.index)).columns]
    late = [t for t in w.index if t not in missing and ui.eur_prices((t,))[t].first_valid_index() > pd.Timestamp(start)]
    if late:
        st.caption("Entrées en cours de route (introductions en Bourse) : " + ", ".join(names.get(t, t) for t in late))

    curves = {"Portefeuille": v}
    for b in benches:
        bc = bt.benchmark_curve(b, v.index[0])
        if not bc.empty:
            curves[BENCHMARKS[b]] = bc
    df = pd.DataFrame(curves).ffill().dropna(how="all")
    ui.show(ui.lines(df, yfmt=",.0f", log=log, height=420, ytitle="Base 100"))

    main_b = bt.benchmark_curve(benches[0], v.index[0]) if benches else None
    stats = bt.perf_stats(v, main_b)
    pct_keys = {"Rendement annualisé", "Performance totale", "Volatilité", "Perte maximale", "Mois positifs",
                "Rendement annualisé de l'indice", "Surperformance annualisée", "Écart de suivi"}
    k = st.columns(4)
    k[0].metric("Rendement annualisé", ui.pct(stats.get("Rendement annualisé")), border=True,
                delta=ui.pct(stats.get("Surperformance annualisée"), signe=True) + " vs indice" if main_b is not None else None)
    k[1].metric("Volatilité", ui.pct(stats.get("Volatilité")), border=True)
    k[2].metric("Perte maximale", ui.pct(stats.get("Perte maximale")), border=True)
    k[3].metric("Ratio de Sharpe", ui.num(stats.get("Ratio de Sharpe"), 2), border=True,
                help="Rendement au-delà d'un taux sans risque de 2 %, par unité de volatilité.")

    a, b = st.columns(2)
    with a:
        st.markdown("**Pertes depuis le plus haut**")
        dd = pd.DataFrame({k_: bt.drawdown(s_) for k_, s_ in list(curves.items())[:2]})
        ui.show(ui.drawdown_chart(dd))
    with b:
        st.markdown("**Rendements annuels**")
        yr = pd.DataFrame({k_: bt.annual_returns(s_) for k_, s_ in list(curves.items())[:2]})
        ui.show(ui.grouped_bars(yr, height=260))

    with st.expander("Toutes les statistiques"):
        table = pd.DataFrame({"Valeur": [ui.pct(x) if k_ in pct_keys else ui.num(x, 2) for k_, x in stats.items()]},
                             index=list(stats))
        ui.tableau(table, width="stretch")
        if main_b is not None:
            roll = bt.rolling_excess(v, main_b, 3)
            if not roll.empty:
                st.markdown("**Surperformance annualisée glissante sur 3 ans**")
                fig = ui.lines(roll.to_frame("Surperformance 3 ans"), yfmt=".0%", height=260)
                ui.show(fig)

if mode == MODES[1]:
    from pf import backtest_pit as bp
    from pf.data import load_prices

    st.info("Ici, pas de regard vers l'avenir : chaque 1er avril depuis 2012, les indicateurs sont recalculés avec les "
            "seuls comptes publiés à cette date (comptes déposés à la SEC, réputés connus 90 jours après la clôture), "
            "puis les meilleures valeurs sont gardées un an à poids égaux. On voit ainsi si une méthode de notation "
            "aurait réellement choisi les bonnes actions.", icon=":material/science:")
    c = st.columns([3, 1, 1])
    choix_m = c[0].multiselect("Méthodes testées", list(bp.METHODES),
                               default=["Qualité", "Qualité + valeur", "Piliers (qualité, croissance, valeur, momentum)",
                                        "Momentum"], key="bt_pit_methodes")
    n_pit = c[1].slider("Lignes", 10, 40, 20, 5, key="bt_pit_n")
    debut_pit = c[2].selectbox("Depuis", list(range(2012, 2022)), index=0, key="bt_pit_debut")
    if not choix_m:
        st.stop()

    @st.cache_data(show_spinner=False)
    def _preparer(version):
        fin = set(sc.index[sc["financiere"].fillna(False).astype(bool)])
        return bp.preparer(list(sc.index), fin)

    @st.cache_data(show_spinner=False)
    def _simuler(version, methodes, n, debut):
        prep = _preparer(version)
        return bp.simuler(prep, {m: bp.METHODES[m] for m in methodes}, n=n, debut=debut,
                          reference=load_prices().get("SXR8.DE"))

    with st.spinner("Reconstitution des comptes à chaque date et simulation (une trentaine de secondes la première fois)…"):
        res = _simuler(ui.data_version(), tuple(choix_m), n_pit, debut_pit)
    if not res:
        st.error("Pas assez de données pour simuler.")
        st.stop()
    courbes = res["courbes"]
    univers_nom = "Toutes les valeurs testables (poids égaux)"
    ui.show(ui.lines(courbes, yfmt=",.0f", log=True, height=440, ytitle="Base 100, en euros"), key="bt_pit_courbes")
    lignes_stats = []
    for nom in courbes.columns:
        s = bp.statistiques(courbes[nom], courbes[univers_nom] if nom != univers_nom else None)
        lignes_stats.append({"methode": nom, **s})
    stats_df = pd.DataFrame(lignes_stats).set_index("methode")
    ui.tableau(ui.as_pct_cols(stats_df, ["rendement_annualise", "ecart_annuel", "volatilite", "perte_maximale",
                                         "annees_gagnantes"]), width="stretch", column_config={
        "rendement_annualise": ui.PCT("Rendement annualisé"),
        "ecart_annuel": ui.PCT("Écart annuel", "Par rapport à toutes les valeurs testables à poids égaux (même univers, "
                                               "même biais du survivant) : la mesure la plus juste du talent de sélection"),
        "volatilite": ui.PCT("Volatilité"), "perte_maximale": ui.PCT("Perte maximale"),
        "annees_gagnantes": ui.PCT("Années gagnantes", "Part des années civiles où la méthode bat toutes les valeurs "
                                                       "testables à poids égaux", 0),
    })
    with st.expander("Valeurs choisies chaque année"):
        m_detail = st.selectbox("Méthode", choix_m, key="bt_pit_detail")
        sel = res["selections"].get(m_detail, {})
        st.dataframe(pd.DataFrame({f"{d:%Y}": pd.Series(v) for d, v in sel.items()}), hide_index=True, width="stretch")
    st.caption(f"{res['nb_valeurs']} sociétés américaines testables (comptes SEC sur au moins 4 exercices), hors banques, "
               "assureurs et sociétés financières. Indicateurs reconstitués : rentabilité des fonds propres, marges "
               "opérationnelle et de FCF, dilution (qualité) ; croissance du CA sur 3 ans ; rendements du FCF et des "
               "bénéfices (valeur) ; momentum 12-1 mois. Les quatre regards et les critères ne sont pas reconstitués.")
    st.warning("**Biais du survivant.** L'univers est celui d'aujourd'hui : les sociétés disparues, rachetées ou sorties "
               "de l'indice manquent, et celles qui ont grossi jusqu'à y entrer sont là. Toutes les courbes en sont "
               "gonflées, et ce biais avantage surtout les méthodes croissance et momentum (elles choisissent les futures "
               "gagnantes que l'univers contient déjà). Comparez surtout chaque méthode à « toutes les valeurs "
               "testables », et regardez les pertes maximales autant que les rendements.", icon=":material/warning:")
