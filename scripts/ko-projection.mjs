// Résolution des équipes de phase finale côté serveur (même logique que l'app).
// Entrée : lignes `matchs` (id, equipe_dom, equipe_ext, groupe, score_dom, score_ext).
// Sortie : copie des matchs avec equipe_dom/equipe_ext résolus pour le KO
//          ("2e Gr.A" -> vraie équipe) quand les résultats de groupes le permettent.
//
// Sert à associer les cotes (vraies équipes côté API) aux bons match_id KO,
// puisque le calendrier en base ne contient que des libellés.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Table officielle FIFA des 3es : clé = 4 groupes non qualifiés, valeur = 8 lettres
// dans l'ordre des colonnes 1A,1B,1D,1E,1G,1I,1K,1L = matchs 79,85,81,74,82,77,87,80.
const R32 = JSON.parse(fs.readFileSync(path.join(__dirname, 'r32-table.json'), 'utf8'));
const R32_ORDER = [79, 85, 81, 74, 82, 77, 87, 80];

// Classement FIFA (départage final) — copié de l'app (index.html).
const FIFA_RANKS = { "Argentine": 1, "Espagne": 2, "France": 3, "Angleterre": 4, "Portugal": 5, "Brésil": 6, "Maroc": 7, "Pays-Bas": 8, "Belgique": 9, "Allemagne": 10, "Croatie": 11, "Colombie": 13, "Mexique": 14, "Sénégal": 15, "Uruguay": 16, "États-Unis": 17, "Japon": 18, "Suisse": 19, "Iran": 20, "Turquie": 22, "Équateur": 23, "Autriche": 24, "Corée du Sud": 25, "Australie": 27, "Algérie": 28, "Égypte": 29, "Canada": 30, "Norvège": 31, "Côte d'Ivoire": 33, "Panama": 34, "Suède": 38, "Rép. tchèque": 40, "Paraguay": 41, "Écosse": 42, "Tunisie": 45, "RD Congo": 46, "Ouzbékistan": 50, "Qatar": 56, "Irak": 57, "Afrique du Sud": 60, "Arabie saoudite": 61, "Jordanie": 63, "Bosnie-Herzég.": 64, "Cap-Vert": 67, "Ghana": 73, "Curaçao": 82, "Haïti": 83, "Nouvelle-Zélande": 85 };

// Classement des groupes, mêmes départages que l'app : H2H pts → H2H diff → H2H BP
// → diff générale → BP général → classement FIFA → alpha.
function groupStandings(matchs) {
  const gm = matchs.filter(m => m.groupe);
  const groups = {};
  for (const m of gm) {
    const g = m.groupe;
    groups[g] = groups[g] || {};
    for (const t of [m.equipe_dom, m.equipe_ext]) if (!groups[g][t]) groups[g][t] = { team: t, pts: 0, j: 0, gf: 0, ga: 0, d: 0 };
    if (m.score_dom == null || m.score_ext == null) continue;
    const a = Number(m.score_dom), b = Number(m.score_ext);
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
    const t1 = groups[g][m.equipe_dom], t2 = groups[g][m.equipe_ext];
    t1.j++; t2.j++; t1.gf += a; t1.ga += b; t2.gf += b; t2.ga += a; t1.d = t1.gf - t1.ga; t2.d = t2.gf - t2.ga;
    if (a > b) t1.pts += 3; else if (b > a) t2.pts += 3; else { t1.pts++; t2.pts++; }
  }
  const h2h = (g, tset) => {
    const h = {}; tset.forEach(t => { h[t] = { pts: 0, gf: 0, ga: 0 }; });
    gm.filter(m => m.groupe === g && tset.has(m.equipe_dom) && tset.has(m.equipe_ext)).forEach(m => {
      if (m.score_dom == null || m.score_ext == null) return;
      const a = Number(m.score_dom), b = Number(m.score_ext);
      if (!Number.isFinite(a) || !Number.isFinite(b)) return;
      h[m.equipe_dom].gf += a; h[m.equipe_dom].ga += b; h[m.equipe_ext].gf += b; h[m.equipe_ext].ga += a;
      if (a > b) h[m.equipe_dom].pts += 3; else if (b > a) h[m.equipe_ext].pts += 3; else { h[m.equipe_dom].pts++; h[m.equipe_ext].pts++; }
    });
    return h;
  };
  const fifaSort = (g, arr) => {
    if (arr.length <= 1) return arr;
    const byPts = {}; arr.forEach(t => { (byPts[t.pts] = byPts[t.pts] || []).push(t); });
    return Object.keys(byPts).sort((a, b) => b - a).flatMap(pts => {
      const grp = byPts[pts]; if (grp.length === 1) return grp;
      const tset = new Set(grp.map(t => t.team)); const hh = h2h(g, tset);
      grp.sort((a, b) => {
        const ha = hh[a.team], hb = hh[b.team];
        return hb.pts - ha.pts || (hb.gf - hb.ga) - (ha.gf - ha.ga) || hb.gf - ha.gf || b.d - a.d || b.gf - a.gf || (FIFA_RANKS[a.team] || 999) - (FIFA_RANKS[b.team] || 999) || a.team.localeCompare(b.team);
      });
      return grp;
    });
  };
  const sorted = {};
  Object.keys(groups).sort().forEach(g => { sorted[g] = fifaSort(g, Object.values(groups[g])); });
  return sorted;
}

