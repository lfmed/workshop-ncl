#!/bin/bash
# Acompanha um job run: emite mudancas de estado das tasks e termina quando o run acaba.
RUN=$1; PROFILE=${2:-nuclea-genie}; prev=""
while true; do
  s=$(databricks jobs get-run "$RUN" --profile "$PROFILE" -o json 2>/dev/null || true)
  cur=$(echo "$s" | jq -r '.tasks[]? | "\(.task_key): \(.state.life_cycle_state) \(.state.result_state // "")"' | sort)
  comm -13 <(echo "$prev") <(echo "$cur"); prev=$cur
  lc=$(echo "$s" | jq -r '.state.life_cycle_state')
  case "$lc" in TERMINATED|INTERNAL_ERROR|SKIPPED) echo "RUN: $lc $(echo "$s" | jq -r '.state.result_state')"; exit 0;; esac
  sleep 30
done
