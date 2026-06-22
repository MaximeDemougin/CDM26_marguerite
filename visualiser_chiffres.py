import cv2
import numpy as np
from lire_score import ancrage_blindé, trouver_rangees_chiffres


def trouver_rect_chiffre(cellule_gray):
    """Retourne le bounding rect du contenu sombre dans la cellule, ou None."""
    _, bin_img = cv2.threshold(cellule_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)
    # Chiffre = pixels sombres
    contenu = cv2.bitwise_not(bin_img)
    coords = cv2.findNonZero(contenu)
    if coords is None:
        return None
    return cv2.boundingRect(coords)


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

    rangees, bandes_sombres, _ = trouver_rangees_chiffres(roi_gray)

    debug = img.copy()
    labels = ["VISITEUR", "CLUB"]
    couleurs = [(0, 220, 0), (0, 80, 255)]  # vert / orange

    for idx, (y1, y2) in enumerate(rangees[:2]):
        couleur = couleurs[idx]
        bande_gray = roi_gray[y1 + 3:y2, :]
        h_bande, w_bande = bande_gray.shape
        largeur_col = w_bande // nb_cols

        for col in range(nb_cols):
            cx1 = col * largeur_col
            cx2 = cx1 + largeur_col
            cellule = bande_gray[:, cx1:cx2]

            rect_chiffre = trouver_rect_chiffre(cellule)

            # Rectangle de la colonne (fond semi-transparent)
            abs_x1 = px + cx1
            abs_y1 = py + y1 + 3
            abs_x2 = px + cx2
            abs_y2 = py + y2
            overlay = debug.copy()
            cv2.rectangle(overlay, (abs_x1, abs_y1), (abs_x2, abs_y2), couleur, -1)
            cv2.addWeighted(overlay, 0.12, debug, 0.88, 0, debug)
            cv2.rectangle(debug, (abs_x1, abs_y1), (abs_x2, abs_y2), couleur, 1)

            # Rectangle serré autour du chiffre détecté
            if rect_chiffre is not None:
                rx, ry, rw, rh = rect_chiffre
                cv2.rectangle(debug,
                               (abs_x1 + rx, abs_y1 + ry),
                               (abs_x1 + rx + rw, abs_y1 + ry + rh),
                               couleur, 2)

            # Numéro de colonne
            cv2.putText(debug, str(col + 1),
                        (abs_x1 + 4, abs_y1 + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, couleur, 1)

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
