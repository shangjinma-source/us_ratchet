"""Freeze the original-eight research control used by dynamic shadow paths."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_original8_control import build_original8_control  # noqa: E402


PROTECTED = (
    ROOT / "config/config.yaml",
    ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze the original-eight research control.")
    parser.add_argument(
        "--dynamic-manifest",
        default="data/cache/research/ndx_dynamic_walkforward_v1/manifest.json",
    )
    parser.add_argument(
        "--identity-manifest",
        default="data/cache/research/ndx_incumbent_pit_attribution_v1/manifest.json",
    )
    parser.add_argument(
        "--output",
        default="data/cache/research/ndx_original_8_control_v1/manifest.json",
    )
    args = parser.parse_args()

    before = {path: _sha(path) for path in PROTECTED}
    payload = build_original8_control(
        ROOT,
        dynamic_manifest_path=(ROOT / args.dynamic_manifest),
        identity_manifest_path=(ROOT / args.identity_manifest),
    )
    output = (ROOT / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        stable_keys = (
            "manifest_type",
            "status",
            "definition",
            "definition_sha256",
            "identity_projection_date",
            "weight_source",
            "source_state_sha256",
            "inputs",
            "live_mutation",
        )
        if any(existing.get(key) != payload.get(key) for key in stable_keys):
            raise RuntimeError("immutable original-eight control already exists with different content")
        payload = existing
    else:
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    after = {path: _sha(path) for path in PROTECTED}
    if after != before:
        raise RuntimeError("protected live files changed while freezing research control")
    print(
        "original-eight research control frozen | "
        f"securities={len(payload['definition']['securities'])} | "
        f"definition_sha256={payload['definition_sha256']} | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
