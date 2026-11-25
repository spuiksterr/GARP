import math

import numpy as np
import pandas as pd
import streamlit as st

from pf import (
    criteres,
    dirigeants,
    historique,
    homme_cle,
    photos,
    postes,
    prix_juste,
    regles,
    scenarios,
    sec,
    ui,
    ventilation,
)
from pf import prix_achat as pa
from pf import watchlist as wl
from pf.config import load_cas_particuliers, load_strategy
from pf.data import fx_rate, load_fundamentals, load_fx
from pf.metrics import annual_table
from pf.theses import append_journal, read_thesis
from pf.valuation import implied_growth, implied_irr, value_driver_ev

sc = ui.require_data()
mp = ui.model()
strat = load_strategy()
names = ui.label_map(sc)
options = sorted(sc.index, key=lambda t: str(sc.loc[t, "nom"]).lower())
default = st.session_state.get("fiche_ticker") or (mp.index[0] if len(mp) else options[0])
ticker = st.selectbox("Valeur", options, index=options.index(default) if default in options else 0,
                      format_func=lambda t: names.get(t, t), label_visibility="collapsed")
st.session_state["fiche_ticker"] = ticker
r = sc.loc[ticker]
fund = load_fundamentals(ticker) or {}
info = fund.get("info", {})

titre, bouton = st.columns([3, 1.3], vertical_alignment="center")
titre.title(f"{r['nom']}")
if wl.contient(ticker):
    if bouton.button("Dans la watchlist", icon=":material/star:", width="stretch", help="Cliquer pour la retirer de la watchlist"):
        wl.retirer(ticker)
        st.rerun()
elif bouton.button("Ajouter à la watchlist", icon=":material/star_border:", width="stretch"):
    ui.ajouter_watchlist([ticker])
    st.rerun()
if bouton.button("Simuler dans mon portefeuille", icon=":material/science:", width="stretch",
                 help="Effet d'un ajout (ou d'un autre poids) sur la concentration, la volatilité, les devises, les "
                      "scénarios de choc et la corrélation avec vos lignes : page Risques."):
    st.session_state["simulation_ticker"] = ticker
    st.switch_page("vues/risques.py")
tags = [ticker, str(r.get("secteur", "")), str(r.get("pays", "")), str(r.get("enveloppe", ""))]
if ticker in mp.index:
    tags.append(f"En portefeuille : {mp.loc[ticker, 'poche']}, cible {float(mp.loc[ticker, 'poids_cible']):.1f} %".replace(".", ","))
st.caption(" · ".join(t for t in tags if t and t != "nan"))
# Fraîcheur : un cours resté en arrière du marché, ou des comptes lus il y a longtemps, faussent les indicateurs.
cours_hist = ui.local_prices(ticker)
date_cours = cours_hist.index[-1] if len(cours_hist) else None
date_marche = pd.Timestamp(ui.data_date()) if ui.data_date() else None
lu = str(fund.get("fetched") or "")[:10]
st.caption(" · ".join(x for x in [f"Cours du {date_cours:%d/%m/%Y}" if date_cours is not None else "Pas de cours",
                                   f"comptes Yahoo lus le {pd.Timestamp(lu):%d/%m/%Y}" if lu else ""] if x))
if date_cours is not None and date_marche is not None and (date_marche - date_cours).days > 4:
    st.warning(f"Cours arrêté au {date_cours:%d/%m/%Y}, alors que le marché est au {date_marche:%d/%m/%Y} : Yahoo ne "
               "le met plus à jour (ticker changé, valeur suspendue ou retirée de la cote ?).", icon=":material/schedule:")
if isinstance(r.get("profil"), str) and r["profil"]:
    st.markdown(f"_{r['profil']}_")

if r["statut"] == "Exclu":
    st.error(f"Exclue par les filtres : {r['motifs_exclusion']}", icon=":material/block:")
elif r["statut"] == "Fonds":
    st.info("Fonds (ETF ou ETC) : sans états financiers, il n'a ni filtres, ni note GARP, ni valorisation. "
            "Seuls le cours, le risque et la fiche de thèse s'appliquent.", icon=":material/info:")
else:
    st.success(f"Éligible, rang {int(r['rang'])} sur {int((sc['statut'] == 'Éligible').sum())}", icon=":material/verified:")
if r.get("alertes"):
    st.warning(r["alertes"], icon=":material/warning:")

est_fonds = r["statut"] == "Fonds"
# ------------------------------------------------------------------ la décision d'abord : quel prix payer ?
if not est_fonds:
    regl = pa.reglages(strat)
    juste = pa.prix_juste(r, strat["valorisation"], regl["rendement"])
    achat = juste * (1 - regl["marge"]) if math.isfinite(juste) else math.nan
    cours = float(r["cours"]) if pd.notna(r.get("cours")) else math.nan
    verdict = pa.verdict(cours, juste, achat)
    devise = str(r.get("devise") or "")
    vise = wl.load_watchlist()["prix_cible"].get(ticker) if wl.contient(ticker) else None
    with st.container(border=True):
        unite = f" ({devise})" if devise else ""
        d = st.columns(4)
        d[0].metric("Cours" + unite, ui.num(cours, 2) if math.isfinite(cours) else "n.d.")
        d[1].metric("Votre prix d'achat" + unite, ui.num(achat, 2) if math.isfinite(achat) else "n.d.",
                    help=f"Prix juste moins votre marge de sécurité de {ui.pct(regl['marge'], 0)}.")
        d[2].metric("Prix juste" + unite, ui.num(juste, 2) if math.isfinite(juste) else "n.d.",
                    help=f"Cours auquel l'action rapporterait {ui.pct(regl['rendement'], 1)} par an si sa croissance "
                         f"attendue ({ui.pct(r.get('croissance_attendue'))} par an) se réalise.")
        ecart = cours / achat - 1 if math.isfinite(achat) and achat > 0 and math.isfinite(cours) else None
        with d[3]:
            st.markdown("Verdict", help=pa.EXPLICATIONS[verdict])
            st.markdown(f'<div class="garp-verdict garp-verdict-{ui.COULEURS_VERDICT.get(verdict, "gray")}">'
                        f"{verdict}</div>", unsafe_allow_html=True)
            if ecart is not None:
                st.caption(f"{ui.pct(ecart, 0, signe=True)} du prix d'achat")
        e = st.columns([1, 3.2], vertical_alignment="center")
        if e[0].button("Suivre à ce prix", icon=":material/flag:", width="stretch", disabled=not math.isfinite(achat),
                       help="Inscrit votre prix d'achat comme prix visé dans la watchlist : le tableau de bord vous "
                            "préviendra quand le cours y passera."):
            wl.fixer_cible(ticker, achat, f"Prix d'achat : rendement {ui.pct(regl['rendement'], 1)}, marge "
                           f"{ui.pct(regl['marge'], 0)}", cours=cours if math.isfinite(cours) else None)
            st.toast("Prix visé inscrit dans la watchlist.", icon=":material/flag:")
            st.rerun()
        precisions = [f"Au rendement exigé de {ui.pct(regl['rendement'], 1)} et avec une marge de "
                      f"{ui.pct(regl['marge'], 0)}, réglables dans le Screener."]
        if vise is not None and pd.notna(vise):
            precisions.append(f"Votre prix visé dans la watchlist : {ui.num(float(vise), 2)} {devise}.")
        if not math.isfinite(juste):
            precisions.append("Prix juste non calculable (holding, société en perte ou comptes incomplets) : voir la "
                              "section « Prix juste » pour les multiples.")
        e[1].caption(" ".join(precisions) + " Détail et autres méthodes : sections « Prix juste » et « Valorisation ». "
                     "Une estimation, pas un conseil.")
