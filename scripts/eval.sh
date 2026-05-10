#!/usr/bin/env bash
# Success-metric eval: feed each line of samples/error.log through
# `claude-cli --schema schemas.RootCause` and count how many produce
# valid Pydantic-typed JSON. Target: >= 9 / 10.
#
# Usage:
#   ANTHROPIC_API_KEY=sk-... ./scripts/eval.sh
set -uo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ANTHROPIC_API_KEY not set. Export it first." >&2
  exit 2
fi

SAMPLES="samples/error.log"
total=0
passed=0
failed_lines=()

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  total=$((total + 1))
  echo "--- line $total ---"
  echo "$line"
  if out=$(printf '%s\n' "$line" | claude-cli --schema schemas.RootCause 2>/tmp/claude-cli-err); then
    # Sanity: ensure stdout is parseable JSON (already validated by CLI, but belt-and-braces).
    if printf '%s' "$out" | python3 -c "import json,sys; json.loads(sys.stdin.read())" 2>/dev/null; then
      passed=$((passed + 1))
      echo "PASS"
    else
      echo "FAIL (stdout not JSON):"
      echo "$out"
      failed_lines+=("$total")
    fi
  else
    echo "FAIL:"
    cat /tmp/claude-cli-err
    failed_lines+=("$total")
  fi
done < "$SAMPLES"

echo
echo "============================="
echo "Result: ${passed}/${total} valid responses"
if (( ${#failed_lines[@]} > 0 )); then
  echo "Failed line numbers: ${failed_lines[*]}"
fi
echo "============================="

# Exit non-zero if we missed the bar.
if (( passed < 9 )); then
  exit 1
fi
