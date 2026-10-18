r"""Print the current read-only health of the retired v1 shadow lineage.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_legacy_v1_health.py
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_legacy_v1_health import (  # noqa: E402
    HEALTHY_STATUS,
    build_legacy_v1_health,
)


def probe_legacy_registration(repository_root: Path) -> dict[str, Any]:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    installer = repository_root / "scripts/install_ndx_dynamic_shadow_selection_task.ps1"
    if not powershell or not installer.is_file():
        return {
            "passed": False,
            "returncode": None,
            "reason": "PowerShell or the legacy selection-task verifier is unavailable",
        }
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-ProjectRoot",
            str(repository_root),
            "-VerifyRegistrationEvidence",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    detail = (completed.stderr.strip() or completed.stdout.strip())[-4000:]
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "reason": None if completed.returncode == 0 else detail,
    }


def main() -> int:
    payload = build_legacy_v1_health(
        ROOT, registration_probe=probe_legacy_registration,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == HEALTHY_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
