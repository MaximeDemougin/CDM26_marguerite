#!/usr/bin/env node
// Backfill des cotes WC2026 depuis OddsPortal.
//
// Source  : OddsPortal (scraping HTML + __NEXT_DATA__ Next.js)
// Cible   : table Supabase `cotes_marche`
// Exécution : manuel via workflow_dispatch
//
// Variables d'environnement :
//   SUPABASE_URL                 ex. https://xxxx.supabase.co
//   SUPABASE_SERVICE_KEY         clé "service_role" (ou _ROLE_KEY / _KEY)
//   MATCHS_FIXTURE_FILE          JSON matchs hors-ligne
//   ODDS_PORTAL_FIXTURE_FILE     JSON événements format The Odds API (hors-ligne)
//   DELAY_MS                     délai ms entre requêtes OddsPortal (défaut 1200)
//   DRY_RUN=1                    affiche sans écrire
//
// Usage : node scripts/backfill-cotes.mjs [--dry-run]

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { TEAMS_FR_EN, norm, buildEnToFr, buildRows } from './update-cotes.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DRY = process.argv.includes('--dry-run') || process.env.DRY_RUN === '1';
const DELAY_MS = Number(process.env.DELAY_MS) || 1200;

// ── HTTP ───────────────────────────────────────────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function httpGet(url) {
  const res = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.9',
      'Cache-Control': 'no-cache',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
    },
  });
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status} — ${url}`), { status: res.status });
  return res.text();
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

async function fetchMatchsFromDb() {
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

// ── Parsing OddsPortal ─────────────────────────────────────────────────────────
const OP_BASE = 'https://www.oddsportal.com';
const OP_SLUGS = [
  '/football/world/world-cup-2026',
  '/football/world/world-championship-2026',
];
// Chemins qui ne sont pas des matchs individuels
const NON_MATCH = /\/(results|standings|teams|players|schedule|fixtures|draw|tables|archive)\/?$/;

function extractNextData(html) {
  const m = html.match(/<script[^>]+id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) return null;
  try { return JSON.parse(m[1]); } catch { return null; }
}

// Parcours en profondeur (DFS) d'un objet JSON
function* walkJson(obj, depth = 0) {
  if (depth > 40 || obj === null || typeof obj !== 'object') return;
  yield obj;
  const vals = Array.isArray(obj) ? obj : Object.values(obj);
  for (const v of vals) {
    if (v && typeof v === 'object') yield* walkJson(v, depth + 1);
  }
}

function isOdd(v) { return typeof v === 'number' && isFinite(v) && v > 1.0 && v < 201; }

// Extraire noms d'équipes depuis le HTML (title, og:title, h1)
function extractTeamNamesFromHtml(html) {
  for (const re of [
    /<title[^>]*>([^<|]+?)\s*[\|–-]/i,
    /<meta[^>]+property="og:title"[^>]+content="([^"]+)"/i,
    /<meta[^>]+content="([^"]+)"[^>]+property="og:title"/i,
  ]) {
    const m = html.match(re);
    if (!m) continue;
    const parts = m[1].trim().split(/\s+[-–]\s+/);
    if (parts.length === 2 && parts[0].length > 1 && parts[1].length > 1) {
      return { homeEn: parts[0].trim(), awayEn: parts[1].trim() };
    }
  }
  return null;
}

// Cherche les cotes bookmaker dans __NEXT_DATA__
// Retourne [{ title, home, draw, away }] (valeurs nullables)
function extractBookmakerOdds(data, homeEn, awayEn) {
  const found = [];
  const seen = new Set();

  for (const node of walkJson(data)) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) continue;

    const rawName = node.bookmakername ?? node.bookmakerName ?? node.bkname;
    const title = typeof rawName === 'string' ? rawName.trim() : null;
    if (!title || title.length < 2 || title.length > 80) continue;
    // Déduplique par titre (on garde la première occurrence)
    if (seen.has(title.toLowerCase())) continue;

    // Pattern OddsPortal : odd1=home, odd2=draw(X), odd3=away(2) — format 1X2
    if (isOdd(node.odd1) && isOdd(node.odd3)) {
      seen.add(title.toLowerCase());
      found.push({ title, home: node.odd1, draw: isOdd(node.odd2) ? node.odd2 : null, away: node.odd3 });
      continue;
    }
  }

  // Cherche aussi le pattern outcomes nommés (format The Odds API ou similaire)
  for (const node of walkJson(data)) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) continue;
    const rawName = node.name ?? node.title ?? node.bookmakername ?? node.bookmakerName;
    if (typeof rawName !== 'string' || rawName.length < 2 || rawName.length > 80) continue;
    if (seen.has(rawName.toLowerCase())) continue;

    const outcomes = node.outcomes ?? node.markets?.[0]?.outcomes;
    if (!Array.isArray(outcomes) || outcomes.length < 2) continue;

    let h = null, d = null, a = null;
    for (const o of outcomes) {
      const price = Number(o.price ?? o.odd ?? o.value);
      if (!isOdd(price)) continue;
      const oname = String(o.name || o.team || '');
      if (norm(oname) === norm(homeEn)) h = price;
      else if (norm(oname) === norm(awayEn)) a = price;
      else if (/draw|tie|nul/i.test(oname)) d = price;
    }
    if (h != null || a != null) {
      seen.add(rawName.toLowerCase());
      found.push({ title: rawName.trim(), home: h, draw: d, away: a });
    }
  }

  return found;
}

// Convertit en format The Odds API (compatible buildRows/bestOdds)
function toOddsApiFormat(homeEn, awayEn, bookies) {
  if (!bookies.length) return null;
  const bookmakers = bookies.map(b => ({
    title: b.title,
    markets: [{
      key: 'h2h',
      outcomes: [
        ...(b.home != null ? [{ name: homeEn, price: b.home }] : []),
        ...(b.away != null ? [{ name: awayEn, price: b.away }] : []),
        ...(b.draw != null ? [{ name: 'Draw', price: b.draw }] : []),
      ],
    }],
  }));
  return { home_team: homeEn, away_team: awayEn, bookmakers };
}

// Extrait les liens de matchs depuis la page résultats
function extractMatchLinks(html, slug) {
  const links = new Set();

  // Via __NEXT_DATA__ (valeurs d'URL dans le JSON)
  const nd = extractNextData(html);
  if (nd) {
    for (const node of walkJson(nd)) {
      const url = node?.url ?? node?.link ?? node?.href;
      if (typeof url === 'string'
        && url.startsWith(slug + '/')
        && url.endsWith('/')
        && !NON_MATCH.test(url)
        && url.length > slug.length + 8) {
        links.add(url);
      }
    }
  }

  // Fallback : regex sur les href HTML
  const slugEscaped = slug.replace(/\//g, '\\/');
  const re = new RegExp(`href="(${slugEscaped}\\/[^/"]+\\/)"`, 'g');
  let m;
  while ((m = re.exec(html)) !== null) {
    if (!NON_MATCH.test(m[1])) links.add(m[1]);
  }

  return [...links];
}

