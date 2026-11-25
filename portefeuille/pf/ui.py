"""Briques communes de l'interface Streamlit : thème des graphiques, données en cache, mise à jour."""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import autonome
from .config import (
    CAS_PARTICULIERS_CSV,
    METRICS_PARQUET,
    STRATEGIE_JSON,
    SURVEILLANCE_CSV,
    UNIVERS_CSV,
    load_model_portfolio,
    load_strategy,
    load_universe,
    read_csv_fr,
)
from .criteres import Critere, texte_valeur
from .data import currency_map, load_fx, load_prices, prices_in_eur
from .formats import eur, nombre, pct  # noqa: F401  (réexportés pour les pages)
from .formats import nombre as num  # noqa: F401  (réexporté pour les pages : ui.num)
from .metrics import load_metrics
from .regards import AJUSTEMENTS_CSV
from .scoring import build_screener, screener_prepare

# Palette de référence validée (ordre fixe, jamais recyclé) : les mêmes huit teintes, à des pas différents
# pour le fond clair et le fond sombre (validées en vision normale et en daltonisme sur chaque fond).
THEMES = {
    "light": {"series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
              "surface": "#fcfcfb", "infobulle": "#ffffff", "encre": "#0b0b0b", "neutre": "#f0efec",
              "accent": "#8a5a12"},
    "dark": {"series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
             "surface": "#1a1a19", "infobulle": "#242422", "encre": "#f0efec", "neutre": "#383835",
             "accent": "#c98b2e"},
}
# Ocre de la marque (docs/MARQUE.md) : le portefeuille et ses répartitions ; l'indice de comparaison en gris (GRIS).
# Ocre foncé en thème clair pour le contraste. Les graphiques à plusieurs séries gardent la palette validée.

# Verdicts de prix (pf/prix_achat.py) : vert au bon prix, ambre au prix correct, gris sinon ; jamais la couleur seule,
# le mot est toujours écrit.
COULEURS_VERDICT = {"Au bon prix": "green", "Prix correct": "orange", "À attendre": "gray", "Non évalué": "gray"}


def accent() -> str:
    return couleurs()["accent"]


def colonne_verdict(label: str = "Verdict", help: str | None = None):
    """Colonne de tableau où le verdict s'affiche en pastille colorée (valeurs : listes d'un seul verdict, voir
    pastilles_verdict)."""
    return st.column_config.MultiselectColumn(label, options=list(COULEURS_VERDICT),
                                             color=list(COULEURS_VERDICT.values()), help=help)


def pastilles_verdict(serie: pd.Series) -> pd.Series:
    """Verdicts prêts pour colonne_verdict : chaque valeur devient une liste d'un élément."""
    return serie.map(lambda v: [v] if isinstance(v, str) and v else [])


def badge_verdict(verdict: str) -> None:
    st.badge(verdict, color=COULEURS_VERDICT.get(verdict, "gray"))
# Trame des graphiques commune aux deux modes : gris moyen lisible sur fond clair comme sombre, et
# translucide pour les traits. Un graphique reste lisible même dessiné juste avant un changement de
# thème (Streamlit ne relance pas la page à ce moment-là).
GRIS = "#898781"
TRAIT, TRAIT_FORT = "rgba(137,135,129,0.22)", "rgba(137,135,129,0.45)"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"  # couleurs d'état, identiques dans les deux modes
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
# Dates des axes à la française, du jour à l'année selon l'étendue affichée (pas de « Oct 29 »).
JOUR_MS = 86_400_000
DATES = [dict(dtickrange=[None, 40 * JOUR_MS], value="%d/%m"), dict(dtickrange=[40 * JOUR_MS, 400 * JOUR_MS], value="%m/%Y"),
         dict(dtickrange=[400 * JOUR_MS, None], value="%Y")]


def mode() -> str:
    """« light » ou « dark » selon le thème affiché (réglage du système ou menu Réglages de Streamlit)."""
    try:
        t = st.context.theme.type
    except Exception:  # hors de l'application (tests, ligne de commande)
        t = None
    return t if t in THEMES else "light"


def couleurs() -> dict:
    return THEMES[mode()]


# --------------------------------------------------------------------------- graphiques

def style(fig: go.Figure, height: int = 360, legend: bool = True, hover: str = "closest") -> go.Figure:
    c = couleurs()
    fig.update_layout(
        height=height, font=dict(family=FONT, color=GRIS, size=13), colorway=c["series"],
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=16, t=40 if legend else 16, b=8), hovermode=hover,
        hoverlabel=dict(bgcolor=c["infobulle"], bordercolor=TRAIT_FORT, font=dict(color=c["encre"], family=FONT)),
        showlegend=legend, barcornerradius=4,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None, font=dict(color=GRIS)),
        separators=", ",
    )
    fig.update_xaxes(showgrid=False, linecolor=TRAIT_FORT, tickfont=dict(color=GRIS), title_font=dict(color=GRIS),
                     zeroline=False, ticks="", automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=TRAIT, gridwidth=1, linecolor=TRAIT_FORT, tickfont=dict(color=GRIS),
                     title_font=dict(color=GRIS), zeroline=False, ticks="", automargin=True)
    return fig


