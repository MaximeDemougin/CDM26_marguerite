import cv2
import numpy as np
import pytesseract


# ---------------------------------------------------------------------------
# Détection du panneau avec correction de perspective
# ---------------------------------------------------------------------------

def _ordonner_coins(pts):
    """Ordonne 4 points : top-left, top-right, bottom-right, bottom-left.
    Tri par Y puis X : robuste à la rotation (sum/diff échoue >5°)."""
    pts = pts.astype(np.float32)
    sorted_y = pts[np.argsort(pts[:, 1])]      # tri par Y croissant
    top = sorted_y[:2][np.argsort(sorted_y[:2, 0])]   # 2 haut → X croissant
    bot = sorted_y[2:][np.argsort(sorted_y[2:, 0])]   # 2 bas  → X croissant
    return np.array([top[0], top[1], bot[1], bot[0]], dtype=np.float32)
    # ordre : TL, TR, BR, BL


def _trouver_contour_panneau(thresh, kernel, min_w=150, min_h=50):
    """Fermeture + extraction du plus grand contour dépassant les seuils."""
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valides = [(c, cv2.boundingRect(c)) for c in contours
               if cv2.boundingRect(c)[2] > min_w and cv2.boundingRect(c)[3] > min_h]
    if not valides:
        return None, closed
    # Le panneau est le plus grand blob valide
    best = max(valides, key=lambda x: cv2.contourArea(x[0]))
    return best[0], closed