ticker_us = sec.sec_ticker(ticker) is not None
ORIGINE_COMPTES = {True: "les comptes déposés à la SEC", False: "les rapports annuels européens (ESEF)"}
# ------------------------------------------------------------------ sections
# Seule la section choisie est calculée : la fiche s'affiche plus vite qu'avec tout empilé (ou des onglets,
# que Streamlit calcule tous).
SECTIONS = ["Résumé", "Prix juste", "Activité", "Historique", "Valorisation", "Thèse"]
section = st.segmented_control("Section de la fiche", SECTIONS, default="Résumé", key="fiche_section",
                               label_visibility="collapsed") or "Résumé"
if est_fonds and section in ("Prix juste", "Activité", "Historique", "Valorisation"):
    st.info("Fonds (ETF ou ETC) : sans états financiers, cette section ne s'applique pas. Voir « Résumé » (cours) et "
            "« Thèse ».", icon=":material/info:")

if section == "Résumé":
    # ------------------------------------------------------------------ scores et indicateurs
    if not est_fonds:
        a, b = st.columns([1, 2])
        with a:
            st.metric("Note GARP", ui.num(r["score"], 0) + " / 100", border=True,
                      help="La croissance, sans la surpayer : croissance 40 %, valorisation 35 %, qualité 25 %, chaque "
                           "pilier en rang centile dans l'univers (100 = meilleur).")
            st.markdown("**Les trois piliers de la note**")
            piliers = pd.Series({"Croissance · 40 %": r["croissance"], "Valorisation · 35 %": r["valorisation"],
                                 "Qualité · 25 %": r["qualite"]})
            fig = ui.hbar(piliers / 100, fmt=".0%", height=170)
            fig.update_traces(text=[f"{v:.0f}" for v in piliers.sort_values().values])
            ui.show(fig)
            st.caption("Rangs centiles dans l'univers (100 = meilleur). Banques, assureurs et holdings sont comparés entre "
                       f"eux sur la qualité et la valorisation. Hors note : momentum {ui.num(r.get('momentum'), 0)} / 100.")
            # Quatre avis à lire un par un : ni additionnés, ni comptés dans la note (22/11/2026).
            st.markdown("**Quatre regards**, sur 5, hors note", help="Chacun juge selon sa propre grille : un écart "
                        "entre eux (Fisher enthousiaste, Buffett réservé sur le prix) est instructif.")
            st.markdown(f"Buffett **{int(r['buffett'])}** · Munger **{int(r['munger'])}** · "
                        f"Fisher **{int(r['fisher'])}** · Smith **{int(r['smith'])}**")
            if r.get("regards_correction"):
                st.caption(f"Correction manuelle : {r['regards_correction']}.")
        with b:
            q, cr = st.columns(2)
            q.markdown(ui.bloc_chiffres("Qualité", [
                ("ROIC moyen", ui.pct(r.get("roic_moyen"))), ("ROE moyen", ui.pct(r.get("roe_moyen"))),
                ("Marge brute", ui.pct(r.get("marge_brute"))), ("Marge opérationnelle", ui.pct(r.get("marge_operationnelle"))),
                ("Conversion en cash", ui.pct(r.get("conversion_fcf"), 0)),
                ("Dette nette / EBITDA", ui.num(r.get("dette_nette_ebitda"), 1, "x")),
                ("Actions, par an (3 ans)", ui.pct(r.get("evolution_actions"), 1, signe=True)),
            ]), unsafe_allow_html=True)
            cr.markdown(ui.bloc_chiffres("Croissance", [
                ("Chiffre d'affaires, par an", ui.pct(r.get("croiss_ca"))),
                ("Bénéfice par action, par an", ui.pct(r.get("croiss_bpa"))),
                ("Consensus BPA", ui.pct(r.get("croiss_bpa_estimee"))), ("Consensus CA", ui.pct(r.get("croiss_ca_estimee"))),
                ("Croissance retenue", ui.pct(r.get("croissance_attendue"))),
            ], fort={"Croissance retenue"}), unsafe_allow_html=True)
            v, m = st.columns(2)
            v.markdown(ui.bloc_chiffres("Valorisation", [
                ("PER (12 mois)", ui.num(r.get("per"), 1)), ("PER prospectif", ui.num(r.get("per_prospectif"), 1)),
                ("Rendement du FCF", ui.pct(r.get("rendement_fcf"))), ("EBIT / valeur d'entreprise", ui.pct(r.get("rendement_benefices"))),
                ("Rendement du dividende", ui.pct(r.get("rendement_dividende"))),
                ("Croissance implicite", ui.pct(r.get("croissance_implicite"))), ("TRI implicite", ui.pct(r.get("tri_implicite"))),
            ], fort={"TRI implicite"}), unsafe_allow_html=True)
            m.markdown(ui.bloc_chiffres("Cours et risque", [
                ("1 mois", ui.pct(r.get("perf_1m"), 1, True)), ("12 mois", ui.pct(r.get("perf_12m"), 1, True)),
                ("Momentum 12-1 mois", ui.pct(r.get("mom_12_1"), 1, True)),
                ("Écart à la moyenne 200 jours", ui.pct(r.get("ecart_mm200"), 1, True)),
                ("Volatilité", ui.pct(r.get("volatilite"))), ("Perte maximale 3 ans", ui.pct(r.get("drawdown_max_3a"))),
                ("Objectif des analystes", ui.pct(r.get("objectif_analystes"), 1, True)),
            ]), unsafe_allow_html=True)
            h = st.columns(3)
            h[0].metric("Moat estimé", r.get("moat") if isinstance(r.get("moat"), str) else "n.d.", border=True,
                        help="Traces d'un avantage concurrentiel dans les comptes des 5 derniers exercices : "
                             "rentabilité élevée et tenue, marge brute "
                             "forte et défendue, marges stables. Estimation chiffrée, pas le moat de Morningstar.")
            h[1].metric("PER actuel", ui.num(r.get("per"), 1), border=True)
            h[2].metric("PER habituel", ui.num(r.get("per_historique"), 1),
                        delta=ui.pct(r.get("ecart_per_historique"), 0, True) if pd.notna(r.get("ecart_per_historique")) else None,
                        delta_color="inverse", border=True,
                        help="PER médian aux dernières clôtures annuelles (six au plus). "
                             "L'écart indique si l'action est chère ou non par rapport à elle-même. "
                             "Une forte décote peut aussi signaler un vrai problème.")
            v = st.columns(3)
            v[0].metric("P/FCF actuel", ui.num(r.get("p_fcf"), 1), border=True,
                        help="Capitalisation / flux de trésorerie disponible des 12 derniers mois. Non calculé si le flux est négatif, "
                             "ni pour les banques et assureurs.")
            v[1].metric("P/FCF habituel", ui.num(r.get("p_fcf_historique"), 1),
                        delta=ui.pct(r.get("ecart_p_fcf_historique"), 0, True) if pd.notna(r.get("ecart_p_fcf_historique")) else None,
                        delta_color="inverse", border=True, help="P/FCF médian aux dernières clôtures annuelles (six au plus).")
            v[2].metric("P/FCF hors SBC", ui.num(r.get("p_fcf_net"), 1),
                        delta=ui.pct(r.get("ecart_p_fcf_net_historique"), 0, True) if pd.notna(r.get("ecart_p_fcf_net_historique")) else None,
                        delta_color="inverse", border=True,
                        help="Capitalisation / (flux de trésorerie disponible − rémunérations en actions), sur 12 mois. Ces actions "
                             "gratuites sont un vrai coût, payé en dilution plutôt qu'en cash. Son inverse, le rendement du FCF net "
                             f"({ui.pct(r.get('rendement_fcf_hors_sbc'))}), compte dans le score de valorisation. Écart : par "
                             "rapport à son niveau médian aux dernières clôtures annuelles.")
            s = st.columns(3)
            s[0].metric("Piotroski", ui.num(r.get("piotroski"), 0, " / 9"), border=True,
                        help="Neuf critères sur le dernier exercice : rentabilité, dette, liquidité, efficacité. 0 à 2 : faible, 8 ou 9 : forte.")
            s[1].metric("Altman", ui.num(r.get("altman_z"), 1), border=True,
                        help="Risque de faillite. Sous 1,8 : zone fragile. Au-dessus de 3 : zone sûre. Pensé pour les industriels.")
            s[2].metric("Beneish", ui.num(r.get("beneish_m"), 2), border=True,
                        help="Au-dessus de -1,78 : comptes à examiner. Une forte croissance ou une acquisition déclenchent aussi "
                             "ce signal : ce n'est pas une preuve de fraude.")
            if bool(r.get("financiere")):
                st.caption("Ces trois signaux ne sont pas calculés pour les banques, assureurs et holdings : "
                           "leurs formules supposent un bilan d'entreprise classique.")
            # Risque homme-clé, recalculé ici depuis la fiche en cache (dirigeants relus par « pf homme-cle »).
            hc = homme_cle.evaluer(fund.get("info", {}), *homme_cle.load_ajustements().get(ticker, (0.0, "")))
            k = st.columns([1, 2])
            note = hc["homme_cle"]
            k[0].metric("Risque homme-clé", "n.d." if not math.isfinite(note) else f"{ui.num(note, 1)} / 10",
                        hc["homme_cle_niveau"] if math.isfinite(note) else None,
                        delta_color="off", delta_arrow="off", border=True,
                        help="Dépendance de la société à une seule personne, de 0 à 10 : fondateur aux commandes (4), "
                             "fondateur président du conseil (3), PDG cumulant les deux fonctions (1,5), dirigeant de 65 ans "
                             "ou plus (1 ou 2), initiés détenant 10 % ou 30 % du capital (1 ou 2), conseil peu indépendant "
                             "selon ISS (1), moins de 3 000 salariés (1). Faible sous 3, élevé à partir de 6. Un fondateur "
                             "aux commandes est aussi souvent une force : c'est un point à suivre, pas un défaut.")
            with k[1]:
                if math.isfinite(note):
                    if hc["homme_cle_dirigeant"]:
                        st.markdown(f"**Dirigeant principal** : {hc['homme_cle_dirigeant']}")
                    st.markdown(f"**Facteurs** : {hc['homme_cle_facteurs']}.")
                else:
                    st.caption("Dirigeants pas encore lus pour cette valeur : ils arrivent avec le renouvellement de sa "
                               "fiche, ou tout de suite avec la commande « pf homme-cle " + ticker + " ».")

    else:
        q = st.columns(4)
        q[0].metric("Performance 12 mois", ui.pct(r.get("perf_12m"), 1, True), border=True)
        q[1].metric("Volatilité", ui.pct(r.get("volatilite")), border=True)
        q[2].metric("Perte max 3 ans", ui.pct(r.get("drawdown_max_3a")), border=True)
        q[3].metric("Écart à la moyenne 200 jours", ui.pct(r.get("ecart_mm200"), 1, True), border=True)

    # ------------------------------------------------------------------ six critères
    if not est_fonds and fund:
        sec_data = sec.comptes_officiels(ticker)
        crits = criteres.evaluer(fund, sec_data, financiere=bool(r.get("financiere")), seuils=strat.get("criteres"),
                                 tresorerie_clients=ticker in load_cas_particuliers()["tresorerie_clients"])
        ok, evalues = sum(c.rempli is True for c in crits), sum(c.rempli is not None for c in crits)
        st.subheader(f"Six critères de qualité : {ok} rempli{'s' if ok > 1 else ''} sur {evalues}")
        for ligne in (crits[:3], crits[3:]):
            for col, c in zip(st.columns(3), ligne):
                col.markdown(ui.carte_critere(c, criteres.texte_seuil(c, strat.get("criteres"))), unsafe_allow_html=True)
        _, prolonge = postes.historique(fund, sec_data)
        if prolonge:
            source = (f"les 4 exercices Yahoo, prolongés par {ORIGINE_COMPTES[ticker_us]} "
                      "(raccord vérifié à 3 % près sur les exercices communs)")
        elif ticker_us:
            source = "les 4 exercices Yahoo, soit 3 ans de croissance : les comptes SEC n'ont pas pu les prolonger"
        elif sec_data:
            source = ("les 4 exercices Yahoo, soit 3 ans de croissance : les rapports annuels européens (ESEF) trouvés ne "
                      "reproduisent pas les chiffres Yahoo à 3 % près, ils ne sont donc pas utilisés")
        else:
            source = ("les 4 exercices Yahoo, soit 3 ans de croissance au lieu de 5 : pas de rapport annuel européen (ESEF) "
                      "trouvé pour cette société (python -m pf esef)")
        st.caption(f"Historique : {source}. ROCE = résultat opérationnel / (total du bilan − dettes courantes). Free cash flow = flux "
                   "d'exploitation − investissements. Seuils réglables dans config/strategie.json (criteres).")

    # ------------------------------------------------------------------ cours
    st.subheader("Cours")
    c1, c2, c3 = st.columns([3, 1, 1])
    periode = c1.segmented_control("Période", ["1 an", "3 ans", "5 ans", "10 ans", "Max"], default="5 ans", label_visibility="collapsed")
    en_eur = c2.toggle("En euros", value=False, help="Convertit le cours au taux de change de chaque jour.")
    log = c3.toggle("Échelle log", value=True)
    s = ui.eur_prices((ticker,))[ticker].dropna() if en_eur else ui.local_prices(ticker)
    if not s.empty:
        years = {"1 an": 1, "3 ans": 3, "5 ans": 5, "10 ans": 10}.get(periode or "5 ans")
        full = s.copy()
        if years:
            s = s[s.index >= s.index.max() - pd.Timedelta(days=int(365.25 * years))]
        ma = full.rolling(200).mean().reindex(s.index)
        df = pd.DataFrame({"Cours (dividendes réinvestis)": s, "Moyenne 200 jours": ma})
        devise = "EUR" if en_eur else str(r.get("devise", ""))
        ui.show(ui.lines(df, yfmt=",.2f", log=log, height=360, ytitle=devise))

    # ------------------------------------------------------------------ évolution du rang (photos datées)
    evo = photos.evolution(ticker)
    if len(evo) >= 2:
        st.subheader("Rang dans le screener")
        dernier = evo.iloc[-1]
        st.caption(f"{len(evo)} photos depuis le {evo.index[0]:%d/%m/%Y} ; rang actuel {ui.num(dernier['rang'], 0)} "
                   f"({dernier['statut']}). Plus le rang est petit, meilleure est la note GARP. Une photo est prise à "
                   "chaque mise à jour normale ou complète.")
        ui.show(ui.lines(evo[["rang"]].rename(columns={"rang": "Rang"}), yfmt=",.0f", height=240))

    if info.get("longBusinessSummary"):
        with st.expander("Description de l'activité (Yahoo Finance, en anglais)"):
            st.write(info["longBusinessSummary"])


