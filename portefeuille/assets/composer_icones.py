"""Icônes de G.A.R.P à partir de l'emblème rendu par Blender (assets/blender/logo.py). Depuis portefeuille/ :

    .venv/Scripts/python.exe assets/composer_icones.py planche <dossier des rendus> <planche.png>
    .venv/Scripts/python.exe assets/composer_icones.py icones <embleme.png>

« planche » compare les concepts rendus (grande icône et petites tailles). « icones » écrit toutes les icônes :
outil du PC (assets/garp.png, garp.ico, entete.png), images de l'installateur Windows (installateur/*.bmp) et
bandeau du README (docs/bandeau.png).
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent.parent
INSTALLATEUR = RACINE / "installateur"

# Couleurs de la marque (voir docs/MARQUE.md), depuis le 15/11/2026 : anthracite, ocre, ivoire.
ANTHRACITE = (24, 25, 28)   # #18191C
GRAPHITE = (58, 60, 65)     # #3A3C41
OCRE = (201, 139, 46)       # #C98B2E
IVOIRE = (237, 230, 216)    # #EDE6D8
BLANC = (246, 248, 250)
# Ancienne marque (M-10), pour revoir les pistes écartées.
NUIT = (13, 39, 71)        # #0D2747
FORET = (14, 107, 92)      # #0E6B5C
PALETTES = {"marque": (ANTHRACITE, GRAPHITE), "premium": (ANTHRACITE, GRAPHITE), "verte": (NUIT, FORET),
            "blanc": ((255, 255, 255), (231, 232, 235))}


def degrade(taille: int, a=ANTHRACITE, b=GRAPHITE) -> Image.Image:
    """Dégradé diagonal, du haut à gauche vers le bas à droite."""
    petit = Image.new("RGB", (256, 256))
    px = petit.load()
    for y in range(256):
        for x in range(256):
            t = min(max((x + y) / 510, 0), 1)
            t = t * t * (3 - 2 * t)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return petit.resize((taille, taille), Image.BICUBIC)


def masque_arrondi(taille: int, rayon: float = 0.225) -> Image.Image:
    """Carré aux coins arrondis, lissé (dessiné quatre fois plus grand)."""
    grand = Image.new("L", (taille * 4, taille * 4), 0)
    ImageDraw.Draw(grand).rounded_rectangle([0, 0, taille * 4 - 1, taille * 4 - 1], radius=int(taille * 4 * rayon),
                                            fill=255)
    return grand.resize((taille, taille), Image.LANCZOS)


def recadrer(embleme: Image.Image) -> Image.Image:
    """Emblème réduit à ses pixels visibles, dans un carré."""
    boite = embleme.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    e = embleme.crop(boite)
    cote = max(e.size)
    carre = Image.new("RGBA", (cote, cote), (0, 0, 0, 0))
    carre.paste(e, ((cote - e.width) // 2, (cote - e.height) // 2))
    return carre


def avec_ombre(embleme: Image.Image, taille: int, part: float) -> Image.Image:
    """Emblème centré sur un calque transparent de `taille`, occupant `part` du côté, avec une ombre douce."""
    cote = round(taille * part)
    e = recadrer(embleme).resize((cote, cote), Image.LANCZOS)
    calque = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    pos = ((taille - cote) // 2, (taille - cote) // 2)
    ombre = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    alpha = Image.new("L", (taille, taille), 0)
    alpha.paste(e.getchannel("A"), (pos[0], pos[1] + round(taille * 0.025)))
    alpha = alpha.filter(ImageFilter.GaussianBlur(taille * 0.025)).point(lambda v: round(v * 0.45))
    ombre.putalpha(alpha)
    calque = Image.alpha_composite(calque, ombre)
    calque.alpha_composite(e, pos)
    return calque


def icone(embleme: Image.Image, taille: int = 1024, part: float = 0.70, arrondi: float = 0.225,
          palette: str = "marque") -> Image.Image:
    """Icône complète : fond en dégradé aux coins arrondis, emblème au centre."""
    fond = degrade(taille, *PALETTES[palette]).convert("RGBA")
    fond = Image.alpha_composite(fond, avec_ombre(embleme, taille, part))
    if arrondi:
        fond.putalpha(ImageChops.multiply(fond.getchannel("A"), masque_arrondi(taille, arrondi)))
    return fond


def police(taille: int, gras: bool = True):
    for nom in (("segoeuib.ttf", "bahnschrift.ttf") if gras else ("segoeui.ttf",)):
        try:
            return ImageFont.truetype(nom, taille)
        except OSError:
            continue
    return ImageFont.load_default(taille)


def planche(rendus: Path, sortie: Path, palette: str = "marque") -> None:
    concepts = sorted(rendus.glob("*.png"))
    largeur, haut = 560, 760
    p = Image.new("RGB", (largeur * len(concepts), haut), (236, 240, 244))
    d = ImageDraw.Draw(p)
    for i, chemin in enumerate(concepts):
        # « nom__palette.png » : fond propre à ce rendu (marque, premium ou blanc).
        nom, _, propre = chemin.stem.partition("__")
        fond = propre or palette
        e = Image.open(chemin).convert("RGBA")
        x = i * largeur
        d.text((x + 40, 24), f"{i + 1}. {nom}", fill=(20, 30, 45), font=police(34))
        grande = icone(e, 440, palette=fond)
        p.paste(grande, (x + 60, 90), grande)
        for j, t in enumerate((128, 64, 48, 32)):
            petite = icone(e, t, palette=fond)
            p.paste(petite, (x + 60 + sum((128, 64, 48, 32)[:j]) + j * 30, 600 + (128 - t) // 2), petite)
    p.save(sortie)


def silhouette(embleme: Image.Image, taille: int, part: float) -> Image.Image:
    """Emblème en blanc uni (icône monochrome d'Android, teintée par le système)."""
    cote = round(taille * part)
    a = recadrer(embleme).resize((cote, cote), Image.LANCZOS).getchannel("A")
    out = Image.new("RGBA", (taille, taille), (255, 255, 255, 0))
    plein = Image.new("RGBA", (cote, cote), (255, 255, 255, 255))
    plein.putalpha(a)
    out.alpha_composite(plein, ((taille - cote) // 2, (taille - cote) // 2))
    return out


def bandeau(embleme: Image.Image, largeur: int = 1600, hauteur: int = 480) -> Image.Image:
    """Bandeau du README : emblème, nom et promesse."""
    fond = degrade(max(largeur, hauteur)).crop((0, 0, largeur, hauteur)).convert("RGBA")
    cote = round(hauteur * 0.74)
    e = avec_ombre(embleme, cote, 0.92)
    fond.alpha_composite(e, (round(hauteur * 0.16), (hauteur - cote) // 2))
    d = ImageDraw.Draw(fond)
    x = round(hauteur * 0.16) + cote + 50
    d.text((x, hauteur * 0.20), "G.A.R.P", fill=BLANC, font=police(round(hauteur * 0.30)))
    d.text((x, hauteur * 0.56), "La croissance, au juste prix.", fill=OCRE,
           font=police(round(hauteur * 0.085), gras=False))
    d.text((x, hauteur * 0.70), "Growth at a reasonable price", fill=(150, 152, 158),
           font=police(round(hauteur * 0.06), gras=False))
    return fond


def entete(embleme: Image.Image, hauteur: int = 192) -> Image.Image:
    """En-tête de la barre latérale de l'outil : l'icône arrondie et « G.A.R.P » en ocre, fond transparent. L'icône
    garde son fond anthracite et le nom est ocre : lisibles sur le thème sombre comme sur le clair."""
    ic = icone(embleme, hauteur)
    f = police(round(hauteur * 0.56))
    texte = "G.A.R.P"
    boite = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texte, font=f)
    ecart = round(hauteur * 0.2)
    largeur = hauteur + ecart + (boite[2] - boite[0]) + round(hauteur * 0.05)
    out = Image.new("RGBA", (largeur, hauteur), (0, 0, 0, 0))
    out.alpha_composite(ic, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((hauteur + ecart - boite[0], (hauteur - (boite[3] - boite[1])) / 2 - boite[1]), texte, fill=OCRE, font=f)
    return out


def icones(source: Path) -> None:
    e = Image.open(source).convert("RGBA")
    grande = icone(e, 1024)
    entete(e).save(ICI / "entete.png", optimize=True)

    # Application de bureau (Streamlit, fenêtre, raccourcis) et documentation.
    grande.resize((512, 512), Image.LANCZOS).save(ICI / "garp.png", optimize=True)
    grande.save(ICI / "garp.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    bandeau(e).convert("RGB").save(ICI.parent / "docs" / "bandeau.png", optimize=True)

    # Installateur Windows (Inno Setup) : bandeau vertical de l'assistant et vignette, en 100 % et 200 %.
    inst = INSTALLATEUR
    inst.mkdir(exist_ok=True)
    for suffixe, f in (("", 1), ("@2x", 2)):
        larg, h = 164 * f, 314 * f
        g = degrade(h).resize((larg, h), Image.BICUBIC).convert("RGBA")
        g.alpha_composite(avec_ombre(e, larg, 0.72), (0, round(h * 0.18)))
        g.convert("RGB").save(inst / f"grande{suffixe}.bmp")
        v = Image.new("RGBA", (55 * f, 55 * f), (255, 255, 255, 255))
        v.alpha_composite(icone(e, 55 * f))
        v.convert("RGB").save(inst / f"petite{suffixe}.bmp")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "planche":
        planche(Path(sys.argv[2]), Path(sys.argv[3]), *sys.argv[4:5])
    elif mode == "icones":
        icones(Path(sys.argv[2]))
    print("fait")
