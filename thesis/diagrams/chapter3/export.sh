#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEX="${SCRIPT_DIR}/index.html"
OUT_DIR="${SCRIPT_DIR}/../../images"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [[ ! -x "${CHROME}" ]]; then
  CHROME="/Applications/Google Chrome 2.app/Contents/MacOS/Google Chrome"
fi
if [[ ! -x "${CHROME}" ]]; then
  echo "Google Chrome executable not found. Set CHROME=/path/to/chrome." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

figures=(
  "system_architecture:1800:920"
  "data_pipeline:1800:830"
  "agent_pipeline:1800:1490"
  "multilevel_memory:1800:940"
  "agent_blueprint:1800:870"
  "agent_ehr_flow:1800:540"
  "agent_lab_flow:1800:540"
  "agent_diag_flow:1800:1060"
  "agent_reviewer_flow:1800:540"
  "agent_refiner_flow:1800:980"
  "tech_stack:1800:1180"
)

for item in "${figures[@]}"; do
  IFS=":" read -r name width height <<< "${item}"
  "${CHROME}" \
    --headless=new \
    --disable-gpu \
    --hide-scrollbars \
    --run-all-compositor-stages-before-draw \
    --virtual-time-budget=1000 \
    --force-device-scale-factor=2 \
    --window-size="${width},${height}" \
    --screenshot="${OUT_DIR}/ch3_${name}.png" \
    "file://${INDEX}?figure=${name}" >/dev/null 2>&1
  echo "exported ch3_${name}.png"
done
