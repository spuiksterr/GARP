"""Grands investisseurs : portefeuilles 13F de gérants reconnus et transactions déclarées par des élus américains."""
import difflib
import math
import re
import unicodedata

import pandas as pd
import streamlit as st

from pf import autonome, congres, ui
from pf import investisseurs as inv

sc = ui.require_data()

st.title("Grands investisseurs")
st.caption("Ce que détiennent et achètent des investisseurs reconnus, d'après leurs déclarations officielles. "
           "Pour s'inspirer et trouver des idées à étudier, pas pour copier : ces déclarations arrivent avec des "
           "semaines de retard, sans le prix payé ni la raison de l'achat.")


# --------------------------------------------------------------------------- outils

def montant(v: float) -> str:
    """Montant en dollars, lisible : « 65,9 Md$ », « 577 M$ », « 15 k$ »."""
    if not (isinstance(v, (int, float)) and math.isfinite(v)):
        return "—"
    for seuil, unite, d in ((1e9, "Md$", 1), (1e6, "M$", 1), (1e3, "k$", 0)):
        if abs(v) >= seuil:
            return f"{ui.num(v / seuil, d)} {unite}"
    return f"{ui.num(v, 0)} $"


def trimestre(periode: str | None) -> str:
    if not periode:
        return "n.d."
    t = pd.Timestamp(periode)
    return f"T{t.quarter} {t.year}"


def _sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().upper()


FORMES = r"\b(SA|SE|AG|NV|PLC|INC|CORP|CO|LTD|LIMITED|HOLDINGS?|GROUP|THE|ORD|ADR|SPA|AB|ASA|A/S|CL|CLASS|COM)\b"


@st.cache_data(ttl=3600, show_spinner=False)
def noms_univers(version: float) -> dict[str, str]:
    """Nom normalisé -> ticker des valeurs de l'univers, pour relier les titres déclarés sans ticker (L'Oréal…)."""
    out = {}
    for t, nom in sc["nom"].items():
        cle = re.sub(r"\s+", " ", re.sub(FORMES, " ", re.sub(r"[^A-Z0-9 ]", " ", _sans_accents(nom)))).strip()
        if cle:
            out[cle] = t
    return out


def dans_univers(ticker, nom: str = "") -> str | None:
    """Ticker de l'univers correspondant à une ligne déclarée (par le ticker, sinon par le nom)."""
    if isinstance(ticker, str) and ticker in sc.index:
        return ticker
    if nom:
        cle = re.sub(r"\s+", " ", re.sub(FORMES, " ", re.sub(r"[^A-Z0-9 ]", " ", _sans_accents(nom)))).strip()
        noms = noms_univers(ui.data_version())
        proche = difflib.get_close_matches(cle, list(noms), n=1, cutoff=0.88)
        if proche:
            return noms[proche[0]]
    return None


def tableau_cliquable(df: pd.DataFrame, cle: str, colonne_univers: str = "univers", **kwargs) -> None:
    """Tableau dont un clic sur une ligne reliée à l'univers ouvre la fiche de la valeur."""
    compteur = f"{cle}_n"
    event = ui.tableau(df.drop(columns=[colonne_univers]), on_select="rerun", selection_mode="single-cell",
                       key=f"{cle}_{st.session_state.get(compteur, 0)}", hide_index=True, width="stretch", **kwargs)
    cellules = event.selection.cells if event and event.selection else []
    if cellules:
        ticker = df.iloc[cellules[0][0]][colonne_univers]
        st.session_state[compteur] = st.session_state.get(compteur, 0) + 1
        if isinstance(ticker, str) and ticker:
            st.session_state["fiche_ticker"] = ticker
            st.switch_page("vues/fiche.py")
        else:
            st.toast("Valeur hors de votre univers : pas de fiche.", icon=":material/info:")


@st.cache_data(ttl=600, show_spinner=False)
def _positions(cik: int, periode: str | None, version: str | None) -> pd.DataFrame:
    return inv.positions(cik, periode)


@st.cache_data(ttl=600, show_spinner=False)
def _mouvements(version: str | None) -> pd.DataFrame:
    return inv.mouvements()


@st.cache_data(ttl=600, show_spinner=False)
def _consensus(version: str | None) -> pd.DataFrame:
    return inv.consensus()


