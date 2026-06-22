import cv2
import numpy as np
import pytesseract


# ---------------------------------------------------------------------------
# Détection du panneau avec correction de perspective
# ---------------------------------------------------------------------------

def _ordonner_coins(pts):
    """Ordonne 4 points : top-left, top-right, bottom-right, bottom-left."""
    pts = pts.astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    return np.array([pts[np.argmin(s)],   # tl
                     pts[np.argmin(d)],   # tr
                     pts[np.argmax(s)],   # br
                     pts[np.argmax(d)]],  # bl
                    dtype=np.float32)


def _candidats_depuis_kernel(thresh, kernel, min_w=200, min_h=20):
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [(c, cv2.boundingRect(c)) for c in contours
            if cv2.boundingRect(c)[2] > min_w and cv2.boundingRect(c)[3] > min_h]


def detecter_et_redresser(img):
    """
    Détecte le panneau de score et retourne un ROI redressé à plat.
    Essaie plusieurs noyaux morphologiques pour être robuste à la rotation.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 90, 255, cv2.THRESH_BINARY_INV)

    # Kernels par ordre de préférence :
    # horizontal (fonctionne bien à 0°) → carré large (robuste jusqu'à ±20°)
    kernels = [
        np.ones((10, 40), np.uint8),   # horizontal — optimal à 0°
        np.ones((20, 20), np.uint8),   # carré — robuste en rotation
        np.ones((25, 25), np.uint8),   # plus grand si panneau plus éloigné
        np.ones((35, 35), np.uint8),   # très grand — rotation ±20° ou caméra loin
    ]

    candidats = []
    for k in kernels:
        candidats = _candidats_depuis_kernel(thresh, k)
        if candidats:
            break

    # Fallback : seuillage OTSU si threshold fixe à 90 ne suffit pas
    if not candidats:
        _, thresh_otsu = cv2.threshold(gray, 0, 255,
                                       cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        for k in kernels:
            candidats = _candidats_depuis_kernel(thresh_otsu, k)
            if candidats:
                break

    if not candidats:
        return None

    contour = sorted(candidats, key=lambda x: x[1][1])[0][0]

    # Chercher 4 coins via convex hull + epsilon croissant
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    pts = None
    for eps in (0.02, 0.04, 0.06, 0.08, 0.10, 0.15):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(-1, 2)
            break
    if pts is None:
        pts = cv2.boxPoints(cv2.minAreaRect(contour))

    coins = _ordonner_coins(pts)
    tl, tr, br, bl = coins

    W = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    H = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))

    if W < H:
        W, H = H, W
        coins = _ordonner_coins(np.array([tr, br, bl, tl]))

    # Marges autour du panneau : évite de rogner les chiffres en bord de ROI
    PAD = 14
    dst = np.array([
        [PAD,         PAD        ],
        [W - 1 + PAD, PAD        ],
        [W - 1 + PAD, H - 1 + PAD],
        [PAD,         H - 1 + PAD],
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(coins, dst)
    roi = cv2.warpPerspective(img, M, (W + 2 * PAD, H + 2 * PAD))
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