async function scrapeMatchPage(url) {
  const fullUrl = url.startsWith('http') ? url : OP_BASE + url;
  const html = await httpGet(fullUrl);

  const teams = extractTeamNamesFromHtml(html);
  if (!teams) {
    console.warn(`  [skip] noms d'équipes non trouvés : ${fullUrl}`);
    return null;
  }

  const nd = extractNextData(html);
  if (!nd) {
    console.warn(`  [skip] pas de __NEXT_DATA__ : ${fullUrl}`);
    return null;
  }

  const bookies = extractBookmakerOdds(nd, teams.homeEn, teams.awayEn);
  const pinnacleFound = bookies.some(b => /pinnacle/i.test(b.title));
  console.log(`  [teams] ${teams.homeEn} vs ${teams.awayEn} — ${bookies.length} bookmakers${pinnacleFound ? ' (Pinnacle ✓)' : ''}`);

  return toOddsApiFormat(teams.homeEn, teams.awayEn, bookies);
}

async function scrapeOddsPortal() {
  let links = [], usedSlug = null;

  for (const slug of OP_SLUGS) {
    const url = `${OP_BASE}${slug}/results/`;
    console.log(`[op] résultats : ${url}`);
    try {
      const html = await httpGet(url);
      links = extractMatchLinks(html, slug);
      console.log(`[op] ${links.length} liens trouvés pour slug ${slug}`);
      if (links.length) { usedSlug = slug; break; }
    } catch (e) {
      console.warn(`[warn] ${slug} : ${e.message}`);
    }
    await sleep(DELAY_MS);
  }

  if (!links.length) {
    console.error('[erreur] Aucun lien trouvé — vérifier les slugs OddsPortal ou les headers HTTP');
    return [];
  }

  console.log(`[op] scraping ${links.length} matchs (délai ${DELAY_MS}ms) …`);
  const events = [];
  for (const link of links) {
    await sleep(DELAY_MS);
    console.log(`[op] match : ${link}`);
    try {
      const ev = await scrapeMatchPage(link);
      if (ev) events.push(ev);
    } catch (e) {
      console.warn(`  [erreur] ${e.message}`);
    }
  }
  return events;
}

// ── Main ───────────────────────────────────────────────────────────────────────
async function main() {
  const offlineAll = process.env.ODDS_PORTAL_FIXTURE_FILE && process.env.MATCHS_FIXTURE_FILE;
  if (!offlineAll) {
    if (!process.env.SUPABASE_URL) throw new Error('Secret manquant : SUPABASE_URL');
    if (!serviceKey()) throw new Error('Secret manquant : clé service Supabase (SUPABASE_SERVICE_KEY / _ROLE_KEY / _KEY)');
  }

  const today = new Date().toISOString().slice(0, 10);
  const allMatchs = await fetchMatchsFromDb();
  const pastMatchs = allMatchs.filter(m => m.date_match && m.date_match < today && m.equipe_dom && m.equipe_ext);
  console.log(`[in] ${allMatchs.length} matchs en base, ${pastMatchs.length} passés à traiter (avant ${today})`);

  if (!pastMatchs.length) { console.log('Aucun match passé — rien à faire.'); return; }

  let events;
  if (process.env.ODDS_PORTAL_FIXTURE_FILE) {
    events = JSON.parse(fs.readFileSync(process.env.ODDS_PORTAL_FIXTURE_FILE, 'utf8'));
    console.log(`[fixture] ${events.length} événements chargés`);
  } else {
    events = await scrapeOddsPortal();
    console.log(`[op] ${events.length} événements scraped au total`);
  }

  if (!events.length) { console.log('Aucun événement — rien à écrire.'); return; }

  const { rows, matched, unmatched } = buildRows(pastMatchs, events);
  console.log(`[match] ${rows.length} matchs associés`);
  matched.forEach(l => console.log('  ✓ ' + l));
  if (unmatched.length) {
    console.log(`[non associés] ${unmatched.length} :`);
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