def _dates_fr(fig: go.Figure) -> None:
    fig.update_xaxes(tickformatstops=DATES, hoverformat="%d/%m/%Y")


def show(fig: go.Figure, key: str | None = None) -> None:
    """Affiche un graphique avec notre palette (theme=None : le thème Streamlit ne la remplace pas).

    `key` distingue deux graphiques identiques sur une même page (cartes vides d'une banque, par exemple).
    """
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False}, key=key)


def fr(v: float, fmt: str) -> str:
    """Format d3/Python vers la typographie française : 20.5% -> 20,5 %, 1,234.5 -> 1 234,5."""
    s = format(v, fmt)
    s = s.replace(",", " ").replace(".", ",")
    return s[:-1] + " %" if s.endswith("%") else s


def lines(df: pd.DataFrame, yfmt: str = ",.0f", log: bool = False, height: int = 380,
          colors: dict | None = None, ytitle: str | None = None) -> go.Figure:
    """Une courbe par colonne (2 px), infobulle unifiée sur l'axe des dates."""
    serie = couleurs()["series"]
    fig = go.Figure()
    for i, col in enumerate(df.columns):
        color = (colors or {}).get(col, serie[i % len(serie)])
        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=str(col), mode="lines",
                                 line=dict(width=2, color=color, shape="linear"),
                                 hovertemplate=f"%{{y:{yfmt}}}<extra>{col}</extra>"))
    style(fig, height, legend=len(df.columns) > 1, hover="x unified")
    fig.update_yaxes(type="log" if log else "linear", tickformat=yfmt, title=ytitle)
    if isinstance(df.index, pd.DatetimeIndex):
        _dates_fr(fig)
    return fig


def drawdown_chart(dd: pd.DataFrame, height: int = 260) -> go.Figure:
    serie = couleurs()["series"]
    fig = go.Figure()
    for i, col in enumerate(dd.columns):
        c = serie[i % len(serie)]
        fig.add_trace(go.Scatter(x=dd.index, y=dd[col], name=str(col), mode="lines", line=dict(width=2, color=c),
                                 fill="tozeroy", fillcolor=_alpha(c, 0.10),
                                 hovertemplate="%{y:.1%}<extra>" + str(col) + "</extra>"))
    style(fig, height, legend=len(dd.columns) > 1, hover="x unified")
    fig.update_yaxes(tickformat=".0%")
    _dates_fr(fig)
    return fig


def hbar(s: pd.Series, fmt: str = ".1%", height: int | None = None, color: str | None = None,
         highlight: dict | None = None) -> go.Figure:
    """Barres horizontales triées, une seule couleur (catégories nominales), valeur en bout de barre."""
    color = color or accent()
    s = s.dropna().sort_values()
    colors = [(highlight or {}).get(k, color) for k in s.index]
    fig = go.Figure(go.Bar(x=s.values, y=[str(i) for i in s.index], orientation="h", marker_color=colors,
                           text=[fr(v, fmt) for v in s.values], textposition="outside",
                           textfont=dict(color=GRIS), cliponaxis=False,
                           hovertemplate="%{y} : %{x:" + fmt + "}<extra></extra>"))
    style(fig, height or max(200, 26 * len(s) + 50), legend=False)
    fig.update_layout(bargap=0.35)
    # Place pour la valeur écrite au bout de la plus longue barre : sans elle, « 35,5 % » était coupé au bord.
    bas, haut = min(0.0, float(s.min())) if len(s) else 0.0, max(0.0, float(s.max())) if len(s) else 1.0
    marge = 0.22 * ((haut - bas) or 1.0)
    fig.update_xaxes(showgrid=False, showticklabels=False,
                     range=[bas - (marge if bas < 0 else 0.0), haut + (marge if haut > 0 else 0.0)])
    fig.update_yaxes(showgrid=False, tickfont=dict(color=GRIS))
    return fig


def grouped_bars(df: pd.DataFrame, fmt: str = ".1%", height: int = 340) -> go.Figure:
    serie = couleurs()["series"]
    fig = go.Figure()
    for i, col in enumerate(df.columns):
        fig.add_trace(go.Bar(x=[str(x) for x in df.index], y=df[col], name=str(col), marker_color=serie[i % len(serie)],
                             hovertemplate="%{x} : %{y:" + fmt + "}<extra>" + str(col) + "</extra>"))
    style(fig, height, legend=len(df.columns) > 1)
    fig.update_layout(bargap=0.35, bargroupgap=0.08)
    fig.update_xaxes(type="category")  # sinon « 2016 » est lu comme un nombre et un an sur deux disparaît
    fig.update_yaxes(tickformat=fmt.replace(".1", ".0"))
    return fig