if section == "Prix juste":
    # ------------------------------------------------------------------ prix juste
    def _fixer_prix_vise(ticker: str, ratio: str, cours: float, actuel: float, devise: str) -> None:
        """Rappel du bouton : relit la cible saisie (une saisie suivie d'un clic arrive dans le même passage)."""
        cible = st.session_state.get(f"pj_cible_{ticker}_{ratio}")
        prix = prix_juste.prix_cible(cours, actuel, float(cible)) if cible else math.nan
        if math.isfinite(prix):
            wl.fixer_cible(ticker, prix, f"{ratio} {ui.num(cible, 1)}", cours)
            st.toast(f"Prix visé enregistré dans la watchlist : {ui.num(prix, 2)} {devise}.", icon=":material/star:")


    if not est_fonds and fund:
        st.subheader(f"Quel est le prix juste pour {r['nom']} ?")
        choix = prix_juste.ratios_pour(bool(r.get("financiere")), bool(r.get("holding")))
        prix_local = ui.local_prices(ticker)
        if not choix:
            st.info("Holding : son prix se juge sur la décote par rapport à la valeur de ses participations (actif net), "
                    "que Yahoo ne fournit pas.", icon=":material/info:")
        elif prix_local.empty:
            st.info("Cours indisponible : lancez une mise à jour.")
        else:
            h_pj, prolonge_pj = postes.historique(fund, sec.comptes_officiels(ticker))
            fx_pj = load_fx()
            devise = str(r.get("devise"))
            series = {k: prix_juste.serie(k, fund, h_pj, prix_local, r.get("capitalisation_comptes", math.nan), fx_pj, devise,
                                          str(r.get("devise_comptes"))) for k in choix}
            cours = float(prix_local.iloc[-1])

            with st.container(border=True):
                c = st.columns([1.1, 1.0, 1.6, 1.3], vertical_alignment="center")
                ratio = c[0].selectbox("Choisissez un ratio", choix, key=f"pj_ratio_{ticker}",
                                       help="\n".join(f"{k} : {prix_juste.DEFINITIONS[k]}." for k in choix))
                s_ratio = series[ratio]
                actuel = prix_juste.actuel(s_ratio)
                m5, m10 = prix_juste.mediane(s_ratio, 5), prix_juste.mediane(s_ratio, 10)
                defaut = prix_juste.cible_par_defaut(s_ratio)
                defaut = defaut if math.isfinite(defaut) else 15.0
                fin_pas = ratio == "P/CA"  # un prix / chiffre d'affaires se compte en dixièmes
                cible = c[1].number_input(f"Votre {ratio} cible", min_value=0.1, max_value=500.0,
                                          value=min(max(round(float(defaut), 1), 0.1), 500.0), step=0.1 if fin_pas else 0.5,
                                          format="%.1f", key=f"pj_cible_{ticker}_{ratio}",
                                          help="Proposé au départ : la médiane du ratio sur 5 ans (à défaut sur 10 ans, puis "
                                               "sur tout l'historique). Pour garder une marge de sécurité, visez en dessous.")
                c[1].caption("Calcul sur les 12 derniers mois")
                prix = prix_juste.prix_cible(cours, actuel, cible)
                c[2].markdown(ui.carte_prix_cible(prix, cours, devise, prix * fx_rate(fx_pj, devise, "EUR")),
                              unsafe_allow_html=True)
                liste = wl.load_watchlist()
                suivie = ticker in liste.index
                deja = suivie and pd.notna(liste.loc[ticker, "prix_cible"])
                c[3].button("Mettre à jour" if deja else "Viser ce prix" if suivie else "Ajouter à la watchlist",
                            icon=":material/star:", type="primary", width="stretch", disabled=not math.isfinite(prix),
                            key=f"pj_bouton_{ticker}", on_click=_fixer_prix_vise, args=(ticker, ratio, cours, actuel, devise),
                            help="Enregistre ce prix cible comme prix visé dans la watchlist : elle et le tableau de bord "
                                 "signaleront le moment où le cours passera dessous.")
                if deja:
                    objectif = str(liste.loc[ticker, "objectif"] or "").strip() or "objectif non précisé"
                    c[3].caption(f"Prix visé actuel : {ui.num(liste.loc[ticker, 'prix_cible'], 2)} {devise} ({objectif})")
            valides = s_ratio.dropna()
            depuis = f" depuis {valides.index.min().year}" if len(valides) else ""
            st.caption(f"Repères du {ratio} : actuel {ui.num(actuel, 1)} · médiane sur 5 ans {ui.num(m5, 1)} · sur 10 ans "
                       f"{ui.num(m10, 1)} · médiane{depuis} {ui.num(prix_juste.mediane(s_ratio), 1)} · minimum "
                       f"{ui.num(s_ratio.min(), 1)}. Le prix cible suppose des résultats inchangés : il se recalcule à chaque "
                       "publication. Un multiple tombé sous sa médiane peut traduire des perspectives dégradées plutôt "
                       "qu'une aubaine : la médiane passée n'est un repère que si l'entreprise n'a pas changé.")

            # Graphiques des multiples : P/FCF (ou PER pour une banque) et prix / chiffre d'affaires.
            c1, c2 = st.columns([3, 2])
            periode_pj = c1.segmented_control("Période des multiples", ["1 an", "3 ans", "5 ans", "10 ans", "Depuis toujours"],
                                              default="Depuis toujours", label_visibility="collapsed", key="pj_periode")
            net = "P/FCF hors SBC" in choix and c2.toggle(
                "Retirer les SBC", value=ratio == "P/FCF hors SBC", key=f"pj_net_{ticker}",
                help="Retire du flux de trésorerie disponible les rémunérations en actions (stock-based compensation) : "
                     "un coût réel, payé en dilution plutôt qu'en cash.")
            ans = {"1 an": 1, "3 ans": 3, "5 ans": 5, "10 ans": 10}.get(periode_pj or "Depuis toujours")
            graphiques = ([("Prix / Free cash flow", "P/FCF hors SBC" if net else "P/FCF"), ("Prix / Chiffre d'affaires", "P/CA")]
                          if "P/CA" in choix else [("Prix / Bénéfice", "PER")])
            for col, (titre, nom) in zip(st.columns(len(graphiques)), graphiques):
                s_full = series[nom]
                vue = s_full[s_full.index >= s_full.index.max() - pd.Timedelta(days=int(365.25 * ans))] if ans and len(s_full) else s_full
                if vue.first_valid_index() is not None:  # historique court (Europe) : pas de vide à gauche
                    vue = vue[vue.index >= vue.first_valid_index()]
                with col.container(border=True):
                    st.markdown(f"**{titre}**")
                    if vue.dropna().empty:
                        st.caption(f"{nom} incalculable sur la période : résultat négatif ou absent.")
                        continue
                    fig = ui.lines(pd.DataFrame({nom: vue}), yfmt=",.1f", height=300, colors={nom: ui.accent()})
                    fig.update_traces(connectgaps=False)
                    bas = float(vue.min())
                    fig.add_hline(y=bas, line_dash="dash", line_width=1.5, line_color=ui.GOOD,
                                  annotation_text=f"Min {ui.num(bas, 2)}", annotation_position="bottom right",
                                  annotation_font=dict(color=ui.GOOD))
                    fig.update_yaxes(rangemode="tozero")
                    ui.show(fig, key=f"multiple_{nom}")
                    actuel_nom = prix_juste.actuel(s_full)
                    st.markdown(f"Le {nom} actuel est de **{ui.num(actuel_nom, 2)}**")
                    st.markdown(ui.lignes_medianes(actuel_nom, prix_juste.reperes(s_full)), unsafe_allow_html=True)
            st.caption("Multiple du jour = capitalisation du jour / résultat du dernier exercice publié (clôture + 60 jours), "
                       "puis des 12 derniers mois. "
                       + (f"Comptes Yahoo prolongés par {ORIGINE_COMPTES[ticker_us]}. " if prolonge_pj
                          else "Comptes Yahoo : quatre exercices au plus, d'où un historique court. ")
                       + "Les trous correspondent aux exercices à résultat négatif. Cours ajustés des dividendes : les "
                       "multiples passés sont un peu sous-estimés.")

