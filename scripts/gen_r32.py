# Parse + valide la table officielle FIFA d'attribution des 3es (round of 32).
# Colonnes (ordre) : 1A,1B,1D,1E,1G,1I,1K,1L  ->  matchs M79,M85,M81,M74,M82,M77,M87,M80
# Sortie : JSON { "<4 groupes non qualifies tries>": "<8 lettres, ordre colonnes>" }
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALLG = list("ABCDEFGHIJKL")
COL_WINNER = ["A","B","D","E","G","I","K","L"]  # vainqueur de groupe par colonne

out = {}
errors = []
count = 0

with open(os.path.join(HERE, "r32-raw.txt"), encoding="utf-8") as f:
    for line in f:
        t = line.split()
        if not t or not t[0].isdigit():
            continue
        count += 1
        num = t[0]
        try:
            k = next(i for i, x in enumerate(t) if x in ("Yes", "No"))
        except StopIteration:
            errors.append(f"row {num}: pas de Yes/No"); continue
        groups = t[1:k]
        thirds = [x[1:] if x.startswith("3") else x for x in t[k+1:]]
        if len(groups) != 8:
            errors.append(f"row {num}: {len(groups)} groupes ({''.join(groups)})")
        if len(thirds) != 8:
            errors.append(f"row {num}: {len(thirds)} thirds ({''.join(thirds)})")
        gset, tset = set(groups), set(thirds)
        if len(tset) != 8 or not tset.issubset(gset):
            errors.append(f"row {num}: thirds != permutation (g={''.join(groups)} t={''.join(thirds)})")
        for i, g in enumerate(thirds):
            if i < len(COL_WINNER) and g == COL_WINNER[i]:
                errors.append(f"row {num}: colonne 1{COL_WINNER[i]} recoit son propre groupe")
        missing = "".join(g for g in ALLG if g not in gset)
        if len(missing) != 4:
            errors.append(f"row {num}: {len(missing)} groupes manquants ({missing})")
        if missing in out:
            errors.append(f"row {num}: combinaison en double ({missing})")
        out[missing] = "".join(thirds)

print("Lignes lues :", count, file=sys.stderr)
print("Combinaisons uniques :", len(out), file=sys.stderr)
print("Erreurs :", len(errors), file=sys.stderr)
for e in errors[:40]:
    print("  - " + e, file=sys.stderr)

cur = out.get("CHJK")
print(f"CHJK = {cur} | 1I(M77) = {cur[5] if cur else '??'} (attendu F)", file=sys.stderr)

if not errors and len(out) == 495:
    with open(os.path.join(HERE, "r32-table.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print("OK -> r32-table.json ecrit", file=sys.stderr)
else:
    print("ABANDON : corriger les erreurs.", file=sys.stderr)
    sys.exit(1)
