# 📋 Changelog — CDM26 Marguerite

> Wesh la data, voilà ce qui a bougé. Du plus récent au plus ancien.

---

## [2026-06-17] — Table « Détail par match » niveau pro 🗂️

- **En-tête figé** : la ligne des titres de colonnes reste collée en haut quand tu scrolles dans la table (comme un *figer les volets* dans Excel).
- **Rappel des couleurs des joueurs** : sous chaque nom dans l'en-tête, une pastille de la couleur du joueur (la même que la courbe « Évolution des bons pronos »).
- **Colonnes réordonnées** : `Score` et `Rés` sont maintenant placés juste après `Retenu`.
- **Lignes cliquables** : un clic sur une ligne ouvre le match dans l'onglet *Matchs* (filtres date/phase appliqués + scroll auto).

## [2026-06-17] — Paris placés + export 💸

- **Tous les paris affichés** : fini la limite aux 6 derniers, la carte « Paris placés » montre la totalité avec scroll (en attente d'abord, réglés ensuite).
- **Nouvelle table « Détail par match »** en bas des stats : pour chaque match → score, résultat, prono de chaque joueur (vert = bon, rouge = raté), vote retenu, cote, pari placé et gain/perte.
- **Export CSV / Excel** : bouton vert dans l'en-tête de la table. Génère `cdm26_matchs_AAAA-MM-JJ.csv`, compatible Excel FR (séparateur `;`, virgule décimale, BOM UTF-8). Les pronos sont écrits en clair (ex : « Mexique », « Nul ») plutôt qu'en code `1/N/2`.

## [2026-06-17] — Carte « Bilan paris » 🤑

- Ajout du gain idéal **« si tout passait »** : ce qu'on aurait empoché si chaque pari placé avait été gagné à sa cote (4 × cote − 4 € par pari). Affiché en vert avec une infobulle **(?)** explicative.

## [2026-06-16] — Lisibilité du graphe 📈

- **Légende « Évolution des bons pronos »** : les noms des joueurs ne sont plus tronqués sur la droite (largeur élargie + police légèrement réduite).
- **Carte « Forme récente »** : grille rendue responsive, plus lisible sur mobile.

---

*Projet : appli de pronostics Coupe du Monde 2026 — `index.html` (SPA + Supabase).*
