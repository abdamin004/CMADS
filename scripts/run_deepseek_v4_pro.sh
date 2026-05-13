#!/usr/bin/env bash
# Run the MAS pipeline against DeepSeek-V4-Pro on NVIDIA NIM.
#
# Prerequisite — in .env:
#   NVIDIA_API_KEY=nvapi-<your-new-key>
#
# Usage:
#   ./scripts/run_deepseek_v4_pro.sh smoke            # 1-patient smoke test
#   ./scripts/run_deepseek_v4_pro.sh batch            # full 20-patient batch

set -euo pipefail

cd "$(dirname "$0")/.."

# ── Load NVIDIA_API_KEY from .env ─────────────────────────
if [ ! -f .env ]; then
  echo "ERROR: .env not found." >&2
  exit 1
fi
set -a
. ./.env
set +a

if [ -z "${NVIDIA_API_KEY:-}" ]; then
  echo "ERROR: NVIDIA_API_KEY not set in .env." >&2
  echo "Add the line: NVIDIA_API_KEY=nvapi-<your-new-key>" >&2
  exit 1
fi

# ── Point CMADS at NVIDIA NIM (OpenAI-compatible) ─────────
export LLM_PROVIDER=openai
export LLM_MODEL="deepseek-ai/deepseek-v4-pro"
export OPENAI_BASE_URL="https://integrate.api.nvidia.com/v1"
export OPENAI_API_KEY="$NVIDIA_API_KEY"

# Keep the evaluator on Groq/Qwen3-32B so this is an apples-to-apples
# comparison against the existing Groq and Med42 runs (same judge).
# (LLM_EVALUATOR_PROVIDER + LLM_EVALUATOR_MODEL must already be in .env.)
if [ -z "${LLM_EVALUATOR_MODEL:-}" ]; then
  export LLM_EVALUATOR_MODEL="qwen/qwen3-32b"
fi
if [ -z "${LLM_EVALUATOR_PROVIDER:-}" ]; then
  export LLM_EVALUATOR_PROVIDER="groq"
fi

# ── Isolate results so we don't clobber the Groq run ──────
export MAS_RESULTS_DIR="data/gold/mas_results_deepseek_v4_pro"
mkdir -p "$MAS_RESULTS_DIR"

# DeepSeek reasoning models can be slow — raise per-agent timeout.
export AGENT_TIMEOUT="${AGENT_TIMEOUT:-900}"

echo "────────────────────────────────────────────────────────────"
echo "Provider:       $LLM_PROVIDER"
echo "Model:          $LLM_MODEL"
echo "Endpoint:       $OPENAI_BASE_URL"
echo "Evaluator:      $LLM_EVALUATOR_PROVIDER / $LLM_EVALUATOR_MODEL"
echo "Results dir:    $MAS_RESULTS_DIR"
echo "Agent timeout:  ${AGENT_TIMEOUT}s"
echo "────────────────────────────────────────────────────────────"

MODE="${1:-smoke}"
case "$MODE" in
  smoke)
    # Pick the first UUID from the batch so the smoke test uses a patient
    # that will also run in the full batch.
    UUID="$(/usr/local/bin/python3.14 -c 'import json; print(json.load(open("data/gold/batches/batch_4_med42_20.json"))[0])')"
    echo "SMOKE TEST on patient $UUID"
    /usr/local/bin/python3.14 -c "from src.orchestrator.graph import run_single_patient; run_single_patient('$UUID')"
    ;;
  batch)
    echo "FULL BATCH — 20 patients"
    /usr/local/bin/python3.14 -c "from src.orchestrator.graph import run_cohort; run_cohort('data/gold/batches/batch_4_med42_20.json')"
    ;;
  *)
    echo "Usage: $0 {smoke|batch}" >&2
    exit 2
    ;;
esac
