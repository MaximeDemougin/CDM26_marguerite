import cv2
import numpy as np
import pytesseract


# ---------------------------------------------------------------------------
# Détection du panneau
# ---------------------------------------------------------------------------

def ancrage_blindé(img):
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
    seuil_sombre = max(20.0, profil.max() * 0.25)
    in_dark = profil > seuil_sombre

    bandes_sombres = []
    debut = None
    for i, val in enumerate(in_dark):
        if val and debut is None:
            debut = i
        elif not val and debut is not None:
            if i - debut > 5:
                bandes_sombres.append((debut, i))
            debut = None
    if debut is not None and h_img - debut > 5:
        bandes_sombres.append((debut, h_img))

    rangees = []
    for i, (_, fin) in enumerate(bandes_sombres):
        debut_suivant = bandes_sombres[i + 1][0] if i + 1 < len(bandes_sombres) else h_img
        if debut_suivant - fin > 10:
            rangees.append((fin, debut_suivant))

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

def lire_cellule(cellule_bgr):
    """
    Lit un chiffre dans une cellule BGR.
    Détecte le '1' par aspect ratio, utilise Tesseract pour les autres.
    """
    propre = masquer_marqueurs(cellule_bgr)
    gray = cv2.cvtColor(propre, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = max(1, 80 // h)
    grande = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    _, bin_img = cv2.threshold(grande, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)

    # Détection du '1' par aspect ratio
    contenu = cv2.bitwise_not(bin_img)
    coords = cv2.findNonZero(contenu)
    if coords is not None:
        _, _, cw, ch = cv2.boundingRect(coords)
        if ch > 0 and cw / ch < 0.38:
            return "1"

    # Tesseract pour les autres chiffres
    img_ocr = cv2.copyMakeBorder(bin_img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
    for psm in (8, 10, 13):
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

    rect = ancrage_blindé(img)
    if rect is None:
        raise RuntimeError("Panneau non détecté.")

    px, py, pw, ph = rect
    roi = img[py:py + ph, px:px + pw]
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    rangees, bandes_sombres, _ = trouver_rangees_chiffres(roi_gray)
    if len(rangees) < 2:
        raise RuntimeError(f"Seulement {len(rangees)} rangée(s) détectée(s), attendu 2.")

    labels = ["VISITEUR", "CLUB"]
    score = {}
    debug = img.copy()
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

            # Dessin debug
            ax1, ay1 = px + bx, py + y1 + 3 + by
            cv2.rectangle(debug, (ax1, ay1), (ax1 + bw, ay1 + bh), couleur, 2)
            cv2.putText(debug, chiffre, (ax1 + 3, ay1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)

        score[labels[idx]] = chiffres
        cv2.putText(debug, f"{labels[idx]}: {' | '.join(chiffres)}",
                    (px + 2, py + y1 - 4),
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
