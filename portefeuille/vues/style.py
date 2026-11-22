"""Mon style d'investisseur : un questionnaire propose l'un des cinq styles (pf/styles.py), avec l'explication du
choix ; le style retenu classe « La bonne action au bon prix ». Second onglet : comparaison des styles (actions
retenues, actions communes, comportement passé par le backtest à date)."""
import pandas as pd
import streamlit as st

from pf import prix_achat as pa
from pf import styles as sty
from pf import ui
from pf.config import load_strategy

sc = ui.require_data()
strat = load_strategy()
names = ui.label_map(sc)
profil = sty.profil()

st.title("Mon style d'investisseur")
st.markdown(
    "La méthode qui marche le mieux est souvent celle que l'on arrive à tenir dans les mauvaises années. Huit questions "
    "proposent l'un des cinq styles ; vous pouvez en prendre un autre. Le style retenu **classe** les actions de « La "
    "bonne action au bon prix » ; le **prix d'achat** et le **verdict** ne changent pas : ils jugent le prix, pas "
    "l'entreprise.")

onglet_style, onglet_comparer = st.tabs(["Mon style", "Comparer les styles"])

# ------------------------------------------------------------------ questionnaire et choix
with onglet_style:
    if profil:
        s = sty.STYLES[profil["style"]]
        with st.container(border=True):
            st.markdown(f"#### Votre style : {s.libelle}")
            st.markdown(f"*{s.devise}* Vous cherchez {s.cherche} ; vous acceptez {s.accepte}. Ses mauvaises années : "
                        f"{s.souffre}.")
            propose = profil.get("propose")
            st.caption(f"Retenu le {pd.Timestamp(profil['date']):%d/%m/%Y}"
                       + (f", proposé par le questionnaire : {sty.STYLES[propose].libelle}."
                          if propose in sty.STYLES and propose != profil["style"] else "."))
    else:
        st.info("Pas encore de style retenu : « La bonne action au bon prix » classe pour l'instant selon le style "
                f"**{sty.STYLES[sty.DEFAUT].libelle}**, le nom même de l'outil.", icon=":material/person:")

    anciennes = profil.get("reponses", {}) if profil else {}
    with st.form("questionnaire_style"):
        st.markdown("##### Le questionnaire")
        reponses = {}
        for q in sty.QUESTIONS:
            cles = list(q.reponses)
            reponses[q.cle] = st.radio(
                q.titre, cles, format_func=lambda k, q=q: q.reponses[k][0], key=f"style_q_{q.cle}",
                index=cles.index(anciennes[q.cle]) if anciennes.get(q.cle) in cles else None)
        envoye = st.form_submit_button("Voir le style proposé", type="primary", icon=":material/psychology:")
    if envoye:
        manquantes = [q.titre for q in sty.QUESTIONS if not reponses.get(q.cle)]
        if manquantes:
            st.warning(f"{len(manquantes)} question(s) sans réponse : le style est proposé sur les autres.",
                       icon=":material/help:")
        st.session_state["style_proposition"] = (sty.proposer(reponses), {k: v for k, v in reponses.items() if v})

    if "style_proposition" in st.session_state:
        p, rep = st.session_state["style_proposition"]
        with st.container(border=True):
            st.markdown("##### Le style proposé")
            st.markdown(sty.explication(p))
            points = pd.Series({sty.STYLES[k].libelle: v for k, v in p.points.items()}).sort_values()
            st.bar_chart(points.rename("Points"), horizontal=True, height=200, color=ui.accent(),
                         x_label="Points du questionnaire", y_label="")
            choix = st.segmented_control("Style retenu", list(sty.STYLES), format_func=lambda k: sty.STYLES[k].libelle,
                                         default=p.style, key="style_retenu") or p.style
            if choix != p.style:
                st.caption(f"Vous préférez **{sty.STYLES[choix].libelle}** au style proposé : c'est votre choix. "
                           f"{sty.STYLES[choix].devise}")
            if st.button("Retenir ce style", type="primary", icon=":material/check:"):
                sty.enregistrer(choix, rep, p.style)
                st.session_state.pop("style_proposition", None)
                st.toast(f"Style retenu : {sty.STYLES[choix].libelle}.", icon=":material/check:")
                st.rerun()

    with st.expander("Choisir directement un style, sans le questionnaire"):
        direct = st.segmented_control("Style", list(sty.STYLES), format_func=lambda k: sty.STYLES[k].libelle,
                                      default=profil.get("style") if profil else None, key="style_direct")
        if st.button("Retenir", disabled=not direct, key="style_direct_ok"):
            sty.enregistrer(direct)
            st.rerun()

    st.markdown("##### Les cinq styles")
    for s in sty.STYLES.values():
        with st.expander(f"{s.libelle} : {s.devise}"):
            st.markdown(f"- **Ce qu'il cherche** : {s.cherche}.\n- **Ce qu'il accepte** : {s.accepte}.\n"
                        f"- **Ses mauvaises années** : {s.souffre}.")
    st.caption("Un questionnaire reste grossier, et aucun style ne garantit un résultat. G.A.R.P propose un style et "
               "l'explique ; le choix reste le vôtre. Outil d'aide à la décision, pas un conseil en investissement "
               "personnalisé.")

