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
    Stratégie : les bandeaux VISITEUR / CLUB sont des bandes sombres.
    On les détecte, puis les zones de chiffres sont les espaces clairs juste en dessous.
    Retourne une liste de (y_debut, y_fin) pour chaque rangée de chiffres.
    """
    h_img = roi_gray.shape[0]

    # Profil : proportion de pixels sombres par ligne
    _, dark = cv2.threshold(roi_gray, 80, 255, cv2.THRESH_BINARY_INV)
    profil = dark.mean(axis=1)

    # Bandes sombres = bandeaux texte (VISITEUR / CLUB)
    seuil_sombre = max(20.0, profil.max() * 0.25)
    in_dark = profil > seuil_sombre

    # Trouve les intervalles de bandes sombres
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

    # Les zones de chiffres sont les espaces clairs ENTRE les bandes sombres.
    # Délimitation : fin de la bande courante → début de la bande suivante.
    rangees = []
    for i, (_, fin) in enumerate(bandes_sombres):
        debut_suivant = bandes_sombres[i + 1][0] if i + 1 < len(bandes_sombres) else h_img
        hauteur = debut_suivant - fin
        if hauteur > 10:
            rangees.append((fin, debut_suivant))

    return rangees, bandes_sombres, profil


def preparer_cellule(cellule_gray):
    """
    Prétraitement d'une cellule contenant un seul chiffre.
    On agrandit, on binarise avec Otsu, on s'assure que le fond est blanc.
    Pas de CLAHE : il crée des artefacts sur les chiffres fins (le '1' devient '4').
    """
    h, w = cellule_gray.shape
    # Agrandir jusqu'à ~80 px de haut pour Tesseract
    scale = max(1, 80 // h)
    grande = cv2.resize(cellule_gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
    # Binarisation Otsu
    _, bin_img = cv2.threshold(grande, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Garantir fond blanc (Tesseract préfère texte sombre sur fond clair)
    if np.mean(bin_img) < 127:
        bin_img = cv2.bitwise_not(bin_img)
    # Marge blanche autour pour éviter que le chiffre touche le bord
    bin_img = cv2.copyMakeBorder(bin_img, 10, 10, 10, 10,
                                  cv2.BORDER_CONSTANT, value=255)
    return bin_img


def segmenter_colonnes(bande_gray, nb_cols=3):
    """Lit chaque chiffre individuellement (--psm 10 = caractère unique)."""
    h, w = bande_gray.shape
    # Ignorer les 3 premiers pixels (résidu possible du bandeau texte au-dessus)
    bande_gray = bande_gray[3:, :]
    largeur_col = w // nb_cols
    chiffres = []
    for i in range(nb_cols):
        cellule = bande_gray[:, i * largeur_col:(i + 1) * largeur_col]
        img = preparer_cellule(cellule)
        cv2.imwrite(f"debug_cellule_{i}.jpg", img)
        config = "--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789"
        texte = pytesseract.image_to_string(img, config=config).strip()
        chiffres.append(texte[0] if texte and texte[0].isdigit() else "?")
    return chiffres


def sauver_profil_debug(profil, bandes_sombres, rangees, chemin="debug_profil.png"):
    """Sauvegarde une image du profil vertical avec annotations."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(profil, label="Profil sombre (moyenne par ligne)")
    for (y1, y2) in bandes_sombres:
        ax.axvspan(y1, y2, alpha=0.3, color="red", label="Bandeau sombre")
    for (y1, y2) in rangees:
        ax.axvspan(y1, y2, alpha=0.3, color="green", label="Zone chiffres")
    handles = [
        mpatches.Patch(color="red", alpha=0.5, label="Bandeau sombre (VISITEUR/CLUB)"),
        mpatches.Patch(color="green", alpha=0.5, label="Zone chiffres détectée"),
    ]
    ax.legend(handles=handles)
    ax.set_xlabel("Ligne y dans le ROI")
    ax.set_ylabel("Intensité sombre moyenne")
    ax.set_title("Profil vertical du ROI")
    plt.tight_layout()
    plt.savefig(chemin)
    plt.close()


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

    # Sauvegarde intermédiaire 1 : ROI brut
    cv2.imwrite("debug_1_roi.jpg", roi)

    rangees, bandes_sombres, profil = trouver_rangees_chiffres(roi_gray)

    # Sauvegarde intermédiaire 2 : ROI annoté (bandes sombres + zones chiffres)
    roi_annote = cv2.cvtColor(roi_gray, cv2.COLOR_GRAY2BGR)
    for (y1, y2) in bandes_sombres:
        cv2.rectangle(roi_annote, (0, y1), (roi_annote.shape[1], y2), (0, 0, 200), 2)
    for (y1, y2) in rangees:
        cv2.rectangle(roi_annote, (0, y1), (roi_annote.shape[1], y2), (0, 200, 0), 2)
    cv2.imwrite("debug_2_roi_annote.jpg", roi_annote)

    # Sauvegarde intermédiaire 3 : profil vertical
    try:
        sauver_profil_debug(profil, bandes_sombres, rangees, "debug_3_profil.png")
    except ImportError:
        pass  # matplotlib optionnel

    if len(rangees) < 2:
        raise RuntimeError(
            f"Seulement {len(rangees)} rangée(s) de chiffres détectée(s) (attendu 2).\n"
            f"  Bandes sombres trouvées : {bandes_sombres}\n"
            f"  Consultez debug_1_roi.jpg et debug_2_roi_annote.jpg pour diagnostiquer."
        )

    labels = ["VISITEUR", "CLUB"]
    score = {}
    debug = img.copy()

    for idx, (y1, y2) in enumerate(rangees[:2]):
        bande = roi_gray[y1:y2, :]
        # Sauvegarde intermédiaire 4/5 : chaque bande de chiffres
        cv2.imwrite(f"debug_4_bande_{labels[idx].lower()}.jpg", bande)
        chiffres = segmenter_colonnes(bande, nb_cols)
        score[labels[idx]] = chiffres

        cv2.rectangle(debug,
                      (x, y + y1), (x + w, y + y2),
                      (0, 255, 0) if idx == 0 else (0, 0, 255), 2)
        texte_score = " | ".join(chiffres)
        cv2.putText(debug, f"{labels[idx]}: {texte_score}",
                    (x + 5, y + y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if idx == 0 else (0, 0, 255), 2)

    cv2.imwrite("debug_5_resultat_final.jpg", debug)
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
