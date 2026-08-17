#!/usr/bin/env bash
set -euo pipefail

dataset_dir="${1:-backend/evals/benchmarks/scifact}"
dataset_url="https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"

if [[ -e "$dataset_dir/corpus.jsonl" ]]; then
  printf 'SciFact already exists at %s\n' "$dataset_dir"
  exit 0
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

curl -fL --retry 3 "$dataset_url" -o "$tmp_dir/scifact.zip"
unzip -q "$tmp_dir/scifact.zip" -d "$tmp_dir"
mkdir -p "$(dirname "$dataset_dir")"
mv "$tmp_dir/scifact" "$dataset_dir"
printf 'Downloaded BEIR SciFact to %s\n' "$dataset_dir"
