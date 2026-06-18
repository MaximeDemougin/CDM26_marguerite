#!/usr/bin/env node
// Backfill des cotes de marché WC2026 depuis un fichier CSV.
//
// Le calendrier quotidien (update-cotes.mjs) ne couvre que les matchs à venir
// via The Odds API. Ce script remplit a posteriori les matchs déjà joués à
// partir d'un fichier de cotes fourni manuellement (cotes max du marché).
//
// Source  : CSV — scripts/backfill-data.csv
//           colonnes : HomeTeam ; AwayTeam ; date ; home_max ; draw_max ; away_max
//           (séparateur « ; » ou « , » ; guillemets optionnels)
// Cible   : table Supabase `cotes_marche` (réutilise buildRows/bestOdds)
//
// Variables d'environnement :
//   SUPABASE_URL                 ex. https://xxxx.supabase.co
//   SUPABASE_SERVICE_KEY         clé service (ou SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY)
//   BACKFILL_CSV                 chemin du CSV (défaut scripts/backfill-data.csv)
//   MATCHS_FIXTURE_FILE          JSON matchs hors-ligne (selftest, sans réseau)
//   DRY_RUN=1                    affiche sans écrire
//
// Usage : node scripts/backfill-cotes.mjs [--dry-run]

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildRows } from './update-cotes.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DRY = process.argv.includes('--dry-run') || process.env.DRY_RUN === '1';

// ── CSV → événements (format compatible buildRows / The Odds API) ──────────────
// On crée un unique « bookmaker » nommé Max : ce sont les meilleures cotes du
// marché (pas de Pinnacle historique disponible côté gratuit, cf. « sinon max »).
export function parseCsvToEvents(text) {
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const delim = (lines[0].match(/;/g) || []).length >= (lines[0].match(/,/g) || []).length ? ';' : ',';
  const cut = l => l.split(delim).map(s => s.replace(/"/g, '').trim());

  const first = cut(lines[0]);
  const looksHeader = first.some(x => /home|away|team|max|date/i.test(x) && !isFinite(Number(x)));
  const head = looksHeader ? first.map(h => h.toLowerCase()) : [];
  const at = (name, dflt) => { const i = head.indexOf(name); return i >= 0 ? i : dflt; };
  const iHome = at('hometeam', 0), iAway = at('awayteam', 1);
  const iH = at('home_max', 3), iD = at('draw_max', 4), iA = at('away_max', 5);

  const events = [];
  for (const line of looksHeader ? lines.slice(1) : lines) {
    const c = cut(line);
    const home = c[iHome], away = c[iAway];
    if (!home || !away) continue;
    const h = Number(c[iH]), d = Number(c[iD]), a = Number(c[iA]);
    const outcomes = [];
    if (isFinite(h)) outcomes.push({ name: home, price: h });
    if (isFinite(a)) outcomes.push({ name: away, price: a });
    if (isFinite(d)) outcomes.push({ name: 'Draw', price: d });
    if (!outcomes.length) continue;
    events.push({ home_team: home, away_team: away, bookmakers: [{ title: 'Max', markets: [{ key: 'h2h', outcomes }] }] });
  }
  return events;
}

// ── Supabase ───────────────────────────────────────────────────────────────────
function serviceKey() {
  return process.env.SUPABASE_SERVICE_KEY
    || process.env.SUPABASE_SERVICE_ROLE_KEY
    || process.env.SUPABASE_KEY || '';
}

function supaHeaders() {
  const k = serviceKey();
  return { apikey: k, Authorization: `Bearer ${k}`, 'Content-Type': 'application/json' };
}

async function fetchMatchs() {
  if (process.env.MATCHS_FIXTURE_FILE) {
    return JSON.parse(fs.readFileSync(process.env.MATCHS_FIXTURE_FILE, 'utf8'));
  }
  const url = `${process.env.SUPABASE_URL}/rest/v1/matchs?select=id,equipe_dom,equipe_ext,date_match`;
  const res = await fetch(url, { headers: supaHeaders() });
  if (!res.ok) throw new Error(`Supabase GET matchs ${res.status} ${await res.text()}`);
  return res.json();
}

async function upsertCotes(rows) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/cotes_marche`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { ...supaHeaders(), Prefer: 'resolution=merge-duplicates,return=minimal' },
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(`Supabase upsert ${res.status} ${await res.text()}`);
}

// ── Main ───────────────────────────────────────────────────────────────────────
async function main() {
  const offline = !!process.env.MATCHS_FIXTURE_FILE;
  if (!offline) {
    if (!process.env.SUPABASE_URL) throw new Error('Secret manquant : SUPABASE_URL');
    if (!serviceKey()) throw new Error('Secret manquant : clé service Supabase (SUPABASE_SERVICE_KEY / _ROLE_KEY / _KEY)');
  }

  const csvPath = process.env.BACKFILL_CSV || path.join(__dirname, 'backfill-data.csv');
  if (!fs.existsSync(csvPath)) throw new Error(`Fichier CSV introuvable : ${csvPath}`);
  const events = parseCsvToEvents(fs.readFileSync(csvPath, 'utf8'));
  console.log(`[csv] ${events.length} matchs lus depuis ${path.basename(csvPath)}`);
  if (!events.length) { console.log('CSV vide — rien à faire.'); return; }

  const matchs = await fetchMatchs();
  console.log(`[in] ${matchs.length} matchs en base`);

  const { rows, matched, unmatched } = buildRows(matchs, events);
  console.log(`[match] ${rows.length} matchs associés`);
  matched.forEach(l => console.log('  ✓ ' + l));
  if (unmatched.length) {
    console.log(`[non associés] ${unmatched.length} (alias d'équipe ou absent du calendrier) :`);
    unmatched.forEach(l => console.log('  · ' + l));
  }

  if (!rows.length) { console.log('Rien à écrire.'); return; }
  if (DRY) { console.log('[dry-run] écriture ignorée.'); return; }
  await upsertCotes(rows);
  console.log(`[ok] ${rows.length} lignes écrites dans cotes_marche.`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => { console.error('[échec]', e.message); process.exit(1); });
}
