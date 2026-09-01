#!/usr/bin/env bash
set -euo pipefail

MYSQL_USER="${MYSQL_USER:-fhope}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-123456}"
MYSQL_DB="${MYSQL_DB:-fhope_lab}"

run_one() {
  local mode="$1"
  local count="$2"
  local name="$3"
  shift 3
  echo
  echo "========== $name =========="
  python3 client.py \
    --user "$MYSQL_USER" \
    --password "$MYSQL_PASSWORD" \
    --database "$MYSQL_DB" \
    --mode "$mode" \
    --count "$count" \
    --run-name "$name" \
    "$@"
}

run_one original 8 original_observation
run_one same-number 20 same_number_20 --value 5
run_one same-string 20 same_string_20 --value apple
run_one increasing 20 increasing_20
run_one skewed 20 skewed_20
run_one random-small-domain 50 random_small_domain_50 --domain-size 10

python3 scripts/analyze_results.py --results-dir results
