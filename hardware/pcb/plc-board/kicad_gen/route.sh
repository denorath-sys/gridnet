#!/usr/bin/env bash
#
# Take plc-board.kicad_pcb from placement to a routed, poured, DRC-clean
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

BOARD=../plc-board.kicad_pcb
SCHEMATIC=../plc-board.kicad_sch

echo "== regenerating symbol library and schematic =="
python3 build_library.py
python3 build_schematic.py

echo "== exporting netlist =="
kicad-cli sch export netlist "$SCHEMATIC" --format kicadsexpr -o /tmp/plc-board.net

for attempt in $(seq 1 "$ATTEMPTS"); do
    echo "== attempt $attempt/$ATTEMPTS: placement =="
    python3 build_pcb.py

    echo "== attempt $attempt/$ATTEMPTS: autorouting =="
    python3 -c "
import pcbnew
board = pcbnew.LoadBoard('$BOARD')
pcbnew.ExportSpecctraDSN(board, '$WORK/board.dsn')
"
    # Keep signals off the two plane layers. KiCad writes every copper layer as
    # '(type signal)'; Specctra has a type for a plane and KiCad does not use
    # it.
    #
    # This was tried once before and reverted, because back then the planes
    # were poured *before* the DSN export: marking the layers stopped
    # Freerouting laying signals across them, but also stopped it treating
    # them as connecting GND and +5V, and it fell to 52 unrouted from 7. The
    # planes now go in after routing, so that side-effect is gone and only the
    # wanted half remains. Leaving them routable produced a real short --
    # a +5V via through In2.Cu into a /ST_TMS track laid on the plane layer.
    python3 - "$WORK/board.dsn" <<'PYDSN'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
for layer in ("In1.Cu", "In2.Cu"):
    text, n = re.subn(rf"(\(layer {re.escape(layer)}\s*\n\s*\(type )signal(\))", r"\1power\2", text)
    if n != 1:
        sys.exit(f"could not mark {layer} as a power layer in the DSN (matched {n})")
open(path, "w", encoding="utf-8").write(text)
print("DSN: In1.Cu and In2.Cu marked as power layers")
PYDSN
    "$JAVA" -jar "$FREEROUTING_JAR" -de "$WORK/board.dsn" -do "$WORK/board.ses" \
        --gui.enabled=false -mp "$PASSES" 2>&1 | grep -E "session completed" || true

    python3 -c "
import pcbnew
board = pcbnew.LoadBoard('$BOARD')
pcbnew.ImportSpecctraSES(board, '$WORK/board.ses')
board.Save('$BOARD')
"

    # Pour before repairing, not after. The planes are what connect the power
    # fanout vias -- every power pad on the QFN gets a stub and a via at build
    # time, and until the copper is poured those vias are isolated points the
    # router would have to tie together itself, which is the problem the
    # fanout exists to remove. Pouring first makes them connected, so repair
    # only sees connections that are genuinely missing.
    #
    # This is not the ordering the Main Board warns about. There the danger is
    # pouring before *routing*, which makes the autorouter treat GND as done
    # and lay no copper for it. Routing has already happened here.
    echo "== attempt $attempt/$ATTEMPTS: pouring ground =="
    python3 build_pcb.py --pour

    echo "== attempt $attempt/$ATTEMPTS: finishing what the autorouter dropped =="
    if python3 finish_routing.py; then
        echo "== isolation barrier, on copper this time =="
        python3 -c "
import sys; sys.path.insert(0, '.')
import pcbnew, build_pcb
board = pcbnew.LoadBoard('$BOARD')
build_pcb.check_isolation_barrier(board)
print('barrier: clean')
"

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
