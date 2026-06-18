# Routine quotidienne — Cotes de marché (1/N/2)

Récupère chaque jour les **meilleures cotes 1/N/2** des matchs de la CDM 2026 via
**The Odds API**, et les écrit dans la table Supabase **`cotes_marche`**.
L'app les affiche dans la colonne « Cotes marché » du tableau *Détail par match*.

```
The Odds API  ──>  scripts/update-cotes.mjs  ──>  Supabase (cotes_marche)  ──>  app (Stats)
```

---

## 1. Créer la table Supabase (une seule fois)

Dans **Supabase → SQL Editor**, exécute :

```sql
create table if not exists public.cotes_marche (
  match_id  integer primary key references public.matchs(id) on delete cascade,
  cote_1    numeric,           -- meilleure cote victoire domicile (équipe e1)
  book_1    text,              -- bookmaker associé
  cote_n    numeric,           -- meilleure cote match nul
  book_n    text,
  cote_2    numeric,           -- meilleure cote victoire extérieur (équipe e2)
  book_2    text,
  maj_le    timestamptz not null default now()
);

alter table public.cotes_marche enable row level security;

-- Lecture publique (clé anon de l'app)
create policy "cotes_marche lecture publique"
  on public.cotes_marche for select using (true);
```

> La routine écrit avec la clé **service_role**, qui ignore la RLS : aucune policy
> d'écriture n'est nécessaire. Si la contrainte `references public.matchs(id)` pose
> souci, retire-la (`... match_id integer primary key,`).

---

## 2. Obtenir une clé The Odds API

1. Crée un compte gratuit sur https://the-odds-api.com (offre gratuite ≈ 500 requêtes/mois).
2. Récupère ta clé API. Une exécution quotidienne consomme ~1 crédit par région
   (`ODDS_REGIONS=eu,uk` → 2 crédits/jour ≈ 60/mois : large marge).

Le sport visé est `soccer_fifa_world_cup` (modifiable via `ODDS_SPORT_KEY`).

---

## 3. Secrets / variables d'environnement

À définir dans l'**environnement Claude Code web** (Settings → Environment) :

| Variable | Description |
|---|---|
| `ODDS_API_KEY` | clé The Odds API |
| `SUPABASE_URL` | ex. `https://zvpbolszzsbufqsykwex.supabase.co` |
| `SUPABASE_SERVICE_KEY` | clé **service_role** Supabase (secret — écrit en base) |
| `ODDS_REGIONS` | *(optionnel)* défaut `eu,uk` |
| `ODDS_SPORT_KEY` | *(optionnel)* défaut `soccer_fifa_world_cup` |

> ⚠️ La clé `service_role` est sensible : ne la mets **jamais** dans le code ni dans
> `index.html`. Uniquement en variable d'environnement secrète.

---

## 4. Lancer manuellement

```bash
# essai sans écriture (affiche les correspondances)
node scripts/update-cotes.mjs --dry-run

# exécution réelle (écrit dans cotes_marche)
node scripts/update-cotes.mjs
```

Test **hors-ligne** de la logique d'association (sans clé ni réseau) :

```bash
MATCHS_FIXTURE_FILE=scripts/exemple-matchs.json \
ODDS_FIXTURE_FILE=scripts/exemple-odds.json \
DRY_RUN=1 node scripts/update-cotes.mjs
```

La sortie liste les matchs **associés** (`✓`) et **non associés** (alias d'équipe
inconnu, ou phase à venir comme les 8es de finale dont les équipes ne sont pas encore
connues — c'est normal).

---

## 5. Planifier la routine (Claude Code web)

Crée un **déclencheur planifié quotidien** sur ce dépôt depuis Claude Code web
(voir la doc : https://code.claude.com/docs/en/claude-code-on-the-web), avec ce prompt :

> **Routine cotes CDM26.** Exécute `node scripts/update-cotes.mjs`.
> Si des matchs apparaissent en « non associés » à cause d'un **alias d'équipe inconnu**
> (un nom anglais renvoyé par l'API qui n'est pas reconnu), ajoute l'alias manquant dans
> `scripts/teams-fr-en.json`, puis relance la commande. Commit et push sur `main`
> uniquement si tu as modifié le dictionnaire. Termine par un court résumé : nombre de
> cotes mises à jour, et la liste des éventuels matchs non associés restants.

C'est là tout l'intérêt d'une **routine Claude** plutôt qu'un simple script : quand une
nouvelle équipe se qualifie pour les phases finales, ou que l'API change un libellé,
Claude complète le dictionnaire tout seul et la routine continue de tourner.

---

## Détails techniques

- **Aucune dépendance npm** : `update-cotes.mjs` utilise `fetch` (Node ≥ 18) et l'API
  REST Supabase (PostgREST). Rien à installer.
- **Meilleure cote** : pour chaque issue (1/N/2), on prend le **prix le plus élevé** parmi
  tous les bookmakers renvoyés, et on mémorise le bookmaker correspondant.
- **Orientation 1/2** : l'API expose `home_team`/`away_team` ; on réoriente selon le
  domicile défini côté app (`equipe_dom`), donc `cote_1` correspond toujours à l'équipe
  affichée à gauche, même si l'API inverse domicile/extérieur.
- **Correspondance des noms** : `scripts/teams-fr-en.json` mappe chaque équipe FR vers ses
  libellés anglais possibles ; la comparaison ignore accents, casse et ponctuation.