// Renvoie une COPIE des matchs avec les libellés KO résolus en vraies équipes
// (quand c'est possible avec les résultats disponibles).
export function resolveKnockout(matchs) {
  const tables = groupStandings(matchs);
  const first = {}, second = {}, thirdByGroup = {}, third = [];
  for (const g of Object.keys(tables)) {
    const arr = tables[g];
    if (arr[0]) first[g] = arr[0].team;
    if (arr[1]) second[g] = arr[1].team;
    if (arr[2]) { thirdByGroup[g] = arr[2].team; third.push({ group: g, ...arr[2] }); }
  }
  // 8 meilleurs 3es (même tri que l'app), puis attribution officielle aux matchs.
  const best = third.slice().sort((a, b) => b.pts - a.pts || b.d - a.d || b.gf - a.gf || (FIFA_RANKS[a.team] || 999) - (FIFA_RANKS[b.team] || 999) || a.team.localeCompare(b.team)).slice(0, 8);
  const thirdByMatch = {};
  if (best.length === 8) {
    const present = new Set(best.map(x => x.group));
    const missing = "ABCDEFGHIJKL".split("").filter(g => !present.has(g)).join("");
    const v = R32[missing];
    if (v && v.length === 8) for (let i = 0; i < 8; i++) thirdByMatch[R32_ORDER[i]] = thirdByGroup[v[i]];
  }
  const origById = new Map(matchs.map(m => [m.id, m]));
  const winners = {}, losers = {};
  const resolveLabel = (lbl, id) => {
    if (typeof lbl !== 'string') return lbl;
    let mm;
    if (mm = lbl.match(/^1er Gr\.([A-L])$/)) return first[mm[1]] || lbl;
    if (mm = lbl.match(/^2e Gr\.([A-L])$/)) return second[mm[1]] || lbl;
    if (/^3[A-L]+$/.test(lbl)) return thirdByMatch[id] || lbl;
    if (mm = lbl.match(/^V\.M(\d+)$/)) return winners[Number(mm[1])] || lbl;
    if (mm = lbl.match(/^Perdant M(\d+)$/)) return losers[Number(mm[1])] || lbl;
    return lbl;
  };
  const resolved = matchs.map(m => ({ ...m }));
  // KO dans l'ordre des id (V.M/Perdant dépendent des matchs précédents).
  for (const m of resolved.filter(x => !x.groupe).sort((a, b) => a.id - b.id)) {
    const orig = origById.get(m.id);
    m.equipe_dom = resolveLabel(orig.equipe_dom, m.id);
    m.equipe_ext = resolveLabel(orig.equipe_ext, m.id);
    if (m.score_dom != null && m.score_ext != null) {
      const a = Number(m.score_dom), b = Number(m.score_ext);
      // Sans prolongation/TAB côté serveur : on ne tranche que les scores décisifs.
      if (Number.isFinite(a) && Number.isFinite(b) && a !== b) {
        winners[m.id] = a > b ? m.equipe_dom : m.equipe_ext;
        losers[m.id] = a > b ? m.equipe_ext : m.equipe_dom;
      }
    }
  }
  return resolved;
}
