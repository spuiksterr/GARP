"""Styles d'investisseur : qualité, croissance, GARP, valeur, momentum.

Les quatre regards (Buffett, Munger, Fisher, Terry Smith) sont quatre nuances d'une même famille, « qualité, temps
long » : les vraies différences de tempérament se jouent entre les styles ci-dessous. Chacun classe les actions avec
une méthode de notation de pf/portfolio.py (NOTATIONS) ; le prix d'achat et le verdict (pf/prix_achat.py) ne
changent pas d'un style à l'autre : ils jugent le prix, pas l'entreprise.

Un questionnaire de huit questions propose un style, avec l'explication du choix ; l'utilisateur peut en prendre
un autre. Le choix est enregistré dans profil/style.json (fichier personnel, exclu de Git).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .config import PROFIL_DIR, ecrire_json, lire_json

STYLE_JSON = PROFIL_DIR / "style.json"
DEFAUT = "garp"  # le nom même de l'outil : la croissance, sans la surpayer


@dataclass(frozen=True)
class Style:
    libelle: str
    notation: str  # clé de pfo.NOTATIONS
    devise: str  # en une phrase
    cherche: str
    accepte: str
    souffre: str  # quand le style traverse ses mauvaises années
    backtest: str  # clé de backtest_pit.METHODES


STYLES: dict[str, Style] = {
    "qualite": Style(
        "Qualité", "qualite", "Payer pour l'excellence et la durabilité.",
        "des entreprises très rentables, solides et durables, que l'on garde longtemps",
        "de les payer un peu cher, si leur rentabilité dure",
        "quand le marché s'emballe pour les valeurs bon marché ou cycliques, et quand les entreprises de qualité "
        "deviennent trop chères : elles peuvent alors stagner plusieurs années",
        "Qualité"),
    "croissance": Style(
        "Croissance", "croissance", "Accepter un prix élevé pour une croissance forte.",
        "des entreprises dont le chiffre d'affaires et les bénéfices grandissent vite",
        "des multiples élevés et des cours très volatils",
        "quand les taux d'intérêt montent ou qu'une croissance déçoit : les baisses de 30 à 50 % ne sont pas rares",
        "Croissance"),
    "garp": Style(
        "GARP", "garp", "La croissance, sans la surpayer.",
        "des entreprises de bonne qualité, en croissance, à un prix raisonnable",
        "de laisser passer les plus belles histoires, trop chères, et les plus grosses décotes, trop fragiles",
        "rarement en tête : ni dans les emballements pour la croissance, ni dans les rebonds des valeurs décotées",
        "GARP (croissance, valeur, qualité)"),
    "valeur": Style(
        "Valeur", "valeur", "Acheter ce qui est décoté.",
        "des actions bon marché par rapport à leurs flux, avec un minimum de qualité",
        "de détenir des entreprises imparfaites ou mal aimées, et d'attendre que le marché les réévalue",
        "pendant les longues périodes où la croissance mène le marché : de 2007 à 2020, la valeur a été en retard "
        "presque chaque année",
        "Valeur"),
    "momentum": Style(
        "Momentum", "momentum", "Suivre la tendance.",
        "les actions qui ont le plus monté sur douze mois, en changeant souvent",
        "de vendre ce qui baisse sans attendre, et un suivi fréquent",
        "lors des retournements brutaux : au printemps 2009, les actions les plus en retard ont rebondi les "
        "premières, et le momentum a perdu une grande partie de ses gains en quelques semaines",
        "Momentum"),
}


@dataclass(frozen=True)
class Question:
    cle: str
    titre: str
    reponses: dict[str, tuple[str, dict[str, int]]]  # clé -> (texte, points par style)


QUESTIONS: list[Question] = [
    Question("priorite", "Ce que vous cherchez d'abord dans une entreprise", {
        "excellence": ("Une entreprise excellente et durable, même un peu chère", {"qualite": 2, "garp": 1}),
        "croissance": ("Une croissance forte, quitte à la payer cher", {"croissance": 2}),
        "raisonnable": ("Une belle croissance, mais pas à n'importe quel prix", {"garp": 2}),
        "decote": ("Une action décotée, même si l'entreprise est imparfaite", {"valeur": 2}),
        "tendance": ("Une action qui monte, portée par le marché", {"momentum": 2}),
    }),
    Question("duree", "Combien de temps gardez-vous une action ?", {
        "dix_ans": ("Dix ans et plus", {"qualite": 2, "garp": 1}),
        "cinq_ans": ("Trois à cinq ans", {"croissance": 1, "garp": 1, "valeur": 1}),
        "un_an": ("Moins d'un an, je change souvent", {"momentum": 2}),
    }),
    Question("baisse", "Une de vos actions perd 30 % en quelques mois, sans mauvaise nouvelle sur l'entreprise", {
        "racheter": ("J'en rachète : le prix est meilleur", {"valeur": 2, "qualite": 1}),
        "garder": ("Je garde : la thèse compte plus que le cours", {"qualite": 1, "garp": 1, "croissance": 1}),
        "vendre": ("Je vends : le marché sait peut-être quelque chose", {"momentum": 2}),
    }),
    Question("multiple", "Payer une action 40 fois ses bénéfices", {
        "jamais": ("Jamais", {"valeur": 2}),
        "si_croissance": ("Si la croissance le justifie, chiffres à l'appui", {"garp": 2}),
        "exceptionnelle": ("Oui, pour une entreprise exceptionnelle", {"qualite": 1, "croissance": 1}),
        "peu_importe": ("Le prix compte peu, la tendance compte", {"momentum": 1, "croissance": 1}),
    }),
    Question("mal_aimee", "Une entreprise mal aimée, aux résultats en baisse, mais très bon marché", {
        "occasion": ("C'est là que sont les occasions", {"valeur": 2}),
        "si_solide": ("Seulement si son activité reste solide", {"garp": 1, "qualite": 1}),
        "eviter": ("Je l'évite", {"qualite": 1, "croissance": 1, "momentum": 1}),
    }),
    Question("retard", "Être en retard sur le marché trois ans de suite", {
        "supporte": ("Je le supporte si ma méthode est bonne", {"valeur": 1, "qualite": 1}),
        "difficile": ("Difficilement", {"garp": 1, "croissance": 1}),
        "change": ("Je change d'approche", {"momentum": 1}),
    }),
    Question("suivi", "Le temps que vous consacrez au suivi", {
        "peu": ("Quelques heures par an", {"qualite": 2, "garp": 1}),
        "mois": ("Un moment chaque mois", {"garp": 1, "valeur": 1, "croissance": 1}),
        "semaine": ("Un moment chaque semaine", {"momentum": 2}),
    }),
    Question("regret", "Ce que vous regretteriez le plus", {
        "trop_cher": ("Avoir payé trop cher", {"valeur": 1, "garp": 1}),
        "rate": ("Avoir raté une très belle croissance", {"croissance": 2}),
        "degrade": ("Avoir gardé une entreprise qui se dégrade", {"qualite": 2}),
        "hausse": ("Être resté à l'écart d'une hausse", {"momentum": 2}),
    }),
]
ORDRE = ["garp", "qualite", "croissance", "valeur", "momentum"]  # départage des ex aequo


@dataclass(frozen=True)
class Proposition:
    style: str
    points: dict[str, int]
    raisons: list[str]  # réponses qui ont le plus pesé vers le style proposé
    second: str | None  # style le plus proche, s'il est à un point ou moins


def proposer(reponses: dict[str, str]) -> Proposition:
    """Style proposé d'après les réponses (clé de question -> clé de réponse) ; les questions sans réponse ne
    comptent pas."""
    points = dict.fromkeys(STYLES, 0)
    for q in QUESTIONS:
        choix = q.reponses.get(reponses.get(q.cle, ""))
        if choix:
            for s, p in choix[1].items():
                points[s] += p
    classement = sorted(STYLES, key=lambda s: (-points[s], ORDRE.index(s)))
    style = classement[0]
    raisons = []
    for q in QUESTIONS:
        choix = q.reponses.get(reponses.get(q.cle, ""))
        if choix and choix[1].get(style, 0) >= 2:
            raisons.append(f"{q.titre} : « {choix[0]} »")
    second = classement[1] if points[classement[0]] - points[classement[1]] <= 1 else None
    return Proposition(style, points, raisons, second)


def explication(p: Proposition) -> str:
    """Le pourquoi du style proposé, en quelques phrases."""
    s = STYLES[p.style]
    texte = (f"**{s.libelle}** : {s.devise.lower().rstrip('.')}. Vous cherchez surtout {s.cherche}, et vous acceptez "
             f"{s.accepte}.")
    if p.raisons:
        texte += " Ce qui a pesé : " + " ; ".join(p.raisons) + "."
    if p.second:
        texte += (f" Le style **{STYLES[p.second].libelle}** arrive juste derrière : vos réponses hésitent entre les "
                  "deux.")
    return texte


# ------------------------------------------------------------------ profil enregistré

def profil() -> dict:
    """{"style", "propose", "reponses", "date"} ; vide si le questionnaire n'a jamais été fait."""
    p = lire_json(STYLE_JSON, {}) or {}
    return p if p.get("style") in STYLES else {}


