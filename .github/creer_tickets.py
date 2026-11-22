"""Crée sur GitHub les tickets de FEUILLE_DE_ROUTE.md (ticket G-06).

Prérequis : l'outil GitHub `gh`, installé et connecté par le propriétaire
(`winget install GitHub.cli`, puis `gh auth login`).

Depuis la racine du dépôt :
    python .github/creer_tickets.py             simulation, rien n'est envoyé
    python .github/creer_tickets.py --envoyer   création

Relançable sans doublon : un ticket dont le titre existe déjà sur GitHub n'est pas recréé.
Crée aussi les étiquettes (phase, priorité, taille, décision, anomalie) et un jalon par phase.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DEPOT = "spuiksterr/GARP"
FEUILLE = Path(__file__).resolve().parent.parent / "FEUILLE_DE_ROUTE.md"
URL_FEUILLE = f"https://github.com/{DEPOT}/blob/main/FEUILLE_DE_ROUTE.md"
ECARTES = {"D-10", "D-11"}  # § 6 « Écarté pour l'instant »


def lire(texte: str):
    """Phases, tickets (tableaux du § 4), paragraphes détaillés et décisions (§ 3)."""
    phases, tickets, details, decisions = {}, [], {}, []
    phase = section = None
    for ligne in texte.splitlines():
        if ligne.startswith("## "):
            section, phase = ligne, None
        m = re.match(r"### Phase (\d) : (.+)", ligne)
        if m:
            phase = int(m.group(1))
            phases[phase] = m.group(2).strip()
            continue
        m = re.match(r"\| ([A-Z]-\d{2}) \| (.+?) \| (P\d) \| ([SML](?: à [SML])?) \|", ligne)
        if m and phase is not None:
            note = re.search(r"\(\*\*(.*?)\*\*", m.group(2))
            tickets.append({"id": m.group(1), "titre": re.sub(r" \(\*\*.*?\*\*.*?\)$", "", m.group(2)).strip(),
                            "p": m.group(3), "taille": m.group(4), "phase": phase,
                            "note": note.group(1) if note else ""})
        m = re.match(r"- \*\*([A-Z]-\d{2})\.\*\* (.+)", ligne)
        if m:
            details[m.group(1)] = m.group(2).strip()
        m = re.match(r"\| (DEC-\d) \| (.+?) \| (.+?) \| (.+?) \|$", ligne)
        if m and section and section.startswith("## 3"):
            decisions.append({"id": m.group(1), "question": m.group(2), "options": m.group(3),
                              "tickets": m.group(4)})
    accords = re.search(r"\*\*Accords en attente \(DEC-6\) :\*\*\n\n((?:- .+\n)+)", texte)
    for d in decisions:
        if d["id"] == "DEC-6" and accords:
            d["options"] = "accord ou refus, point par point :\n\n" + accords.group(1).strip()
    return phases, tickets, details, decisions


def corps_ticket(t, phases, details):
    d = details.get(t["id"], "Pas de détail dans la feuille de route : le titre du tableau fait foi. "
                              "Préciser le travail avec le propriétaire avant de coder.")
    lignes = [f"**Phase {t['phase']} ({phases[t['phase']]}) · priorité {t['p']} · taille {t['taille']}**", "", d]
    if t["note"]:
        lignes += ["", f"État : {t['note']}."]
    lignes += ["", "---", f"Ticket {t['id']} de la [feuille de route]({URL_FEUILLE}). Avant de commencer : lire "
               "`CLAUDE.md` et le § 1 de la feuille de route (une branche et une demande de fusion par ticket, "
               "tests, fichiers protégés)."]
    return "\n".join(lignes)


def corps_decision(d):
    return "\n".join(["**Décision à prendre par le propriétaire.** Un agent ne la tranche pas.", "",
                      f"**Question :** {d['question']}", "", f"**Options :** {d['options']}", "",
                      f"**Tickets concernés :** {d['tickets']}", "", "---",
                      f"Décision {d['id']} de la [feuille de route]({URL_FEUILLE}), § 3. Répondre en commentaire, "
                      "puis reporter le choix dans la feuille de route."])


def appel(methode, chemin, donnees=None):
    """API GitHub par `gh` : la connexion reste celle du propriétaire."""
    cmd = ["gh", "api", "-X", methode, f"repos/{DEPOT}{chemin}"]
    if donnees is not None:
        cmd += ["--input", "-"]
    for essai in range(5):
        r = subprocess.run(cmd, input=json.dumps(donnees) if donnees is not None else None,
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            return json.loads(r.stdout or "null")
        if ("rate limit" in r.stderr.lower() or "HTTP 403" in r.stderr) and essai < 4:
            time.sleep(60)  # limite de débit de GitHub
            continue
        raise RuntimeError(f"{methode} {chemin} : {r.stderr[:300]}")


def main():
    envoyer = "--envoyer" in sys.argv
    phases, tickets, details, decisions = lire(FEUILLE.read_text(encoding="utf-8"))
    a_creer = [t for t in tickets if t["id"] not in ECARTES and not t["note"].startswith(("fait", "sans objet"))]
    dec_a_creer = [d for d in decisions if not d["options"].startswith(("**Tranché", "Écarté le"))]
    print(f"{len(tickets)} tickets lus ; à créer : {len(a_creer)} tickets et "
          f"{len(dec_a_creer)} décisions ({', '.join(d['id'] for d in dec_a_creer)})")
    if not envoyer:
        print("Simulation : relancer avec --envoyer pour créer les tickets.")
        return

    print("Dépôt :", appel("GET", "")["full_name"])
    existantes = {x["name"] for x in appel("GET", "/labels?per_page=100")}
    etiquettes = {f"phase {n}": "c5def5" for n in phases} | {
        "P0": "b60205", "P1": "d93f0b", "P2": "fbca04", "P3": "c2e0c6", "taille S": "ededed",
        "taille M": "bfbfbf", "taille L": "8c8c8c", "décision": "5319e7", "anomalie": "d73a4a"}
    for nom, couleur in etiquettes.items():
        if nom not in existantes:
            appel("POST", "/labels", {"name": nom, "color": couleur})

    jalons = {j["title"]: j["number"] for j in appel("GET", "/milestones?state=all&per_page=100")}
    for n, nom in phases.items():
        if f"Phase {n} : {nom}" not in jalons:
            jalons[f"Phase {n} : {nom}"] = appel("POST", "/milestones", {"title": f"Phase {n} : {nom}"})["number"]

    deja = {i["title"]: i["number"] for page in range(1, 5)
            for i in appel("GET", f"/issues?state=all&per_page=100&page={page}")}
    crees = {}

    def creer(cle, titre, donnees):
        numero = deja.get(titre)
        if numero is None:
            numero = appel("POST", "/issues", {"title": titre, **donnees})["number"]
            time.sleep(1.5)
        crees[cle] = numero
        print(cle, "->", numero, flush=True)

    for d in dec_a_creer:
        creer(d["id"], f"[{d['id']}] {d['question']}", {"body": corps_decision(d), "labels": ["décision"]})
    for t in a_creer:
        creer(t["id"], f"[{t['id']}] {t['titre']}", {
            "body": corps_ticket(t, phases, details),
            "milestone": jalons[f"Phase {t['phase']} : {phases[t['phase']]}"],
            "labels": [f"phase {t['phase']}", t["p"], f"taille {t['taille'][-1]}"]})
    print(f"Terminé : {len(crees)} tickets sur GitHub.")


if __name__ == "__main__":
    main()
