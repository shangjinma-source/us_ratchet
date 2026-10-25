"""Append-only evidence archive; never approves a policy or alters an account."""
from hashlib import sha256
import json
from pathlib import Path

from core.strategy_account_ledger import canonical, require


def archive_rebound_evidence(*, root, receipt_bytes, files):
    """Save exact rebound bytes, retaining partial failures for investigation.

    Source names are logical keys only. Physical filenames are content hashes.
    Reuse requires a complete receipt and exact verification of every byte.
    """
    require(type(receipt_bytes) is bytes, "REBOUND_ARCHIVE_RECEIPT_REQUIRED")
    receipt = json.loads(receipt_bytes)
    require(receipt.get("schema") == "SERVER_REVIEWED_DAILY_EVIDENCE_V1",
            "REBOUND_ARCHIVE_SCHEMA")
    pins = receipt.get("source_sha256")
    require(type(files) is dict and type(pins) is dict and set(files) == set(pins)
            and 0 < len(files) <= 2000
            and all(type(name) is str and type(raw) is bytes for name, raw in files.items())
            and len(receipt_bytes) + sum(map(len, files.values())) <= 32 * 1024 * 1024,
            "REBOUND_ARCHIVE_BUDGET")
    require(all(sha256(raw).hexdigest() == pins[name] for name, raw in files.items()),
            "REBOUND_ARCHIVE_SOURCE_CHANGED")
    root = Path(root).absolute()
    require(not root.is_symlink() and all(not p.is_symlink() for p in root.parents),
            "REBOUND_ARCHIVE_SYMLINK")
    root.mkdir(parents=True, exist_ok=True)
    digest = sha256(receipt_bytes).hexdigest()
    folder = root / digest
    manifest = canonical(dict(schema="DAILY_REBOUND_ARCHIVE_V1", receipt_sha256=digest,
                              source_sha256=pins))
    completion = canonical(dict(schema="DAILY_REBOUND_ARCHIVE_COMPLETE_V1",
                                manifest_sha256=sha256(manifest).hexdigest(),
                                receipt_sha256=digest))
    expected = {"receipt.json": receipt_bytes, "manifest.json": manifest}
    expected.update({"sources/" + pins[name] + ".bin": raw for name, raw in files.items()})

    def check(path, raw):
        require(not path.is_symlink() and all(not p.is_symlink() for p in path.parents),
                "REBOUND_ARCHIVE_SYMLINK")
        require(path.is_file() and path.read_bytes() == raw, "REBOUND_ARCHIVE_BYTES_CHANGED")

    if folder.exists() or folder.is_symlink():
        require(not folder.is_symlink() and (folder / "complete.json").is_file(),
                "REBOUND_ARCHIVE_RECOVERY_REQUIRED")
        check(folder / "complete.json", completion)
        for name, raw in expected.items():
            check(folder / name, raw)
    else:
        # A concurrent mkdir fails; do not replace or clear another writer.
        folder.mkdir()
        (folder / "sources").mkdir()
        for name, raw in expected.items():
            with (folder / name).open("xb") as stream:
                stream.write(raw)
        for name, raw in expected.items():
            check(folder / name, raw)
        with (folder / "complete.json").open("xb") as stream:
            stream.write(completion)
        check(folder / "complete.json", completion)
    return dict(receipt_path=str(folder / "receipt.json"), receipt_sha256=digest,
                manifest_path=str(folder / "manifest.json"),
                manifest_sha256=sha256(manifest).hexdigest(),
                complete_path=str(folder / "complete.json"),
                policy_approval_created=False, account_mutated=False)