if section == "Activité":
    # ------------------------------------------------------------------ dirigeants
    def _montant(v: float, devise: str) -> str:
        """886 342 -> « 886 k USD » ; 2 540 964 -> « 2,5 M USD »."""
        if not (isinstance(v, (int, float)) and math.isfinite(v)) or v == 0:
            return "—"
        for seuil, unite, d in ((1e9, "Md", 1), (1e6, "M", 1), (1e3, "k", 0)):
            if abs(v) >= seuil:
                return f"{ui.num(v / seuil, d)} {unite} {devise}"
        return f"{ui.num(v, 0)} {devise}"


    if not est_fonds and fund and fund.get("info", {}).get("dirigeants"):
        st.subheader("Équipe dirigeante")
        equipe = pd.DataFrame(fund["info"]["dirigeants"])
        ui.tableau(equipe, hide_index=True, width="stretch", column_config={
            "nom": "Nom", "fonction": "Fonction (libellé de Yahoo, en anglais)",
            "age": st.column_config.NumberColumn("Âge", format="%d")})
        st.caption("Source : Yahoo Finance. Elle nourrit le risque homme-clé de la section Résumé.")

    if not est_fonds and fund:
        st.subheader("Achats et ventes des dirigeants")
        if sec.sec_ticker(ticker) is None:
            st.caption("Disponible pour les sociétés américaines (formulaires 4 déposés à la SEC). En Europe, les "
                       "déclarations des dirigeants sont publiées par chaque régulateur national (AMF, BaFin…), sans base "
                       "commune exploitable.")
        elif not sec.contact():
            st.caption("Renseignez `contact_sec` dans profil/prive.json pour lire les déclarations déposées à la SEC.")
        else:
            deja_lu = dirigeants.en_cache(ticker) is not None
            if deja_lu or st.button("Lire les déclarations des 12 derniers mois (15 à 30 secondes la première fois)",
                                    icon=":material/badge:", key=f"dg_lire_{ticker}"):
                barre = st.progress(0.0, text="Lecture des formulaires 4…") if not dirigeants.a_jour(ticker) else None
                tx = dirigeants.transactions(ticker, progress=(lambda k, n: barre.progress(k / n, text=f"Formulaire {k} sur {n}"))
                                             if barre else None)
                if barre:
                    barre.empty()
                syn = dirigeants.synthese(tx)
                dev = str(r.get("devise") or "USD")
                programmees = syn["part_ventes_programmees"]
                c = st.columns(3)
                c[0].metric("Sur 12 mois", syn["signal"],
                            help="Achats groupés : au moins trois dirigeants ou administrateurs ont acheté en bourse, avec leur "
                                 "argent. On vend pour mille raisons (impôts, diversification, achat d'une maison) ; on "
                                 "n'achète que pour une.")
                c[1].metric("Achats en bourse", _montant(syn["montant_achats"], dev),
                            f"{syn['achats']} achat(s), {syn['acheteurs']} acheteur(s)" if syn["achats"] else None,
                            delta_color="off", delta_arrow="off")
                c[2].metric("Ventes en bourse", _montant(syn["montant_ventes"], dev),
                            (f"{syn['vendeurs']} vendeur(s), {ui.pct(programmees, 0)} programmées"
                             if math.isfinite(programmees) else f"{syn['vendeurs']} vendeur(s)") if syn["ventes"] else None,
                            delta_color="off", delta_arrow="off")
                if tx is not None and len(tx):
                    t = tx.assign(type=tx["code"].map(dirigeants.CODES),
                                  programme=tx["plan_10b5_1"].map({True: "Oui", False: ""}),
                                  date=pd.to_datetime(tx["date"], errors="coerce"))
                    ui.tableau(t[["date", "nom", "fonction", "type", "actions", "prix", "montant", "programme", "detenues_apres"]],
                               hide_index=True, width="stretch", height=min(400, 35 * len(t) + 38), column_config={
                                   "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                                   "nom": "Déclarant", "fonction": "Fonction", "type": "Opération",
                                   "actions": st.column_config.NumberColumn("Actions", format="%.0f"),
                                   "prix": st.column_config.NumberColumn(f"Prix ({dev})", format="%.2f"),
                                   "montant": st.column_config.NumberColumn(f"Montant ({dev})", format="%.0f"),
                                   "programme": st.column_config.TextColumn(
                                       "Programmée", help="Vente décidée à l'avance (plan 10b5-1) : elle dit peu de choses "
                                                          "de l'opinion du dirigeant au moment de la vente."),
                                   "detenues_apres": st.column_config.NumberColumn("Détenues après", format="%.0f"),
                               })
                lu = (tx.attrs.get("lu_le") if tx is not None else None) or "n.d."
                st.caption("Source : formulaires 4 déposés à la SEC, achats (code P) et ventes (code S) en bourse ; "
                           "attributions gratuites et levées d'options ignorées. Indicateur « programmée » renseigné "
                           f"depuis 2023 seulement. Liste des dépôts lue le {lu}. Un achat de dirigeant est un indice, "
                           "pas une preuve : il peut se tromper, ou soutenir le cours.")

    # ------------------------------------------------------------------ d'où vient le chiffre d'affaires
    if not est_fonds and fund:
        st.subheader("D'où vient le chiffre d'affaires")
        vent = None
        if "." not in ticker:
            with st.spinner("Lecture du dernier rapport annuel déposé à la SEC…"):
                vent = ventilation.ventilation(ticker)
        if not vent or not vent.get("total"):
            st.caption("Répartition disponible pour les sociétés américaines : elle est lue dans leur rapport annuel déposé à la SEC "
                       "(10-K). Yahoo ne la fournit pas, et les rapports européens arrivent trop tard sur les bases publiques.")
        else:
            g = st.columns(2)
            for col, titre, parts, absent in (
                    (g[0], f"Comment {r['nom']} gagne de l'argent", vent.get("activites"),
                     "Le rapport ne ventile pas le chiffre d'affaires par activité de façon exploitable."),
                    (g[1], f"Où {r['nom']} gagne de l'argent", vent.get("geographie"),
                     "Le rapport ne distingue pas les ventes réalisées aux États-Unis du reste du monde.")):
                with col.container(border=True):
                    st.markdown(f"**{titre}**")
                    if parts:
                        ui.show(ui.camembert(parts), key=f"ventilation_{titre}")
                    else:
                        st.caption(absent)
            st.caption(f"Source : rapport {vent.get('formulaire', '10-K')} de l'exercice clos le "
                       f"{pd.Timestamp(vent['exercice']):%d/%m/%Y}, chiffre d'affaires de {ui.num(vent['total'] / 1e9, 1)} Md "
                       f"{r.get('devise_comptes', '')}. Libellés repris du rapport, en anglais.")

