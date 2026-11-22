"""Ligne de commande : python -m pf <commande>  (python -m pf --help pour la liste)."""
from __future__ import annotations

import argparse
import math
import sys
from datetime import date

import pandas as pd

from . import backtest as bt
from . import criteres, esef, indices, sec, tracker
from . import portfolio as pfo
from .config import (
    BENCHMARKS,
    RAPPORTS_DIR,
    SURVEILLANCE_CSV,
    all_tracked_tickers,
    load_cas_particuliers,
    load_model_portfolio,
    load_strategy,
    read_csv_fr,
)
from .data import load_fundamentals
from .formats import eur, nombre, pct
from .maj import bilan, tout_mettre_a_jour
from .regards import compute_regards
from .scoring import build_screener
from .theses import read_thesis

PCT_COLS = {"rentabilite", "marge_brute", "marge_operationnelle", "croiss_ca", "croissance_attendue",
            "croissance_implicite", "tri_implicite", "rendement_fcf", "mom_12_1", "perf_12m", "poids",
            "volatilite", "rendement_dividende", "pv_latente_pct", "poids_cible", "poids_reel", "ecart"}


def _fmt_df(df: pd.DataFrame) -> str:
    out = df.copy()
    for c in out.columns:
        if c in PCT_COLS:
            out[c] = pd.to_numeric(out[c], errors="coerce").map(lambda v: "" if pd.isna(v) else pct(v))
        elif pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].map(lambda v: "" if pd.isna(v) else nombre(v, 1))
    return out.to_string()


