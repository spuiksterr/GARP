"""Logo G.A.R.P (anciennement Climax) en 3D, rendu par Blender (Cycles, fond transparent).

    blender -b --factory-startup --python assets/blender/logo.py -- <dossier de sortie> [concept ...]

Logo retenu le 19/11/2026 : « garp_pousse » (une pousse ivoire monte de l'intérieur d'une pièce, un anneau de métal ocre : la
croissance, au juste prix). Les autres pistes G.A.R.P sont « garp_zone », « garp_g », « garp_balance »,
« garp_points » (logo du 18/11/2026) et « garp_etiquette ». Logo de Climax, du 15/11 au 18/11/2026 : « expo_ivoire_ocre » (courbe
exponentielle ocre au-dessus de barres ivoire). Les autres concepts sont les pistes écartées : « pousse », « canopee »,
« sommet », « percee », « elan », « exponentielle » (en vert), « chevrons », « cime », « apex », « pic »,
« ascension », « lame », les variantes « c_* », « lame_barres* » et « expo_* ». Chaque concept donne
<concept>.png (1024 px, emblème seul sur fond transparent) ; assets/composer_icones.py en tire
les icônes (Android, Windows, application de bureau) et la planche de présentation.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

BLANC = (0.93, 0.95, 0.97, 1)
MENTHE = (0.04, 0.56, 0.30, 1)
OR = (0.95, 0.55, 0.12, 1)


# ------------------------------------------------------------------------------------------ outils

def vider_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def materiau(nom, couleur, rugosite=0.3, metal=0.0, vernis=0.4):
    m = bpy.data.materials.new(nom)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = couleur
    p.inputs["Roughness"].default_value = rugosite
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = vernis
    p.inputs["Coat Roughness"].default_value = 0.15
    return m


def lisser(obj):
    for f in obj.data.polygons:
        f.use_smooth = True


def donner(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def sphere(nom, centre, rayon, mat, segments=64):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=segments // 2, radius=rayon, location=centre)
    o = bpy.context.active_object
    o.name = nom
    lisser(o)
    return donner(o, mat)


def feuille(nom, base, longueur, largeur, angle_deg, mat, courbure=0.18, rondeur=0.35, evasement=0.35):
    """Feuille pointue, de `base` vers le haut, inclinée de `angle_deg` (0 : verticale, positif : vers la droite).
    `largeur` : demi-largeur. `rondeur` : 0,35 donne une feuille pleine, 0,8 une amande effilée aux deux bouts.
    `evasement` : 0,35 élargit le premier tiers, 0 garde une amande symétrique."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1)
    o = bpy.context.active_object
    o.name = nom
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        t = v.co.z  # -1 (base) .. 1 (pointe)
        resserrement = max(1 - t * t, 0) ** rondeur
        x, y = v.co.x * resserrement, v.co.y * resserrement
        # Plus large au premier tiers, pointue au bout.
        profil = 1.0 - evasement * (t + 1) / 2
        v.co.x = x * largeur * profil
        v.co.y = y * largeur * 0.22
        v.co.z = (t + 1) / 2 * longueur
        v.co.y -= courbure * longueur * ((t + 1) / 2) ** 2  # la pointe se courbe vers l'avant
    bm.to_mesh(o.data)
    bm.free()
    lisser(o)
    o.location = base
    o.rotation_euler = (0, math.radians(angle_deg), 0)
    return donner(o, mat)


def barre(nom, x, hauteur, largeur, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, hauteur / 2))
    o = bpy.context.active_object
    o.name = nom
    o.scale = (largeur, largeur, hauteur)
    bpy.ops.object.transform_apply(scale=True)
    m = o.modifiers.new("arrondi", "BEVEL")
    m.width = largeur * 0.48
    m.segments = 16
    m.limit_method = "NONE"
    lisser(o)
    return donner(o, mat)


# ------------------------------------------------------------------------------------------ concepts

def pousse():
    blanc, menthe = materiau("blanc", BLANC, 0.22), materiau("menthe", MENTHE, 0.3)
    ouverture = 42  # demi-angle de l'ouverture du C, vers la droite
    bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.27, major_segments=160, minor_segments=40)
    c = bpy.context.active_object
    c.name = "C"
    bm = bmesh.new()
    bm.from_mesh(c.data)
    trop = [v for v in bm.verts if abs(math.degrees(math.atan2(v.co.y, v.co.x))) < ouverture]
    bmesh.ops.delete(bm, geom=trop, context="VERTS")
    bm.to_mesh(c.data)
    bm.free()
    lisser(c)
    donner(c, blanc)
    # Bouts arrondis, puis le C debout face à la caméra.
    a = math.radians(ouverture + 1.5)
    bas = sphere("bout_bas", (math.cos(a), -math.sin(a), 0), 0.27, blanc)
    haut = sphere("bout_haut", (math.cos(a), math.sin(a), 0), 0.27, blanc)
    for o in (c, bas, haut):
        o.select_set(True)
    bpy.context.view_layer.objects.active = c
    bpy.ops.object.join()
    c.rotation_euler = (math.radians(90), 0, 0)
    # Pousse : une tige courte sortie du bout du haut, puis deux feuilles en V.
    x, z = math.cos(a), math.sin(a)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.06, depth=0.34, location=(x, 0, z + 0.3))
    lisser(donner(bpy.context.active_object, menthe))
    depart = (x, 0, z + 0.42)
    feuille("grande", depart, 0.95, 0.40, 38, menthe, courbure=0.1)
    feuille("petite", (x - 0.02, 0, z + 0.4), 0.62, 0.30, -42, menthe, courbure=0.1)