# ------------------------------------------------------------------ comparaison des styles
with onglet_comparer:
    regl = pa.reglages(strat)
    part = st.slider("Tête de classement de chaque style", 10, 50, 25, 5, format="%d %%", key="style_part",
                     help="Part des actions éligibles la mieux notée par le style, avant le prix.") / 100
    st.markdown(
        f"Un style **retient** une action quand elle passe les filtres de qualité, figure dans les {round(part * 100)} % "
        "les mieux notés du style et se trouve **au bon prix** ou à un **prix correct** (rendement exigé de "
        f"{ui.pct(regl['rendement'], 1)}, marge de {ui.pct(regl['marge'], 0)}, réglables dans « La bonne action au bon "
        "prix »).")
    elig = sc.index[sc["statut"] == "Éligible"]
    verdicts = pa.tableau(sc, dict.fromkeys(elig, "Univers"), strat["valorisation"], regl["rendement"],
                          regl["marge"])["verdict"]
    choix = sty.retenues(sc, verdicts, part)
    mon = sty.style_choisi()
    m = st.columns(len(sty.STYLES))
    for col, (k, tickers) in zip(m, choix.items()):
        col.metric(sty.STYLES[k].libelle + (" (vous)" if k == mon and profil else ""), len(tickers), border=True,
                   help=sty.STYLES[k].devise)

    c = st.columns([1.1, 1.4])
    with c[0]:
        st.markdown("##### Actions communes à deux styles")
        ui.tableau(sty.recoupements(choix), width="stretch")
        st.caption("Sur la diagonale, les actions retenues par le style lui-même ; ailleurs, celles que deux styles "
                   "retiennent tous les deux.")
    with c[1]:
        freq = sty.frequence(choix)
        st.markdown("##### Retenues par plusieurs styles")
        communes = freq[freq["nb_styles"] >= 2] if not freq.empty else freq
        if communes.empty:
            st.caption("Aucune action n'est retenue par deux styles à la fois.")
        else:
            vue = communes.assign(nom=[names.get(t, t) for t in communes.index])
            ui.tableau(vue[["nom", "nb_styles", "styles"]], width="stretch", height=min(400, 35 * len(vue) + 38),
                       column_config={"nom": "Valeur", "nb_styles": st.column_config.NumberColumn("Styles"),
                                      "styles": "Lesquels"})
    seul = st.segmented_control("Propres à un seul style", list(sty.STYLES), key="style_seul",
                                format_func=lambda k: sty.STYLES[k].libelle, default=mon)
    if seul and not freq.empty:
        propres = [t for t in choix[seul] if freq.loc[t, "nb_styles"] == 1]
        st.caption(f"{len(propres)} action(s) que seul le style {sty.STYLES[seul].libelle} retient"
                   + (" : " + " · ".join(names.get(t, t) for t in propres[:15]) if propres else ".")
                   + (" …" if len(propres) > 15 else ""))

    st.markdown("##### Leur comportement passé")
    st.markdown("\n".join(f"- **{s.libelle}** souffre {s.souffre}." for s in sty.STYLES.values()))
    if st.toggle("Rappel chiffré : backtest à date depuis 2012", key="style_backtest",
                 help="Les meilleures valeurs de chaque style, choisies chaque 1er avril avec les seuls comptes publiés "
                      "à cette date (sociétés américaines), gardées un an. Une trentaine de secondes la première fois."):
        from pf import backtest_pit as bp
        from pf.data import load_prices

        @st.cache_data(show_spinner=False)
        def _preparer(version):
            fin = set(sc.index[sc["financiere"].fillna(False).astype(bool)])
            return bp.preparer(list(sc.index), fin)

        @st.cache_data(show_spinner=False)
        def _simuler(version):
            methodes = {s.libelle: bp.METHODES[s.backtest] for s in sty.STYLES.values()}
            return bp.simuler(_preparer(version), methodes, n=20, debut=2012, reference=load_prices().get("SXR8.DE"))

        with st.spinner("Reconstitution des comptes à chaque date et simulation…"):
            res = _simuler(ui.data_version())
        if not res:
            st.info("Pas assez de comptes historiques sur ce poste pour simuler (comptes déposés à la SEC).",
                    icon=":material/info:")
        else:
            courbes = res["courbes"]
            univers_nom = "Toutes les valeurs testables (poids égaux)"
            stats = pd.DataFrame([{"style": nom, **bp.statistiques(courbes[nom], courbes[univers_nom]
                                                                   if nom != univers_nom else None)}
                                  for nom in courbes.columns]).set_index("style")
            ui.tableau(ui.as_pct_cols(stats, ["rendement_annualise", "ecart_annuel", "volatilite", "perte_maximale",
                                              "annees_gagnantes"]), width="stretch", column_config={
                "rendement_annualise": ui.PCT("Rendement annualisé"),
                "ecart_annuel": ui.PCT("Écart annuel", "Par rapport à toutes les valeurs testables à poids égaux"),
                "volatilite": ui.PCT("Volatilité"), "perte_maximale": ui.PCT("Perte maximale"),
                "annees_gagnantes": ui.PCT("Années gagnantes", "Part des années où le style bat toutes les valeurs "
                                                               "testables à poids égaux", 0),
            })
            st.warning("**Un passé reconstitué, pas une promesse.** Sociétés américaines seulement, indicateurs "
                       "simplifiés, et biais du survivant (l'univers est celui d'aujourd'hui), qui avantage surtout la "
                       "croissance et le momentum. Regardez les pertes maximales autant que les rendements : c'est là "
                       "qu'un style se tient, ou s'abandonne.", icon=":material/warning:")
        st.page_link("vues/backtest.py", label="Le détail dans la page Backtest", icon=":material/history:")
