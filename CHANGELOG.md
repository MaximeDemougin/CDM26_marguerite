# 📋 Changelog — CDM26 Marguerite

> Wesh la data, voilà ce qui a bougé. Du plus récent au plus ancien.

---

## [2026-06-18] — Cotes marché : fiabilité, backfill & stats financières 📊

### Cotes de marché

- **Priorité Pinnacle** : `update-cotes.mjs` préfère désormais les cotes Pinnacle (le bookmaker le plus sharp du marché) ; si Pinnacle n'est pas dispo sur un match, on tombe sur la meilleure cote tous bookmakers confondus.
- **Filtre anti-live** : l'API est appelée avec `commenceTimeFrom=maintenant` pour n'obtenir que les matchs à venir. Un filtre local en double-sécurité écarte tout événement dont `commence_time` est déjà passé, et loggue le nombre d'événements live ignorés.
- **Planification 2×/jour** : le cron GitHub Actions tourne désormais à **08h00** et **16h00** heure de Paris (06:00 et 14:00 UTC) au lieu d'une seule fois par jour.
- **Backfill des matchs joués** : nouveau script `scripts/backfill-cotes.mjs` + workflow `backfill-cotes.yml`. Permet d'alimenter `cotes_marche` pour les matchs déjà disputés à partir d'un fichier CSV (`backfill-data.csv`) avec les colonnes `HomeTeam;AwayTeam;date;home_max;draw_max;away_max`. 28 matchs des phases de poules (11–18 juin) ont été importés.

### UI — Carte match

- **Affichage des cotes** : le bloc « Cotes marché » est aligné à gauche (comme le titre « Choix des pronostics ») ; les pills 1 / N / 2 ont la forme iconique `0 7px 0 7px` de l'appli, sont centrées et compactes.
- **Heure de mise à jour** : la date+heure de dernière maj est affichée directement collée au label (ex. *Cotes marché · maj 18/06 14:32*), plus dans un coin isolé.

### Stats — Courbe d'évolution

- **Toggle Pronos / Finance** : deux boutons dans le header de la courbe permettent de switcher entre :
  - **Pronos** — courbe cumulative des bons pronostics par joueur (mode par défaut).
  - **Finance** — bilan individuel simulé : chaque joueur « mise » 4 € sur son propre pick à la cote marché disponible. Gain affiché en euros, tooltip adapté, légende mise à jour au switch.

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