if section == "Historique":
    # ------------------------------------------------------------------ historique financier
    if not est_fonds:
        st.subheader("Historique financier")
        a_tab = annual_table(fund, sec.comptes_officiels(ticker)) if fund else pd.DataFrame()
        if a_tab.empty:
            st.info("États financiers indisponibles.")
        else:
            unit = 1e9 if a_tab["revenue"].abs().max() > 5e9 else 1e6
            u = "Md" if unit == 1e9 else "M"
            cur = r.get("devise_comptes", "")
            t = historique.tableau(fund, sec.comptes_officiels(ticker))
            periode_hist = st.segmented_control("Période des graphiques", ["5 ans", "10 ans", "Depuis toujours"],
                                                default="Depuis toujours", key="hist_periode", label_visibility="collapsed")
            n = {"5 ans": 5, "10 ans": 10}.get(periode_hist or "Depuis toujours")
            if n:  # n derniers exercices, plus les 12 mois
                annuels = [i for i in t.index if i != historique.DOUZE_MOIS]
                t_vue = t.loc[annuels[-n:] + [i for i in t.index if i == historique.DOUZE_MOIS]]
            else:
                t_vue = t
            st.caption(f"Montants en {cur}. Exercices clos, puis les 12 derniers mois (« {historique.DOUZE_MOIS} »)"
                       + (f". Comptes Yahoo prolongés par {ORIGINE_COMPTES[ticker_us]}, poste par poste quand ils concordent."
                          if postes.historique(fund, sec.comptes_officiels(ticker))[1] else ". Comptes Yahoo : 4 exercices au plus."))

            def carte(col, titre, fig, sous_titre=None, croissance=None):
                with col.container(border=True):
                    st.markdown(f"**{titre}**" + (f"  \n<span style='font-size:0.85rem;{ui.SECONDAIRE}'>{sous_titre}</span>"
                                                   if sous_titre else ""), unsafe_allow_html=True)
                    ui.show(fig, key=f"historique_{titre}")
                    if croissance:
                        st.markdown(ui.badges_croissance(historique.croissance(t, croissance, 5),
                                                         historique.croissance(t, croissance, 10)), unsafe_allow_html=True)

            g = st.columns(3)
            carte(g[0], "Chiffre d'affaires", ui.barres_historique(t_vue[["chiffre_affaires"]].rename(
                columns={"chiffre_affaires": "Chiffre d'affaires"})), croissance="chiffre_affaires")
            carte(g[1], "Free cash flow et SBC", ui.barres_historique(t_vue[["fcf", "sbc"]].rename(
                columns={"fcf": "Free cash flow", "sbc": "SBC"})), croissance="fcf")
            carte(g[2], "Free cash flow par action", ui.barres_historique(t_vue[["fcf_action"]].rename(
                columns={"fcf_action": "FCF par action"}), fmt=",.2f", montants=False), croissance="fcf_action")
            g = st.columns(3)
            carte(g[0], "ROCE", ui.courbe_historique(t_vue["roce"]), "Résultat opérationnel / capitaux employés")
            carte(g[1], "Marge brute", ui.courbe_historique(t_vue["marge_brute"]))
            carte(g[2], "Marge du free cash flow", ui.courbe_historique(t_vue["marge_fcf"]))
            g = st.columns(3)
            carte(g[0], "Actions en circulation diluées", ui.barres_historique(t_vue[["actions"]].rename(
                columns={"actions": "Actions"})))
            carte(g[1], "Dividendes par action", ui.barres_historique(t_vue[["dividende_action"]].rename(
                columns={"dividende_action": "Dividende par action"}), fmt=",.2f", montants=False),
                f"Rendement : {ui.pct(r.get('rendement_dividende'), 2)} · Taux de distribution : "
                f"{ui.pct(historique.taux_distribution(t), 1)}")
            carte(g[2], "Cash et dette", ui.barres_historique(t_vue[["cash", "dette"]].rename(
                columns={"cash": "Trésorerie", "dette": "Dette"})), "Dette : loyers capitalisés compris")

            sec_data = sec.load(ticker)
            verif = sec.detail(fund, sec_data)
            if not verif.empty:
                libelle = r.get("verif_sec") or "Non comparable"
                with st.expander(f"Recoupement avec les comptes déposés à la SEC : {str(libelle).lower()}",
                                 expanded=libelle == "Écart"):
                    annee = verif.attrs["exercice"][:4]
                    show = verif.copy()
                    show[["yahoo", "sec"]] = show[["yahoo", "sec"]] / unit
                    show["ecart"] = show["ecart"] * 100
                    ui.tableau(show, width="stretch", column_config={
                        "yahoo": st.column_config.NumberColumn(f"Yahoo ({u} {cur})", format="%.2f"),
                        "sec": st.column_config.NumberColumn(f"SEC ({u} {cur})", format="%.2f"),
                        "ecart": st.column_config.NumberColumn("Écart", format="%.1f %%"),
                    })
                    st.caption(f"Exercice {annee}. Source officielle : rapports 10-K / 20-F (XBRL, data.sec.gov). Les investissements "
                               "ne comptent pas dans le verdict (Yahoo y ajoute souvent les logiciels immobilisés), ni le chiffre "
                               "d'affaires des banques, assureurs et foncières (sans définition commune).")
                    if pd.notna(r.get("sec_retard")) and bool(r.get("sec_retard")):
                        st.warning("La SEC a un exercice plus récent que Yahoo : les indicateurs reposent sur des comptes en retard d'un an.")
            elif "." not in ticker and not sec.contact():
                st.caption("Comptes non recoupés avec la SEC : renseignez « contact_sec » dans profil/prive.json puis mettez à jour.")
            elif "." not in ticker:
                st.caption("Pas de rapport annuel comparable à la SEC (société récente, scission, ou comptes dans une autre devise).")
            else:
                st.caption("Comptes issus de Yahoo seul : pas de seconde source gratuite et à jour pour les sociétés cotées hors des États-Unis.")

