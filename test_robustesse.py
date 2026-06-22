"""
Script de test de robustesse : génère des images transformées (rotation,
perspective, bruit) et exécute le pipeline complet en sauvegardant toutes
les étapes intermédiaires.
"""
import cv2
import numpy as np
import os
import sys
from lire_score import (
    detecter_et_redresser, trouver_rangees_chiffres,
    detecter_digits_par_projection, boites_depuis_colonnes_ref,
    lire_cellule, masquer_marqueurs, _binariser, etendue_verticale
)


# ---------------------------------------------------------------------------
# Générateurs de transformations
# ---------------------------------------------------------------------------

def rotation(img, angle_deg):
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    # Calculer la nouvelle taille pour ne rien rogner
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw = int(h * sin + w * cos)
    nh = int(h * cos + w * sin)
    M[0, 2] += (nw - w) / 2
    M[1, 2] += (nh - h) / 2
    fond = img.copy()
    # Remplir le fond de la couleur dominante du bord (mur blanc)
    couleur_fond = tuple(int(v) for v in img[0, 0])
    return cv2.warpAffine(fond, M, (nw, nh),
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=couleur_fond)


def perspective(img, force=0.05):
    """Déformation trapézoïdale simulant un angle de caméra."""
    h, w = img.shape[:2]
    dx = int(w * force)
    dy = int(h * force)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[dx, dy], [w - dx, 0], [w, h], [0, h - dy]])
    M = cv2.getPerspectiveTransform(src, dst)
    couleur_fond = tuple(int(v) for v in img[0, 0])
    return cv2.warpPerspective(img, M, (w, h),
                               borderMode=cv2.BORDER_CONSTANT,
                               borderValue=couleur_fond)


def bruit_gaussien(img, sigma=8):
    bruit = np.random.normal(0, sigma, img.shape).astype(np.int16)
    return np.clip(img.astype(np.int16) + bruit, 0, 255).astype(np.uint8)


def translation(img, dx, dy):
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    couleur_fond = tuple(int(v) for v in img[0, 0])
    return cv2.warpAffine(img, M, (w, h),
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=couleur_fond)


# ---------------------------------------------------------------------------
# Pipeline avec sauvegarde de toutes les étapes intermédiaires
# ---------------------------------------------------------------------------