def canopee():
    blanc, menthe = materiau("blanc", BLANC, 0.25), materiau("menthe", MENTHE, 0.35, vernis=0.25)
    # Cime : boules fondues entre elles (métaballes), converties en maillage.
    meta = bpy.data.metaballs.new("cime")
    meta.resolution = 0.03
    meta.threshold = 0.6
    for (x, z, r) in [(0, 1.25, 0.62), (-0.55, 0.95, 0.5), (0.58, 0.98, 0.52), (-0.25, 0.7, 0.45), (0.28, 0.72, 0.45)]:
        e = meta.elements.new()
        e.co = (x, 0, z)
        e.radius = r
    o = bpy.data.objects.new("cime", meta)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    cime = bpy.context.active_object
    lisser(cime)
    donner(cime, menthe)
    # Tronc qui se divise en deux branches.
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.15, depth=0.7, location=(0, 0, 0.2))
    tronc = donner(bpy.context.active_object, blanc)
    m = tronc.modifiers.new("arrondi", "BEVEL")
    m.width, m.segments = 0.06, 8
    lisser(tronc)
    for cote in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.07, depth=0.5,
                                            location=(cote * 0.16, 0, 0.62), rotation=(0, math.radians(cote * 38), 0))
        lisser(donner(bpy.context.active_object, blanc))
    # Socle : une marche, comme un sol.
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=0.7, depth=0.2, location=(0, 0, -0.2))
    socle = donner(bpy.context.active_object, blanc)
    socle.scale = (1, 0.35, 1)
    m = socle.modifiers.new("arrondi", "BEVEL")
    m.width, m.segments = 0.05, 8
    lisser(socle)


def sommet():
    blanc, menthe, metal_or = materiau("blanc", BLANC, 0.22), materiau("menthe", MENTHE, 0.3), \
        materiau("or", OR, 0.3, vernis=0.7)
    for i, (h, mat) in enumerate([(0.75, blanc), (1.15, blanc), (1.65, metal_or)]):
        barre(f"barre{i}", (i - 1) * 0.62, h, 0.42, mat)
    feuille("feuille", (0.64, 0, 1.6), 0.8, 0.36, 34, menthe, courbure=0.1)
    feuille("feuille2", (0.6, 0, 1.6), 0.5, 0.26, -40, menthe, courbure=0.1)


# ------------------------------------------------------------------- concepts « performance » (2026-11)

def tout_deselectionner():
    for o in bpy.context.selected_objects:
        o.select_set(False)


def tube(nom, points, rayon, mat, bouts=True):
    """Tube lisse le long de points (x, z) dans le plan face à la caméra, bouts arrondis."""
    cu = bpy.data.curves.new(nom, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = rayon
    cu.bevel_resolution = 10
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for p, (x, z) in zip(sp.points, points):
        p.co = (x, 0, z, 1)
    o = bpy.data.objects.new(nom, cu)
    bpy.context.collection.objects.link(o)
    tout_deselectionner()
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.active_object
    lisser(donner(o, mat))
    if bouts:
        for i in (0, -1):
            sphere(f"{nom}_bout{i}", (points[i][0], 0, points[i][1]), rayon, mat, segments=48)
    return o


def trait(nom, points, rayon, mat):
    """Ligne brisée aux angles arrondis : des cylindres entre les points, une sphère à chaque point."""
    for i, ((x1, z1), (x2, z2)) in enumerate(zip(points, points[1:])):
        dx, dz = x2 - x1, z2 - z1
        # Sans couvercles : le cylindre rejoint les sphères sans arête visible.
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=rayon, depth=math.hypot(dx, dz), end_fill_type="NOTHING",
                                            location=((x1 + x2) / 2, 0, (z1 + z2) / 2),
                                            rotation=(0, math.atan2(dx, dz), 0))
        bpy.context.active_object.name = f"{nom}{i}"
        lisser(donner(bpy.context.active_object, mat))
    for i, (x, z) in enumerate(points):
        sphere(f"{nom}_joint{i}", (x, 0, z), rayon, mat, segments=48)


