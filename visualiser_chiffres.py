import cv2
import numpy as np
from lire_score import (detecter_et_redresser, trouver_rangees_chiffres,
                        detecter_digits_par_projection, boites_depuis_colonnes_ref)


def visualiser_chiffres(chemin_image, nb_cols=3):
    img = cv2.imread(chemin_image)
    if img is None:
        raise FileNotFoundError(f"Image introuvable : {chemin_image}")

    roi = detecter_et_redresser(img)
    if roi is None:
        raise RuntimeError("Panneau non détecté.")

    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    rangees, _, _ = trouver_rangees_chiffres(roi_gray)

    debug = roi.copy()
    labels = ["VISITEUR", "CLUB"]
    couleurs = [(0, 220, 0), (0, 80, 255)]
    colonnes_ref = None

    for idx, (y1, y2) in enumerate(rangees[:2]):
        couleur = couleurs[idx]
        bande_bgr = roi[y1 + 3:y2, :]

        if idx == 0:
            boites = detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols)
            colonnes_ref = [(bx, bx + bw) for bx, _, bw, _ in boites]
        else:
            boites = (boites_depuis_colonnes_ref(bande_bgr, colonnes_ref)
                      if colonnes_ref
                      else detecter_digits_par_projection(bande_bgr, nb_attendus=nb_cols))

        for col, (bx, by, bw, bh) in enumerate(boites):
            x1, y_abs = bx, y1 + 3 + by
            overlay = debug.copy()
            cv2.rectangle(overlay, (x1, y_abs), (x1 + bw, y_abs + bh), couleur, -1)
            cv2.addWeighted(overlay, 0.15, debug, 0.85, 0, debug)
            cv2.rectangle(debug, (x1, y_abs), (x1 + bw, y_abs + bh), couleur, 2)
            cv2.putText(debug, str(col + 1), (x1 + 3, y_abs + 13),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, couleur, 1)

        cv2.putText(debug, labels[idx], (4, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, couleur, 2)

    cv2.imwrite("visualisation_chiffres.jpg", debug)
    print("Sauvegardé : visualisation_chiffres.jpg")


if __name__ == "__main__":
    import sys
    chemin = sys.argv[1] if len(sys.argv) > 1 else "score_brut_cropped_terrain1_2025-07-11_13-30-15.jpg"
    visualiser_chiffres(chemin)
