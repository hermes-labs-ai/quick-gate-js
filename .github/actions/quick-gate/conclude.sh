#!/usr/bin/env bash
set -euo pipefail

gate_status="${1:-}"
repair_status="${2:-skipped}"

if [[ "$gate_status" == "pass" || ( "$gate_status" == "fail" && "$repair_status" == "pass" ) ]]; then
  exit 0
fi

echo "Quick Gate failed (gate: ${gate_status:-unknown}, repair: $repair_status)." >&2
exit 1