if section == "Valorisation" and not est_fonds:
    # ------------------------------------------------------------------ valorisation
    st.subheader("Valorisation : que suppose le cours ?")
    vcfg = strat["valorisation"]
    fin = bool(r.get("financiere"))
    base = r.get("benefice_ttm") if fin else r.get("nopat_ttm")
    mcap = r.get("valeur_entreprise") - r.get("dette_nette") if pd.notna(r.get("valeur_entreprise")) else math.nan
    target = mcap if fin else r.get("valeur_entreprise")
    if r.get("holding") or not (pd.notna(base) and base > 0 and pd.notna(target) and target > 0):
        st.info("Modèle non applicable (holding, pertes ou données manquantes). Pour une holding, comparez le cours à l'actif net publié.")
    else:
        st.caption("Modèle des « value drivers » : flux libre = résultat × (1 − croissance / ROIC). La croissance coûte du capital, "
                   "d'autant moins que l'entreprise est rentable. Ajustez les hypothèses pour juger du prix.")
        roic_min = vcfg.get("roic_incremental_min", 0.12)
        roic0 = float(np.clip(r.get("rentabilite") if pd.notna(r.get("rentabilite")) else roic_min, roic_min, vcfg["roic_incremental_max"]))
        g0 = float(r.get("croissance_attendue")) if pd.notna(r.get("croissance_attendue")) else 0.05
        c = st.columns(4)
        rr = c[0].slider("Rendement exigé", 6.0, 14.0, vcfg["taux_actualisation"] * 100, 0.5, format="%.1f %%") / 100
        g = c[1].slider("Croissance années 1-5", -5.0, 40.0, float(np.clip(round(g0 * 200) / 2, -5, 40)), 0.5, format="%.1f %%") / 100
        gt = c[2].slider("Croissance perpétuelle", 0.0, 4.0, vcfg["croissance_terminale"] * 100, 0.5, format="%.1f %%") / 100
        roic = c[3].slider("ROIC des nouveaux investissements", 6.0, 60.0, float(round(roic0 * 100)), 1.0, format="%.0f %%") / 100
        kw = dict(g_term=gt, roic=roic, years_high=vcfg["annees_croissance"], years_fade=vcfg["annees_convergence"])
        ev_model = value_driver_ev(base, g, rr, **kw)
        equity = ev_model if fin else ev_model - r.get("dette_nette")
        upside = equity / mcap - 1
        k = st.columns(3)
        k[0].metric("Valeur intrinsèque / prix", ui.pct(upside, signe=True), border=True,
                    help="Écart entre la valeur des fonds propres selon vos hypothèses et la capitalisation actuelle.")
        k[1].metric("Croissance que suppose le cours", ui.pct(implied_growth(target, base, r=rr, **kw)), border=True,
                    help="Croissance annuelle des années 1-5 qui justifie exactement le prix, au rendement exigé choisi.")
        k[2].metric("TRI si votre scénario se réalise", ui.pct(implied_irr(target, base, g, **kw)), border=True)
        grid_r = [rr - 0.01, rr, rr + 0.01]
        grid_g = [g - 0.04, g - 0.02, g, g + 0.02, g + 0.04]
        sens = pd.DataFrame(
            [[(value_driver_ev(base, gg, r_, **kw) - (0 if fin else r.get("dette_nette"))) / mcap - 1 for gg in grid_g] for r_ in grid_r],
            index=[f"Rendement exigé {x * 100:.1f} %" for x in grid_r], columns=[f"Croissance {x * 100:.0f} %" for x in grid_g])
        st.markdown("**Sensibilité : écart valeur / prix**")
        ui.tableau((sens * 100).round(0), width="stretch",
                     column_config={c_: st.column_config.NumberColumn(c_, format="%+.0f %%") for c_ in sens.columns})

