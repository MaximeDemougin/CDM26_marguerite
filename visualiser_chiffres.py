import cv2
import numpy as np
from lire_score import (ancrage_blindé, trouver_rangees_chiffres,
                        etendue_verticale, masquer_marqueurs,
                        detecter_digits_par_projection, boites_depuis_colonnes_ref)



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

    colonnes_ref = None   # colonnes x détectées sur VISITEUR, réutilisées pour CLUB

    for idx, (y1, y2) in enumerate(rangees[:2]):
        couleur = couleurs[idx]
        bande_bgr = roi[y1 + 3:y2, :]

        if idx == 0:
            # VISITEUR : détection libre
            boites = detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols)
            # Mémoriser les colonnes x pour CLUB
            colonnes_ref = [(bx, bx + bw) for bx, _, bw, _ in boites]
        else:
            # CLUB : on force les mêmes colonnes x que VISITEUR
            if colonnes_ref:
                boites = boites_depuis_colonnes_ref(bande_bgr, colonnes_ref)
            else:
                boites = detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols)

        for col, (bx, by, bw, bh) in enumerate(boites):
            abs_x1 = px + bx
            abs_y1 = py + y1 + 3 + by
            abs_x2 = abs_x1 + bw
            abs_y2 = abs_y1 + bh

            overlay = debug.copy()
            cv2.rectangle(overlay, (abs_x1, abs_y1), (abs_x2, abs_y2), couleur, -1)
            cv2.addWeighted(overlay, 0.15, debug, 0.85, 0, debug)
            cv2.rectangle(debug, (abs_x1, abs_y1), (abs_x2, abs_y2), couleur, 2)
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
