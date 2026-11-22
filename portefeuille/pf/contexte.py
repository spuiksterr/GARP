"""Synthèses texte pour la ligne de commande et les commandes Claude (/analyse-valeur, /revue-portefeuille…).

Elles rassemblent ce que l'interface montre dans plusieurs pages : historique et sa source, prix juste, dirigeants,
grands investisseurs, élus, actualités, scénarios, conditions de vente, prix visé, risques du portefeuille.
"""
from __future__ import annotations

import math

import pandas as pd

from .formats import nombre, pct


def _section(titre: str) -> list[str]:
    return ["", f"== {titre}"]


def contexte_valeur(ticker: str, sc: pd.DataFrame, reseau: bool = True) -> list[str]:
    """Lignes de texte décrivant tout ce que l'outil sait d'une valeur, au-delà des indicateurs de la fiche."""
    from . import actualites, congres, dirigeants, postes, prix_juste, regles, scenarios, sec
    from . import investisseurs as inv
    from .data import load_fundamentals, load_fx, load_prices
    from .watchlist import load_watchlist

    r = sc.loc[ticker]
    lignes = [f"{r['nom']} ({ticker}) — contexte au {pd.Timestamp.today():%d/%m/%Y}"]
    fund = load_fundamentals(ticker) or {}

    # Historique
    lignes += _section("Historique des comptes")
    if fund:
        h, prolonge = postes.historique(fund, sec.comptes_officiels(ticker))
        ca = h["revenue"].dropna() if "revenue" in h.columns else pd.Series(dtype=float)
        source = ("Yahoo prolongé par la SEC" if sec.load(ticker) else "Yahoo prolongé par les rapports ESEF") if prolonge \
            else "Yahoo seul"
        lignes.append(f"{len(ca)} exercices ({ca.index.min().year if len(ca) else 'n.d.'}-"
                      f"{ca.index.max().year if len(ca) else 'n.d.'}), {source}.")
    else:
        lignes.append("Pas de fiche de fondamentaux.")

    # Prix juste
    choix = prix_juste.ratios_pour(bool(r.get("financiere")), bool(r.get("holding")))
    prix = load_prices()
    if fund and choix and ticker in prix.columns:
        lignes += _section("Multiples (prix juste)")
        h, _ = postes.historique(fund, sec.comptes_officiels(ticker))
        for ratio in choix:
            s = prix_juste.serie(ratio, fund, h, prix[ticker].dropna(), r.get("capitalisation_comptes", math.nan),
                                 load_fx(), str(r.get("devise")), str(r.get("devise_comptes")))
            act, m5, m10, tout = (prix_juste.actuel(s), prix_juste.mediane(s, 5), prix_juste.mediane(s, 10),
                                  prix_juste.mediane(s))
            lignes.append(f"{ratio} : actuel {nombre(act, 1)} · médiane 5 ans {nombre(m5, 1)} · 10 ans {nombre(m10, 1)} · "
                          f"tout l'historique {nombre(tout, 1)}")

    # Watchlist et prix visé
    wl = load_watchlist()
    if ticker in wl.index:
        x = wl.loc[ticker]
        lignes += _section("Watchlist")
        lignes.append(f"Suivie depuis le {x['ajoute_le']}" + (f", prix visé {nombre(x['prix_cible'], 2)} "
                                                             f"{r.get('devise', '')} ({x['objectif']})"
                                                             if pd.notna(x["prix_cible"]) else ", sans prix visé") + ".")

    # Scénarios et conditions de vente
    d = scenarios.derniers(ticker)
    if len(d):
        lignes += _section(f"Scénarios à 5 ans (enregistrés le {pd.Timestamp(d['date'].iloc[0]):%d/%m/%Y})")
        for _, x in d.iterrows():
            lignes.append(f"{x['scenario']} : croissance {pct(x['croissance'], 1)}, marge {pct(x['marge'], 1)}, multiple "
                          f"{nombre(x['multiple'], 1)} -> {nombre(x['prix_5ans'], 2)} {x['devise']} "
                          f"({pct(scenarios.rendement_annuel(x['prix_5ans'], float(r.get('cours'))), 1)} par an au cours actuel)")
    ev = regles.evaluer(sc)
    ev = ev[ev["ticker"] == ticker]
    if len(ev):
        lignes += _section("Conditions de vente chiffrées")
        lignes += [f"[{x['statut']}] {x['regle']} : actuellement {x['valeur']}" for _, x in ev.iterrows()]

    # Dirigeants (sociétés américaines)
    if sec.sec_ticker(ticker) is not None:
        lignes += _section("Achats et ventes des dirigeants (12 mois)")
        tx = dirigeants.transactions(ticker) if reseau else dirigeants.en_cache(ticker)
        if tx is None:
            lignes.append("Non lus.")
        else:
            s = dirigeants.synthese(tx)
            lignes.append(f"{s['signal']} : {s['achats']} achat(s) par {s['acheteurs']} dirigeant(s) pour "
                          f"{nombre(s['montant_achats'] / 1e6, 2)} M ; ventes {nombre(s['montant_ventes'] / 1e6, 2)} M"
                          + (f", dont {pct(s['part_ventes_programmees'], 0)} programmées"
                             if pd.notna(s["part_ventes_programmees"]) else "") + ".")

    # Grands investisseurs et élus
    qui = inv.detenteurs_par_ticker().get(ticker, [])
    lignes += _section("Grands investisseurs (dernier trimestre déclaré)")
    lignes.append(f"Détenue par {len(qui)} investisseur(s) suivi(s)" + (f" : {', '.join(qui)}" if qui else "") + ".")
    mvt = inv.mouvements()
    if not mvt.empty:
        for _, x in mvt[mvt["ticker"] == ticker].iterrows():
            lignes.append(f"{x['investisseur']} : {x['mouvement'].lower()} ({pd.Timestamp(x['periode']):%m/%Y})")
    tx = congres.transactions()
    if not tx.empty:
        t_elus = tx[(tx["ticker"] == ticker) & (pd.to_datetime(tx["date"]) >= pd.Timestamp.today() - pd.DateOffset(years=1))]
        if len(t_elus):
            lignes += _section("Transactions d'élus américains suivis (12 mois)")
            for _, x in t_elus.head(8).iterrows():
                lignes.append(f"{x['date']} {x['elu']} : {congres.OPERATIONS.get(x['operation'], x['operation'])} "
                              f"{congres.TYPES.get(x['type'], x['type'])} {x['montant']}")

    # Actualités
    lignes += _section("Actualités récentes")
    items = (actualites.lire_json(actualites.path_of(ticker)) or {}).get("items", [])
    if not items and reseau:
        try:
            items = actualites.presse(str(r["nom"]), actualites.requetes().get(ticker)) + actualites.declarations_8k(ticker) \
                + actualites.prochains_resultats(ticker)
        except Exception as exc:
            lignes.append(f"Sources injoignables : {str(exc)[:80]}")
    for x in sorted(items, key=lambda x: x["date"], reverse=True)[:10]:
        lignes.append(f"{x['date'][:10]} [{x['source']}] {x['titre']}")
    if not items:
        lignes.append("Aucune.")
    return lignes


