import cv2
import numpy as np
from lire_score import ancrage_blindé, trouver_rangees_chiffres


def detecter_digits_par_contours(bande_gray, nb_attendus=3):
    """
    Trouve les bounding boxes des chiffres dans une bande en cherchant
    les grands composants connexes, plutôt qu'en découpant en tiers égaux.
    Retourne une liste de (x, y, w, h) triés par x, dans les coordonnées de la bande.
    """
    _, bin_img = cv2.threshold(bande_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)

    # Chiffres = pixels sombres
    inv = cv2.bitwise_not(bin_img)

    # Fermeture légère pour relier les segments d'un même chiffre
    kernel = np.ones((5, 3), np.uint8)
    fermé = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(fermé, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h_bande, w_bande = bande_gray.shape
    aire_min = (h_bande * w_bande) / (nb_attendus * 12)  # au moins ~8% de la surface d'une cellule

    boites = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        aire = cv2.contourArea(c)
        # Filtrer le bruit (trop petit) et les artefacts de bord (trop large)
        if aire > aire_min and w < w_bande * 0.6 and h > h_bande * 0.25:
            boites.append((x, y, w, h))

    # Fusionner les boites qui se chevauchent horizontalement (segments d'un même chiffre)
    boites = sorted(boites, key=lambda b: b[0])
    fusionnées = []
    for b in boites:
        bx, by, bw, bh = b
        if fusionnées and bx < fusionnées[-1][0] + fusionnées[-1][2] + 8:
            px, py, pw, ph = fusionnées[-1]
            nx = min(px, bx)
            ny = min(py, by)
            nw = max(px + pw, bx + bw) - nx
            nh = max(py + ph, by + bh) - ny
            fusionnées[-1] = (nx, ny, nw, nh)
        else:
            fusionnées.append(b)

    # Garder les nb_attendus plus grandes boites
    fusionnées = sorted(fusionnées, key=lambda b: b[2] * b[3], reverse=True)[:nb_attendus]
    return sorted(fusionnées, key=lambda b: b[0])


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
