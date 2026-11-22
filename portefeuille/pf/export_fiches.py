"""Fichiers complémentaires de l'application G.A.R.P, publiés avec garp-donnees.json.gz (pf/export_app.py).

- `garp-fiches.json.gz` : le détail de chaque valeur, lu à l'ouverture d'une fiche : historique financier
  (historique.py), repères des multiples et leur série trimestrielle (prix_juste.py), description de l'activité,
  et, quand ils sont en cache, achats et ventes des dirigeants (dirigeants.py) et ventilation du chiffre
  d'affaires (ventilation.py).
- `garp-investisseurs.json.gz` : portefeuilles 13F des investisseurs suivis, titres les plus partagés,
  transactions des élus américains (investisseurs.py, congres.py).

Aucune donnée personnelle. Aucun accès réseau ici : on publie ce que les mises à jour ont mis en cache
(`prechauffer` lit les sources SEC des fiches, dans un temps limité, pour le flux de nuit).
"""
from __future__ import annotations

import math
import time

import pandas as pd

NOM_FICHES = "garp-fiches.json.gz"
NOM_INVESTISSEURS = "garp-investisseurs.json.gz"
ANNEES_MULTIPLES = 12
TRANSACTIONS_DIRIGEANTS = 20
LIGNES_13F = 80
OPERATIONS_ELUS = 600


def _sig(v, chiffres: int = 5):
    """Nombre arrondi à `chiffres` chiffres significatifs ; None pour NaN et infinis."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    if v == 0:
        return 0
    r = round(v, chiffres - 1 - math.floor(math.log10(abs(v))))
    return int(r) if abs(r) >= 10 ** chiffres else r


def _vrai(v) -> bool:
    return bool(v) if pd.notna(v) else False


def _historique(fund: dict, comptes: dict | None) -> dict | None:
    from . import historique

    t = historique.tableau(fund, comptes)
    if t.empty:
        return None
    return {"an": [str(i) for i in t.index], **{c: [_sig(x) for x in t[c]] for c in t.columns}}


def _reperes(r: pd.Series, fund: dict, h: pd.DataFrame, prix: pd.Series, fx: pd.DataFrame) -> dict:
    """Par ratio : multiple actuel, médianes sur 5 et 10 ans et sur tout l'historique, minimum, série trimestrielle."""
    from . import prix_juste

    out = {}
    if prix.empty or h.empty:
        return out
    for ratio in prix_juste.ratios_pour(_vrai(r.get("financiere")), _vrai(r.get("holding"))):
        try:
            s = prix_juste.serie(ratio, fund, h, prix, r.get("capitalisation_comptes", math.nan), fx,
                                 str(r.get("devise")), str(r.get("devise_comptes")))
        except Exception:  # comptes incomplets : pas de repère pour ce ratio
            continue
        valides = s.dropna()
        if valides.empty:
            continue
        recent = s[s.index >= s.index.max() - pd.DateOffset(years=ANNEES_MULTIPLES)].resample("QE").last()
        recent = recent.loc[recent.first_valid_index():]
        out[ratio] = {"actuel": _sig(prix_juste.actuel(s)), "m5": _sig(prix_juste.mediane(s, 5)),
                      "m10": _sig(prix_juste.mediane(s, 10)), "tout": _sig(prix_juste.mediane(s)),
                      "depuis": int(valides.index.min().year), "min": _sig(valides.min()),
                      "debut": f"{recent.index[0]:%Y-%m-%d}", "v": [_sig(x, 4) for x in recent.tolist()]}
    return out


def _dirigeants(ticker: str) -> dict | None:
    from . import dirigeants

    df = dirigeants.en_cache(ticker)
    if df is None:
        return None
    s = dirigeants.synthese(df)
    return {**{k: (_sig(v) if isinstance(v, float) else v) for k, v in s.items()}, "lu_le": df.attrs.get("lu_le"),
            "transactions": [{"date": x["date"], "nom": x["nom"], "fonction": x["fonction"], "code": x["code"],
                              "actions": _sig(x["actions"]), "prix": _sig(x["prix"]), "montant": _sig(x["montant"]),
                              "plan": bool(x["plan_10b5_1"])}
                             for _, x in df.head(TRANSACTIONS_DIRIGEANTS).iterrows()]}


def _ventilation(ticker: str) -> dict | None:
    from . import ventilation
    from .config import lire_json

    v = lire_json(ventilation.CACHE / f"{ticker}.json")
    if not v or not (v.get("activites") or v.get("geographie")):
        return None
    return {"exercice": v.get("exercice"), "formulaire": v.get("formulaire"), "total": _sig(v.get("total")),
            "activites": {k: _sig(x) for k, x in (v.get("activites") or {}).items()},
            "geographie": {k: _sig(x) for k, x in (v.get("geographie") or {}).items()}}