def detecter_et_redresser(img, debug_dir=None):
    """
    Détecte le panneau de score et retourne un ROI redressé à plat.
    Si debug_dir est fourni, sauvegarde les étapes internes du deskew.
    """
    import os

    def _dbg(nom, image):
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(os.path.join(debug_dir, nom), image)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Lissage léger : réduit le bruit gaussien (σ≈12) sans effacer les bords
    gray_smooth = cv2.GaussianBlur(gray, (5, 5), 0)

    # ── Stratégie 1 : panneau BLANC sur fond gris (seuil fixe 200) ──────────
    # Panneau blanc ~220-250, mur gris ~120-160 → seuil 200 isole le blanc.
    # Fermeture pour boucher les bandes sombres intérieures (max 40 px).
    _, thresh_bright = cv2.threshold(gray_smooth, 200, 255, cv2.THRESH_BINARY)
    _dbg("dsk0_thresh.jpg", thresh_bright)

    contour = None
    closed_dbg = thresh_bright
    for k_size in (40, 30, 20):
        k = np.ones((k_size, k_size), np.uint8)
        c, closed = _trouver_contour_panneau(thresh_bright, k)
        if c is not None:
            contour = c
            closed_dbg = closed
            break

    # ── Stratégie 2 : contenu sombre avec très grand noyau ──────────────────
    if contour is None:
        _, thresh_dark = cv2.threshold(gray_smooth, 90, 255, cv2.THRESH_BINARY_INV)
        _dbg("dsk0b_thresh_dark.jpg", thresh_dark)
        for k_size in (60, 50, 40, 30, 20):
            k = np.ones((k_size, k_size), np.uint8)
            c, closed = _trouver_contour_panneau(thresh_dark, k)
            if c is not None:
                contour = c
                closed_dbg = closed
                break

    if contour is None:
        return None

    _dbg("dsk1_closed.jpg", closed_dbg)

    # Contour sélectionné sur l'image originale
    if debug_dir:
        vis_contour = img.copy()
        cv2.drawContours(vis_contour, [contour], -1, (0, 255, 0), 2)
        _dbg("dsk2_contour.jpg", vis_contour)

    # minAreaRect sur le hull : toujours exactement 4 coins bien placés,
    # robuste à la rotation, pas sensible à l'irrégularité du blob.
    hull = cv2.convexHull(contour)
    rect = cv2.minAreaRect(hull)
    pts = cv2.boxPoints(rect)
    coins = _ordonner_coins(pts)
    tl, tr, br, bl = coins

    W = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    H = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))

    if W < H:
        W, H = H, W
        coins = _ordonner_coins(np.array([tr, br, bl, tl]))

    # 4 coins retenus sur l'image originale
    if debug_dir:
        vis_coins = img.copy()
        labels_c = ["TL", "TR", "BR", "BL"]
        couleurs_c = [(0,255,0),(0,200,255),(0,0,255),(255,0,0)]
        for pt, label, col in zip(coins, labels_c, couleurs_c):
            px, py = int(pt[0]), int(pt[1])
            cv2.circle(vis_coins, (px, py), 8, col, -1)
            cv2.putText(vis_coins, label, (px + 6, py - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
        _dbg("dsk3_coins.jpg", vis_coins)

    PAD = 14
    dst = np.array([
        [PAD,         PAD        ],
        [W - 1 + PAD, PAD        ],
        [W - 1 + PAD, H - 1 + PAD],
        [PAD,         H - 1 + PAD],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(coins, dst)
    roi = cv2.warpPerspective(img, M, (W + 2 * PAD, H + 2 * PAD))
    _dbg("dsk4_warp.jpg", roi)

    # ── Recadrage sur la zone blanche du panneau ─────────────────────────────
    # Le warp peut inclure du mur gris autour du panneau.
    # On détecte les lignes/colonnes dominées par le blanc (>180) et on recadre.
    wg = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, wmask = cv2.threshold(wg, 180, 255, cv2.THRESH_BINARY)
    rows_ok = np.where(wmask.mean(axis=1) > 40)[0]
    cols_ok = np.where(wmask.mean(axis=0) > 40)[0]
    if len(rows_ok) > 20 and len(cols_ok) > 20:
        r0, r1 = max(0, rows_ok[0] - 4), min(roi.shape[0], rows_ok[-1] + 4)
        c0, c1 = max(0, cols_ok[0] - 4), min(roi.shape[1], cols_ok[-1] + 4)
        roi = roi[r0:r1, c0:c1]
    _dbg("dsk5_crop.jpg", roi)
    return roi


# Alias pour compatibilité avec visualiser_chiffres.py
def ancrage_blindé(img):
    """Retourne (x, y, w, h) du panneau — maintenu pour compatibilité."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 90, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((10, 40), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidats = [(x, y, w, h) for c in contours
                 for x, y, w, h in [cv2.boundingRect(c)]
                 if w > 200 and h > 20]
    if not candidats:
        return None
    return sorted(candidats, key=lambda b: b[1])[0]


def trouver_rangees_chiffres(roi_gray):
    h_img = roi_gray.shape[0]
    _, dark = cv2.threshold(roi_gray, 80, 255, cv2.THRESH_BINARY_INV)
    profil = dark.mean(axis=1)

    def _detecter_bandes(facteur):
        seuil = max(15.0, profil.max() * facteur)
        active = profil > seuil
        bandes = []
        debut = None
        for i, v in enumerate(active):
            if v and debut is None:
                debut = i
            elif not v and debut is not None:
                if i - debut > 5:
                    bandes.append((debut, i))
                debut = None
        if debut is not None and h_img - debut > 5:
            bandes.append((debut, h_img))
        return bandes

    # Essai à 0.25 d'abord ; si insuffisant, descendre à 0.15
    bandes_sombres = _detecter_bandes(0.25)
    if len(bandes_sombres) < 2:
        bandes_sombres = _detecter_bandes(0.15)

    rangees = []
    for i, (_, fin) in enumerate(bandes_sombres):
        debut_suivant = bandes_sombres[i + 1][0] if i + 1 < len(bandes_sombres) else h_img
        if debut_suivant - fin > 15:
            rangees.append((fin, debut_suivant))

    # Garder les 2 zones les plus hautes (= vraies rangées de chiffres)
    # Protège contre les fausses bandes de la publicité en haut du panneau
    if len(rangees) > 2:
        rangees = sorted(rangees, key=lambda r: r[1] - r[0], reverse=True)[:2]
        rangees = sorted(rangees, key=lambda r: r[0])

    return rangees, bandes_sombres, profil


# ---------------------------------------------------------------------------
# Segmentation des chiffres par projection verticale
# ---------------------------------------------------------------------------

def masquer_marqueurs(bande_bgr):
    """Efface les marqueurs roses/magenta (points de keypoints) en blanc."""
    hsv = cv2.cvtColor(bande_bgr, cv2.COLOR_BGR2HSV)
    masque1 = cv2.inRange(hsv, (140, 80, 80), (180, 255, 255))
    masque2 = cv2.inRange(hsv, (0,   80, 80), (10,  255, 255))
    masque = cv2.bitwise_or(masque1, masque2)
    résultat = bande_bgr.copy()
    résultat[masque > 0] = (255, 255, 255)
    return résultat


def etendue_verticale(inv_slice):
    """Retourne (y_debut, hauteur) du bloc de lignes le plus dense et continu."""
    h, w = inv_slice.shape
    if w == 0:
        return 0, h
    densite = inv_slice.sum(axis=1) / 255
    if densite.max() == 0:
        return 0, h
    seuil = densite.max() * 0.15
    active = densite > seuil
    segments = []
    debut = None
    for i, v in enumerate(active):
        if v and debut is None:
            debut = i
        elif not v and debut is not None:
            segments.append((debut, i))
            debut = None
    if debut is not None:
        segments.append((debut, h))
    if not segments:
        return 0, h
    y1, y2 = max(segments, key=lambda s: s[1] - s[0])
    return y1, y2 - y1


def _binariser(bande_bgr):
    propre = masquer_marqueurs(bande_bgr)
    gray = cv2.cvtColor(propre, cv2.COLOR_BGR2GRAY)
    _, bin_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)
    return cv2.bitwise_not(bin_img)   # inv : chiffre = blanc


def detecter_digits_par_projection(bande_bgr, nb_attendus=3):
    """Segmente les chiffres par projection verticale. Retourne [(x,y,w,h), ...]."""
    inv = _binariser(bande_bgr)
    projection = inv.sum(axis=0) / 255
    proj_lissée = np.convolve(projection, np.ones(3) / 3, mode='same')

    seuil = proj_lissée.max() * 0.06
    est_chiffre = proj_lissée > seuil

    segments = []
    debut = None
    for i, val in enumerate(est_chiffre):
        if val and debut is None:
            debut = i
        elif not val and debut is not None:
            segments.append((debut, i))
            debut = None
    if debut is not None:
        segments.append((debut, len(est_chiffre)))
    if not segments:
        return []

    fusionnés = [list(segments[0])]
    for x1, x2 in segments[1:]:
        if x1 - fusionnés[-1][1] < 3:
            fusionnés[-1][1] = x2
        else:
            fusionnés.append([x1, x2])

    h_bande, w_bande = inv.shape
    largeur_max = w_bande / nb_attendus * 1.4
    segments_finaux = []
    for x1, x2 in fusionnés:
        if x2 - x1 > largeur_max:
            creux = int(np.argmin(proj_lissée[x1:x2])) + x1
            if x1 < creux < x2 - 1:
                segments_finaux += [[x1, creux], [creux, x2]]
                continue
        segments_finaux.append([x1, x2])

    marge = int(w_bande * 0.05)
    segments_finaux = [s for s in segments_finaux if s[0] >= marge and s[1] <= w_bande - marge]

    if len(segments_finaux) > nb_attendus:
        segments_finaux = sorted(segments_finaux, key=lambda s: s[1] - s[0], reverse=True)[:nb_attendus]
        segments_finaux = sorted(segments_finaux, key=lambda s: s[0])

    boites = []
    for x1, x2 in segments_finaux:
        ry, rh = etendue_verticale(inv[:, x1:x2])
        boites.append((x1, ry, x2 - x1, rh))
    return boites


def boites_depuis_colonnes_ref(bande_bgr, colonnes_x):
    """Pour CLUB : cherche les chiffres dans les mêmes colonnes x que VISITEUR."""
    inv = _binariser(bande_bgr)
    h_bande, w_bande = inv.shape

    boites = []
    for x1_ref, x2_ref in colonnes_x:
        marge = 20
        x1 = max(0, x1_ref - marge)
        x2 = min(w_bande, x2_ref + marge)

        proj_col = inv[:, x1:x2].sum(axis=0) / 255
        actives = proj_col > h_bande * 0.15

        centre_ref = (x1_ref + x2_ref) / 2
        segs = []
        debut = None
        for i, val in enumerate(actives):
            if val and debut is None:
                debut = i
            elif not val and debut is not None:
                segs.append((x1 + debut, x1 + i))
                debut = None
        if debut is not None:
            segs.append((x1 + debut, x1 + len(actives)))

        segs = [(s1, s2) for s1, s2 in segs if s2 - s1 > 3]
        if not segs:
            boites.append((x1_ref, 0, x2_ref - x1_ref, h_bande))
            continue

        sx1, sx2 = min(segs, key=lambda s: abs((s[0] + s[1]) / 2 - centre_ref))
        ry, rh = etendue_verticale(inv[:, sx1:sx2])
        boites.append((sx1, ry, sx2 - sx1, rh))
    return boites


# ---------------------------------------------------------------------------
# Lecture OCR d'une cellule
# ---------------------------------------------------------------------------

def _est_un(bin_img):
    """
    Détecte le chiffre '1' par deux critères combinés :
    - aspect ratio étroit (largeur/hauteur du contenu < 0.50)
    - fill rate faible (pixels noirs / aire bbox < 0.40) — un '1' est un trait fin
    Plus robuste qu'un seuil unique après warpPerspective qui élargit légèrement.
    """
    contenu = cv2.bitwise_not(bin_img)
    coords = cv2.findNonZero(contenu)
    if coords is None:
        return False
    _, _, cw, ch = cv2.boundingRect(coords)
    if ch == 0:
        return False
    ratio = cw / ch
    fill = np.count_nonzero(contenu) / (cw * ch) if cw * ch > 0 else 1.0
    # Critères stricts : un '4' noisy peut passer ratio<0.50, mais pas 0.40
    return ratio < 0.40 and fill < 0.38


def lire_cellule(cellule_bgr):
    """
    Lit un chiffre dans une cellule BGR.
    Détecte le '1' par forme (aspect + fill rate), Tesseract pour les autres.
    """
    if cellule_bgr.size == 0:
        return "?"

    propre = masquer_marqueurs(cellule_bgr)
    gray = cv2.cvtColor(propre, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Garantir une taille minimale pour Tesseract (min 100px de haut)
    scale = max(1, 100 // max(h, 1))
    grande = cv2.resize(gray, (max(w * scale, 40), max(h * scale, 100)),
                        interpolation=cv2.INTER_CUBIC)

    _, bin_otsu = cv2.threshold(grande, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_otsu) < 127:
        bin_otsu = cv2.bitwise_not(bin_otsu)

    if _est_un(bin_otsu):
        return "1"

    # Essayer aussi le seuillage adaptatif si Otsu donne un mauvais résultat
    bin_adapt = cv2.adaptiveThreshold(grande, 255,
                                      cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 15, 4)
    if np.mean(bin_adapt) < 127:
        bin_adapt = cv2.bitwise_not(bin_adapt)

    if _est_un(bin_adapt):
        return "1"

    # Tesseract : essayer les deux binarisations, garder le premier résultat
    for bin_img in (bin_otsu, bin_adapt):
        img_ocr = cv2.copyMakeBorder(bin_img, 20, 20, 20, 20,
                                     cv2.BORDER_CONSTANT, value=255)
        for psm in (8, 10, 13, 6):
            texte = pytesseract.image_to_string(
                img_ocr,
                config=f"--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789"
            ).strip()
            chiffres = [c for c in texte if c.isdigit()]
            if chiffres:
                return chiffres[0]
    return "?"


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def lire_score(chemin_image, nb_cols=3):
    img = cv2.imread(chemin_image)
    if img is None:
        raise FileNotFoundError(f"Image introuvable : {chemin_image}")

    roi = detecter_et_redresser(img)
    if roi is None:
        raise RuntimeError("Panneau non détecté.")

    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    rangees, _, _ = trouver_rangees_chiffres(roi_gray)
    if len(rangees) < 2:
        raise RuntimeError(f"Seulement {len(rangees)} rangée(s) détectée(s), attendu 2.")

    labels = ["VISITEUR", "CLUB"]
    score = {}
    debug = roi.copy()
    colonnes_ref = None

    for idx, (y1, y2) in enumerate(rangees[:2]):
        bande_bgr = roi[y1 + 3:y2, :]

        if idx == 0:
            boites = detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols)
            colonnes_ref = [(bx, bx + bw) for bx, _, bw, _ in boites]
        else:
            boites = (boites_depuis_colonnes_ref(bande_bgr, colonnes_ref)
                      if colonnes_ref
                      else detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols))

        chiffres = []
        couleur = (0, 220, 0) if idx == 0 else (0, 80, 255)
        for bx, by, bw, bh in boites:
            cellule = bande_bgr[by:by + bh, bx:bx + bw]
            chiffre = lire_cellule(cellule)
            chiffres.append(chiffre)

            ax1, ay1 = bx, y1 + 3 + by
            cv2.rectangle(debug, (ax1, ay1), (ax1 + bw, ay1 + bh), couleur, 2)
            cv2.putText(debug, chiffre, (ax1 + 3, ay1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)

        score[labels[idx]] = chiffres
        cv2.putText(debug, f"{labels[idx]}: {' | '.join(chiffres)}",
                    (4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)

    cv2.imwrite("score_resultat.jpg", debug)
    return score


if __name__ == "__main__":
    import sys
    chemin = sys.argv[1] if len(sys.argv) > 1 else "score_brut_cropped_terrain1_2025-07-11_13-30-15.jpg"
    try:
        score = lire_score(chemin)
        print("=== Score détecté ===")
        for equipe, chiffres in score.items():
            print(f"  {equipe} : {' | '.join(chiffres)}")
        print("Résultat sauvegardé dans score_resultat.jpg")
    except Exception as e:
        print(f"Erreur : {e}")
