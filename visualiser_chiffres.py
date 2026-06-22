import cv2
import numpy as np
from lire_score import ancrage_blindé, trouver_rangees_chiffres


def masquer_marqueurs(bande_bgr):
    """
    Met à blanc les pixels colorés (marqueurs roses/magenta) en HSV.
    Retourne une image BGR nettoyée.
    """
    hsv = cv2.cvtColor(bande_bgr, cv2.COLOR_BGR2HSV)
    # Rose/magenta : teinte 140-180 ou 0-10, saturation > 80
    masque1 = cv2.inRange(hsv, (140, 80, 80), (180, 255, 255))
    masque2 = cv2.inRange(hsv, (0,  80, 80), (10,  255, 255))
    masque = cv2.bitwise_or(masque1, masque2)
    résultat = bande_bgr.copy()
    résultat[masque > 0] = (255, 255, 255)   # remplacer par blanc
    return résultat


def detecter_digits_par_projection(bande_bgr, nb_attendus=3):
    """
    Segmente les chiffres par projection verticale (somme de pixels sombres
    par colonne). Trouve les vallées entre chiffres sans morphologie.
    Retourne une liste de (x, y, w, h) dans les coordonnées de la bande.
    """
    bande_propre = masquer_marqueurs(bande_bgr)
    bande_gray = cv2.cvtColor(bande_propre, cv2.COLOR_BGR2GRAY)

    _, bin_img = cv2.threshold(bande_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)

    inv = cv2.bitwise_not(bin_img)           # pixels sombres = blanc
    projection = inv.sum(axis=0) / 255       # nb de pixels sombres par colonne

    # Lisser légèrement pour éviter les micro-vallées dans un chiffre
    kernel_lisse = np.ones(5) / 5
    proj_lissée = np.convolve(projection, kernel_lisse, mode='same')

    seuil = proj_lissée.max() * 0.08         # vallée = < 8 % du maximum
    est_chiffre = proj_lissée > seuil

    # Extraire les segments continus de colonnes "avec du contenu"
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

    # Fusionner les segments trop proches (< 4 px de gap)
    fusionnés = [segments[0]]
    for x1, x2 in segments[1:]:
        if x1 - fusionnés[-1][1] < 4:
            fusionnés[-1] = (fusionnés[-1][0], x2)
        else:
            fusionnés.append((x1, x2))

    # Si trop de segments, garder les nb_attendus les plus larges
    if len(fusionnés) > nb_attendus:
        fusionnés = sorted(fusionnés, key=lambda s: s[1] - s[0], reverse=True)[:nb_attendus]
        fusionnés = sorted(fusionnés, key=lambda s: s[0])

    # Construire les bounding boxes (x, y, w, h) dans la bande
    h_bande = bande_gray.shape[0]
    boites = []
    for x1, x2 in fusionnés:
        # Trouver l'étendue verticale réelle du chiffre dans cette colonne
        col_slice = inv[:, x1:x2]
        lignes = np.where(col_slice.sum(axis=1) > 0)[0]
        if len(lignes) == 0:
            continue
        y1_digit = int(lignes[0])
        y2_digit = int(lignes[-1]) + 1
        boites.append((x1, y1_digit, x2 - x1, y2_digit - y1_digit))

    return boites


def visualiser_chiffres(chemin_image, nb_cols=3):
    img = cv2.imread(chemin_image)
    if img is None:
        raise FileNotFoundError(f"Image introuvable : {chemin_image}")

    rect = ancrage_blindé(img)
    if rect is None:
        raise RuntimeError("Panneau non détecté.")

    px, py, pw, ph = rect
    roi = img[py:py + ph, px:px + pw]
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    rangees, _, _ = trouver_rangees_chiffres(roi_gray)

    debug = img.copy()
    labels = ["VISITEUR", "CLUB"]
    couleurs = [(0, 220, 0), (0, 80, 255)]

    for idx, (y1, y2) in enumerate(rangees[:2]):
        couleur = couleurs[idx]
        bande_bgr  = roi[y1 + 3:y2, :]

        boites = detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols)

        for col, (bx, by, bw, bh) in enumerate(boites):
            abs_x1 = px + bx
            abs_y1 = py + y1 + 3 + by
            abs_x2 = abs_x1 + bw
            abs_y2 = abs_y1 + bh

            # Fond semi-transparent
            overlay = debug.copy()
            cv2.rectangle(overlay, (abs_x1, abs_y1), (abs_x2, abs_y2), couleur, -1)
            cv2.addWeighted(overlay, 0.15, debug, 0.85, 0, debug)

            # Contour du rectangle
            cv2.rectangle(debug, (abs_x1, abs_y1), (abs_x2, abs_y2), couleur, 2)

            # Numéro de colonne
            cv2.putText(debug, str(col + 1),
                        (abs_x1 + 3, abs_y1 + 13),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, couleur, 1)

        # Label de la rangée
        cv2.putText(debug, labels[idx],
                    (px + 2, py + y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, couleur, 2)

    sortie = "visualisation_chiffres.jpg"
    cv2.imwrite(sortie, debug)
    print(f"Sauvegardé : {sortie}")


if __name__ == "__main__":
    import sys
    chemin = sys.argv[1] if len(sys.argv) > 1 else "score_brut_cropped_terrain1_2025-07-11_13-30-15.jpg"
    visualiser_chiffres(chemin)
