"""Print a findings summary from a redteam JSON results file."""
import json
import sys

if len(sys.argv) < 2:
    sys.exit(0)

path = sys.argv[1]
try:
    d = json.load(open(path))
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(0)

results = d.get("results", [])
passed = d.get("passed_types", [])

print("━" * 60)
print("  FINDINGS")
print("━" * 60)

if not results:
    print("  No findings.")

for r in results:
    defn = r.get("definition", {})
    sid = defn.get("id", "?")
    sev = r.get("severity", "?").upper()
    print(f"  🔴 [{sev}] {sid}")
    turns = r.get("turns", [])
    if turns:
        resp = turns[0].get("response", "")[:120].replace("\n", " ")
        print(f"     └─ {resp}...")

if passed:
    print()
    print(f"  ✅ {len(passed)} attack(s) passed (no finding)")

print("━" * 60)