def pipeline_debug(img_transformée, dossier, nb_cols=3):
    """
    Exécute le pipeline complet et sauvegarde chaque étape dans `dossier`.
    Retourne le score détecté ou None en cas d'échec.
    """
    os.makedirs(dossier, exist_ok=True)

    # ── Étape 0 : image d'entrée ──────────────────────────────────────────
    cv2.imwrite(f"{dossier}/0_entree.jpg", img_transformée)

    # ── Étape 1 : détection et redressement ───────────────────────────────
    roi = detecter_et_redresser(img_transformée)
    if roi is None:
        _ecrire_texte(img_transformée, "PANNEAU NON DÉTECTÉ",
                      f"{dossier}/ECHEC_detection.jpg")
        return None
    cv2.imwrite(f"{dossier}/1_roi_redresse.jpg", roi)

    # ── Étape 2 : masquage des marqueurs ──────────────────────────────────
    roi_propre = masquer_marqueurs(roi)
    cv2.imwrite(f"{dossier}/2_marqueurs_masques.jpg", roi_propre)

    # ── Étape 3 : détection des rangées (profil horizontal) ───────────────
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    rangees, bandes_sombres, profil = trouver_rangees_chiffres(roi_gray)

    annote = roi.copy()
    for y1, y2 in bandes_sombres:
        cv2.rectangle(annote, (0, y1), (roi.shape[1], y2), (0, 0, 200), 2)
    for y1, y2 in rangees:
        cv2.rectangle(annote, (0, y1), (roi.shape[1], y2), (0, 200, 0), 2)
    cv2.imwrite(f"{dossier}/3_rangees_detectees.jpg", annote)

    if len(rangees) < 2:
        _ecrire_texte(roi, f"RANGÉES INSUFFISANTES ({len(rangees)}/2)",
                      f"{dossier}/ECHEC_rangees.jpg")
        return None

    # ── Étape 4 : bandes de chiffres brutes ───────────────────────────────
    labels = ["VISITEUR", "CLUB"]
    couleurs = [(0, 220, 0), (0, 80, 255)]
    score = {}
    colonnes_ref = None
    debug_final = roi.copy()

    for idx, (y1, y2) in enumerate(rangees[:2]):
        bande_bgr = roi[y1 + 3:y2, :]
        cv2.imwrite(f"{dossier}/4_bande_{labels[idx].lower()}_brute.jpg", bande_bgr)

        # ── Étape 5 : binarisation de la bande ───────────────────────────
        inv = _binariser(bande_bgr)
        cv2.imwrite(f"{dossier}/5_bande_{labels[idx].lower()}_binarisee.jpg",
                    cv2.bitwise_not(inv))

        # ── Étape 6 : projection verticale ───────────────────────────────
        proj = inv.sum(axis=0) / 255
        proj_img = _dessiner_projection(proj, inv.shape[0])
        cv2.imwrite(f"{dossier}/6_projection_{labels[idx].lower()}.jpg", proj_img)

        # ── Étape 7 : détection des boîtes ───────────────────────────────
        couleur = couleurs[idx]
        if idx == 0:
            boites = detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols)
            colonnes_ref = [(bx, bx + bw) for bx, _, bw, _ in boites]
        else:
            boites = (boites_depuis_colonnes_ref(bande_bgr, colonnes_ref)
                      if colonnes_ref
                      else detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols))

        bande_boites = bande_bgr.copy()
        for bx, by, bw, bh in boites:
            cv2.rectangle(bande_boites, (bx, by), (bx + bw, by + bh), couleur, 2)
        cv2.imwrite(f"{dossier}/7_boites_{labels[idx].lower()}.jpg", bande_boites)

        # ── Étape 8 : cellules individuelles + OCR ────────────────────────
        chiffres = []
        for i, (bx, by, bw, bh) in enumerate(boites):
            cellule = bande_bgr[by:by + bh, bx:bx + bw]
            cv2.imwrite(f"{dossier}/8_cellule_{labels[idx].lower()}_{i}.jpg", cellule)
            chiffre = lire_cellule(cellule)
            chiffres.append(chiffre)

            # Résultat sur le debug final
            ax1, ay1 = bx, y1 + 3 + by
            cv2.rectangle(debug_final, (ax1, ay1), (ax1 + bw, ay1 + bh), couleur, 2)
            cv2.putText(debug_final, chiffre, (ax1 + 3, ay1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, couleur, 2)

        score[labels[idx]] = chiffres
        cv2.putText(debug_final, f"{labels[idx]}: {' | '.join(chiffres)}",
                    (4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)

    cv2.imwrite(f"{dossier}/9_resultat_final.jpg", debug_final)
    return score


# ---------------------------------------------------------------------------
# Helpers de visualisation
# ---------------------------------------------------------------------------

def _dessiner_projection(proj, hauteur):
    """Transforme un vecteur de projection en image visualisable."""
    w = len(proj)
    h = 120
    img = np.ones((h, w, 3), dtype=np.uint8) * 240
    max_val = proj.max() if proj.max() > 0 else 1
    for x, val in enumerate(proj):
        bar_h = int(val / max_val * (h - 10))
        cv2.line(img, (x, h), (x, h - bar_h), (50, 50, 200), 1)
    # Ligne de seuil à 6 %
    seuil_y = h - int(0.06 * (h - 10))
    cv2.line(img, (0, seuil_y), (w, seuil_y), (0, 180, 0), 1)
    return img


def _ecrire_texte(img, texte, chemin):
    out = img.copy()
    cv2.putText(out, texte, (10, 40), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 0, 255), 2)
    cv2.imwrite(chemin, out)


# ---------------------------------------------------------------------------
# Cas de test
# ---------------------------------------------------------------------------

TRANSFORMATIONS = [
    ("00_original",          lambda img: img.copy()),
    ("01_rotation_+5deg",    lambda img: rotation(img,  5)),
    ("02_rotation_+10deg",   lambda img: rotation(img, 10)),
    ("03_rotation_+15deg",   lambda img: rotation(img, 15)),
    ("04_rotation_-5deg",    lambda img: rotation(img, -5)),
    ("05_rotation_-10deg",   lambda img: rotation(img, -10)),
    ("06_rotation_-15deg",   lambda img: rotation(img, -15)),
    ("07_perspective_faible",lambda img: perspective(img, 0.04)),
    ("08_perspective_forte", lambda img: perspective(img, 0.09)),
    ("09_translation",       lambda img: translation(img, 30, 20)),
    ("10_bruit",             lambda img: bruit_gaussien(img, 12)),
    ("11_rotation+bruit",    lambda img: bruit_gaussien(rotation(img, 8), 10)),
]


def main(chemin_image):
    img = cv2.imread(chemin_image)
    if img is None:
        print(f"Image introuvable : {chemin_image}")
        sys.exit(1)

    dossier_racine = "test_robustesse"
    os.makedirs(dossier_racine, exist_ok=True)

    resultats = []

    for nom, transformer in TRANSFORMATIONS:
        print(f"\n{'─'*50}")
        print(f"  Cas : {nom}")
        print(f"{'─'*50}")

        img_t = transformer(img)
        dossier = os.path.join(dossier_racine, nom)

        score = pipeline_debug(img_t, dossier)

        if score:
            for equipe, chiffres in score.items():
                print(f"  {equipe:10s}: {' | '.join(chiffres)}")
            resultats.append((nom, score, True))
        else:
            print("  ✗ Échec de détection")
            resultats.append((nom, None, False))

    # ── Résumé ──────────────────────────────────────────────────────────────
    print(f"\n{'═'*50}")
    print("  RÉSUMÉ")
    print(f"{'═'*50}")
    succes = sum(1 for _, _, ok in resultats if ok)
    print(f"  {succes}/{len(resultats)} cas réussis\n")
    for nom, score, ok in resultats:
        statut = "✓" if ok else "✗"
        if score:
            v = ' '.join(score.get('VISITEUR', ['?']))
            c = ' '.join(score.get('CLUB', ['?']))
            print(f"  {statut}  {nom:<30s}  VISITEUR={v}  CLUB={c}")
        else:
            print(f"  {statut}  {nom}")

    print(f"\n  Images dans : {dossier_racine}/")


if __name__ == "__main__":
    chemin = sys.argv[1] if len(sys.argv) > 1 else \
        "score_brut_cropped_terrain1_2025-07-11_13-30-15.jpg"
    main(chemin)