@st.cache_data(ttl=600, show_spinner=False)
def _transactions(version: str | None) -> pd.DataFrame:
    return congres.transactions()


# --------------------------------------------------------------------------- mise à jour

v13f, vcongres = inv.derniere_mise_a_jour(), congres.derniere_mise_a_jour()
c1, c2 = st.columns([3, 1], vertical_alignment="center")
c1.caption(f"Portefeuilles 13F lus le {pd.Timestamp(v13f):%d/%m/%Y à %H:%M}" if v13f else "Portefeuilles 13F jamais lus.")
c1.caption(f"Transactions des élus lues le {pd.Timestamp(vcongres):%d/%m/%Y à %H:%M}" if vcongres
           else "Transactions des élus jamais lues.")
if autonome.actif():
    # Version installée : les déclarations arrivent avec les données de la nuit (lues chaque nuit par GitHub).
    c2.caption("Relues chaque nuit par GitHub, avec les données de la nuit.")
elif c2.button("Mettre à jour", icon=":material/refresh:", width="stretch",
               help="Lit les nouvelles déclarations : gérants consultés au plus une fois par semaine, élus chaque "
                    "jour. Aussi fait par chaque mise à jour de la barre latérale."):
    with st.status("Lecture des déclarations…", expanded=True) as statut:
        ligne = st.empty()
        r1 = inv.mettre_a_jour(progress=lambda m: ligne.caption(m.strip()))
        r2 = congres.mettre_a_jour(progress=lambda m: ligne.caption(m.strip()))
        st.cache_data.clear()
        if r1.get("saute"):
            statut.update(label="Portefeuilles 13F non lus : la SEC exige une adresse de contact (contact_sec dans "
                                "profil/prive.json, voir « Méthode et routine »).", state="error")
            st.stop()
        statut.update(label=f"Fait : {r1.get('nouvelles', 0)} trimestres de gérants et {r2['nouveaux']} rapports d'élus lus.",
                      state="complete", expanded=False)
    st.rerun()

liste = inv.load_liste()
onglets = st.tabs(["Portefeuilles 13F", "Mouvements du trimestre", "Élus du Congrès", "Gérer les listes"])