def unite_montants(valeurs) -> tuple[float, str]:
    """Diviseur et suffixe lisibles pour une série de montants : milliards (Md), millions (M) ou unités."""
    m = pd.to_numeric(pd.Series(np.ravel(valeurs)), errors="coerce").abs().max()
    if not np.isfinite(m):
        return 1.0, ""
    return (1e9, " Md") if m >= 1e9 else (1e6, " M") if m >= 1e6 else (1.0, "")


def barres_historique(df: pd.DataFrame, fmt: str = ",.1f", montants: bool = True, height: int = 240) -> go.Figure:
    """Barres par exercice (une couleur par colonne, dans l'ordre de la palette), montants mis à l'échelle."""
    df = df.dropna(how="all")  # chaque série a sa profondeur d'historique : pas d'années vides en tête
    diviseur, suffixe = unite_montants(df.values) if montants else (1.0, "")
    serie = couleurs()["series"]
    fig = go.Figure()
    for i, col in enumerate(df.columns):
        fig.add_trace(go.Bar(x=list(df.index), y=df[col] / diviseur, name=str(col), marker_color=serie[i % len(serie)],
                             hovertemplate="%{x} : %{y:" + fmt + "}" + suffixe + "<extra>" + str(col) + "</extra>"))
    style(fig, height, legend=len(df.columns) > 1)
    fig.update_layout(bargap=0.3, bargroupgap=0.06, margin=dict(l=4, r=8, t=30 if len(df.columns) > 1 else 8, b=4))
    fig.update_xaxes(type="category", tickangle=-45, tickfont=dict(size=11))
    # « ~ » retire les zéros inutiles : 1,5 Md et 2 Md, sans arrondir 1,5 à « 2 » (graduations en double).
    fig.update_yaxes(tickformat=",.1~f" if montants else fmt, ticksuffix=suffixe)
    return fig


def courbe_historique(s: pd.Series, fmt: str = ".0%", height: int = 240) -> go.Figure:
    """Courbe à points par exercice, pour un ratio (marges, ROCE)."""
    s = s.loc[s.first_valid_index():] if s.notna().any() else s
    fig = go.Figure(go.Scatter(x=list(s.index), y=s.values, mode="lines+markers", connectgaps=False,
                               line=dict(width=2, color=couleurs()["series"][0]),
                               marker=dict(size=7, line=dict(width=1.5, color=couleurs()["surface"])),
                               hovertemplate="%{x} : %{y:" + fmt + "}<extra></extra>"))
    style(fig, height, legend=False)
    fig.update_layout(margin=dict(l=4, r=8, t=8, b=4))
    fig.update_xaxes(type="category", tickangle=-45, tickfont=dict(size=11))
    fig.update_yaxes(tickformat=fmt, rangemode="tozero")
    return fig


def badges_croissance(c5: float, c10: float) -> str:
    """Pastilles « 5 ans / 10 ans » de croissance annuelle : vertes si elle est positive, rouges sinon."""
    def badge(label, v):
        if not np.isfinite(v):
            return f'<span style="padding:2px 8px;border-radius:6px;{SECONDAIRE};background:{TRAIT}">{label} : n.d.</span>'
        c = GOOD if v >= 0 else CRITICAL
        return (f'<span style="padding:2px 8px;border-radius:6px;background:{_alpha(c, 0.14)};color:{c};font-weight:600">'
                f'{label} : {pct(v, 2, signe=True)}</span>')
    return (f'<div style="font-size:0.8rem;display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:center;'
            f'white-space:nowrap"><span style="{SECONDAIRE}">Croissance / an</span>{badge("5 ans", c5)}{badge("10 ans", c10)}</div>')


def camembert(parts: dict[str, float], height: int = 300) -> go.Figure:
    """Répartition en camembert : parts dans l'ordre de la palette, « Autres » en gris, pourcentages dans les parts."""
    serie = couleurs()["series"]
    noms = list(parts)
    teintes = [GRIS if n == "Autres" else serie[i % len(serie)] for i, n in enumerate(noms)]
    fig = go.Figure(go.Pie(labels=noms, values=list(parts.values()), sort=False, direction="clockwise",
                           marker=dict(colors=teintes, line=dict(color=couleurs()["surface"], width=2)),
                           textinfo="percent", textposition="inside", insidetextfont=dict(color="#ffffff", size=13),
                           hovertemplate="%{label} : %{percent}<extra></extra>"))
    style(fig, height, legend=True)
    # Légende sous le camembert : à droite, un libellé long (« Contract Manufacturing… ») l'écraserait.
    fig.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5, font=dict(color=GRIS)),
                      margin=dict(l=8, r=8, t=8, b=8), uniformtext=dict(minsize=10, mode="hide"))
    return fig