# ------------------------------------------------------------------ scénarios à 5 ans
if section == "Valorisation" and not est_fonds and fund:
    st.subheader("Scénarios à 5 ans")
    base_sc = scenarios.base_de(r)
    st.caption(("Flux de trésorerie disponible" if base_sc == "fcf" else "Résultat net") + " dans 5 ans × multiple de "
               "sortie, ramené à une action (évolution du nombre d'actions comprise), hors dividendes. Départ : croissance "
               "attendue, marge actuelle et multiple médian de la valeur ; ajustez-les à votre analyse.")
    depart = scenarios.hypotheses_initiales(r)
    deja = scenarios.derniers(ticker)
    if len(deja):  # on repart des derniers scénarios enregistrés
        depart = {n: {"croissance": float(x["croissance"]), "marge": float(x["marge"]), "multiple": float(x["multiple"])}
                  for n, x in deja.set_index("scenario").iterrows() if n in scenarios.NOMS} or depart
    lib_marge = "Marge de FCF" if base_sc == "fcf" else "Marge nette"
    lib_mult = "P/FCF de sortie" if base_sc == "fcf" else "PER de sortie"
    hyp, cols = {}, st.columns(3)
    for col, nom in zip(cols, scenarios.NOMS):
        h = depart[nom]
        with col.container(border=True):
            st.markdown(f"**{nom}**")
            g_ = st.number_input("Croissance annuelle du CA (%)", -20.0, 60.0, round(h["croissance"] * 100, 1), 0.5,
                                 key=f"sc_g_{ticker}_{nom}") / 100
            m_ = st.number_input(f"{lib_marge} (%)", 0.5, 80.0, max(0.5, round(h["marge"] * 100, 1)), 0.5,
                                 key=f"sc_m_{ticker}_{nom}") / 100
            x_ = st.number_input(lib_mult, 2.0, 100.0, max(2.0, float(h["multiple"])), 0.5, key=f"sc_x_{ticker}_{nom}")
            hyp[nom] = {"croissance": g_, "marge": m_, "multiple": x_}
            prix5 = scenarios.prix_futur(r, g_, m_, x_)
            tri5 = scenarios.rendement_annuel(prix5, float(r.get("cours")))
            st.metric("Prix dans 5 ans", f"{ui.num(prix5, 2)} {r.get('devise', '')}",
                      f"{ui.pct(tri5, 1, signe=True)} par an" if tri5 == tri5 else None,
                      delta_color="normal" if tri5 == tri5 else "off")
    if len(deja):
        jour = pd.Timestamp(deja["date"].iloc[0])
        st.caption(f"Repart des scénarios enregistrés le {jour:%d/%m/%Y} (cours d'alors : "
                   f"{ui.num(float(deja['cours'].iloc[0]), 2)} {r.get('devise', '')}).")
    if st.button("Enregistrer ces scénarios", icon=":material/save:", key=f"sc_save_{ticker}",
                 help="Datés, dans profil/scenarios.csv et dans le journal de la thèse. Le tableau de bord signalera un "
                      "cours au-dessus de votre prix optimiste ou sous votre prix pessimiste."):
        enr = scenarios.enregistrer(ticker, r, hyp)
        resume = " ; ".join(f"{x['scenario']} {ui.num(x['prix_5ans'], 2)} {r.get('devise', '')} (croissance "
                            f"{ui.pct(x['croissance'], 1)}, marge {ui.pct(x['marge'], 1)}, multiple {ui.num(x['multiple'], 1)})"
                            for _, x in enr.iterrows())
        append_journal(ticker, f"Scénarios à 5 ans, cours {ui.num(float(r.get('cours')), 2)} {r.get('devise', '')} : {resume}.")
        st.toast("Scénarios enregistrés.", icon=":material/save:")