# --------------------------------------------------------------------------- un portefeuille
with onglets[0]:
    if liste.empty:
        st.info("Aucun investisseur suivi : ajoutez-en dans l'onglet « Gérer les listes ».")
    else:
        c = st.columns([2, 1])
        cik = c[0].selectbox("Investisseur", list(liste.index),
                             format_func=lambda k: f"{liste.loc[k, 'investisseur']} · {liste.loc[k, 'societe']}",
                             key="inv_choix")
        dispo = inv.periodes(cik)
        if not dispo:
            st.info("Déclarations pas encore lues : cliquez sur « Mettre à jour ».")
        else:
            periode = c[1].selectbox("Trimestre", list(reversed(dispo)), format_func=trimestre, key=f"inv_periode_{cik}")
            p = _positions(cik, periode, v13f)
            st.caption(str(liste.loc[cik, "style"] or ""))
            detenues = p[p["valeur"] > 0]
            mv = p["mouvement"].value_counts() if "mouvement" in p.columns else pd.Series(dtype=int)
            m = st.columns(4)
            m[0].metric("Valeur déclarée", montant(p.attrs["total"]))
            m[1].metric("Lignes", len(detenues))
            m[2].metric("Trimestre", trimestre(p.attrs["periode"]), f"déposé le {pd.Timestamp(p.attrs['depose_le']):%d/%m/%Y}",
                        delta_color="off")
            m[3].metric("Entrées / sorties", f"{mv.get('Nouvelle', 0)} / {mv.get('Soldée', 0)}",
                        f"{mv.get('Renforcée', 0)} renforcées · {mv.get('Allégée', 0)} allégées" if p.attrs["precedente"]
                        else "premier trimestre lu", delta_color="off")

            g, d = st.columns([3, 2])
            with g.container(border=True):
                st.markdown("**Dix premières lignes**")
                top = detenues.head(10)
                fig = ui.hbar(pd.Series(top["poids"].values, index=[f"{n.title()} ({t})" if isinstance(t, str) else n.title()
                                                                    for n, t in zip(top["nom"], top["ticker"])]), fmt=".1%")
                fig.update_layout(margin=dict(r=60))  # place pour le pourcentage de la plus longue barre
                ui.show(fig, key=f"inv_top_{cik}")
            with d.container(border=True):
                st.markdown("**Ce qui a bougé ce trimestre**")
                if not p.attrs["precedente"]:
                    st.caption("Premier trimestre lu : pas de comparaison possible.")
                for libelle, couleur in (("Nouvelle", ui.GOOD), ("Renforcée", ui.GOOD), ("Allégée", ui.CRITICAL),
                                         ("Soldée", ui.CRITICAL)):
                    lignes = p[p["mouvement"] == libelle] if "mouvement" in p.columns else p.iloc[0:0]
                    if lignes.empty:
                        continue
                    def etiquette(n, tk, v):
                        details = [tk] if isinstance(tk, str) else []
                        if libelle in ("Renforcée", "Allégée") and math.isfinite(v):  # noqa: B023 (appelée dans ce tour)
                            details.append(ui.pct(v, 0, signe=True))
                        return f"{n} ({', '.join(details)})" if details else n

                    noms = ", ".join(etiquette(n, tk, v) for n, tk, v
                                     in zip(lignes["nom"].str.title(), lignes["ticker"], lignes["variation"]))
                    st.markdown(f'<span style="color:{couleur};font-weight:600">{libelle}s</span> : {noms}',
                                unsafe_allow_html=True)

            t = p.copy()
            t["univers"] = [dans_univers(tk, n) for tk, n in zip(t["ticker"], t["nom"])]
            t["score"] = t["univers"].map(lambda x: sc.loc[x, "score"] if isinstance(x, str) else None)
            t["nom"] = t["nom"].str.title()
            t["variation"] = [ui.pct(v, 0, signe=True) if m_ in ("Renforcée", "Allégée") and math.isfinite(v) else ""
                              for m_, v in zip(t["mouvement"], t["variation"])]
            t["depuis_txt"] = [("≤ " if debut_fenetre else "") + trimestre(x) for x, debut_fenetre
                               in zip(t["depuis"], t["depuis_debut_fenetre"])]
            show = ui.as_pct_cols(t[["nom", "ticker", "poids", "valeur", "actions", "mouvement", "variation", "depuis_txt",
                                     "score", "univers"]], ["poids"])
            show["valeur"] = show["valeur"] / 1e6
            show.insert(0, "rang", range(1, len(show) + 1))
            tableau_cliquable(show, f"inv_tab_{cik}", height=min(600, 35 * len(show) + 38), column_config={
                "rang": st.column_config.NumberColumn("N°", format="%d", width="small", pinned=True),
                "nom": st.column_config.TextColumn("Titre", pinned=True), "ticker": "Ticker",
                "poids": ui.PCT("Poids"), "valeur": st.column_config.NumberColumn("Valeur (M$)", format="%.1f"),
                "actions": st.column_config.NumberColumn("Actions", format="%.0f"),
                "mouvement": "Mouvement",
                "variation": st.column_config.TextColumn("Variation", help="Variation du nombre d'actions sur le trimestre"),
                "depuis_txt": st.column_config.TextColumn(
                    "Détenue depuis", help=f"Premier trimestre d'une détention continue. « ≤ » : déjà détenue au début "
                                           f"de l'historique lu ({trimestre(p.attrs['premiere'])})."),
                "score": ui.SCORE("Votre score", "Score de l'outil si la valeur est dans votre univers ; clic : sa fiche"),
            })
            st.caption("Formulaire 13F déposé à la SEC : positions longues en actions cotées aux États-Unis, à la date de "
                       "fin du trimestre, publiées jusqu'à 45 jours plus tard. Ni ventes à découvert, ni options, ni "
                       "liquidités, ni la plupart des valeurs cotées hors des États-Unis. Un mouvement compare le nombre "
                       "d'actions d'un trimestre à l'autre (une division d'actions apparaît comme un renforcement). "
                       "Cliquez sur une ligne de votre univers pour ouvrir sa fiche.")

