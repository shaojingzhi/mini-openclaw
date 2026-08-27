#!/usr/bin/env bash
set -euo pipefail

dataset_dir="${1:-backend/evals/benchmarks/hotpotqa_distractor}"
dataset_file="$dataset_dir/validation_offset_0_length_100.json"
dataset_url="https://datasets-server.huggingface.co/rows?dataset=hotpotqa%2Fhotpot_qa&config=distractor&split=validation&offset=0&length=100"

if [[ -e "$dataset_file" ]]; then
  printf 'HotpotQA sample already exists at %s\n' "$dataset_file"
  exit 0
fi

mkdir -p "$dataset_dir"
curl --fail --location --retry 3 --proxy "${HTTPS_PROXY:-http://127.0.0.1:7890}" \
  "$dataset_url" \
  -o "$dataset_file"
printf 'Downloaded HotpotQA distractor validation sample to %s\n' "$dataset_file"
