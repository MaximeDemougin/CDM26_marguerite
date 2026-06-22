import cv2
import numpy as np
from lire_score import ancrage_blindé, trouver_rangees_chiffres


def detecter_digits_par_contours(bande_gray, nb_attendus=3):
    """
    Trouve les bounding boxes des chiffres dans une bande.
    Stratégie : on collecte tous les blobs significatifs, puis on divise
    la largeur en nb_attendus zones et on prend le meilleur blob dans chaque zone.
    Cela évite de rater le '1' (petite aire) ou les chiffres en bord de bande.
    Retourne une liste de (x, y, w, h) triés par x, dans les coords de la bande.
    """
    _, bin_img = cv2.threshold(bande_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)

    inv = cv2.bitwise_not(bin_img)

    # Fermeture pour relier les segments d'un même chiffre
    kernel = np.ones((5, 3), np.uint8)
    fermé = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(fermé, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h_bande, w_bande = bande_gray.shape

    # Seuils très permissifs — on veut attraper le '1' fin
    aire_min = h_bande * 3          # au moins 3 px de haut × 1 px de large
    h_min = h_bande * 0.20          # au moins 20 % de la hauteur de la bande
    w_max = w_bande * 0.65          # pas plus large que 65 % de la bande

    blobs = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        aire = w * h
        if aire > aire_min and h > h_min and w < w_max:
            blobs.append((x, y, w, h))

    if not blobs:
        return []

    # Fusionner les blobs qui se chevauchent horizontalement (ex : chiffre en 2 morceaux)
    blobs = sorted(blobs, key=lambda b: b[0])
    fusionnés = []
    for b in blobs:
        bx, by, bw, bh = b
        if fusionnés and bx < fusionnés[-1][0] + fusionnés[-1][2] + 6:
            px, py2, pw, ph = fusionnés[-1]
            nx = min(px, bx)
            ny = min(py2, by)
            nw = max(px + pw, bx + bw) - nx
            nh = max(py2 + ph, by + bh) - ny
            fusionnés[-1] = (nx, ny, nw, nh)
        else:
            fusionnés.append(b)

    # Diviser la largeur en nb_attendus zones et prendre le meilleur blob par zone
    zone_w = w_bande / nb_attendus
    résultat = []
    for i in range(nb_attendus):
        zone_x1 = i * zone_w
        zone_x2 = (i + 1) * zone_w
        # Blobs dont le centre est dans cette zone
        candidats = [b for b in fusionnés
                     if zone_x1 <= b[0] + b[2] / 2 < zone_x2]
        if candidats:
            # Prendre le plus grand
            meilleur = max(candidats, key=lambda b: b[2] * b[3])
            résultat.append(meilleur)

    return sorted(résultat, key=lambda b: b[0])


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
        bande_gray = roi_gray[y1 + 3:y2, :]

        boites = detecter_digits_par_contours(bande_gray, nb_attendus=nb_cols)

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