def style_choisi() -> str:
    return profil().get("style", DEFAUT)


def enregistrer(style: str, reponses: dict[str, str] | None = None, propose: str | None = None,
                jour: date | None = None) -> None:
    if style not in STYLES:
        raise ValueError(f"style inconnu : {style}")
    ancien = lire_json(STYLE_JSON, {}) or {}
    ecrire_json(STYLE_JSON, {
        "style": style,
        "propose": propose if propose is not None else ancien.get("propose"),
        "reponses": reponses if reponses is not None else ancien.get("reponses", {}),
        "date": (jour or date.today()).isoformat(),
    }, indent=1)


# ------------------------------------------------------------------ notes et comparaison

def note(sc: pd.DataFrame, style: str) -> pd.Series:
    """Note de 0 à 100 de chaque valeur selon le style (rangs centiles dans tout le tableau donné)."""
    from .portfolio import NOTATIONS, note_construction

    return note_construction(sc, NOTATIONS[STYLES[style].notation][2])


def retenues(sc: pd.DataFrame, verdicts: pd.Series, part: float = 0.25,
             admis: tuple[str, ...] = ("Au bon prix", "Prix correct")) -> dict[str, list[str]]:
    """Par style, les actions qu'il retient : éligibles, dans la tête de classement du style (la `part` la mieux
    notée des éligibles) et à un prix admis par le verdict. Classées par note du style."""
    elig = sc[sc["statut"] == "Éligible"]
    out = {}
    for s in STYLES:
        n = note(elig, s).dropna().sort_values(ascending=False)
        tete = n.head(max(1, round(len(n) * part)))
        out[s] = [t for t in tete.index if verdicts.get(t) in admis]
    return out


def recoupements(choix: dict[str, list[str]]) -> pd.DataFrame:
    """Nombre d'actions communes à chaque paire de styles (la diagonale : celles du style lui-même)."""
    noms = list(choix)
    return pd.DataFrame([[len(set(choix[a]) & set(choix[b])) for b in noms] for a in noms],
                        index=[STYLES[s].libelle for s in noms], columns=[STYLES[s].libelle for s in noms])


def frequence(choix: dict[str, list[str]]) -> pd.DataFrame:
    """Chaque action retenue, avec le nombre de styles qui la retiennent et lesquels, des plus partagées aux
    propres à un seul style."""
    lignes: dict[str, list[str]] = {}
    for s, tickers in choix.items():
        for t in tickers:
            lignes.setdefault(t, []).append(STYLES[s].libelle)
    df = pd.DataFrame({"nb_styles": {t: len(v) for t, v in lignes.items()},
                       "styles": {t: ", ".join(v) for t, v in lignes.items()}})
    return df.sort_values("nb_styles", ascending=False, kind="stable") if not df.empty else df
