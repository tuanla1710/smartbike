#!/bin/bash
# Open the Smart Bike V1 board in the user-local KiCad 9 install.
set -euo pipefail
ROOT="/home/oran/opt/kicad-root"
SHARE="$ROOT/usr/share/kicad"
LINK="$HOME/.kcad"
if [ ! -e "$LINK" ]; then
    ln -s "$SHARE" "$LINK"
fi
export LD_LIBRARY_PATH="$ROOT/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$ROOT/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
export KICAD9_SYMBOL_DIR="$LINK/symbols"
export KICAD9_FOOTPRINT_DIR="$LINK/footprints"
export KICAD9_TEMPLATE_DIR="$LINK/template"
export KICAD9_3DMODEL_DIR="$LINK/3dmodels"
PROJECT="/home/oran/latuan/v5/hardware/kicad/smartbike_v5/smartbike_v5.kicad_pro"
exec "$ROOT/usr/bin/kicad" "$PROJECT" "$@"