def cmd_maj(a):
    rapide = a.rapide
    if a.auto:
        # Mise à jour planifiée (Planificateur de tâches, sans fenêtre) : journal dans data/journaux, mise à jour
        # complète si la dernière a 6 jours ou plus, rapide sinon.
        from datetime import datetime

        from .config import DATA_DIR
        from .maj import jours_depuis_complete

        dossier = DATA_DIR / "journaux"
        dossier.mkdir(parents=True, exist_ok=True)
        for ancien in sorted(dossier.glob("maj-*.log"))[:-30]:  # un mois de journaux
            ancien.unlink(missing_ok=True)
        sortie = open(dossier / f"maj-{date.today().isoformat()}.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = sortie
        jours = jours_depuis_complete()
        rapide = jours is not None and jours < 6
        print(f"--- {datetime.now():%d/%m/%Y %H:%M} : mise à jour {'rapide' if rapide else 'complète'} automatique")
    res, sc = tout_mettre_a_jour(complet=a.complet, age=a.age, rapide=rapide)
    print()
    for ligne in bilan(res, sc):
        print(ligne)


def cmd_screener(a):
    sc = build_screener()
    if a.enveloppe:
        sc = sc[sc["enveloppe"] == a.enveloppe.upper()]
    if not a.tous:
        sc = sc[sc["statut"] == "Éligible"]
    cols = ["nom", "enveloppe", "secteur", "score", "qualite", "croissance", "valorisation", "momentum",
            "rentabilite", "croissance_attendue", "per_prospectif", "tri_implicite", "mom_12_1", "statut"]
    print(_fmt_df(sc[cols].head(a.top)))


def cmd_fiche(a):
    sc = build_screener()
    t = a.ticker
    if t not in sc.index:
        print(f"{t} absent de l'univers calculé. Ajoutez-le à config/univers.csv puis lancez « python -m pf maj ».")
        return 1
    r = sc.loc[t]
    print(f"{r['nom']} ({t}) — {r['secteur']} — {r['pays']} — {r['enveloppe']}")
    print(f"Statut : {r['statut']}  |  Rang : {'' if pd.isna(r['rang']) else int(r['rang'])}  |  Score : {nombre(r['score'], 0)}/100")
    print(f"Piliers : qualité {nombre(r['qualite'], 0)}, croissance {nombre(r['croissance'], 0)}, "
          f"valorisation {nombre(r['valorisation'], 0)}, momentum {nombre(r['momentum'], 0)}")
    if r["motifs_exclusion"]:
        print("Motifs d'exclusion :", r["motifs_exclusion"])
    if r["alertes"]:
        print("Alertes :", r["alertes"])
    rows = [
        ("Cours (devise de cotation)", r.get("cours"), "n"), ("Capitalisation (Md€)", r.get("capitalisation_eur", math.nan) / 1e9, "n"),
        ("ROIC moyen", r.get("roic_moyen"), "p"), ("ROE moyen", r.get("roe_moyen"), "p"),
        ("Marge brute", r.get("marge_brute"), "p"), ("Marge opérationnelle", r.get("marge_operationnelle"), "p"),
        ("Conversion FCF / résultat", r.get("conversion_fcf"), "p"), ("Dette nette / EBITDA", r.get("dette_nette_ebitda"), "n"),
        ("Évolution du nombre d'actions / an", r.get("evolution_actions"), "p"),
        ("Croissance CA historique / an", r.get("croiss_ca"), "p"), ("Croissance BPA estimée", r.get("croiss_bpa_estimee"), "p"),
        ("Croissance attendue (retenue)", r.get("croissance_attendue"), "p"),
        ("PER (12 mois)", r.get("per"), "n"), ("PER prospectif", r.get("per_prospectif"), "n"),
        ("Rendement FCF", r.get("rendement_fcf"), "p"), ("Rendement EBIT / VE", r.get("rendement_benefices"), "p"),
        ("Croissance implicite dans le cours", r.get("croissance_implicite"), "p"), ("TRI implicite", r.get("tri_implicite"), "p"),
        ("Momentum 12-1 mois", r.get("mom_12_1"), "p"), ("Volatilité 1 an", r.get("volatilite"), "p"),
        ("Perte maximale 3 ans", r.get("drawdown_max_3a"), "p"), ("Objectif moyen des analystes", r.get("objectif_analystes"), "p"),
    ]
    for label, v, kind in rows:
        print(f"  {label:<38} {pct(v) if kind == 'p' else nombre(v, 2):>12}")
    fund = load_fundamentals(t)
    if fund and r["statut"] != "Fonds":
        crits = criteres.evaluer(fund, sec.comptes_officiels(t), financiere=bool(r.get("financiere")), seuils=load_strategy().get("criteres"),
                                 tresorerie_clients=t in load_cas_particuliers()["tresorerie_clients"])
        print(f"\nSix critères de qualité : {sum(c.rempli is True for c in crits)} remplis sur "
              f"{sum(c.rempli is not None for c in crits)}")
        for c in crits:
            etat = {True: "oui", False: "non", None: " - "}[c.rempli]
            print(f"  [{etat}] {c.titre:<34} {criteres.texte_valeur(c):>9}  {c.periode or c.note}")
    thesis = read_thesis(t)
    if thesis:
        print("\n" + thesis)


def cmd_modele(a):
    sc = build_screener()
    w = pfo.model_weights()
    mp = load_model_portfolio()
    df = mp[["nom", "enveloppe", "poche", "conviction"]].copy()
    df["poids"] = w
    df = df.join(sc[["score", "rentabilite", "croissance_attendue", "per_prospectif", "tri_implicite", "mom_12_1", "statut"]])
    print(_fmt_df(df.sort_values("poids", ascending=False)))
    print("\nCaractéristiques pondérées :")
    for k, v in pfo.characteristics(w, sc).items():
        print(f"  {k:<34} {pct(v) if k != 'PER prospectif' else nombre(v, 1):>9}")
    risk = pfo.risk_profile(w)
    if risk:
        print(f"  {'Volatilité ex ante (3 ans, EUR)':<34} {pct(risk['volatilite']):>9}")
        print(f"  {'Nombre effectif de lignes':<34} {nombre(risk['nombre_effectif'], 1):>9}")
        print(f"  {'Ratio de diversification':<34} {nombre(risk['ratio_diversification'], 2):>9}")
    print("\nPar secteur :")
    print(pfo.breakdown(w, sc, "secteur").map(pct).to_string())
    print("\nPar enveloppe :")
    print(w.groupby(mp["enveloppe"]).sum().map(pct).to_string())


def cmd_construire(a):
    sc = build_screener()
    w = pfo.build_quant_portfolio(sc, nb_lignes=a.n, methode=a.methode, part_pea=a.pea, notation=a.notation)
    df = sc.reindex(w.index)[["nom", "enveloppe", "secteur", "score", "tri_implicite"]].copy()
    df["poids"] = w
    print(_fmt_df(df))


def cmd_backtest(a):
    sc = build_screener()
    if a.portefeuille == "modele":
        w = pfo.model_weights()
    else:
        w = pfo.build_quant_portfolio(sc)
    freq = {"aucun": None, "annuel": "YS", "semestriel": "6MS", "trimestriel": "QS"}[a.reequilibrage]
    curve = bt.run_backtest(w, a.depuis, rebalance=freq)
    bench = bt.benchmark_curve(a.indice, curve.index[0])
    stats = bt.perf_stats(curve["valeur"], bench)
    print(f"Backtest {a.portefeuille} depuis {curve.index[0].date()} (rééquilibrage {a.reequilibrage}) vs {BENCHMARKS.get(a.indice, a.indice)}")
    print("Attention : sélection faite aujourd'hui, donc biais rétrospectif. À lire comme un profil de risque.\n")
    for k, v in stats.items():
        ratios = ("Ratio de Sharpe", "Ratio de Sortino", "Ratio de Calmar", "Bêta", "Ratio d'information", "Corrélation")
        fmt = nombre(v, 2) if k in ratios else pct(v)
        print(f"  {k:<34} {fmt}")
    yr = pd.DataFrame({"Portefeuille": bt.annual_returns(curve["valeur"]), "Indice": bt.annual_returns(bench)})
    print("\nRendements annuels :")
    print(yr.map(lambda v: "" if pd.isna(v) else pct(v)).to_string())


def cmd_suivi(a):
    tx = tracker.load_transactions()
    if tx.empty:
        print("Aucune opération dans data/transactions.csv : l'interface s'appuie désormais sur la photo du "
              "portefeuille prise à chaque import (profil/positions.csv).")
        return
    for anomalie in tracker.controle_ventes(tx)[1]:
        print("Journal corrigé :", anomalie)
    pos = tracker.positions(tx)
    print(_fmt_df(pos[["compte", "ticker", "quantite", "pru_eur", "cours_eur", "valeur_eur", "pv_latente_eur", "pv_latente_pct", "poids"]]))
    hist = tracker.history(tx)
    perf = tracker.twr(hist)
    rdt, annualise = tracker.rendement_argent(hist)
    strat = load_strategy()
    shadow = tracker.benchmark_shadow(hist, strat["suivi"]["benchmark"])
    print(f"\nValeur totale : {eur(hist['valeur_totale'].iloc[-1])}  |  Apports nets : {eur(hist['apports_cumules'].iloc[-1])}")
    print(f"Performance (TWR) : {pct(perf.iloc[-1] / 100 - 1, signe=True)}  |  "
          f"{'TRI annualisé' if annualise else 'Rendement de votre argent sur la période (moins d’un an, non annualisé)'} : "
          f"{pct(rdt, signe=True)}")
    if not shadow.empty:
        print(f"Même argent investi dans {strat['suivi']['benchmark']} : {eur(shadow.iloc[-1])}")
    alerts = tracker.drift_alerts(pos, pfo.model_weights(), strat["suivi"]["seuil_reequilibrage"])
    if not alerts.empty:
        print("\nÉcarts aux poids cibles :")
        print(_fmt_df(alerts))


def cmd_apport(a):
    mp = load_model_portfolio()
    w = pfo.model_weights()
    strat = load_strategy()
    compte = (a.compte or pfo.compte_principal(w, mp)).upper()
    ecartees = {} if a.toutes_lignes else pfo.lignes_a_ecarter(build_screener(), w.index)
    for t, raison in ecartees.items():
        print(f"Écartée de l'apport : {mp['nom'].get(t, t)} ({t}), {raison}.")
    plan = tracker.contribution_plan(a.montant, compte, w.drop(index=list(ecartees)), mp["enveloppe"],
                                     min_order=a.min or strat["suivi"]["ordre_min_eur"], fractional=a.fractions,
                                     max_orders=a.max_ordres)
    if plan.empty:
        print(f"Aucun ordre proposé sur le {compte} (montant trop faible par rapport à l'ordre minimal, "
              f"ou aucune ligne cible sur ce compte).")
        return
    plan.insert(1, "nom", plan["ticker"].map(mp["nom"]))
    print(_fmt_df(plan[["ticker", "nom", "quantite", "cours_eur", "montant_eur"]]))
    print(f"\nCompte : {compte}  |  Total investi : {eur(plan['montant_eur'].sum(), 2)}  |  Reste : {eur(plan.attrs.get('reste', 0), 2)}")


def cmd_regards(a):
    t = compute_regards(build_screener(), None if a.tous else a.top, tous=a.tous)
    print(t[["rang", "nom", "statut", "buffett", "munger", "fisher", "smith", "total"]].to_string())
    print("\nCrible chiffré, corrigé à la main : il désigne quoi analyser, pas quoi acheter.")


def cmd_esef(a):
    from .data import load_fundamentals
    tickers = [t for t in all_tracked_tickers() if esef.couvert(t)]
    print(f"Rapports annuels européens (ESEF) : {sum(esef.a_rafraichir(t) for t in tickers)} valeurs à traiter "
          f"sur {len(tickers)}, environ 20 s chacune la première fois.")
    res = esef.update(tickers, load_fundamentals, progress=lambda i, n, t: print(f"  {i}/{n} {t}", flush=True),
                      maximum=a.max)
    print(f"Trouvées : {len(res['ok'])}, introuvables : {len(res['introuvables'])}, erreurs : {len(res['erreurs'])}"
          + (f", reste à traiter : {res['reste']}" if res["reste"] else ""))
    if res["introuvables"]:
        print("Introuvables : " + ", ".join(res["introuvables"]))
    print("Lancez ensuite : python -m pf maj (recalcul des indicateurs).")


def cmd_homme_cle(a):
    from . import homme_cle
    from .config import load_model_portfolio, load_universe
    from .watchlist import load_watchlist
    if a.tickers:
        tickers = a.tickers
    elif a.tous:
        tickers = list(load_universe().index)
    else:
        tickers = list(dict.fromkeys([*load_model_portfolio().index, *load_watchlist().index]))
    print(f"Dirigeants de {len(tickers)} valeurs (Yahoo, environ une seconde chacune)…")
    notes = homme_cle.relire(tickers, progress=lambda i, n, t: print(f"  {i}/{n} {t}", end="\r"))
    print()
    for t, n in sorted(notes.items(), key=lambda x: -(x[1]["homme_cle"] if x[1]["homme_cle"] == x[1]["homme_cle"]
                                                         else -1)):
        note = "  n.d." if n["homme_cle"] != n["homme_cle"] else f"{n['homme_cle']:.1f}".replace(".", ",") + "/10"
        print(f"{t:10} {note:>7} {n['homme_cle_niveau']:8} {n['homme_cle_facteurs']}")
    print("Note reportée dans les indicateurs : screener, composition et fiches l'affichent déjà.")


def cmd_investisseurs(a):
    from . import congres, investisseurs
    print("Portefeuilles 13F des investisseurs suivis (config/investisseurs.csv)…")
    r1 = investisseurs.mettre_a_jour(force=a.force, progress=print)
    if r1.get("saute"):
        print(f"  Non lus : {r1['saute']}")
    else:
        print(f"  {r1.get('nouvelles', 0)} trimestres lus" + (f", erreurs : {r1['erreurs']}" if r1.get("erreurs") else ""))
    print("Transactions des élus suivis (config/elus.csv)…")
    r2 = congres.mettre_a_jour(force=a.force, progress=print)
    print(f"  {r2['nouveaux']} rapports lus, dont {r2['scannes']} scannés (illisibles)"
          + (f", erreurs : {r2['erreurs']}" if r2["erreurs"] else ""))
    if r1.get("saute"):  # visible dans le flux de la nuit (étape en orange) au lieu de « 0 trimestres lus »
        raise SystemExit("Portefeuilles 13F non lus : adresse de contact SEC absente (secret SEC_CONTACT du dépôt "
                         "GitHub, ou contact_sec de profil/prive.json).")


def cmd_contexte(a):
    from .contexte import contexte_valeur

    sc = build_screener()
    if a.ticker not in sc.index:
        print(f"{a.ticker} absent de l'univers calculé.")
        return 1
    print("\n".join(contexte_valeur(a.ticker, sc, reseau=not a.hors_ligne)))


def cmd_risques(a):
    from .contexte import risques_portefeuille

    print("\n".join(risques_portefeuille()))


def cmd_idees(a):
    from .contexte import idees

    print("\n".join(idees(build_screener())))


def cmd_indices(a):
    n = indices.extend_universe()
    print(f"S&P 500 et STOXX 600 : {n} valeur(s) ajoutée(s).")
    if not a.sans_nasdaq:
        print("Nasdaq Global Select : vérification des nouvelles valeurs auprès de Yahoo…")
        r = indices.extend_nasdaq(progress=lambda i, total, t: print(f"  {i}/{total}") if i % 100 == 0 else None)
        print(f"Nasdaq : {r['examinees']} valeur(s) examinée(s), {len(r['ajouts'])} ajoutée(s)"
              + (f" : {', '.join(r['ajouts'][:20])}{'…' if len(r['ajouts']) > 20 else ''}" if r["ajouts"] else "") + ".")
    print("Lancez ensuite : python -m pf maj")


def cmd_export(a):
    sc = build_screener()
    w = pfo.model_weights()
    RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RAPPORTS_DIR / f"portefeuille-{date.today().isoformat()}.xlsx"
    mp = load_model_portfolio().copy()
    mp["poids"] = w
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        mp.join(sc[["score", "criteres", "qualite", "croissance", "valorisation", "momentum", "tri_implicite", "per_prospectif"]]).to_excel(
            xl, sheet_name="Portefeuille")
        sc.drop(columns=[c for c in ("profil",) if c in sc.columns]).to_excel(xl, sheet_name="Screener")
        surv = SURVEILLANCE_CSV
        if surv.exists():
            read_csv_fr(surv).to_excel(xl, sheet_name="Surveillance", index=False)
        pos = tracker.positions()
        if not pos.empty:
            pos.to_excel(xl, sheet_name="Mes positions", index=False)
    print(f"Rapport écrit : {path}")


def cmd_bureau(a):
    from .bureau import ouvrir
    ouvrir(a.port)


def cmd_mobile(a):
    from . import mobile
    try:
        if a.arreter:
            mobile.desactiver()
            print("Accès depuis le téléphone coupé.")
            return 0
        url = mobile.activer(a.port)
    except RuntimeError as exc:
        print(f"Impossible : {exc}.")
        return 1
    print(f"Sur le téléphone (connecté à Tailscale) : {url}")
    print("Puis menu du navigateur > « Ajouter à l'écran d'accueil ». L'application doit tourner sur ce PC "
          "(fenêtre G.A.R.P ou lancer.bat) ; « pf mobile --arreter » coupe l'accès.")
    return 0


def cmd_export_app(a):
    from pathlib import Path

    from .export_app import exporter
    if a.sources_sec:
        from .export_fiches import prechauffer
        from .scoring import build_screener
        print(f"Sources SEC des fiches ({a.sources_sec:g} min au plus) : {prechauffer(build_screener(), a.sources_sec)}")
    chemin = exporter(Path(a.vers))
    for f in sorted(chemin.parent.glob("garp-*.json.gz")):
        print(f"Données de l'application : {f} ({f.stat().st_size / 1e6:.1f} Mo)")


def cmd_export_outil(a):
    from pathlib import Path

    from .export_outil import exporter
    chemin = exporter(Path(a.vers))
    print(f"Données de la version autonome : {chemin} ({chemin.stat().st_size / 1e6:.1f} Mo)")


def cmd_sauvegarde(a):
    from pathlib import Path

    from . import sauvegarde
    if a.vers:
        sauvegarde.memoriser_dossier(Path(a.vers).resolve())
    if not sauvegarde.dossier_configure():
        print("Aucun dossier de sauvegarde. Choisissez-en un hors de ce disque ou synchronisé, par exemple :\n"
              "  pf sauvegarde --vers \"C:\\Users\\<vous>\\OneDrive\\Sauvegardes G.A.R.P\"\n"
              "Il est mémorisé dans profil/prive.json et resservira à chaque mise à jour.")
        return 1
    n = len(sauvegarde.elements())
    print(f"{n} fichiers sauvegardés dans {sauvegarde.creer()}")
    print(f"Les {sauvegarde.GARDER} dernières archives sont gardées. Restaurer : décompresser dans portefeuille/.")
    return 0


def cmd_verifier(a):
    from .verifier import verifier
    constats = verifier()
    if not constats:
        print("Aucun problème détecté.")
        return 0
    for gravite in ("erreur", "avertissement"):
        liste = [c for c in constats if c.gravite == gravite]
        if liste:
            print(f"== {len(liste)} {gravite}{'s' if len(liste) > 1 else ''}")
            for c in liste[: None if a.tout else 40]:
                print(f"  [{c.categorie}] {c.message}")
            if len(liste) > 40 and not a.tout:
                print(f"  … et {len(liste) - 40} autres (--tout pour la liste complète)")
    return 1 if any(c.gravite == "erreur" for c in constats) else 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m pf", description="Outils de stock-picking long terme")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("maj", help="mettre à jour cours, fondamentaux et scores")
    s.add_argument("--age", type=float, default=7, help="rafraîchir les fondamentaux plus vieux que N jours (7)")
    s.add_argument("--complet", action="store_true", help="tout re-télécharger")
    s.add_argument("--auto", action="store_true",
                   help="mode planifié : complète si la dernière a 6 jours ou plus, rapide sinon ; journal dans data/journaux")
    s.add_argument("--rapide", action="store_true",
                   help="cours, changes et calculs seulement (quelques minutes) ; fondamentaux et comptes inchangés")
    s.set_defaults(fn=cmd_maj)
    s = sub.add_parser("screener", help="classement de l'univers")
    s.add_argument("--top", type=int, default=30)
    s.add_argument("--enveloppe", choices=["PEA", "CTO", "pea", "cto"])
    s.add_argument("--tous", action="store_true", help="inclure les valeurs exclues")
    s.set_defaults(fn=cmd_screener)
    s = sub.add_parser("fiche", help="fiche détaillée d'une valeur")
    s.add_argument("ticker")
    s.set_defaults(fn=cmd_fiche)
    s = sub.add_parser("regards", help="note sur 5 selon quatre regards pour les meilleurs scores")
    s.add_argument("--top", type=int, default=50)
    s.add_argument("--tous", action="store_true", help="toutes les valeurs, exclues comprises")
    s.set_defaults(fn=cmd_regards)
    s = sub.add_parser("contexte", help="tout le contexte d'une valeur : historique, prix juste, dirigeants, grands "
                                         "investisseurs, élus, actualités, scénarios, conditions de vente")
    s.add_argument("ticker")
    s.add_argument("--hors-ligne", action="store_true", help="sans accès réseau (données en cache seulement)")
    s.set_defaults(fn=cmd_contexte)
    s = sub.add_parser("risques", help="risques du portefeuille : concentration, devises, scénarios de choc")
    s.set_defaults(fn=cmd_risques)
    s = sub.add_parser("idees", help="idées : valeurs retenues par plusieurs méthodes de notation, consensus des grands investisseurs")
    s.set_defaults(fn=cmd_idees)
    s = sub.add_parser("esef", help="historique des valeurs européennes depuis leurs rapports annuels (ESEF)")
    s.add_argument("--max", type=int, help="nombre maximal de sociétés à traiter")
    s.set_defaults(fn=cmd_esef)
    s = sub.add_parser("investisseurs", help="portefeuilles 13F de grands investisseurs et transactions d'élus américains")
    s.add_argument("--force", action="store_true", help="relire même ce qui a été consulté récemment")
    s.set_defaults(fn=cmd_investisseurs)
    s = sub.add_parser("homme-cle", help="risque homme-clé : relire les dirigeants (portefeuille et watchlist par "
                                         "défaut) sans attendre le renouvellement des fiches")
    s.add_argument("tickers", nargs="*", help="valeurs à relire (sinon portefeuille et watchlist)")
    s.add_argument("--tous", action="store_true", help="tout l'univers (environ 40 minutes)")
    s.set_defaults(fn=cmd_homme_cle)
    s = sub.add_parser("indices", help="ajouter à l'univers les nouveaux entrants du S&P 500, du STOXX 600 "
                                         "et du Nasdaq Global Select (au moins 1 milliard de dollars)")
    s.add_argument("--sans-nasdaq", action="store_true", help="indices S&P 500 et STOXX 600 seulement (rapide)")
    s.set_defaults(fn=cmd_indices)
    s = sub.add_parser("modele", help="portefeuille modèle et ses caractéristiques")
    s.set_defaults(fn=cmd_modele)
    s = sub.add_parser("construire", help="construction de portefeuille : portefeuille construit par des règles (plancher de qualité, "
                                         "secteurs cycliques plafonnés), point de comparaison")
    s.add_argument("--n", type=int)
    s.add_argument("--methode", choices=list(pfo.METHODES))
    s.add_argument("--pea", type=float, help="part du PEA (0-1)")
    s.add_argument("--notation", choices=list(pfo.NOTATIONS), help="méthode de notation qui classe les candidats")
    s.set_defaults(fn=cmd_construire)
    s = sub.add_parser("backtest", help="backtest du portefeuille modèle ou systématique")
    s.add_argument("--portefeuille", choices=["modele", "quant"], default="modele")
    s.add_argument("--depuis", default="2016-01-01")
    s.add_argument("--reequilibrage", choices=["aucun", "annuel", "semestriel", "trimestriel"], default="annuel")
    s.add_argument("--indice", default="IWDA.AS")
    s.set_defaults(fn=cmd_backtest)
    s = sub.add_parser("suivi", help="positions, performance, écarts au modèle")
    s.set_defaults(fn=cmd_suivi)
    s = sub.add_parser("apport", help="répartition d'un apport sans vendre")
    s.add_argument("montant", type=float)
    s.add_argument("--compte", choices=["PEA", "CTO", "pea", "cto"], help="par défaut : le compte qui porte le plus de poids cible")
    s.add_argument("--min", type=float, help="ordre minimal en euros")
    s.add_argument("--fractions", action="store_true", help="le courtier accepte les fractions d'action")
    s.add_argument("--max-ordres", type=int, help="nombre maximal d'ordres (limite les frais)")
    s.add_argument("--toutes-lignes", action="store_true",
                   help="ne pas écarter les lignes sorties des filtres ou en forte baisse")
    s.set_defaults(fn=cmd_apport)
    s = sub.add_parser("export", help="rapport Excel dans rapports/")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("bureau", help="ouvrir l'application dans sa propre fenêtre (version bureau)")
    s.add_argument("--port", type=int, default=8501)
    s.set_defaults(fn=cmd_bureau)
    s = sub.add_parser("mobile", help="ouvrir l'application au téléphone par le réseau privé Tailscale")
    s.add_argument("--port", type=int, default=8501)
    s.add_argument("--arreter", action="store_true", help="couper l'accès depuis le téléphone")
    s.set_defaults(fn=cmd_mobile)
    s = sub.add_parser("export-app", help="fichier de données de l'application G.A.R.P (sans donnée personnelle)")
    s.add_argument("--vers", default="rapports", help="dossier de destination")
    s.add_argument("--sources-sec", type=float, default=0, metavar="MINUTES",
                   help="lire d'abord, pendant ce temps au plus, les sources SEC des fiches (dirigeants, ventilation)")
    s.set_defaults(fn=cmd_export_app)
    s = sub.add_parser("export-outil", help="archive des données pour la version autonome installée (sans donnée "
                                             "personnelle)")
    s.add_argument("--vers", default="rapports", help="dossier de destination")
    s.set_defaults(fn=cmd_export_outil)
    s = sub.add_parser("sauvegarde", help="archive datée des données personnelles (profil, thèses, opérations, "
                                           "historique des scores) dans le dossier choisi")
    s.add_argument("--vers", help="dossier de destination, mémorisé pour les fois suivantes")
    s.set_defaults(fn=cmd_sauvegarde)
    s = sub.add_parser("verifier", help="contrôle du projet : doublons de l'univers, secteurs inconnus, cours "
                                         "absents ou figés, fiches incomplètes, fichiers de configuration mal formés")
    s.add_argument("--tout", action="store_true", help="afficher tous les constats")
    s.set_defaults(fn=cmd_verifier)
    a = p.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
