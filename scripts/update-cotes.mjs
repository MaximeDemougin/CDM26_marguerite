#!/usr/bin/env node
// Met à jour les cotes de marché (meilleures 1/N/2) des matchs de la CDM 2026.
//
// Source  : The Odds API (https://the-odds-api.com) — marché h2h (1/N/2)
// Cible   : table Supabase `cotes_marche` (1 ligne par match)
// Exécution: routine Claude Code web quotidienne (voir scripts/ROUTINE_COTES.md)
//
// Aucune dépendance npm : utilise fetch global (Node >= 18) et l'API REST Supabase.
//
// Variables d'environnement requises :
//   ODDS_API_KEY            clé The Odds API
//   SUPABASE_URL            ex. https://xxxx.supabase.co
//   SUPABASE_SERVICE_KEY    clé "service_role" Supabase (écrit en base, garde-la secrète)
// Optionnelles :
//   ODDS_SPORT_KEY          défaut "soccer_fifa_world_cup"
//   ODDS_REGIONS            défaut "eu,uk"  (chaque région = 1 crédit/marché)
//   ODDS_FIXTURE_FILE       chemin d'un JSON d'événements (mode test hors-ligne)
//   MATCHS_FIXTURE_FILE     chemin d'un JSON de matchs   (mode test hors-ligne)
//   DRY_RUN=1               n'écrit pas en base, affiche seulement
//
// Usage : node scripts/update-cotes.mjs [--dry-run]

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const TEAMS_FR_EN = JSON.parse(fs.readFileSync(path.join(__dirname, 'teams-fr-en.json'), 'utf8'));

const DRY = process.argv.includes('--dry-run') || process.env.DRY_RUN === '1';

