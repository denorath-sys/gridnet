#!/usr/bin/env bash
#
# Take main-board.kicad_pcb from placement to a routed, poured, DRC-clean
# board. Run from this directory:
#
#     FREEROUTING_JAR=/path/to/freerouting.jar JAVA=/path/to/java ./route.sh
#
# Freerouting is not deterministic and not honest about failure: two runs on
# the same input drop different connections, and it reports success either
# way. So the flow is route -> verify -> repair, and if repair cannot close
# the gap, throw that routing away and run it again rather than hand-patching
# a board that the next regeneration would lose anyway. Three attempts has
# always been enough; the failure is loud if it is not.
#
set -euo pipefail

cd "$(dirname "$0")"

JAVA="${JAVA:-java}"
FREEROUTING_JAR="${FREEROUTING_JAR:?set FREEROUTING_JAR to the freerouting jar}"
PASSES="${PASSES:-20}"
ATTEMPTS="${ATTEMPTS:-3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

BOARD=../main-board.kicad_pcb
SCHEMATIC=../main-board.kicad_sch

echo "== regenerating symbol library and schematic =="
python3 build_library.py
python3 build_schematic.py

echo "== exporting netlist =="
kicad-cli sch export netlist "$SCHEMATIC" --format kicadsexpr -o /tmp/main-board.net

for attempt in $(seq 1 "$ATTEMPTS"); do
    echo "== attempt $attempt/$ATTEMPTS: placement =="
    python3 build_pcb.py

    echo "== attempt $attempt/$ATTEMPTS: autorouting =="
    python3 -c "
import pcbnew
board = pcbnew.LoadBoard('$BOARD')
pcbnew.ExportSpecctraDSN(board, '$WORK/board.dsn')
"
    "$JAVA" -jar "$FREEROUTING_JAR" -de "$WORK/board.dsn" -do "$WORK/board.ses" \
        --gui.enabled=false -mp "$PASSES" 2>&1 | grep -E "session completed" || true

    python3 -c "
import pcbnew
board = pcbnew.LoadBoard('$BOARD')
pcbnew.ImportSpecctraSES(board, '$WORK/board.ses')
board.Save('$BOARD')
"

    echo "== attempt $attempt/$ATTEMPTS: finishing what the autorouter dropped =="
    if python3 finish_routing.py; then
        echo "== pouring ground =="
        python3 build_pcb.py --pour
        echo "== DRC =="
        kicad-cli pcb drc "$BOARD" --format json --severity-all -o "$WORK/drc.json"
        python3 - "$WORK/drc.json" <<'PY'
import collections, json, sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
violations = report.get("violations", [])
unconnected = report.get("unconnected_items", [])
errors = [v for v in violations if v["severity"] == "error"]
print("violations:", dict(collections.Counter(v["type"] for v in violations)))
print("unconnected:", len(unconnected))
for v in violations:
    print(" ", v["severity"], v["type"], ":",
          " | ".join(i.get("description", "")[:60] for i in v.get("items", [])))
sys.exit(1 if errors or unconnected else 0)
PY
        echo "== done =="
        exit 0
    fi
    echo "== attempt $attempt/$ATTEMPTS could not be finished; re-routing from scratch =="
done

echo "gave up after $ATTEMPTS attempts" >&2
exit 1