def corr_heatmap(corr: pd.DataFrame, labels: dict | None = None, height: int = 560) -> go.Figure:
    names = [(labels or {}).get(c, c) for c in corr.columns]
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=names, y=names, zmin=-1, zmax=1,
        colorscale=[[0, "#184f95"], [0.5, couleurs()["neutre"]], [1, "#c23a3a"]],
        hovertemplate="%{y} / %{x} : %{z:.2f}<extra></extra>", colorbar=dict(thickness=10, tickformat=".1f"),
        xgap=2, ygap=2))
    style(fig, height, legend=False)
    fig.update_xaxes(tickangle=-45, tickfont=dict(size=11))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=11))
    return fig


def _alpha(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


# --------------------------------------------------------------------------- blocs HTML
# Fonds et bordures translucides, texte hérité du thème : rendu juste en clair comme en sombre,
# y compris juste après un changement de thème (le navigateur applique le CSS sans relancer la page).

CARTES = {True: (_alpha(GOOD, 0.13), _alpha(GOOD, 0.38), "✅"), False: (_alpha(CRITICAL, 0.12), _alpha(CRITICAL, 0.38), "❌"),
          None: ("rgba(137,135,129,0.10)", "rgba(137,135,129,0.30)", f'<span style="color:{GRIS}">⊘</span>')}
SECONDAIRE = "opacity:0.72"


def carte_critere(c: Critere, seuil: str) -> str:
    """Carte d'un critère : fond vert s'il est rempli, rouge sinon, gris s'il n'est pas évalué."""
    fond, bord, icone = CARTES[c.rempli]
    valeur = "—" if c.note.startswith("Sans objet") else texte_valeur(c)
    note = f'<div style="font-size:0.8rem;{SECONDAIRE};margin-top:2px">{html.escape(c.note)}</div>' if c.note else ""
    return (
        f'<div style="background:{fond};border:1px solid {bord};border-radius:12px;padding:14px 18px;'
        f'min-height:132px;margin-bottom:12px">'
        f'<div style="font-size:1.05rem;font-weight:600;margin-bottom:8px">{icone}&nbsp; {html.escape(c.titre)}</div>'
        f'<div style="line-height:1.2"><span style="font-size:1.9rem;font-weight:800">{valeur}</span>'
        f'<span style="font-size:0.85rem;margin-left:6px">{html.escape(c.periode)}</span></div>'
        f'{note}<div style="font-size:0.8rem;{SECONDAIRE};margin-top:6px">{html.escape(seuil)}</div></div>'
    )


def bloc_chiffres(titre: str, lignes: list[tuple[str, str]], fort: set[str] | None = None) -> str:
    """Bloc titré de lignes « libellé … valeur », valeurs alignées à droite et jamais coupées."""
    rangs = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:12px;padding:3px 0;'
        f'border-top:1px solid {TRAIT}{";font-weight:600" if lab in (fort or set()) else ""}">'
        f'<span style="{"" if lab in (fort or set()) else SECONDAIRE}">{html.escape(lab)}</span>'
        f'<span style="white-space:nowrap;font-variant-numeric:tabular-nums">{html.escape(val)}</span></div>'
        for lab, val in lignes)
    return (f'<div style="border:1px solid {TRAIT_FORT};border-radius:10px;padding:12px 16px;margin-bottom:12px">'
            f'<div style="font-weight:600;margin-bottom:6px">{html.escape(titre)}</div>{rangs}</div>')


def carte_prix_cible(prix: float, cours: float, devise: str, prix_eur: float | None = None) -> str:
    """Encadré « Prix cible estimé » : le prix, son écart au cours, et l'équivalent en euros."""
    if not np.isfinite(prix):
        return (f'<div style="border:1px solid {TRAIT_FORT};border-radius:10px;padding:12px 16px">'
                f'<div style="font-size:0.8rem;{SECONDAIRE}">Prix cible estimé</div>'
                f'<div style="font-size:1.6rem;font-weight:800">n.d.</div>'
                f'<div style="font-size:0.8rem;{SECONDAIRE}">Résultat des 12 derniers mois négatif ou nul : '
                f'ce ratio ne permet pas de fixer un prix.</div></div>')
    e = prix / cours - 1
    if abs(e) < 0.0005:
        sens, teinte = "Égal au cours actuel : l'action se paie exactement votre cible", GRIS
    elif e > 0:
        sens, teinte = f"{pct(e, 1)} au-dessus du cours actuel : l'action se paie déjà moins que votre cible", GOOD
    else:
        sens, teinte = f"{pct(-e, 1)} sous le cours actuel : il faudrait une baisse de {pct(-e, 1)}", GRIS
    euros = (f' <span style="font-size:0.9rem;font-weight:400;{SECONDAIRE}">≈ {eur(prix_eur, 2)}</span>'
             if prix_eur is not None and np.isfinite(prix_eur) and devise != "EUR" else "")
    return (f'<div style="border:1px solid {TRAIT_FORT};border-radius:10px;padding:12px 16px">'
            f'<div style="font-size:0.8rem;{SECONDAIRE}">Prix cible estimé</div>'
            f'<div style="font-size:1.6rem;font-weight:800">{nombre(prix, 2)} {html.escape(devise)}{euros}</div>'
            f'<div style="font-size:0.8rem;color:{teinte};font-weight:600">{sens}</div>'
            f'<div style="font-size:0.75rem;{SECONDAIRE}">Cours actuel {nombre(cours, 2)} {html.escape(devise)}</div></div>')