# --------------------------------------------------------------------------- tous les mouvements
with onglets[1]:
    mvt = _mouvements(v13f)
    if mvt.empty:
        st.info("Aucun mouvement lu : cliquez sur « Mettre à jour ».")
    else:
        choix = st.segmented_control("Mouvements", ["Achats", "Ventes"], default="Achats", key="inv_mvt_sens",
                                     label_visibility="collapsed")
        types = ["Nouvelle", "Renforcée"] if choix != "Ventes" else ["Soldée", "Allégée"]
        m = mvt[mvt["mouvement"].isin(types)].copy()
        m["univers"] = [dans_univers(tk, n) for tk, n in zip(m["ticker"], m["nom"])]
        m["nom"] = m["nom"].str.title()
        m["trimestre"] = m["periode"].map(trimestre)
        m = m.sort_values(["poids", "valeur"], ascending=False)
        m["variation"] = [ui.pct(v, 0, signe=True) if m_ in ("Renforcée", "Allégée") and math.isfinite(v) else ""
                          for m_, v in zip(m["mouvement"], m["variation"])]
        show = ui.as_pct_cols(m[["investisseur", "trimestre", "mouvement", "nom", "ticker", "poids", "variation", "univers"]],
                              ["poids"])
        st.caption("Dernier trimestre déclaré par chaque investisseur, mouvements les plus lourds en poids d'abord "
                   "(poids après l'opération ; 0 pour une ligne soldée).")
        tableau_cliquable(show, "inv_mvt", height=min(560, 35 * len(show) + 38), column_config={
            "investisseur": st.column_config.TextColumn("Investisseur", pinned=True), "trimestre": "Trimestre",
            "mouvement": "Mouvement", "nom": "Titre", "ticker": "Ticker", "poids": ui.PCT("Poids"),
            "variation": st.column_config.TextColumn("Variation", help="Variation du nombre d'actions")})

        st.subheader("Les titres les plus partagés")
        cons = _consensus(v13f)
        cons = cons[cons["detenteurs"] >= 2].copy()
        cons["univers"] = [dans_univers(next((x for x in str(tk).split(", ") if x in sc.index), None), n)
                           for tk, n in zip(cons["ticker"], cons["nom"])]
        cons["score"] = cons["univers"].map(lambda x: sc.loc[x, "score"] if isinstance(x, str) else None)
        cons["nom"] = cons["nom"].str.title()
        show = ui.as_pct_cols(cons[["nom", "ticker", "detenteurs", "poids_moyen", "poids_max", "qui", "score", "univers"]],
                              ["poids_moyen", "poids_max"])
        tableau_cliquable(show, "inv_cons", height=min(500, 35 * len(show) + 38), column_config={
            "nom": st.column_config.TextColumn("Titre", pinned=True), "ticker": "Ticker",
            "detenteurs": st.column_config.NumberColumn("Investisseurs", format="%d"),
            "poids_moyen": ui.PCT("Poids moyen", "Poids moyen chez ceux qui le détiennent"), "poids_max": ui.PCT("Poids max."),
            "qui": st.column_config.TextColumn("Détenu par", width="large"),
            "score": ui.SCORE("Votre score")})
        st.caption("Titres détenus par au moins deux des investisseurs suivis à leur dernier trimestre déclaré.")

