#!/usr/bin/env bash
# =============================================================================
# run_batch.sh — Synthea batch runner for Clinical AI Data Lake
# Usage:
#   ./config/run_batch.sh <batch_name> <population_size> [state]
#
# Examples:
#   ./config/run_batch.sh batch_001 1000 Massachusetts
#   ./config/run_batch.sh batch_test 100
#   ./config/run_batch.sh stress_001 10000 California
# =============================================================================

set -euo pipefail

BATCH_NAME="${1:?Usage: run_batch.sh <batch_name> <population_size> [state]}"
POP_SIZE="${2:?Usage: run_batch.sh <batch_name> <population_size> [state]}"
STATE="${3:-Massachusetts}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNTHEA_DIR="$PROJECT_ROOT/synthea"
CONFIG_FILE="$PROJECT_ROOT/config/synthea.properties"
OUTPUT_DIR="$PROJECT_ROOT/data/raw/$BATCH_NAME"

echo "============================================="
echo "  Synthea Batch Runner"
echo "  Batch   : $BATCH_NAME"
echo "  Patients: $POP_SIZE"
echo "  State   : $STATE"
echo "  Output  : $OUTPUT_DIR"
echo "============================================="

# Create batch output dirs
mkdir -p "$OUTPUT_DIR/fhir" "$OUTPUT_DIR/csv" "$OUTPUT_DIR/metadata"

# Override baseDirectory to write directly into the batch folder
java -jar "$SYNTHEA_DIR/build/libs/synthea-with-dependencies.jar" \
  -p "$POP_SIZE" \
  -c "$CONFIG_FILE" \
  --exporter.baseDirectory="$OUTPUT_DIR/" \
  "$STATE"

echo ""
echo "Done. Output in $OUTPUT_DIR"
echo ""
echo "File counts:"
echo "  FHIR bundles : $(ls "$OUTPUT_DIR/fhir/"*.json 2>/dev/null | wc -l)"
echo "  CSV tables   : $(ls "$OUTPUT_DIR/csv/"*.csv 2>/dev/null | wc -l)"
