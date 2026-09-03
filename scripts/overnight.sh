#!/usr/bin/env bash
# Sweep several local models and rebuild the leaderboard.
#
#   ./scripts/overnight.sh                    # default model list
#   ./scripts/overnight.sh qwen3:8b llama3.1:8b
#
# Safe to leave running. Each model writes its own results file, so a model
# that fails does not cost you the ones that already finished.
set -uo pipefail

MODELS=("$@")
if [ ${#MODELS[@]} -eq 0 ]; then
  MODELS=(qwen3:8b llama3.1:8b mistral-nemo qwen2.5:7b granite3.3:8b)
fi

PADS="${PADS:-0,8,16,24}"
REPEATS="${REPEATS:-5}"
MAX_TOKENS="${MAX_TOKENS:-4096}"

mkdir -p results logs
echo "sweeping ${#MODELS[@]} models | pads ${PADS} | repeats ${REPEATS}"

for model in "${MODELS[@]}"; do
  slug="${model//[:\/]/-}"
  echo
  echo "=== ${model} ==="
  if ! ollama pull "$model" >/dev/null 2>&1; then
    echo "  could not pull ${model}, skipping"
    continue
  fi
  callprobe run \
    --model "$model" \
    --pad "$PADS" \
    --repeats "$REPEATS" \
    --max-tokens "$MAX_TOKENS" \
    --out "results/${slug}.json" \
    2>"logs/${slug}.log" | tee "logs/${slug}.txt"
done

echo
echo "=== leaderboard ==="
callprobe leaderboard results/*.json | tee LEADERBOARD.md