# --------------------------------------------------------------------------- élus
with onglets[2]:
    tx = _transactions(vcongres)
    if tx.empty:
        st.info("Aucune transaction lue : cliquez sur « Mettre à jour ».")
    else:
        f = st.columns([2, 1, 1, 1])
        elus = f[0].multiselect("Élus", sorted(tx["elu"].unique()), placeholder="Tous les élus suivis", key="cg_elus")
        sens = f[1].selectbox("Opérations", ["Achats et ventes", "Achats", "Ventes"], key="cg_sens")
        nature = f[2].selectbox("Titres", ["Actions et options", "Tout", "Options seulement"], key="cg_nature")
        duree = f[3].selectbox("Période", ["3 mois", "6 mois", "12 mois", "2 ans"], index=1, key="cg_duree")
        t = tx.copy()
        if elus:
            t = t[t["elu"].isin(elus)]
        if sens == "Achats":
            t = t[t["operation"] == "P"]
        elif sens == "Ventes":
            t = t[t["operation"].str.startswith("S")]
        if nature == "Actions et options":
            t = t[t["type"].isin(["ST", "OP"])]
        elif nature == "Options seulement":
            t = t[t["type"] == "OP"]
        mois = {"3 mois": 3, "6 mois": 6, "12 mois": 12, "2 ans": 24}[duree]
        t = t[pd.to_datetime(t["date"]) >= pd.Timestamp.today() - pd.DateOffset(months=mois)]

        m = st.columns(4)
        m[0].metric("Opérations", len(t))
        m[1].metric("Achats", int((t["operation"] == "P").sum()))
        m[2].metric("Ventes", int(t["operation"].str.startswith("S").sum()))
        m[3].metric("Délai de déclaration", f"{ui.num(t['retard_jours'].median(), 0)} jours" if len(t) else "—",
                    "médiane (limite légale : 45)", delta_color="off")

        g, d = st.columns([1, 1])
        with g.container(border=True):
            st.markdown("**Titres les plus achetés**")
            achats = t[(t["operation"] == "P") & t["ticker"].notna()]
            if achats.empty:
                st.caption("Aucun achat sur la période.")
            else:
                top = (achats.groupby("ticker").agg(achats=("elu", "size"), elus=("elu", "nunique"))
                       .sort_values(["elus", "achats"], ascending=False).head(10))
                ui.show(ui.hbar(top["achats"].astype(float), fmt=".0f"), key="cg_top_achats")
                st.caption("Nombre d'achats sur la période (actions et options).")
        with d.container(border=True):
            st.markdown("**Activité par élu**")
            par_elu = (t.assign(achat=t["operation"] == "P", vente=t["operation"].str.startswith("S"))
                       .groupby(["elu", "parti"]).agg(achats=("achat", "sum"), ventes=("vente", "sum"),
                                                      options=("type", lambda s: int((s == "OP").sum())))
                       .reset_index().sort_values("achats", ascending=False))
            ui.tableau(par_elu, hide_index=True, width="stretch", column_config={
                "elu": "Élu", "parti": "Parti", "achats": st.column_config.NumberColumn("Achats", format="%d"),
                "ventes": st.column_config.NumberColumn("Ventes", format="%d"),
                "options": st.column_config.NumberColumn("Options", format="%d")})

        t = t.head(1500).copy()
        t["univers"] = [dans_univers(tk) for tk in t["ticker"]]
        t["operation"] = t["operation"].map(congres.OPERATIONS).fillna(t["operation"])
        t["type"] = t["type"].map(congres.TYPES).fillna(t["type"])
        t["detenteur"] = t["detenteur"].map(congres.DETENTEURS).fillna(t["detenteur"])
        t["date"] = pd.to_datetime(t["date"])
        show = t[["date", "elu", "parti", "detenteur", "operation", "type", "actif", "ticker", "montant", "description",
                  "retard_jours", "lien", "univers"]]
        tableau_cliquable(show, "cg_tab", height=min(600, 35 * len(show) + 38), column_config={
            "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY", pinned=True),
            "elu": st.column_config.TextColumn("Élu", pinned=True), "parti": "Parti", "detenteur": "Détenteur",
            "operation": "Opération", "type": "Titre", "actif": st.column_config.TextColumn("Actif", width="medium"),
            "ticker": "Ticker", "montant": st.column_config.TextColumn("Montant", help="Tranche déclarée, en dollars"),
            "description": st.column_config.TextColumn("Détail", width="large"),
            "retard_jours": st.column_config.NumberColumn("Déclaré après", format="%d j"),
            "lien": st.column_config.LinkColumn("Rapport", display_text="PDF")})
        st.caption("Rapports de transactions des représentants (STOCK Act), publiés par le greffe de la Chambre : "
                   "opérations de l'élu, de son conjoint ou de ses enfants à charge, déclarées sous 45 jours (délai "
                   "souvent dépassé), montants par tranches. Les options d'achat (calls) amplifient un pari : une "
                   "petite somme y vaut beaucoup d'actions. Le Sénat n'est pas couvert. Cliquez sur une ligne de "
                   "votre univers pour ouvrir sa fiche. 1 500 lignes au plus : affinez les filtres.")
        scannes = congres.rapports_scannes()
        if len(scannes):
            with st.expander(f"Rapports scannés, non lisibles automatiquement ({len(scannes)})"):
                ui.tableau(scannes, hide_index=True, width="stretch", column_config={
                    "elu": "Élu", "depose_le": "Déposé le", "lien": st.column_config.LinkColumn("Rapport", display_text="PDF")})