def fiches(sc: pd.DataFrame, prix: pd.DataFrame, fx: pd.DataFrame) -> dict:
    """{ticker: {h: historique, r: repères des multiples, desc, d: dirigeants, v: ventilation, src: source}}."""
    from . import postes, sec
    from .data import load_fundamentals

    out = {}
    for t, r in sc.iterrows():
        if _vrai(r.get("fonds")):
            continue
        fund = load_fundamentals(t)
        if not fund:
            continue
        f: dict = {}
        try:
            comptes = sec.comptes_officiels(t)
            h, prolonge = postes.historique(fund, comptes)
            hist = _historique(fund, comptes)
            if hist:
                f["h"] = hist
                f["src"] = "prolonge" if prolonge else "yahoo"
            rep = _reperes(r, fund, h, prix[t].dropna() if t in prix.columns else pd.Series(dtype=float), fx)
            if rep:
                f["r"] = rep
        except Exception:  # une fiche illisible ne bloque pas les autres
            pass
        desc = (fund.get("info") or {}).get("longBusinessSummary")
        if isinstance(desc, str) and desc.strip():
            f["desc"] = desc.strip()[:2500]
        d = _dirigeants(t)
        if d:
            f["d"] = d
        v = _ventilation(t)
        if v:
            f["v"] = v
        if f:
            out[t] = f
    return out


def investisseurs_et_elus() -> dict:
    """Portefeuilles 13F, titres les plus partagés et opérations des élus, tels qu'en cache."""
    from . import congres, investisseurs

    liste = investisseurs.load_liste()
    inv = []
    for cik, ligne in liste.iterrows():
        p = investisseurs.positions(cik)
        if p.empty:
            continue
        lignes = [{"nom": x["nom"], "ticker": x["ticker"] if isinstance(x["ticker"], str) else None,
                   "poids": _sig(x["poids"], 4), "valeur": _sig(x["valeur"]), "mouvement": x.get("mouvement") or "",
                   "variation": _sig(x.get("variation"), 4), "depuis": x.get("depuis")}
                  for _, x in p.head(LIGNES_13F).iterrows()]
        inv.append({"cik": int(cik), "investisseur": ligne["investisseur"], "societe": ligne.get("societe", ""),
                    "style": ligne.get("style", ""), "periode": p.attrs.get("periode"),
                    "precedente": p.attrs.get("precedente"), "depose_le": p.attrs.get("depose_le"),
                    "total": _sig(p.attrs.get("total")), "nb_lignes": int((p["valeur"] > 0).sum()), "lignes": lignes})
    cons = investisseurs.consensus(liste) if inv else pd.DataFrame()
    partages = [{"nom": x["nom"], "ticker": x["ticker"], "detenteurs": int(x["detenteurs"]),
                 "poids_moyen": _sig(x["poids_moyen"], 4), "poids_max": _sig(x["poids_max"], 4), "qui": list(x["liste"])}
                for _, x in cons.head(150).iterrows()] if len(cons) else []
    tx = congres.transactions()
    ops = [{"elu": x["elu"], "parti": x.get("parti") or "", "date": x["date"], "depose_le": x["depose_le"],
            "actif": x["actif"], "ticker": x["ticker"] if isinstance(x["ticker"], str) else None,
            "operation": x["operation"], "montant": x["montant"], "detenteur": x.get("detenteur") or "",
            "retard": int(x["retard_jours"]) if pd.notna(x["retard_jours"]) else None, "lien": x["lien"]}
           for _, x in tx.head(OPERATIONS_ELUS).iterrows()] if len(tx) else []
    elus = congres.load_liste()
    return {
        "maj_13f": investisseurs.derniere_mise_a_jour(), "investisseurs": inv, "partages": partages,
        "maj_elus": congres.derniere_mise_a_jour(),
        "elus": [{"elu": f"{e['prenom']} {e['nom']}".strip(), "parti": e.get("parti", ""),
                  "circonscription": e["circonscription"]} for _, e in elus.iterrows()],
        "operations": ops,
    }


def prechauffer(sc: pd.DataFrame, minutes: float = 10, progress=print) -> dict:
    """Lit, dans un temps limité, les sources SEC des fiches (dirigeants, ventilation du chiffre d'affaires) pour les
    valeurs américaines éligibles, les mieux classées d'abord. Ce qui est en cache n'est pas relu : nuit après
    nuit, toutes les fiches se remplissent. Sans adresse de contact SEC, rien n'est lu."""
    from . import dirigeants, sec, ventilation

    if not sec.contact():
        return {"saute": "adresse de contact SEC absente"}
    fin = time.monotonic() + minutes * 60
    us = sc[(sc["statut"] == "Éligible") & ~sc.index.str.contains(r"\.")].sort_values("rang")
    res = {"dirigeants": 0, "ventilations": 0}
    limite = (pd.Timestamp.today() - pd.Timedelta(days=7)).date().isoformat()
    for t in us.index:
        if time.monotonic() > fin:
            break
        try:
            deja = dirigeants.en_cache(t)
            if deja is None or (deja.attrs.get("lu_le") or "") < limite:
                dirigeants.transactions(t)
                res["dirigeants"] += 1
            if not (ventilation.CACHE / f"{t}.json").exists():
                ventilation.ventilation(t, max_age_days=300)
                res["ventilations"] += 1
        except Exception as exc:  # une valeur illisible ne bloque pas les autres
            progress(f"  {t} : {str(exc)[:120]}")
    return res
