"""Read-only monthly handoff status; never runs capture, adopts, or removes locks."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def inspect(*, root, descriptor_path, descriptor_sha256):
    root = Path(root).resolve()
    result = dict(status="INPUT_REVIEW_REQUIRED", account_writes=False,
                  tasks_changed=False, process_liveness_verified=False)
    def path(name):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in str(name):
            raise ValueError("PATH_OUTSIDE_ROOT")
        resolved = (root / relative).resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise ValueError("PATH_OUTSIDE_ROOT")
        return resolved
    def read(reference):
        raw = path(reference["path"]).read_bytes()
        if sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("SOURCE_CHANGED:" + reference["path"])
        return json.loads(raw)
    try:
        descriptor = read(dict(path=descriptor_path, sha256=descriptor_sha256))
        if descriptor["schema"] != "ROA_MONTHLY_PREPARATION_LAUNCHER_V1" or Path(descriptor["root"]).resolve() != root:
            raise ValueError("DESCRIPTOR_SCOPE")
        request = read(descriptor["request"])
        read(request["active"])
        for name, digest in descriptor["source_pins"].items():
            if sha256(path(name).read_bytes()).hexdigest() != digest:
                raise ValueError("CODE_CHANGED:" + name)
        result.update(expected_month=request["package"]["expected_month"],
                      active_sha256=request["active"]["sha256"])
        logs = path(descriptor["log_directory"])
        # A lock alone is not proof of a live process. Never delete it here.
        locks = [p for p in (logs / "running.lock", root / "tmp/roa_monthly_pipeline_execution.lock") if p.exists()]
        if locks:
            return dict(result, status="LOCK_RECONCILIATION_REQUIRED",
                        evidence=[p.relative_to(root).as_posix() for p in locks])
        for filename, status in (("blocked.json", "FAILED_REVIEW_REQUIRED"),
                                 ("prepared.json", "PREPARED_PENDING_REVALIDATION")):
            saved = logs / filename
            if not saved.exists():
                continue
            record = json.loads(saved.read_bytes())
            if record.get("descriptor_sha256") != descriptor_sha256:
                raise ValueError("SAVED_DESCRIPTOR_MISMATCH")
            return dict(result, status=status, evidence=saved.relative_to(root).as_posix(),
                        stage=record.get("result", {}).get("stage"),
                        reason=record.get("error") or record.get("result", {}).get("error"),
                        publication_directory=record.get("result", {}).get("publication_directory"),
                        runtime_month_verified=False)
        return dict(result, status="CONFIGURATION_VALID_NO_COMPLETION", runtime_month_verified=False)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return dict(result, reason=str(error))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor-path", required=True)
    parser.add_argument("--descriptor-sha256", required=True)
    args = parser.parse_args()
    result = inspect(root=Path(__file__).resolve().parents[1], **vars(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