# --------------------------------------------------------------------------- listes suivies
with onglets[3]:
    g, d = st.columns(2)
    with g:
        st.markdown("**Investisseurs suivis (formulaires 13F)**")
        ui.tableau(liste.reset_index(), hide_index=True, width="stretch", column_config={
            "cik": st.column_config.NumberColumn("CIK", format="%d"), "investisseur": "Investisseur",
            "societe": "Société", "style": st.column_config.TextColumn("Style", width="large")})
        with st.form("inv_ajout", clear_on_submit=True):
            st.markdown("Ajouter un investisseur")
            cik_txt = st.text_input("CIK SEC de sa société de gestion",
                                    help="Numéro d'identification SEC. Le trouver : sec.gov, « EDGAR Full Text Search » "
                                         "ou la recherche de sociétés, en filtrant sur le formulaire 13F-HR.")
            nom_txt = st.text_input("Nom à afficher (facultatif)")
            style_txt = st.text_input("Style (facultatif)")
            if st.form_submit_button("Vérifier et ajouter", icon=":material/person_add:"):
                try:
                    ident = inv.ajouter(int(re.sub(r"\D", "", cik_txt)), nom_txt, style_txt)
                    st.success(f"Ajouté : {ident['nom']} (dernière déclaration : {trimestre(ident['derniere'])}). "
                               "Cliquez sur « Mettre à jour » pour lire son portefeuille.")
                except Exception as exc:
                    st.error(f"Ajout impossible : {exc}")
        retrait = st.selectbox("Retirer un investisseur", list(liste.index), index=None, key="inv_retrait",
                               format_func=lambda k: f"{liste.loc[k, 'investisseur']} · {liste.loc[k, 'societe']}",
                               placeholder="Choisir…")
        if retrait is not None and st.button("Retirer", key="inv_retirer", icon=":material/delete:"):
            inv.retirer(retrait)
            st.cache_data.clear()
            st.rerun()
    with d:
        st.markdown("**Élus suivis (Chambre des représentants)**")
        elus_liste = congres.load_liste()
        ui.tableau(elus_liste, hide_index=True, width="stretch", column_config={
            "nom": "Nom", "prenom": "Prénom", "parti": "Parti", "circonscription": "Circonscription"})
        declarants = congres.elus_declarants()
        suivis = {congres.cle(r["nom"], r["circonscription"]) for _, r in elus_liste.iterrows()}
        if len(declarants):
            declarants = declarants[[congres.cle(n, c) not in suivis
                                     for n, c in zip(declarants["nom"], declarants["circonscription"])]]
            with st.form("cg_ajout", clear_on_submit=True):
                st.markdown("Ajouter un élu")
                k = st.selectbox("Élu ayant déclaré des transactions (les plus actifs d'abord)", list(declarants.index),
                                 format_func=lambda i: f"{declarants.loc[i, 'prenom']} {declarants.loc[i, 'nom']} "
                                                       f"({declarants.loc[i, 'circonscription']}, "
                                                       f"{declarants.loc[i, 'rapports']} rapports)")
                parti = st.selectbox("Parti", ["Démocrate", "Républicain", "Indépendant", ""])
                if st.form_submit_button("Ajouter", icon=":material/person_add:"):
                    x = declarants.loc[k]
                    congres.ajouter(x["nom"], x["prenom"], x["circonscription"], parti)
                    st.success(f"Ajouté : {x['prenom']} {x['nom']}. Cliquez sur « Mettre à jour » pour lire ses rapports.")
        retrait_elu = st.selectbox("Retirer un élu", list(elus_liste.index), index=None, key="cg_retrait",
                                   format_func=lambda i: f"{elus_liste.loc[i, 'prenom']} {elus_liste.loc[i, 'nom']}",
                                   placeholder="Choisir…")
        if retrait_elu is not None and st.button("Retirer", key="cg_retirer", icon=":material/delete:"):
            congres.retirer(elus_liste.loc[retrait_elu, "nom"], elus_liste.loc[retrait_elu, "circonscription"])
            st.cache_data.clear()
            st.rerun()
    st.caption("Listes enregistrées dans config/investisseurs.csv et config/elus.csv (modifiables aussi sous Excel, "
               "séparateur « ; »). Les déclarations lues restent en cache dans data/cache.")