def lignes_medianes(actuel: float, medianes: list[tuple[str, float]]) -> str:
    """Tableau « Période | Médiane | Écart » : sous-évalué en vert, surévalué en rouge."""
    def ligne(cellules, entete=False):
        style_cellule = "font-weight:600" if entete else ""
        return (f'<div style="display:grid;grid-template-columns:1fr 1fr 1.6fr;gap:8px;padding:5px 0;'
                f'border-top:1px solid {TRAIT};{style_cellule}">' + "".join(f"<span>{c}</span>" for c in cellules) + "</div>")
    lignes = [ligne(["Période", "Médiane", "Écart"], entete=True)]
    for periode, med in medianes:
        if not (np.isfinite(med) and np.isfinite(actuel) and med > 0):
            lignes.append(ligne([periode, "n.d.", f'<span style="{SECONDAIRE}">historique insuffisant</span>']))
            continue
        e = actuel / med - 1
        teinte, mot = (GOOD, "sous-évalué") if e < 0 else (CRITICAL, "surévalué")
        lignes.append(ligne([periode, nombre(med, 2),
                             f'<span style="color:{teinte};font-weight:600">{pct(abs(e), 1)} {mot}</span>']))
    return f'<div style="font-size:0.9rem;margin-top:4px">{"".join(lignes)}</div>'


# --------------------------------------------------------------------------- tableaux

def as_pct_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Multiplie par 100 les colonnes de ratios pour un affichage « 12,3 » sous un en-tête en %."""
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce") * 100
    return out


PCT = lambda label, help=None, d=1: st.column_config.NumberColumn(label, format=f"%.{d}f %%", help=help)  # noqa: E731
SCORE = lambda label, help=None: st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f", help=help)  # noqa: E731


def _a_la_francaise(df: pd.DataFrame, column_config: dict | None,
                    formats: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Remplace les formats printf (« 12.3 », « 1234.5 ») par les formats du navigateur (« 12,3 », « 1 234,5 »).

    Les pages gardent leurs formats printf, qui servent de consigne : nombre de décimales, et « %% » pour
    une colonne en pourcentage (multipliée par 100 par as_pct_cols), affichée en « percent ».
    """
    if not column_config:
        return df, column_config or {}
    out, cfg = df.copy(), dict(column_config)
    for col, c in column_config.items():
        tc = c.get("type_config") if isinstance(c, dict) else None
        fmt = (tc or {}).get("format")
        if (tc or {}).get("type") != "number" or not isinstance(fmt, str) or not fmt.startswith("%") or col not in out.columns:
            continue
        valeurs = pd.to_numeric(out[col], errors="coerce")
        precision = re.match(r"%[^a-zA-Z%]*?\.(\d+)", fmt)  # « %.1f » ; un point dans le texte (« %d ex. ») n'en est pas
        decimales = int(precision.group(1)) if precision else 0
        if fmt.endswith("%%"):
            out[col] = (valeurs / 100).round(decimales + 2) + 0.0  # + 0.0 : pas de « -0 % » après l'arrondi
            nouveau = "percent"
            if formats is not None:
                formats[col] = lambda v, d=decimales: pct(v, d)
        elif fmt.endswith("g"):
            out[col], nouveau = valeurs, "localized"
        else:
            out[col], nouveau = valeurs.round(decimales) + 0.0, "localized"
            if formats is not None:
                formats[col] = lambda v, d=decimales: nombre(v, d)
        cfg[col] = {**c, "type_config": {**tc, "format": nouveau}}
    return out, cfg


