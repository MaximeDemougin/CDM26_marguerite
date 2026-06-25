# 📋 Changelog — CDM26 Marguerite

> Wesh la data, voilà ce qui a bougé. Du plus récent au plus ancien.

---

## [2026-06-25] — Calendrier dynamique & finance par tête 🗓️

### Calendrier
- **Groupe J réparé** : la 3e journée affichait les mêmes duels que la 1re (Algérie–Argentine / Jordanie–Autriche en miroir, impossible en poule de 4). Remis d'équerre → **Algérie–Autriche** & **Jordanie–Argentine**. C'est d'ailleurs ce que l'actualisateur de cotes essayait de nous dire.
- **Fini le calendrier en dur** : l'appli lit maintenant les équipes, dates et groupes depuis Supabase. Le code se contente de semer/réparer les champs statiques au chargement (les scores ne sont jamais écrasés). Corrige un match en base → l'appli suit au refresh suivant.

### Finance
- **Mise rationalisée à 1 €** : la courbe « Bilan financier individuel » passe d'une mise de 4 € à **1 € par pari**. Échelle plus fine, affichage aux centimes (±X.XX €).

### Bracket
- **Meilleurs 3es enfin placés** : les slots type `3BEFIJ` restaient parfois affichés en code brut. L'ancienne affectation gloutonne se coinçait dès que les groupes autorisés se chevauchaient (elle échouait sur **80 % des combinaisons** possibles !). Remplacée par un vrai couplage biparti complet → les 8 troisièmes sont toujours répartis correctement.

---

## [2026-06-23] — Prol/TAB, stats risque, affichage clean 🎯

### KO Prolongations / Tirs au but
- **Saisie prol/TAB** : matchs nuls à 90 min → inputs pour score prolongation + boutons TAB si toujours égalité. Affichage split : display en zone sombre (team header) + inputs en bas (zone admin).
- **Bracket knockout** : affiche « AET » ou « TAB » à côté du score, équipe qualifiée en vert quelle que soit la manière.
- **Calendrier compétition** : badge [ap] ou [TAB] sur la ligne du match, équipe qualifiée surlignée.

### Stats & pronostics
- **Plus gros risque** : remplace « Plus disputé ». Affiche la cote marché moyenne de **tous** les joueurs (sur pronos terminés), classée du + au − risqué.
- **Écart en queue** : carte « Écart en tête » ajoute la différence dernière vs avant-dernière place (affichage 2-lignes).
- **Noms colorés partout** : chaque joueur affiche sa couleur dans les cartes stats (leader, risque, écart).

### UI Compétition
- **Headers groupe en blanc** : labels Pts / Diff / BP / J déplacés **dans** le header sombre de chaque groupe, en blanc, alignés sur les colonnes.
- **Calendrier symétrique** : layout 1fr/auto/1fr pour centrer les scores à 50% quelle que soit la longueur des noms d'équipe.

### Infrastructure
- **Pre-commit hook** : version bumpe automatiquement à chaque commit (ancien système pre-push cassé, réfixé en pre-commit).
- **v1.5.6 → v1.5.10** : version monte avec chaque change.

---

## [2026-06-18] — Cotes marché, finance, courbe perso 📊

### Cotes de marché
- **Priorité Pinnacle** : meilleur bookmaker du marché d'abord, sinon meilleure cote tous bookmakers confondus.
- **Filtre anti-live** : API appelée avec `commenceTimeFrom=maintenant`, double-check local pour écarter les matchs déjà joués.
- **Planification 2×/jour** : cron GitHub Actions à 08h00 et 16h00 heure de Paris.
- **Backfill matchs joués** : script pour alimenter les cotes des matchs terminés via CSV.

### Affichage matchs
- **Bloc « Cotes marché »** : aligné à gauche, pills 1/N/2 compactes, maj avec date+heure directe.

### Courbe d'évolution
- **Toggle Pronos / Finance** : switch entre la courbe des bons pronos et le bilan financier (4 € par pick à sa cote).

---

## [2026-06-17] — Tables pro, export, bilan paris 💸

- **Table « Détail par match »** : en-tête figé (scroll fixe), pastilles couleur joueur, colonnes reordonnées, cliquable pour ouvrir le match.
- **Paris placés** : carte affichant tous les paris (en attente et réglés), plus les gains/pertes.
- **Export CSV / Excel** : bouton direct, format FR (séparateur `;`, BOM UTF-8), pronos en clair (« France » vs « 1 »).
- **Carte « Bilan paris »** : affiche le gain « si tout passait » (4 × cote − 4 € par pari).

---

## [2026-06-16] — Lisibilité & responsive 📈

- **Légende courbe** : noms de joueurs pas tronqués (largeur ajustée + police réduite).
- **« Forme récente »** : grille responsive, mobile-friendly.

---

*Projet : appli de pronostics Coupe du Monde 2026 — `index.html` (SPA + Supabase).*
