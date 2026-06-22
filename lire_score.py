import cv2
import numpy as np
import pytesseract


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
    """
    Localise les deux bandes horizontales contenant les chiffres (fond noir).
    Retourne une liste de (y_debut, y_fin) pour chaque rangée.
    """
    # Profil vertical : moyenne des pixels sombres par ligne
    _, dark = cv2.threshold(roi_gray, 60, 255, cv2.THRESH_BINARY_INV)
    profil = dark.mean(axis=1)  # moyenne par ligne

    # Seuil : ligne appartenant à un afficheur si beaucoup de pixels sombres
    seuil = profil.max() * 0.4
    in_band = profil > seuil

    rangees = []
    debut = None
    for i, val in enumerate(in_band):
        if val and debut is None:
            debut = i
        elif not val and debut is not None:
            if i - debut > 10:  # ignorer les bandes trop fines
                rangees.append((debut, i))
            debut = None
    if debut is not None:
        rangees.append((debut, len(in_band)))
    return rangees


def lire_chiffre(cellule_gray):
    """
    Lit un chiffre unique dans une cellule (fond sombre, chiffre clair).
    Retourne la chaîne lue ou '?' si échec.
    """
    # Inverser : fond clair, chiffre sombre → meilleur pour Tesseract
    inv = cv2.bitwise_not(cellule_gray)
    # Redimensionner pour aider Tesseract
    h, w = inv.shape
    scale = max(1, 60 // h)
    inv = cv2.resize(inv, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    # Binarisation adaptative
    _, bin_img = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = "--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789"
    texte = pytesseract.image_to_string(bin_img, config=config).strip()
    return texte if texte else "?"


def segmenter_colonnes(bande_gray, nb_cols=3):
    """
    Divise une bande horizontale en nb_cols colonnes et lit chaque chiffre.
    """
    h, w = bande_gray.shape
    largeur_col = w // nb_cols
    chiffres = []
    for i in range(nb_cols):
        x1 = i * largeur_col
        x2 = x1 + largeur_col
        cellule = bande_gray[:, x1:x2]
        chiffres.append(lire_chiffre(cellule))
    return chiffres


def lire_score(chemin_image, nb_cols=3):
    img = cv2.imread(chemin_image)
    if img is None:
        raise FileNotFoundError(f"Image introuvable : {chemin_image}")

    rect = ancrage_blindé(img)
    if rect is None:
        raise RuntimeError("Panneau non détecté.")

    x, y, w, h = rect
    roi = img[y:y + h, x:x + w]
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    rangees = trouver_rangees_chiffres(roi_gray)

    if len(rangees) < 2:
        raise RuntimeError(
            f"Seulement {len(rangees)} rangée(s) de chiffres détectée(s) "
            f"(attendu 2). Essayez d'ajuster le seuil dans trouver_rangees_chiffres."
        )

    # On prend les deux premières rangées trouvées
    labels = ["VISITEUR", "CLUB"]
    score = {}
    debug = img.copy()

    for idx, (y1, y2) in enumerate(rangees[:2]):
        bande = roi_gray[y1:y2, :]
        chiffres = segmenter_colonnes(bande, nb_cols)
        score[labels[idx]] = chiffres

        # Dessin debug sur l'image originale
        cv2.rectangle(debug,
                      (x, y + y1), (x + w, y + y2),
                      (0, 255, 0) if idx == 0 else (0, 0, 255), 2)
        texte_score = " - ".join(chiffres)
        cv2.putText(debug, f"{labels[idx]}: {texte_score}",
                    (x + 5, y + y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if idx == 0 else (0, 0, 255), 2)

    cv2.imwrite("score_debug.jpg", debug)
    return score


if __name__ == "__main__":
    import sys

    chemin = sys.argv[1] if len(sys.argv) > 1 else "score_brut_cropped_terrain1_2025-07-11_13-30-15.jpg"
    try:
        score = lire_score(chemin)
        print("=== Score détecté ===")
        for equipe, chiffres in score.items():
            print(f"  {equipe} : {' | '.join(chiffres)}")
        print("Débogage sauvegardé dans score_debug.jpg")
    except Exception as e:
        print(f"Erreur : {e}")