def tableau(data: pd.DataFrame, column_config: dict | None = None, **kwargs):
    """st.dataframe avec des nombres à la française (virgule décimale, espace des milliers, « 12,3 % »)."""
    formats: dict = {}
    data, column_config = _a_la_francaise(data, column_config, formats)
    if isinstance(data, pd.DataFrame):
        data = data.copy()
        if data.index.name == "ticker":
            data = data.rename_axis("Ticker")
        # Texte absent (fonds sans moat ni critères) : un tiret plutôt que « None ».
        texte = [c for c in data.columns if data[c].dtype == object or pd.api.types.is_string_dtype(data[c])]
        data[texte] = data[texte].astype(object).where(data[texte].notna(), "—")
        # Nombre absent : Streamlit écrit « None » dans toute cellule vide, quel que soit le format. La cellule reçoit
        # donc moins l'infini, qu'un Styler affiche « — » (les autres nombres à la française) : la colonne reste
        # numérique et triable, les valeurs absentes en bout de tri. Le Styler ne vaut que sans format de colonne.
        a_trous = {c: f for c, f in formats.items() if c in data.columns and data[c].isna().any()}
        if a_trous and data.index.is_unique and data.columns.is_unique:
            for c in a_trous:
                cfg = column_config[c]
                column_config[c] = {**cfg, "type_config": {**cfg["type_config"], "format": None}}
            for c in a_trous:
                data[c] = pd.to_numeric(data[c], errors="coerce").fillna(-np.inf)
            data = data.style.format({c: (lambda v, f=f: f(v) if np.isfinite(v) else "—") for c, f in a_trous.items()})
    return st.dataframe(data, column_config=column_config, **kwargs)


# --------------------------------------------------------------------------- navigation et watchlist

def cle_tableau(cle: str) -> str:
    """Clé versionnée d'un tableau cliquable (renouvelée par `fiche_au_clic` pour effacer la sélection au retour)."""
    return f"{cle}_{st.session_state.get(cle, 0)}"


def fiche_au_clic(table: pd.DataFrame, event, cle: str, lignes: bool = True) -> None:
    """Ouvre la fiche de la valeur cliquée dans `table` (cellule, ou case de la ligne si `lignes`).

    Le compteur `cle` renouvelle le tableau : au retour sur la page, la sélection est vide et ne renvoie
    pas aussitôt vers la fiche. Il faut donc créer le tableau avec la clé `cle_tableau(cle)`.
    """
    sel = event.selection if event else None
    if not sel:
        return
    positions = [c[0] for c in sel.cells] + (list(sel.rows) if lignes else [])
    if positions and positions[0] < len(table):
        ticker = table.index[positions[0]]
        st.session_state[cle] = st.session_state.get(cle, 0) + 1
        if isinstance(ticker, str) and ticker:
            st.session_state["fiche_ticker"] = ticker
            st.switch_page("vues/fiche.py")


def ajouter_watchlist(tickers) -> list[str]:
    """Ajoute des valeurs à la watchlist, au dernier cours connu ; renvoie celles qui n'y étaient pas."""
    from . import watchlist as wl  # import local : la watchlist ne sert qu'à quelques pages

    nouvelles = [t for t in tickers if not wl.contient(t)]
    for t in nouvelles:
        cours = local_prices(t)
        wl.ajouter(t, float(cours.iloc[-1]) if not cours.empty else None)
    return nouvelles


# --------------------------------------------------------------------------- données en cache

def data_version(paths: list[Path] | None = None) -> float:
    """Dernière modification des données, des réglages et du code de calcul."""
    paths = paths or [METRICS_PARQUET, UNIVERS_CSV, STRATEGIE_JSON, AJUSTEMENTS_CSV, CAS_PARTICULIERS_CSV,
                      *Path(__file__).parent.glob("*.py")]
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)


def screener_vide_cache() -> None:
    """Après un changement des poids de la note GARP : le screener est reclassé au prochain affichage."""
    _screener.clear()


def screener() -> pd.DataFrame:
    # La version entre dans la clé du cache : un changement ne laisse jamais un ancien tableau en mémoire.
    return _screener(data_version())


@st.cache_data(ttl=3600, show_spinner=False)
def _screener(version: float) -> pd.DataFrame:
    strat = load_strategy()
    pret = screener_prepare(strat)  # calculé par le flux de la nuit, s'il correspond aux données du poste
    if pret is not None:
        return pret
    if load_metrics().empty:
        return pd.DataFrame()
    return build_screener(strategy=strat)


@st.cache_data(ttl=3600, show_spinner=False)
def eur_prices(tickers: tuple) -> pd.DataFrame:
    prices = load_prices()
    cols = [t for t in tickers if t in prices.columns]
    if not cols:
        return pd.DataFrame()
    return prices_in_eur(prices[cols], currency_map(cols), load_fx()).ffill(limit=5)


@st.cache_data(ttl=3600, show_spinner=False)
def local_prices(ticker: str) -> pd.Series:
    prices = load_prices()
    return prices[ticker].dropna() if ticker in prices.columns else pd.Series(dtype=float)


def model() -> pd.DataFrame:
    return load_model_portfolio()


def surveillance() -> pd.DataFrame:
    path = SURVEILLANCE_CSV
    return read_csv_fr(path).set_index("ticker") if path.exists() else pd.DataFrame()


def universe() -> pd.DataFrame:
    return load_universe()


def data_date() -> str | None:
    prices = load_prices()
    return None if prices.empty else prices.index.max().strftime("%d/%m/%Y")