def risques_portefeuille() -> list[str]:
    from . import risques
    from .config import load_strategy
    from .portfolio import risk_profile

    w, source = risques.poids_actuels()
    bench = load_strategy().get("suivi", {}).get("benchmark", "IWDA.AS")
    r_p, r = risques.rendements(w, benchmark=bench)
    c = risques.concentration(w)
    profil = risk_profile(w, returns=r)
    jour, pire = risques.pire_mois(r_p)
    lignes = [f"Risques du portefeuille ({source})", "",
              f"Plus grosse ligne : {c['plus_grosse']} {pct(c['poids_plus_grosse'], 0)} · trois premières "
              f"{pct(c['trois_premieres'], 0)} · nombre effectif de lignes {nombre(c['nombre_effectif'], 1)}",
              f"Volatilité (3 ans) {pct(profil.get('volatilite'), 0)} · perte maximale {pct(risques.perte_maximale(r_p), 0)} "
              f"· pire mois {pct(pire, 0)}" + (f" ({jour:%m/%Y})" if jour is not None else ""),
              "Devises : " + ", ".join(f"{k} {pct(v, 0)}" for k, v in risques.devises(w).items()),
              f"Corrélation moyenne : {nombre(risques.correlation_moyenne(r, list(w.index)), 2)}", ""]
    fonds_or = {t: "or" for t in w.index if "GOLD" in t.upper() or t.upper().startswith("PPFB")}
    for _, x in risques.scenarios(w, r, bench, fonds_or).iterrows():
        lignes.append(f"Scénario {x['scenario']} : {pct(x['impact'], 1)} (ligne la plus touchée : {x['ligne']})")
    return lignes


def idees(sc: pd.DataFrame, n: int = 22) -> list[str]:
    """Valeurs retenues par la note GARP avec les garde-fous, et consensus des grands investisseurs."""
    from . import investisseurs as inv
    from . import portfolio as pfo
    from .config import load_strategy

    c = load_strategy()["construction"]
    retenues = pfo.select(sc, n, int(c["max_par_secteur"]), c.get("part_pea"),
                          criteres_min=int(c.get("criteres_min", 0)),
                          exclure_moat_faible=bool(c.get("exclure_moat_faible")),
                          cycliques_max=c.get("cycliques_max"), note=pfo.note_construction(sc))
    lignes = [f"Les {len(retenues)} meilleures notes GARP qui passent les garde-fous (config/strategie.json) :"]
    for t in retenues:
        r = sc.loc[t]
        lignes.append(f"  {t:10s} {str(r['nom'])[:28]:28s} note GARP {nombre(r['score'], 0)} · critères "
                      f"{r.get('criteres')} · TRI implicite {pct(r.get('tri_implicite'), 1)}")
    cons = inv.consensus()
    if not cons.empty:
        lignes += ["", "Titres détenus par au moins 3 grands investisseurs suivis (statut dans votre univers) :"]
        for _, x in cons[cons["detenteurs"] >= 3].iterrows():
            tks = [t for t in str(x["ticker"]).split(", ") if t in sc.index]
            statut = sc.loc[tks[0], "statut"] if tks else "hors univers"
            lignes.append(f"  {', '.join(tks) or x['ticker']:12s} {str(x['nom']).title()[:28]:28s} {x['detenteurs']} "
                          f"investisseurs · {statut}")
    return lignes
