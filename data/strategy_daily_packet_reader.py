"""Read only the current exchange session's complete server pipeline packet.

No mtime selection, fetch, policy promotion, account write or yesterday fallback.
"""
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from data.strategy_daily_session_capture import pinned, reject_links, require, stamp, validate_identity_binding
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader


class CurrentSessionDailyPacketReader:
    def __init__(self, *, root, configuration_path, configuration_sha256,
                 archive_root, release_path=None, trusted_release_sha256=None):
        reject_links(root)
        self.root = Path(root).resolve()
        self.configuration = dict(path=configuration_path, sha256=configuration_sha256)
        self.archive_root = archive_root
        self.release_path = release_path
        self.release_sha = trusted_release_sha256

    def __call__(self, state, target, now):
        def wait(status, reason):
            return dict(status=status, reason=reason, signal=None)
        root = self.root
        config = json.loads(pinned(root, self.configuration))
        require(config["schema"] == "SERVER_DAILY_SOURCE_PIPELINE_V1", "PIPELINE_SCHEMA")
        for reference in config["source_pins"]:
            pinned(root, reference)
        capture = json.loads(pinned(root, config["capture_configuration"]))
        identity = json.loads(pinned(root, capture["identity_review"]))
        validate_identity_binding(root, identity, capture["security"])
        calendar = json.loads(pinned(root, capture["calendar"]))
        current = stamp(now)
        today = current.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        sessions = [row for row in calendar["sessions"] if row["date"] == today]
        if len(sessions) != 1:
            return wait("WAIT_FRESH_SIGNAL", "WAIT_CALENDAR_SESSION")
        session = sessions[0]
        if current >= stamp(session["close"]):
            return wait("WAIT_FRESH_SIGNAL", "WAIT_NEXT_SESSION")
        directory = root/config["runs_root"]/today
        reject_links(directory)
        directory = directory.resolve()
        require(directory.is_relative_to(root), "PACKET_DIRECTORY_OUTSIDE_ROOT")
        terminal_path = directory/"terminal.json"
        reject_links(terminal_path)
        if not terminal_path.is_file():
            return wait("WAIT_FRESH_SIGNAL", "INCOMPLETE_DAILY_PACKET" if directory.exists()
                        else "WAIT_NEW_SESSION_EVIDENCE")
        terminal = json.loads(terminal_path.read_bytes())
        if terminal.get("status") != "DAILY_CONDITIONAL_PACKET_SAVED":
            return wait("WAIT_SIGNAL", "DAILY_PACKET_NEEDS_RECOVERY")
        require(terminal["configuration_sha256"] == self.configuration["sha256"]
                and terminal["session"] == today, "PACKET_CONFIGURATION_OR_SESSION_CHANGED")
        for key, name in (("receipt_reference","receipt.json"),("manifest_reference","source-paths.json")):
            require(terminal[key]["path"] == (directory/name).relative_to(root).as_posix(),
                    "PACKET_PATH_CHANGED")
        receipt = json.loads(pinned(root, terminal["receipt_reference"]))
        manifest = json.loads(pinned(root, terminal["manifest_reference"]))
        require(receipt["execution_session"] == session, "PACKET_EXECUTION_SESSION_CHANGED")
        require(stamp(receipt["source_received_at"]) <= stamp(receipt["available_at"])
                <= stamp(terminal["finished_at"]) <= current, "PACKET_AVAILABILITY_CHANGED")
        require(state["account_id"] == config["account_id"] == receipt["account_id"], "PACKET_ACCOUNT_CHANGED")
        require(receipt.get("normalization_reviewed") is True
                and receipt.get("unresolved_units") == [] and receipt.get("pending_rights") == [],
                "PACKET_REVIEW_REQUIRED")
        parent = json.loads(pinned(root, config["parent_reference"]))
        require(receipt.get("release_sha256") == parent.get("release_sha256"), "PACKET_POLICY_CHANGED")
        require(set(manifest) == set(receipt["source_sha256"]) and 0 < len(manifest) <= 2000,
                "PACKET_SOURCE_DOMAIN_CHANGED")
        files, source_paths, total = {}, {}, 0
        for name, reference in manifest.items():
            require(reference["sha256"] == receipt["source_sha256"][name], "PACKET_SOURCE_PIN_CHANGED")
            require(reference["path"] == (directory/"files"/(reference["sha256"]+".bin")).relative_to(root).as_posix(),
                    "PACKET_SOURCE_PATH_CHANGED")
            raw = pinned(root, reference)
            total += len(raw)
            require(total <= 32*1024*1024, "PACKET_SOURCE_BUDGET")
            files[name], source_paths[name] = raw, reference["path"]
        inputs = json.loads(files[receipt["normalized_inputs_path"]])
        require(set(inputs["histories"]) == {capture["security"]["security_id"]}, "PACKET_IDENTITY_CHANGED")
        if self.release_path is None or self.release_sha is None:
            return wait("WAIT_POLICY_RELEASE", "APPROVED_SERVER_RELEASE_NOT_CONFIGURED")
        require(receipt.get("release_sha256") == self.release_sha, "REVIEWED_PARENT_POLICY_BINDING_REQUIRED")
        return ArchivedRebindingDailyEvidenceReader(root=root,
            parent_receipt_path=terminal["receipt_reference"]["path"],
            trusted_parent_sha256=terminal["receipt_reference"]["sha256"],
            source_paths=source_paths, archive_root=self.archive_root,
            release_path=self.release_path, trusted_release_sha256=self.release_sha,
            calendar_path=capture["calendar"]["path"])(state, target, now)