def run_update(full: bool = False, rapide: bool = False) -> dict:
    from .maj import bilan, tout_mettre_a_jour  # import différé : la version installée ne met pas à jour

    with st.status("Mise à jour rapide…" if rapide else "Mise à jour des données…", expanded=True) as status:
        line = st.empty()
        res, sc = tout_mettre_a_jour(complet=full, rapide=rapide, progress=lambda msg: line.caption(msg.strip()))
        st.cache_data.clear()
        status.update(label=f"Données à jour au {res['derniere_date']}", state="complete", expanded=False)
    st.session_state["bilan_maj"] = bilan(res, sc)
    return res


def _ouvrir_recherche() -> None:
    """Rappel de la recherche globale : la fiche s'ouvre au passage suivant (pas de changement de page ici)."""
    choix = st.session_state.get("recherche_globale")
    if choix:
        st.session_state["fiche_ticker"] = choix
        st.session_state["recherche_ouvrir"] = True
        st.session_state["recherche_globale"] = None


def sidebar() -> None:
    with st.sidebar:
        sc = screener()
        if not sc.empty:
            noms = sc["nom"].astype(str)
            st.selectbox("Rechercher une valeur", sorted(sc.index, key=lambda t: noms[t].lower()), index=None,
                         key="recherche_globale", on_change=_ouvrir_recherche, placeholder="Nom ou ticker…",
                         format_func=lambda t: f"{noms[t]} ({t})", label_visibility="collapsed")
            if st.session_state.pop("recherche_ouvrir", False):
                st.switch_page("vues/fiche.py")
        d = data_date()
        st.caption(f"Cours au {d}" if d else "Aucune donnée téléchargée")
        if autonome.actif():
            _barre_autonome()
            st.caption("Outil d'aide à la décision, pas un conseil en investissement personnalisé.")
            return
        from .maj import jours_depuis_complete

        for ligne in st.session_state.get("bilan_maj", []):
            st.caption(ligne)
        jours = jours_depuis_complete()
        if st.button("Mise à jour rapide", icon=":material/bolt:", width="stretch", type="primary",
                     help="Chaque jour : cours, changes, grands investisseurs et élus, puis tous les indicateurs et "
                          "scores. Fondamentaux et comptes déposés inchangés. Quelques minutes."):
            run_update(rapide=True)
            st.rerun()
        if st.button("Mise à jour complète", icon=":material/sync:", width="stretch",
                     help="Chaque semaine : en plus, un quart des fiches de fondamentaux par roulement (vos lignes d'abord) et "
                          "les comptes SEC et rapports européens à renouveler. Environ 20 minutes."):
            run_update()
            st.rerun()
        if jours is None:
            st.caption("Aucune mise à jour complète enregistrée.")
        elif jours >= 7:
            st.caption(f":orange[Dernière mise à jour complète il y a {int(jours)} jours : à relancer.]")
        else:
            st.caption(f"Dernière mise à jour complète il y a {int(jours)} jour{'s' if int(jours) > 1 else ''}.")
        st.caption("Outil d'aide à la décision, pas un conseil en investissement personnalisé.")


def telecharger_nuit(jeton: str | None) -> bool:
    """Version installée : télécharge et installe les données publiées la nuit sur GitHub."""
    with st.status("Téléchargement des données de la nuit…", expanded=True) as status:
        barre = st.progress(0.0)
        try:
            autonome.telecharger_donnees(jeton, progression=barre.progress)
        except (autonome.ErreurGitHub, ValueError, OSError) as e:
            status.update(label=f"Téléchargement impossible : {e}", state="error")
            return False
        st.cache_data.clear()
        status.update(label="Données de la nuit installées", state="complete", expanded=False)
    return True


@st.dialog("Jeton GitHub (facultatif)")
def _dialogue_jeton() -> None:
    st.markdown(
        "Les données arrivent chaque nuit du dépôt public du projet sur GitHub, sans jeton. Un jeton en "
        "**lecture seule** n'est utile que si GitHub limite les requêtes anonymes (60 par heure) :\n\n"
        f"1. [créer le jeton sur GitHub]({autonome.URL_CREATION_JETON}) (formulaire pré-rempli : choisissez "
        "« Public repositories », puis « Generate token ») ;\n"
        "2. copiez-le et collez-le ci-dessous.")
    valeur = st.text_input("Jeton GitHub", type="password", placeholder="github_pat_…")
    if st.button("Enregistrer", type="primary", disabled=not valeur.strip()):
        try:
            autonome.verifier_jeton(valeur.strip())
        except autonome.ErreurGitHub as e:
            st.error(str(e))
            return
        autonome.enregistrer_jeton(valeur)
        st.session_state.pop("autonome_verifie", None)
        st.rerun()
    st.caption("Le jeton est chiffré par Windows pour votre session et n'est envoyé qu'à GitHub.")
    if autonome.jeton() and st.button("Retirer le jeton", type="tertiary"):
        autonome.oublier_jeton()
        st.session_state.pop("autonome_verifie", None)
        st.rerun()


