"""Read-only extra admission for the independently versioned diagnostic launcher."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from scripts import preflight_registered_paper_task_cutover as original
from scripts import register_quantity_v2_paper_protocol as registrar


def preflight(*, descriptor_path, expected_descriptor_sha256, owned_lock_token=None, clock=None):
    path = Path(descriptor_path).absolute()
    for component in (path, *path.parents):
        registrar.require(not component.is_symlink()
                          and not getattr(component, "is_junction", lambda: False)(),
                          "DIAGNOSED_CUTOVER_DESCRIPTOR_LINK")
    raw = path.read_bytes()
    registrar.require(sha256(raw).hexdigest() == expected_descriptor_sha256, "DESCRIPTOR_CHANGED")
    descriptor = json.loads(raw)
    root = Path(descriptor["root"]).resolve()
    for name in ("scripts/preflight_diagnosed_paper_cutover.py",
                 "scripts/switch_diagnosed_paper_tasks.ps1",
                 "scripts/run_registered_paper_diagnosed.py",
                 "scripts/paper_failure_diagnostics.py"):
        source = registrar.safe_path(root, name)
        registrar.require(descriptor["source_hashes"].get(name) == sha256(source.read_bytes()).hexdigest(),
                          "DIAGNOSED_CUTOVER_PIN_REQUIRED")
    return original.preflight(descriptor_path=descriptor_path,
                              expected_descriptor_sha256=expected_descriptor_sha256,
                              owned_lock_token=owned_lock_token, clock=clock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor-path", required=True)
    parser.add_argument("--expected-descriptor-sha256", required=True)
    parser.add_argument("--owned-lock-token")
    try:
        result = preflight(**vars(parser.parse_args()))
    except Exception:
        print(json.dumps(dict(status="BLOCKED", reason="DIAGNOSED_CUTOVER_PREFLIGHT_REJECTED")))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