if section == "Thèse":
    # ------------------------------------------------------------------ thèse
    st.subheader("Thèse d'investissement")
    thesis = read_thesis(ticker)
    if thesis:
        with st.container(border=True):
            st.markdown(thesis)
    else:
        st.caption("Pas de fiche de thèse : elle est créée automatiquement pour les lignes du portefeuille, "
                   "ou par la commande Claude /analyse-valeur.")
    # ------------------------------------------------------------------ conditions de vente
    st.subheader("Conditions de vente")
    ecrite = mp.loc[ticker, "condition_vente"] if ticker in mp.index and "condition_vente" in mp.columns else ""
    if isinstance(ecrite, str) and ecrite.strip():
        st.markdown(f"Condition écrite dans votre portefeuille : _{ecrite.strip()}_")
    evaluees = regles.evaluer(sc)
    evaluees = evaluees[evaluees["ticker"] == ticker]
    marques = {"Atteinte": ":red-badge[Atteinte]", "Respectée": ":green-badge[Respectée]",
               "Donnée absente": ":gray-badge[Donnée absente]"}
    if evaluees.empty:
        st.caption("Aucune règle chiffrée : traduisez la condition en règle vérifiée à chaque mise à jour, quand elle se "
                   "mesure (une condition sur un segment d'activité, par exemple, ne se mesure pas ici).")
    for _, x in evaluees.iterrows():
        st.markdown(f"{marques.get(x['statut'], x['statut'])} {x['regle']} : actuellement **{x['valeur']}**"
                    + (f" — {x['note']}" if x["note"] else ""))
    with st.expander("Ajouter ou retirer une règle chiffrée", icon=":material/rule:"):
        with st.form(f"regle_{ticker}", clear_on_submit=True):
            c = st.columns([3, 1, 1])
            indicateur = c[0].selectbox("Indicateur", list(regles.INDICATEURS),
                                        format_func=lambda k: regles.INDICATEURS[k][0])
            operateur = c[1].selectbox("Comparaison", list(regles.OPERATEURS))
            seuil = c[2].number_input("Seuil", value=0.0, step=1.0, help="En % pour un pourcentage (« -5 » pour -5 %), "
                                                                        "tel quel pour un multiple ou un nombre.")
            note_regle = st.text_input("Pourquoi (facultatif)", placeholder="Ex. : la thèse suppose une croissance positive")
            if st.form_submit_button("Ajouter la règle", icon=":material/add:"):
                regles.ajouter(ticker, indicateur, operateur, seuil, note_regle)
                st.rerun()
        if len(evaluees):
            choix_regle = st.selectbox("Règle à retirer", list(evaluees["index"]), index=None, placeholder="Choisir…",
                                       format_func=lambda i: evaluees.set_index("index").loc[i, "regle"])
            if choix_regle is not None and st.button("Retirer la règle", icon=":material/delete:"):
                regles.retirer(int(choix_regle))
                st.rerun()
        st.caption("Règles enregistrées dans profil/regles_vente.csv. Une règle atteinte invite à relire la thèse : "
                   "ce n'est pas un ordre de vente.")

    with st.form("journal", clear_on_submit=True):
        note = st.text_area("Ajouter une note au journal de suivi", placeholder="Ex. : résultats T3 conformes, carnet de commandes record…")
        if st.form_submit_button("Enregistrer la note", icon=":material/edit_note:") and note.strip():
            append_journal(ticker, note)
            st.toast("Note ajoutée à la fiche.")
            st.rerun()