def _date_archive(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y à %Hh%M")
    except ValueError:
        return iso


@st.cache_resource
def _tache_nuit() -> autonome.TacheNuit:
    """Une seule tâche de fond par processus : partagée entre les ouvertures de page."""
    return autonome.TacheNuit()


def _suivi_nuit(tache: autonome.TacheNuit) -> None:
    """État de la recherche des données de la nuit ; bouton pour charger celles qui ont été téléchargées."""
    if tache.statut == "verification":
        st.caption("Recherche de nouvelles données…")
    elif tache.statut == "telechargement":
        st.progress(tache.progression, text="Téléchargement des données de la nuit…")
    elif tache.statut == "erreur":
        st.caption(f":orange[{tache.message}]")
    elif tache.statut == "pret" and tache.archive:
        st.info(f"Nouvelles données de la nuit, publiées le {_date_archive(tache.archive['date'])}.",
                icon=":material/download_done:")
        if st.button("Charger les nouvelles données", type="primary", icon=":material/refresh:", width="stretch"):
            with st.spinner("Installation des données…"):
                try:
                    autonome.installer_en_attente(tache)
                except (ValueError, OSError) as e:
                    st.error(f"Installation impossible : {e}")
                    return
            st.cache_data.clear()
            st.rerun(scope="app")
    # Nouvelle version du logiciel, trouvée par la même recherche de fond.
    installee, derniere = autonome.version_installee(), tache.version
    jeton = autonome.jeton()
    if installee and derniere and derniere["numero"] > installee:
        if st.button(f"Installer la version {derniere['numero']}", icon=":material/system_update:", width="stretch"):
            with st.spinner("Téléchargement de la nouvelle version…"):
                try:
                    autonome.installer_version(jeton, derniere)
                    st.info("L'installateur s'ouvre : il fermera G.A.R.P, puis le rouvrira.")
                except autonome.ErreurGitHub as e:
                    st.error(str(e))


def _barre_autonome() -> None:
    """Barre latérale de la version installée : données de la nuit et nouvelles versions, depuis GitHub (dépôt
    public : sans jeton, sauf si l'utilisateur en a ajouté un)."""
    jeton = autonome.jeton()
    tache = _tache_nuit()
    etat = autonome.etat_local()
    if "autonome_verifie" not in st.session_state:  # une fois par ouverture : nouvelles données, nouvelle version
        st.session_state["autonome_verifie"] = True
        if not etat.get("archive"):
            # Premier lancement : rien à montrer en attendant, le téléchargement se fait sous les yeux.
            try:
                if not autonome.donnees_a_jour(jeton)[0] and telecharger_nuit(jeton):
                    st.rerun()
            except autonome.ErreurGitHub as e:
                st.caption(f":orange[{e}]")
        else:
            autonome.chercher_en_arriere_plan(tache, jeton)
    if etat.get("archive"):
        st.caption(f"Données de la nuit publiées le {_date_archive(etat['archive'])}.")
    # Suivi de la tâche : rafraîchi toutes les 2 secondes tant qu'elle cherche ou télécharge.
    st.fragment(run_every=2 if tache.en_cours() else None)(_suivi_nuit)(tache)
    if tache.statut != "pret" and st.button(
            "Données de la nuit", icon=":material/download:", width="stretch", disabled=tache.en_cours(),
            help="Cherche les dernières données publiées sur GitHub (cours, fondamentaux, indicateurs, scores) et les "
                 "télécharge en arrière-plan. Fait aussi à chaque ouverture de G.A.R.P."):
        autonome.chercher_en_arriere_plan(tache, jeton)
        st.rerun()
    if installee := autonome.version_installee():
        st.caption(f"G.A.R.P version {installee}.")
    if st.button("Jeton GitHub (facultatif)", icon=":material/key:", type="tertiary"):
        _dialogue_jeton()


def require_data() -> pd.DataFrame:
    sc = screener()
    if sc.empty and autonome.actif():
        st.info("Aucune donnée pour l'instant : les données de la nuit se téléchargent depuis GitHub, en une "
                "minute environ.", icon=":material/download:")
        jeton = autonome.jeton()
        if st.button("Télécharger les données de la nuit", type="primary", icon=":material/download:"):
            if telecharger_nuit(jeton):
                st.rerun()
        st.stop()
    if sc.empty:
        st.info("Aucune donnée pour l'instant. Lancez la première mise à jour (environ une heure).")
        if st.button("Télécharger les données", type="primary", icon=":material/download:"):
            run_update()
            st.rerun()
        st.stop()
    return sc


def label_map(sc: pd.DataFrame) -> dict:
    return {t: f"{r['nom']} ({t})" for t, r in sc.iterrows()}


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d")