def prisme(nom, points, epaisseur, mat, arrondi):
    """Polygone (x, z) extrudé vers l'arrière, arêtes arrondies."""
    me = bpy.data.meshes.new(nom)
    bm = bmesh.new()
    avant = [bm.verts.new((x, -epaisseur / 2, z)) for x, z in points]
    arriere = [bm.verts.new((x, epaisseur / 2, z)) for x, z in points]
    bm.faces.new(avant)
    bm.faces.new(list(reversed(arriere)))
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([avant[i], arriere[i], arriere[j], avant[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(nom, me)
    bpy.context.collection.objects.link(o)
    m = o.modifiers.new("arrondi", "BEVEL")
    m.width, m.segments, m.limit_method = arrondi, 10, "NONE"
    lisser(o)
    return donner(o, mat)


def tete(nom, pointe, direction, longueur, largeur, epaisseur, mat):
    """Pointe de flèche plate, la pointe en `pointe` (x, z), orientée selon `direction` (dx, dz)."""
    dx, dz = direction
    n = math.hypot(dx, dz)
    dx, dz = dx / n, dz / n
    o = prisme(nom, [(0, longueur), (-largeur / 2, 0), (largeur / 2, 0)], epaisseur, mat, epaisseur * 0.4)
    o.location = (pointe[0] - dx * longueur, 0, pointe[1] - dz * longueur)
    o.rotation_euler = (0, math.atan2(dx, dz), 0)
    return o


def arc(rayon, debut, fin, n=120, centre=(0.0, 0.0)):
    """Points d'un arc de cercle, angles en degrés (sens trigonométrique si fin > debut)."""
    return [(centre[0] + rayon * math.cos(math.radians(debut + (fin - debut) * i / n)),
             centre[1] + rayon * math.sin(math.radians(debut + (fin - debut) * i / n))) for i in range(n + 1)]


def percee():
    """Un C ouvert à droite ; une courbe de cours en sort par l'ouverture et file vers le haut."""
    blanc, menthe = materiau("blanc", BLANC, 0.22), materiau("menthe", MENTHE, 0.3)
    tube("C", arc(1.0, 50, 310), 0.24, blanc)
    pts = [(-0.6, -0.5), (-0.26, -0.12), (0.04, -0.34), (0.98, 0.4)]
    trait("cours", pts, 0.115, menthe)
    d = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
    n = math.hypot(*d)
    tete("pointe", (pts[-1][0] + d[0] / n * 0.42, pts[-1][1] + d[1] / n * 0.42), d, 0.58, 0.62, 0.23, menthe)


def elan():
    """Un C dont le bout du haut se redresse en flèche qui monte."""
    blanc, menthe = materiau("blanc", BLANC, 0.22), materiau("menthe", MENTHE, 0.3)
    # Le C part d'en bas à droite et tourne dans le sens des aiguilles d'une montre jusqu'en haut.
    tube("C", arc(1.0, -55, -265), 0.25, blanc, bouts=False)
    sphere("C_bout", (math.cos(math.radians(-55)), 0, math.sin(math.radians(-55))), 0.25, blanc)
    # Puis la flèche : le cap passe de l'horizontale à 42° vers le haut, puis va droit.
    x, z = math.cos(math.radians(95)), math.sin(math.radians(95))
    cap, pts = 5.0, [(x, z)]
    for _ in range(40):
        cap += (42 - 5) / 40
        x, z = x + 0.0125 * math.cos(math.radians(cap)), z + 0.0125 * math.sin(math.radians(cap))
        pts.append((x, z))
    x, z = x + 0.45 * math.cos(math.radians(42)), z + 0.45 * math.sin(math.radians(42))
    pts.append((x, z))
    tube("fleche", pts, 0.25, menthe, bouts=False)
    d = (math.cos(math.radians(42)), math.sin(math.radians(42)))
    tete("pointe", (x + d[0] * 0.6, z + d[1] * 0.6), d, 0.72, 1.05, 0.46, menthe)


def exponentielle():
    """Des barres qui montent, et la courbe de la croissance composée qui file au-dessus."""
    blanc, menthe = materiau("blanc", BLANC, 0.22), materiau("menthe", MENTHE, 0.3)

    def f(x):
        return 0.2 + 0.104 * (math.exp(1.6 * (x + 1.0)) - 1)

    for i, (x, h) in enumerate(((-0.68, 0.5), (-0.22, 0.72), (0.24, 1.02), (0.70, 1.45))):
        b = barre(f"barre{i}", x, h, 0.34, blanc)
        b.location.y = 0.35
    pts = [(-1.05 + 1.85 * i / 80, f(-1.05 + 1.85 * i / 80) + 0.12) for i in range(81)]
    tube("courbe", pts[:-1], 0.105, menthe)
    d = (pts[-1][0] - pts[-3][0], pts[-1][1] - pts[-3][1])
    tete("pointe", (pts[-1][0] + d[0] * 2, pts[-1][1] + d[1] * 2), d, 0.5, 0.56, 0.21, menthe)


def chevrons():
    """Trois chevrons empilés qui montent, le plus haut en vert."""
    blanc, menthe = materiau("blanc", BLANC, 0.22), materiau("menthe", MENTHE, 0.3)
    for i, (z, mat) in enumerate([(-0.8, blanc), (-0.08, blanc), (0.64, menthe)]):
        trait(f"chevron{i}", [(-0.8, z), (0, z + 0.58), (0.8, z)], 0.14, mat)


def cime():
    """Un sommet : la montagne, la voie qui monte le long de l'arête et un point d'or au plus haut."""
    blanc, menthe = materiau("blanc", BLANC, 0.25), materiau("menthe", MENTHE, 0.3)
    metal_or = materiau("or", OR, 0.25, metal=0.3, vernis=0.7)
    prisme("montagne", [(-1.25, 0), (1.25, 0), (0.45, 1.62), (0.02, 0.86), (-0.38, 1.12)], 0.4, blanc, 0.07)
    voie = [(-1.0, 0.24), (-0.38, 0.92), (0.02, 0.6), (0.45, 1.36)]
    trait("voie", voie, 0.085, menthe)
    for o in [o for o in bpy.context.scene.objects if o.name.startswith("voie")]:
        o.location.y -= 0.3
    sphere("sommet", (0.45, -0.1, 1.66), 0.16, metal_or)


# --------------------------------------------- concepts « premium » anthracite et ocre (2026-11, 2e série)

OCRE = (0.62, 0.33, 0.08, 1)     # métal ocre (couleur linéaire), environ #C98B2E à l'écran
IVOIRE = (0.85, 0.79, 0.69, 1)   # environ #EDE6D8


def ocre_metal():
    return materiau("ocre", OCRE, rugosite=0.3, metal=1.0, vernis=0.25)


def ivoire():
    return materiau("ivoire", IVOIRE, rugosite=0.35, vernis=0.3)


def apex():
    """Un C fin en métal ocre ; un trait ivoire en sort et monte jusqu'au point culminant."""
    tube("C", arc(1.0, 48, 312), 0.16, ocre_metal())
    iv = ivoire()
    pts = [(-0.42, -0.3), (-0.12, 0.02), (0.1, -0.14), (0.92, 0.72)]
    trait("cours", pts, 0.055, iv)
    sphere("apex", (1.02, 0, 0.82), 0.16, ocre_metal())


def pic():
    """Deux sommets en Λ emboîtés : le grand en métal ocre, le petit en ivoire, l'ensemble monte vers la droite."""
    prisme("grand", [(-0.95, 0), (0.15, 1.55), (1.25, 0), (0.85, 0), (0.15, 0.98), (-0.55, 0)], 0.3,
           ocre_metal(), 0.035)
    p = prisme("petit", [(-1.4, 0), (-0.65, 0.95), (0.1, 0), (-0.22, 0), (-0.65, 0.56), (-1.08, 0)],
               0.3, ivoire(), 0.035)
    p.location.y = -0.22


def ascension():
    """Trois barres dont les sommets, taillés en biais, dessinent une seule ligne qui monte."""
    iv, oc = ivoire(), ocre_metal()

    def haut(x):
        return 0.55 + 0.62 * (x + 0.9)

    for i, (x0, mat) in enumerate([(-0.9, iv), (-0.32, iv), (0.26, oc)]):
        x1 = x0 + 0.44
        prisme(f"barre{i}", [(x0, 0), (x1, 0), (x1, haut(x1)), (x0, haut(x0))], 0.3, mat, 0.03)


def lame():
    """Un C plein, comme une lettre gravée, dont le bout du haut s'effile en lame qui monte."""
    ext, inter = 1.0, 0.64
    contour = [(ext * math.cos(math.radians(a)), ext * math.sin(math.radians(a))) for a in range(62, 301, 2)]
    contour += [(inter * math.cos(math.radians(a)), inter * math.sin(math.radians(a))) for a in range(300, 61, -2)]
    contour.append((1.02, 1.22))
    prisme("C", contour, 0.32, ocre_metal(), 0.03)


# Variantes du « pic » (3e série) : le C de Climax, taillé à facettes, et un signe boursier.

def c_anguleux(nom, mat, ext=1.0, inter=0.7, ouverture=40, epaisseur=0.3):
    """C en octogone (côtés plats en haut, en bas et à gauche), ouvert à droite sur ±`ouverture` degrés."""
    def bord(r, a):
        # Distance au centre du bord de l'octogone dans la direction a (côtés centrés sur 0°, 45°, 90°…).
        milieu = round(a / 45) * 45
        return r * math.cos(math.radians(22.5)) / math.cos(math.radians(a - milieu))

    angles = [ouverture] + [a for a in (67.5, 112.5, 157.5, 202.5, 247.5, 292.5)] + [360 - ouverture]
    pts = [(bord(ext, a) * math.cos(math.radians(a)), bord(ext, a) * math.sin(math.radians(a))) for a in angles]
    pts += [(bord(inter, a) * math.cos(math.radians(a)), bord(inter, a) * math.sin(math.radians(a)))
            for a in reversed(angles)]
    return prisme(nom, pts, epaisseur, mat, 0.03)


def bande(nom, points, largeur, mat, pointe=None, epaisseur=0.3, y=0.0):
    """Ligne brisée épaisse aux angles vifs (onglets), terminée si demandé par une pointe de flèche
    (`pointe` = (longueur, largeur))."""
    def normale(dx, dz):
        n = math.hypot(dx, dz)
        return -dz / n, dx / n

    gauche, droite = [], []
    for i, (x, z) in enumerate(points):
        segs = []
        if i > 0:
            segs.append(normale(x - points[i - 1][0], z - points[i - 1][1]))
        if i < len(points) - 1:
            segs.append(normale(points[i + 1][0] - x, points[i + 1][1] - z))
        nx, nz = sum(s[0] for s in segs), sum(s[1] for s in segs)
        n = math.hypot(nx, nz)
        nx, nz = nx / n, nz / n
        onglet = largeur / 2 / max(nx * segs[0][0] + nz * segs[0][1], 0.35)
        gauche.append((x + nx * onglet, z + nz * onglet))
        droite.append((x - nx * onglet, z - nz * onglet))
    contour = gauche[:]
    if pointe:
        (x1, z1), (x2, z2) = points[-2], points[-1]
        d = math.hypot(x2 - x1, z2 - z1)
        ux, uz = (x2 - x1) / d, (z2 - z1) / d
        lg, lt = pointe
        contour += [(x2 - uz * lt / 2, z2 + ux * lt / 2), (x2 + ux * lg, z2 + uz * lg), (x2 + uz * lt / 2, z2 - ux * lt / 2)]
    contour += list(reversed(droite))
    o = prisme(nom, contour, epaisseur, mat, 0.025)
    o.location.y = y
    return o


def c_cours(couleurs=("ocre", "ivoire")):
    """C à facettes ; une courbe de cours en dents de scie, comme une ligne de crêtes, sort par l'ouverture."""
    mats = {"ocre": ocre_metal(), "ivoire": ivoire()}
    c_anguleux("C", mats[couleurs[0]])
    bande("cours", [(-0.5, -0.36), (-0.22, 0.06), (0.02, -0.16), (0.82, 0.28)], 0.17, mats[couleurs[1]],
          pointe=(0.32, 0.42), y=-0.12)


def c_cours_ivoire():
    c_cours(("ivoire", "ocre"))


def c_bougies():
    """C à facettes ocre ; trois chandeliers boursiers qui montent, le dernier en ocre."""
    oc, iv = ocre_metal(), ivoire()
    c_anguleux("C", oc)
    for i, (x, bas, haut, mat) in enumerate([(-0.34, -0.42, -0.02, iv), (-0.02, -0.22, 0.24, iv),
                                             (0.30, 0.0, 0.52, oc)]):
        prisme(f"corps{i}", [(x - 0.1, bas), (x + 0.1, bas), (x + 0.1, haut), (x - 0.1, haut)], 0.26, mat, 0.02)
        prisme(f"meche{i}", [(x - 0.025, bas - 0.12), (x + 0.025, bas - 0.12), (x + 0.025, haut + 0.14),
                             (x - 0.025, haut + 0.14)], 0.12, mat, 0.01)


def c_sommets():
    """Les deux sommets du « pic » dans un C à facettes ; le grand sommet repart en flèche de cours."""
    oc, iv = ocre_metal(), ivoire()
    c_anguleux("C", iv, ext=1.0, inter=0.76)
    bande("petit", [(-0.52, -0.4), (-0.22, 0.05), (0.02, -0.2)], 0.15, iv, y=-0.1)
    bande("grand", [(-0.22, -0.42), (0.14, 0.2), (0.34, -0.04), (0.86, 0.3)], 0.17, oc, pointe=(0.3, 0.4), y=-0.2)


# Mélange « ascension » et « lame » (4e série) : le C gravé s'effile en lame, et des barres taillées en biais montent
# à l'intérieur ; le haut des barres est sur la droite qui mène à la pointe de la lame.

def lame_barres(couleur_c="ocre", couleur_barres="ivoire", nb=3, pointe=(1.02, 1.22), pente=1.0):
    mats = {"ocre": ocre_metal(), "ivoire": ivoire()}
    ext, inter = 1.0, 0.64
    contour = [(ext * math.cos(math.radians(a)), ext * math.sin(math.radians(a))) for a in range(62, 301, 2)]
    contour += [(inter * math.cos(math.radians(a)), inter * math.sin(math.radians(a))) for a in range(300, 61, -2)]
    contour.append(pointe)
    prisme("C", contour, 0.32, mats[couleur_c], 0.03)

    def haut(x):
        return pointe[1] + pente * (x - pointe[0])

    gauche, droite, ecart = -0.44, 0.30, 0.1
    larg = (droite - gauche - ecart * (nb - 1)) / nb
    for i in range(nb):
        x0 = gauche + i * (larg + ecart)
        x1 = x0 + larg
        b = prisme(f"barre{i}", [(x0, -0.4), (x1, -0.4), (x1, haut(x1)), (x0, haut(x0))], 0.24,
                   mats[couleur_barres], 0.02)
        b.location.y = -0.1


def lame_barres_ivoire():
    lame_barres("ivoire", "ocre")


def lame_barres_fines():
    lame_barres(nb=4, pointe=(1.12, 1.34), pente=1.02)


# C ocre et courbe exponentielle anthracite, pour un fond blanc (5e série).

ANTHRACITE = (0.022, 0.024, 0.028, 1)  # environ #2A2C30 à l'écran


def anthracite():
    return materiau("anthracite", ANTHRACITE, rugosite=0.45, vernis=0.15)


def expo(x0=-0.45, x1=0.62, z0=-0.38, k=2.6, a=0.0806, n=60):
    """Points d'une exponentielle z = z0 + a (e^(k (x - x0)) - 1), de x0 à x1."""
    return [(x0 + (x1 - x0) * i / n, z0 + a * (math.exp(k * (x1 - x0) * i / n) - 1)) for i in range(n + 1)]


def c_grave(mat, ext=1.0, inter=0.64, debut=62, fin=300):
    contour = [(ext * math.cos(math.radians(a)), ext * math.sin(math.radians(a))) for a in range(debut, fin + 1, 2)]
    contour += [(inter * math.cos(math.radians(a)), inter * math.sin(math.radians(a))) for a in range(fin, debut - 1, -2)]
    return prisme("C", contour, 0.32, mat, 0.03)


def c_expo():
    """C plein gravé en métal ocre ; une courbe exponentielle anthracite en sort et monte en flèche."""
    c_grave(ocre_metal())
    bande("courbe", expo(x0=-0.40, x1=0.80, z0=-0.55, a=0.05), 0.15, anthracite(), pointe=(0.3, 0.38), y=-0.12)


def c_expo_rond():
    """C rond et lisse en métal ocre ; même courbe, en tube."""
    tube("C", arc(1.0, 64, 296), 0.2, ocre_metal())
    an = anthracite()
    pts = expo(x0=-0.45, x1=0.85, z0=-0.5, a=0.04)
    tube("courbe", pts, 0.085, an)
    d = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
    n = math.hypot(*d)
    tete("pointe", (pts[-1][0] + d[0] / n * 0.32, pts[-1][1] + d[1] / n * 0.32), d, 0.4, 0.44, 0.17, an)


def c_expo_facettes():
    """C à facettes en métal ocre ; la courbe, un peu plus basse, passe par l'ouverture."""
    c_anguleux("C", ocre_metal())
    bande("courbe", expo(x0=-0.35, x1=0.85, z0=-0.45, a=0.03), 0.15, anthracite(), pointe=(0.3, 0.34), y=-0.12)


# « Exponentielle » (1re série) retenue le 15/11/2026, déclinée en anthracite et ocre.

def exponentielle_couleurs(barres, courbe):
    mats = {"ocre": ocre_metal, "anthracite": anthracite, "ivoire": ivoire}
    mb, mc = mats[barres](), mats[courbe]()

    def f(x):
        return 0.2 + 0.104 * (math.exp(1.6 * (x + 1.0)) - 1)

    for i, (x, h) in enumerate(((-0.68, 0.5), (-0.22, 0.72), (0.24, 1.02), (0.70, 1.45))):
        b = barre(f"barre{i}", x, h, 0.34, mb)
        b.location.y = 0.35
    pts = [(-1.05 + 1.85 * i / 80, f(-1.05 + 1.85 * i / 80) + 0.12) for i in range(81)]
    tube("courbe", pts[:-1], 0.105, mc)
    d = (pts[-1][0] - pts[-3][0], pts[-1][1] - pts[-3][1])
    tete("pointe", (pts[-1][0] + d[0] * 2, pts[-1][1] + d[1] * 2), d, 0.5, 0.56, 0.21, mc)


def expo_anthracite_ocre():
    exponentielle_couleurs("anthracite", "ocre")


def expo_ocre_anthracite():
    exponentielle_couleurs("ocre", "anthracite")


def expo_ivoire_ocre():
    exponentielle_couleurs("ivoire", "ocre")


# G.A.R.P, « Growth at a reasonable price » (6e série, 18/11/2026) : six pistes pour le nouveau nom.

def garp_zone():
    """Repère croissance (horizontal) et prix (vertical) ; la zone sous la diagonale PER / croissance = 1, et la
    valeur choisie, une bille de métal ocre, dedans."""
    iv = ivoire()
    trait("axes", [(-0.85, 0.9), (-0.85, -0.85), (0.9, -0.85)], 0.09, iv)
    zone = prisme("zone", [(0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)], 0.06,
                  materiau("ocre_mat", (0.24, 0.13, 0.035, 1), rugosite=0.65, metal=0.5, vernis=0.0), 0.02)
    zone.location.y = 0.12
    for i in range(1, 8):
        t = -0.7 + 1.4 * i / 8
        sphere(f"diagonale{i}", (t, 0, t), 0.035, iv, segments=24)
    sphere("valeur", (0.35, -0.12, -0.25), 0.25, ocre_metal())


def garp_g():
    """Un G en métal ocre, ouvert en haut à droite ; une flèche ivoire sort par l'ouverture et monte."""
    c = (-0.05, -0.1)
    pts = arc(0.75, 60, 350, centre=c)
    pts.append((0.175, pts[-1][1]))
    tube("G", pts, 0.12, ocre_metal())
    iv = ivoire()
    trait("fleche", [(-0.25, -0.5), (0.6, 0.52)], 0.085, iv)
    d = (0.85, 1.0)
    tete("pointe", (0.9, 0.88), d, 0.4, 0.44, 0.17, iv)


def garp_balance():
    """Le fléau d'une balance à l'horizontale : une pièce (le prix) d'un côté, des barres qui montent (la
    croissance) de l'autre."""
    iv, oc = ivoire(), ocre_metal()
    prisme("pied", [(0, -0.3), (-0.3, -0.85), (0.3, -0.85)], 0.3, iv, 0.03)
    tube("fleau", [(-0.95, -0.3), (0.95, -0.3)], 0.065, iv)
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=0.27, depth=0.09, location=(-0.6, 0, 0.035),
                                        rotation=(math.radians(90), 0, 0))
    piece = bpy.context.active_object
    piece.name = "piece"
    m = piece.modifiers.new("arrondi", "BEVEL")
    m.width, m.segments, m.limit_method = 0.025, 8, "NONE"
    lisser(donner(piece, oc))
    for i, (x, haut) in enumerate(((0.34, 0.05), (0.59, 0.3), (0.84, 0.6))):
        prisme(f"barre{i}", [(x - 0.09, -0.235), (x + 0.09, -0.235), (x + 0.09, haut), (x - 0.09, haut)], 0.18,
               oc, 0.025)


def garp_points():
    """Le G de G.A.R.P en ivoire, et ses points : trois cubes de métal ocre qui montent comme des marches."""
    # Métal satiné : des faces planes en métal poli ne refléteraient que le fond sombre.
    iv, oc = ivoire(), materiau("ocre_satine", OCRE, rugosite=0.42, metal=1.0, vernis=0.3)
    pts = arc(0.6, 50, 330, centre=(-0.25, 0))
    x_fin = pts[-1][0]
    pts += [(x_fin, -0.05), (0.0, -0.05)]
    tube("G", pts, 0.13, iv)
    # Le premier point posé au bas du G, comme un point final ; les deux suivants montent d'une marche chacun.
    c = 0.17  # demi-côté
    for i, (x, z) in enumerate(((0.66, -0.56), (1.06, -0.14), (1.46, 0.28))):
        prisme(f"point{i}", [(x - c, z - c), (x + c, z - c), (x + c, z + c), (x - c, z + c)], 2 * c, oc, 0.06)


def garp_pousse():
    """Une pousse ivoire monte de l'intérieur d'une pièce, un anneau de métal ocre : la croissance part d'un prix
    payé. Reprend trait pour trait l'esquisse retenue (planche « Pousse et pièce », repère 100 x 100 ramené à
    x = (sx - 50) / 40, z = (50 - sy) / 40) : anneau de centre (50, 68) et de rayon 22, trait de 7 ; tige de
    (50, 72) à (50, 24), trait de 6 ; feuille gauche de (50, 50) à (30, 32), feuille droite de (50, 38) à (70, 18),
    en amande, larges d'environ 0,44 fois leur longueur."""
    iv = ivoire()

    def p(sx, sy):
        return (sx - 50) / 40, (50 - sy) / 40

    cx, cz = p(50, 68)
    bpy.ops.mesh.primitive_torus_add(major_radius=22 / 40, minor_radius=3.5 / 40, major_segments=192,
                                     minor_segments=40, location=(cx, 0, cz), rotation=(math.radians(90), 0, 0))
    piece = bpy.context.active_object
    piece.name = "piece"
    lisser(donner(piece, ocre_metal()))
    # Comme sur l'esquisse, la tige et les feuilles passent devant l'anneau (vers la caméra, y négatif).
    devant = -0.12
    tube("tige", [p(50, 72), p(50, 24)], 3 / 40, iv)
    for o in [o for o in bpy.context.scene.objects if o.name.startswith("tige")]:
        o.location.y += devant
    for nom, base, pointe, demi_largeur in (("feuille_gauche", (50, 50), (30, 32), 0.145),
                                            ("feuille_droite", (50, 38), (70, 18), 0.155)):
        (bx, bz), (px, pz) = p(*base), p(*pointe)
        angle = math.degrees(math.atan2(px - bx, pz - bz))
        feuille(nom, (bx, devant, bz), math.hypot(px - bx, pz - bz), demi_largeur, angle, iv, courbure=0.06,
                rondeur=0.8, evasement=0.0)


def garp_etiquette():
    """Une étiquette de prix ivoire, traversée par une courbe de cours en métal ocre qui monte."""
    iv = ivoire()
    trait("etiquette", [(-0.9, 0.5), (0.25, 0.5), (0.85, 0.0), (0.25, -0.5), (-0.9, -0.5), (-0.9, 0.5)], 0.075, iv)
    sphere("oeillet", (0.4, 0, 0), 0.1, iv)
    trait("cours", [(-0.7, -0.3), (-0.4, -0.1), (-0.15, -0.175), (0.15, 0.2)], 0.075, ocre_metal())
    for o in [o for o in bpy.context.scene.objects if o.name.startswith("cours")]:
        o.location.y -= 0.08


GARP = {"garp_zone": garp_zone, "garp_g": garp_g, "garp_balance": garp_balance, "garp_points": garp_points,
        "garp_pousse": garp_pousse, "garp_etiquette": garp_etiquette}

PREMIUM = {"apex", "pic", "ascension", "lame", "c_cours", "c_cours_ivoire", "c_bougies", "c_sommets",
           "lame_barres", "lame_barres_ivoire", "lame_barres_fines", "c_expo", "c_expo_rond", "c_expo_facettes",
           "expo_anthracite_ocre", "expo_ocre_anthracite", "expo_ivoire_ocre", *GARP}
CONCEPTS = {"pousse": pousse, "canopee": canopee, "sommet": sommet, "percee": percee, "elan": elan,
            "exponentielle": exponentielle, "chevrons": chevrons, "cime": cime,
            "apex": apex, "pic": pic, "ascension": ascension, "lame": lame,
            "c_cours": c_cours, "c_cours_ivoire": c_cours_ivoire, "c_bougies": c_bougies, "c_sommets": c_sommets,
            "lame_barres": lame_barres, "lame_barres_ivoire": lame_barres_ivoire,
            "lame_barres_fines": lame_barres_fines,
            "c_expo": c_expo, "c_expo_rond": c_expo_rond, "c_expo_facettes": c_expo_facettes,
            "expo_anthracite_ocre": expo_anthracite_ocre, "expo_ocre_anthracite": expo_ocre_anthracite,
            "expo_ivoire_ocre": expo_ivoire_ocre, **GARP}


# ------------------------------------------------------------------------------------------ rendu

def cadrer_et_eclairer(taille, premium=False):
    objets = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    # Un quart de tour vers la caméra donne du relief.
    pivot = bpy.data.objects.new("pivot", None)
    bpy.context.collection.objects.link(pivot)
    for o in objets:
        o.parent = pivot
    pivot.rotation_euler = (math.radians(6), 0, math.radians(-14))
    bpy.context.view_layer.update()
    coins = [o.matrix_world @ Vector(c) for o in objets for c in o.bound_box]
    mini = Vector([min(c[i] for c in coins) for i in range(3)])
    maxi = Vector([max(c[i] for c in coins) for i in range(3)])
    centre = (mini + maxi) / 2
    etendue = max(maxi.x - mini.x, maxi.z - mini.z)

    cam_data = bpy.data.cameras.new("camera")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = etendue * 1.08
    cam = bpy.data.objects.new("camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (centre.x, centre.y - 12, centre.z)
    cam.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.scene.camera = cam

    def soleil(nom, force, rotation, taille_angle=12):
        d = bpy.data.lights.new(nom, "SUN")
        d.energy = force
        d.angle = math.radians(taille_angle)
        o = bpy.data.objects.new(nom, d)
        bpy.context.collection.objects.link(o)
        o.rotation_euler = tuple(math.radians(a) for a in rotation)

    soleil("principale", 2.6, (50, -35, -30))
    soleil("appoint", 0.7, (70, 40, 40), 30)
    soleil("contre", 1.6, (-60, 0, 160), 8)

    monde = bpy.data.worlds.new("monde")
    monde.use_nodes = True
    if premium:
        # Le métal reflète son entourage : deux grandes boîtes à lumière de studio, un fond chaud et sombre.
        for nom, force, pos in (("boite_gauche", 900, (-6, -7, 4)), ("boite_haut", 600, (3, -5, 8))):
            d = bpy.data.lights.new(nom, "AREA")
            d.energy, d.shape, d.size, d.size_y = force, "RECTANGLE", 6, 2.5
            o = bpy.data.objects.new(nom, d)
            bpy.context.collection.objects.link(o)
            o.location = (centre.x + pos[0], centre.y + pos[1], centre.z + pos[2])
            o.rotation_euler = (centre - o.location).to_track_quat("-Z", "Y").to_euler()
        couleur, force_monde = (0.42, 0.40, 0.37, 1), 0.45
    else:
        couleur, force_monde = (0.55, 0.65, 0.75, 1), 0.55
    monde.node_tree.nodes["Background"].inputs["Color"].default_value = couleur
    monde.node_tree.nodes["Background"].inputs["Strength"].default_value = force_monde
    bpy.context.scene.world = monde

    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = 96
    s.cycles.use_denoising = True
    s.render.film_transparent = True
    s.render.resolution_x = s.render.resolution_y = taille
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA"
    s.view_settings.view_transform = "Standard"


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sortie = Path(args[0] if args else "rendus")
    sortie.mkdir(parents=True, exist_ok=True)
    for nom in args[1:] or list(CONCEPTS):
        vider_scene()
        CONCEPTS[nom]()
        cadrer_et_eclairer(1024, premium=nom in PREMIUM)
        bpy.context.scene.render.filepath = str((sortie / f"{nom}.png").resolve())
        bpy.ops.render.render(write_still=True)
        print("rendu", nom)


main()