// ── Normalisation & correspondance des noms d'équipes ──────────────────────────
export function norm(s) {
  return String(s || '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '') // sans accents
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function buildEnToFr(map = TEAMS_FR_EN) {
  const idx = {};
  for (const [fr, aliases] of Object.entries(map)) {
    idx[norm(fr)] = fr;
    for (const a of aliases) idx[norm(a)] = fr;
  }
  return idx;
}

export const pairKey = (a, b) => [a, b].sort().join(' :: ');

// ── Cotes 1/N/2 d'un événement — Pinnacle en priorité, sinon meilleure cote ───
export function bestOdds(event) {
  const home = event.home_team, away = event.away_team;
  let c1 = null, b1 = null, cn = null, bn = null, c2 = null, b2 = null;
  let p1 = null, pn = null, p2 = null; // cotes Pinnacle
  for (const bk of event.bookmakers || []) {
    const mk = (bk.markets || []).find(m => m.key === 'h2h');
    if (!mk) continue;
    const isPinnacle = /pinnacle/i.test(bk.title);
    for (const o of mk.outcomes || []) {
      const price = Number(o.price);
      if (!isFinite(price)) continue;
      if (o.name === home) {
        if (isPinnacle) p1 = price;
        if (c1 == null || price > c1) { c1 = price; b1 = bk.title; }
      } else if (o.name === away) {
        if (isPinnacle) p2 = price;
        if (c2 == null || price > c2) { c2 = price; b2 = bk.title; }
      } else if (/^(draw|tie|nul)/i.test(o.name)) {
        if (isPinnacle) pn = price;
        if (cn == null || price > cn) { cn = price; bn = bk.title; }
      }
    }
  }
  // Préférer Pinnacle si disponible pour chaque issue
  if (p1 != null) { c1 = p1; b1 = 'Pinnacle'; }
  if (pn != null) { cn = pn; bn = 'Pinnacle'; }
  if (p2 != null) { c2 = p2; b2 = 'Pinnacle'; }
  return { home: { c: c1, b: b1 }, away: { c: c2, b: b2 }, draw: { c: cn, b: bn } };
}

// ── Construit les lignes cotes_marche en associant événements ↔ matchs ─────────
export function buildRows(matchs, events, { enToFr = buildEnToFr(), nowISO = new Date().toISOString() } = {}) {
  const appByPair = new Map();
  for (const m of matchs) {
    if (!m.equipe_dom || !m.equipe_ext) continue;
    appByPair.set(pairKey(norm(m.equipe_dom), norm(m.equipe_ext)), m);
  }
  const rows = [];
  const matched = [];
  const unmatched = [];
  const seen = new Set();
  for (const ev of events) {
    const frHome = enToFr[norm(ev.home_team)];
    const frAway = enToFr[norm(ev.away_team)];
    if (!frHome || !frAway) { unmatched.push(`${ev.home_team} vs ${ev.away_team} (nom inconnu)`); continue; }
    const nHome = norm(frHome), nAway = norm(frAway);
    const m = appByPair.get(pairKey(nHome, nAway));
    if (!m) { unmatched.push(`${frHome} vs ${frAway} (pas dans le calendrier)`); continue; }
    if (seen.has(m.id)) continue; // garde le 1er event pour ce match
    const o = bestOdds(ev);
    if (o.home.c == null && o.away.c == null && o.draw.c == null) { unmatched.push(`${frHome} vs ${frAway} (aucune cote)`); continue; }
    // Oriente 1/2 selon le domicile côté app (equipe_dom)
    const homeIsDom = norm(m.equipe_dom) === nHome;
    const dom = homeIsDom ? o.home : o.away;
    const ext = homeIsDom ? o.away : o.home;
    rows.push({
      match_id: m.id,
      cote_1: dom.c, book_1: dom.b || null,
      cote_n: o.draw.c, book_n: o.draw.b || null,
      cote_2: ext.c, book_2: ext.b || null,
      maj_le: nowISO,
    });
    seen.add(m.id);
    matched.push(`M${String(m.id).padStart(2, '0')} ${m.equipe_dom} v ${m.equipe_ext} → 1:${dom.c ?? '–'} N:${o.draw.c ?? '–'} 2:${ext.c ?? '–'}`);
  }
  return { rows, matched, unmatched };
}

// ── E/S réseau ─────────────────────────────────────────────────────────────────
async function fetchMatchs() {
  if (process.env.MATCHS_FIXTURE_FILE) return JSON.parse(fs.readFileSync(process.env.MATCHS_FIXTURE_FILE, 'utf8'));
  const url = `${process.env.SUPABASE_URL}/rest/v1/matchs?select=id,equipe_dom,equipe_ext,date_match`;
  const res = await fetch(url, { headers: supaHeaders() });
  if (!res.ok) throw new Error(`Supabase GET matchs ${res.status} ${await res.text()}`);
  return res.json();
}

async function fetchOdds() {
  if (process.env.ODDS_FIXTURE_FILE) return JSON.parse(fs.readFileSync(process.env.ODDS_FIXTURE_FILE, 'utf8'));
  const sport = process.env.ODDS_SPORT_KEY || 'soccer_fifa_world_cup';
  const regions = process.env.ODDS_REGIONS || 'eu,uk';
  // commenceTimeFrom = maintenant pour exclure les matchs déjà commencés (cotes live indésirables)
  // Format requis par l'API : YYYY-MM-DDTHH:MM:SSZ (sans millisecondes)
  const from = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
  const url = `https://api.the-odds-api.com/v4/sports/${sport}/odds/?apiKey=${process.env.ODDS_API_KEY}&regions=${regions}&markets=h2h&oddsFormat=decimal&commenceTimeFrom=${from}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`The Odds API ${res.status} ${await res.text()}`);
  const remaining = res.headers.get('x-requests-remaining');
  const used = res.headers.get('x-requests-used');
  if (remaining != null) console.log(`[quota] restant: ${remaining} · utilisé: ${used}`);
  return res.json();
}

// Clé service Supabase : on accepte plusieurs noms de secret courants
function serviceKey() {
  return process.env.SUPABASE_SERVICE_KEY
    || process.env.SUPABASE_SERVICE_ROLE_KEY
    || process.env.SUPABASE_KEY
    || '';
}

function supaHeaders() {
  const k = serviceKey();
  return { apikey: k, Authorization: `Bearer ${k}`, 'Content-Type': 'application/json' };
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
  const offline = process.env.ODDS_FIXTURE_FILE || process.env.MATCHS_FIXTURE_FILE;
  if (!offline) {
    if (!process.env.ODDS_API_KEY) throw new Error("Secret manquant : ODDS_API_KEY");
    if (!process.env.SUPABASE_URL) throw new Error("Secret manquant : SUPABASE_URL");
    if (!serviceKey()) throw new Error("Secret manquant : la clé service Supabase (SUPABASE_SERVICE_KEY, ou SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY) — vérifie le nom exact du secret côté GitHub");
  }
  const [matchs, rawEvents] = await Promise.all([fetchMatchs(), fetchOdds()]);
  const now = Date.now();
  const events = rawEvents.filter(ev => !ev.commence_time || new Date(ev.commence_time).getTime() > now);
  const liveSkipped = rawEvents.length - events.length;
  console.log(`[in] ${matchs.length} matchs en base · ${events.length} événements de cotes${liveSkipped ? ` (${liveSkipped} live ignorés)` : ''}`);
  const { rows, matched, unmatched } = buildRows(matchs, events);
  console.log(`[match] ${rows.length} matchs associés`);
  matched.forEach(l => console.log('  ✓ ' + l));
  if (unmatched.length) {
    console.log(`[non associés] ${unmatched.length} (à vérifier — alias d'équipe ou phase à venir) :`);
    unmatched.forEach(l => console.log('  · ' + l));
  }
  if (!rows.length) { console.log('Rien à écrire.'); return; }
  if (DRY) { console.log('[dry-run] écriture ignorée.'); return; }
  await upsertCotes(rows);
  console.log(`[ok] ${rows.length} lignes écrites dans cotes_marche.`);
}

// N'exécute main() que si lancé directement (pas à l'import depuis un test)
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(e => { console.error('[échec]', e.message); process.exit(1); });
}
