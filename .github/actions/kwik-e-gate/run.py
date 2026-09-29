"""Execute the Action's pinned core without installing a package or importing project code."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(SOURCE))

def _bootstrap_failure(reason: str, export: Path | None) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema": "hermes-gate/receipt-v1",
        "kind": "full" if os.environ.get("KWIK_GATE_MODE") == "full" else "fast",
        "status": "FAIL",
        "created_at": timestamp, "issued_at": timestamp,
        "repository": {"root": os.environ.get("KWIK_GATE_DIRECTORY", "."),
                       "head": None, "remote": None},
        "diff_sha256": "0" * 64, "elapsed_ms": 0, "command_versions": {},
        "checks": [], "findings": [], "reason_code": "ACTION_BOOTSTRAP_ERROR",
        "reason": reason,
    }
    exported = False
    try:
        # Bootstrap failure evidence is never reusable as a checked PASS.
        if export is None:
            raise OSError("receipt export path is unavailable")
        directory = Path(os.environ.get("KWIK_GATE_DIRECTORY", ".")).resolve(strict=True)
        if not directory.is_dir():
            raise OSError("working directory must be an existing directory")
        if export.resolve().is_relative_to(directory):
            raise OSError("receipt export must be outside the working directory")
        export.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        exported = True
    except (OSError, RuntimeError, ValueError) as exc:
        receipt["reason"] += f"; receipt export failed: {exc}"
    return {
        "schema": "hermes-gate/result-v1", "command": "run", "status": "FAIL",
        "reason": receipt["reason"], "receipt": receipt,
        "receipt_path": str(export) if exported else None,
        "export_path": str(export) if exported else None,
        "cached": False, "routing": None, "elapsed_ms": 0,
    }


def main() -> int:
    export = None
    try:
        runner_temp = os.environ.get("RUNNER_TEMP")
        if runner_temp is None:
            runner_temp = tempfile.gettempdir()
        export = Path(runner_temp) / f"kwik-e-gate-{uuid.uuid4().hex}.receipt.json"
        if sys.version_info < (3, 11):
            raise RuntimeError("kwik-e-gate requires Python 3.11 or newer")
        if not all((SOURCE / "hermes_gate" / name).is_file()
                   for name in ("__init__.py", "workflow.py")):
            raise RuntimeError("the Action's pinned core source is missing")
        from hermes_gate import workflow

        if Path(workflow.__file__).resolve() != (SOURCE / "hermes_gate/workflow.py").resolve():
            raise RuntimeError("the imported core is not the Action's pinned source")

        result = workflow.run(
            Path(os.environ.get("KWIK_GATE_DIRECTORY", ".")),
            mode=os.environ.get("KWIK_GATE_MODE", "auto"),
            base=os.environ.get("KWIK_GATE_BASE") or os.environ.get("HERMES_GATE_BASE") or None,
            output=export,
        )
    except Exception as exc:  # noqa: BLE001 -- bootstrap failures must issue a receipt
        result = _bootstrap_failure(str(exc), export)
    print(json.dumps(result, sort_keys=True))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"status={result['status']}\n")
            stream.write(f"receipt-path={result['export_path'] or ''}\n")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
