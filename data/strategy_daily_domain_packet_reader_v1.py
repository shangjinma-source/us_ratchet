"""Read complete current-session security packets without collecting or approving.

Reaggregate the individual reviewed packets against the current account. The
saved aggregate's normalized inputs may contain only monthly target securities;
they must not be used as the source for rebinding held exit securities.
"""
from hashlib import sha256
from fractions import Fraction
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_dynamic_factory_v1 import FACTORY_SOURCES
from data.strategy_daily_security_domain_v1 import aggregate_security_packets
from data.strategy_daily_rolling_parent_v3 import pinned, bounded_read
from data.strategy_daily_session_capture import reject_links, stamp
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.strategy_account_identity import PinnedStrategyIdentity


class DomainSessionDailyPacketReaderV1:
    def __init__(self, *, root, configuration_path, configuration_sha256,
                 archive_root, release_path=None, trusted_release_sha256=None):
        reject_links(root)
        self.root = Path(root).resolve()
        self.reference = dict(path=configuration_path, sha256=configuration_sha256)
        self.archive_root = archive_root
        self.release_path = release_path
        self.release_sha = trusted_release_sha256

    def __call__(self, state, target, now):
        def wait(reason):
            return dict(status="WAIT_SIGNAL", reason=reason, signal=None)

        root = self.root
        config = json.loads(pinned(root, self.reference))
        require(config["schema"] == "SERVER_DYNAMIC_DAILY_SOURCE_V1"
                and FACTORY_SOURCES <= {r["path"] for r in config["source_pins"]},
                "DOMAIN_READER_CONFIGURATION")
        for reference in config["source_pins"]:
            pinned(root, reference)
        pinned(root, config["identity"])
        identity = PinnedStrategyIdentity(root, config["identity"]["path"],
                                          config["identity"]["sha256"])
        calendar_raw = pinned(root, config["calendar"])
        calendar = json.loads(calendar_raw)
        dates = [s["date"] for s in calendar["sessions"]]
        require(calendar["schema"] == "FIXED_EXCHANGE_SESSIONS_V1"
                and calendar["exchange"] == "NASDAQ"
                and dates == sorted(set(dates)), "DOMAIN_READER_CALENDAR")
        current = stamp(now)
        today = current.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if today not in dates:
            return wait("WAIT_CALENDAR_SESSION")
        index = dates.index(today)
        session = calendar["sessions"][index]
        if not index or current >= stamp(session["close"]):
            return wait("WAIT_NEXT_SESSION")
        if target is None or target["payload"]["target_month"] != today[:7]:
            return wait("WAIT_MONTHLY_TARGET")
        require(state["account_id"] == config["account_id"], "DOMAIN_READER_ACCOUNT")
        directory = root/config["runs_root"]/today
        reject_links(directory)
        require(directory.resolve().is_relative_to(root), "DOMAIN_READER_DIRECTORY")
        if not (directory/"terminal.json").is_file():
            return wait("INCOMPLETE_DAILY_PACKET" if directory.exists()
                        else "WAIT_NEW_SESSION_EVIDENCE")
        terminal = json.loads(bounded_read(directory/"terminal.json"))
        if terminal.get("status") != "DYNAMIC_DOMAIN_PACKET_SAVED":
            return wait("DAILY_PACKET_NEEDS_RECOVERY")
        require(terminal["configuration_sha256"] == self.reference["sha256"]
                and terminal["session"] == today, "DOMAIN_READER_TERMINAL")
        finished = stamp(terminal["finished_at"])
        require(finished <= current and finished < stamp(session["close"]),
                "DOMAIN_READER_PUBLICATION_TIME")

        def load(receipt_ref, manifest_ref, receipt_name, manifest_name):
            require(receipt_ref["path"] == (directory/receipt_name).relative_to(root).as_posix()
                    and manifest_ref["path"] == (directory/manifest_name).relative_to(root).as_posix(),
                    "DOMAIN_READER_PACKET_PATH")
            raw = pinned(root, receipt_ref)
            receipt = json.loads(raw)
            manifest = json.loads(pinned(root, manifest_ref))
            require(receipt["schema"] == "SERVER_REVIEWED_DAILY_EVIDENCE_V1"
                    and receipt.get("normalization_reviewed") is True
                    and receipt.get("unresolved_units") == []
                    and receipt.get("pending_rights") == []
                    and receipt["account_id"] == state["account_id"],
                    "DOMAIN_READER_REVIEW")
            require(receipt["execution_session"] == session
                    and stamp(receipt["source_received_at"]) <= stamp(receipt["available_at"]) <= finished
                    and stamp(receipt["source_received_at"]).astimezone(
                        ZoneInfo("America/New_York")).date().isoformat() == today
                    and stamp(receipt["market_asof"]) == stamp(calendar["sessions"][index-1]["close"]),
                    "DOMAIN_READER_MARKET_TIME")
            require(set(manifest) == set(receipt["source_sha256"])
                    and 0 < len(manifest) <= 2000, "DOMAIN_READER_SOURCE_DOMAIN")
            files, total = {}, 0
            for name, reference in manifest.items():
                require(reference["sha256"] == receipt["source_sha256"][name]
                        and reference["path"] == (directory/"files"/(
                            reference["sha256"]+".bin")).relative_to(root).as_posix(),
                        "DOMAIN_READER_SOURCE_PATH")
                body = pinned(root, reference, maximum=32*1024*1024-total)
                total += len(body)
                files[name] = body
            inputs = json.loads(files[receipt["normalized_inputs_path"]])
            require(inputs["signal_date"] == dates[index-1], "DOMAIN_READER_SIGNAL_DATE")
            return dict(receipt_bytes=raw, trusted_receipt_sha256=receipt_ref["sha256"],
                        files=files), receipt

        saved, aggregate = load(terminal["aggregate_reference"],
                                terminal["aggregate_manifest_reference"],
                                "aggregate.json", "aggregate-manifest.json")
        packets = {}
        require(set(terminal["routes"]) == set(terminal["packets"])
                and set(terminal["routes"].values()) <= {"FIRST", "ROLLING"},
                "DOMAIN_READER_ROUTES")
        parents = aggregate["aggregate_parents"]
        require(len(parents) == len(terminal["packets"])
                and {p["security_id"] for p in parents} == set(terminal["packets"]),
                "DOMAIN_READER_AGGREGATE_DOMAIN")
        for sid, reference in terminal["packets"].items():
            key = sha256(sid.encode()).hexdigest()
            packet, receipt = load(reference["receipt_reference"],
                                   reference["manifest_reference"],
                                   key+"/receipt.json", key+"/manifest.json")
            parent = next(p for p in parents if p["security_id"] == sid)
            require(parent["sha256"] == packet["trusted_receipt_sha256"]
                    and saved["files"].get(parent["path"]) == packet["receipt_bytes"]
                    and receipt.get("release_sha256") == aggregate.get("release_sha256"),
                    "DOMAIN_READER_PARENT")
            inputs = json.loads(packet["files"][receipt["normalized_inputs_path"]])
            require(set(inputs["histories"]) == {sid}, "DOMAIN_READER_SECURITY")
            history = inputs["histories"][sid]
            source = json.loads(packet["files"][history["source_reference"]])["chart"]["result"][0]
            resolved = identity(source["meta"]["symbol"])
            require(resolved["security_id"] == sid, "DOMAIN_READER_IDENTITY")
            for name, digest in resolved["source_hashes"].items():
                pinned(root, dict(path=name, sha256=digest))
            unit_review = json.loads(packet["files"][history["units"]["review_reference"]])
            if terminal["routes"][sid] == "FIRST":
                require(unit_review["status"] == "CONDITIONAL_FIRST_WINDOW_REVIEWED",
                        "DOMAIN_READER_FIRST_REVIEW")
                baseline = unit_review["baseline_review"]
                require(baseline["path"] in packet["files"]
                        and sha256(packet["files"][baseline["path"]]).hexdigest() == baseline["sha256"]
                        and bool(unit_review["overlap_exact_dates"]), "DOMAIN_READER_BASELINE")
            else:
                require(unit_review["status"] == "CONDITIONAL_MACHINE_CONTINUITY_CHECKED",
                        "DOMAIN_READER_ROLLING_REVIEW")
                prior_directory = directory.parent/dates[index-1]
                reject_links(prior_directory)
                previous = json.loads(bounded_read(prior_directory/"terminal.json"))
                require(previous["status"] == "DYNAMIC_DOMAIN_PACKET_SAVED"
                        and previous["session"] == dates[index-1]
                        and previous["configuration_sha256"] == self.reference["sha256"],
                        "DOMAIN_READER_PREVIOUS")
                prior_reference = previous["packets"][sid]["receipt_reference"]
                require(prior_reference["path"] == (prior_directory/key/"receipt.json").relative_to(root).as_posix(),
                        "DOMAIN_READER_PREVIOUS_PATH")
                prior_raw = pinned(root, prior_reference)
                prior_hash = sha256(prior_raw).hexdigest()
                require(unit_review["parent_review_sha256"] == prior_hash
                        and packet["files"].get("sid-parents/"+prior_hash+".json") == prior_raw,
                        "DOMAIN_READER_PREVIOUS_BINDING")
                prior = json.loads(prior_raw)
                require(prior["execution_session"] == calendar["sessions"][index-1]
                        and stamp(prior["available_at"]) <= stamp(previous["finished_at"])
                        < stamp(calendar["sessions"][index-1]["close"]),
                        "DOMAIN_READER_PREVIOUS_TIME")
                for name, digest in prior["source_sha256"].items():
                    require(name in packet["files"] and sha256(packet["files"][name]).hexdigest() == digest,
                            "DOMAIN_READER_PREVIOUS_CLOSURE")
                old_history = json.loads(packet["files"][prior["normalized_inputs_path"]])["histories"][sid]
                old = {r["date"]: Fraction(r["close"]) for r in old_history["closes"]}
                new = {r["date"]: Fraction(r["close"]) for r in history["closes"]}
                overlap = set(old) & set(new)
                require(len(overlap) == 19 and sorted(overlap) == unit_review["overlap_exact_dates"]
                        and all(old[d] == new[d] for d in overlap), "DOMAIN_READER_CONTINUITY")
            packets[sid] = packet
        needed = {sid for sid, q in target["payload"]["target_quantities"].items() if q > 0}
        needed.update(sid for sid, q in state["shares"].items() if q > 0)
        needed.update(o["security_id"] for o in state["orders"].values()
                      if o["status"] == "OPEN" and o["remaining_quantity"] > 0)
        if not needed <= set(packets):
            return wait("WAIT_NEW_SECURITY_EVIDENCE")
        domain = dict(account_id=state["account_id"], account_revision=state["revision"],
                      target_id=target["target_id"], securities={sid: {} for sid in needed})
        result = aggregate_security_packets(
            domain=domain, packets={sid: packets[sid] for sid in needed},
            state=state, target=target, now=current.isoformat())
        if result.get("receipt") is None:
            return wait(result["status"])
        return self._admit(state=state, target=target, current=current, domain=domain,
                           packets={sid: packets[sid] for sid in needed},
                           result=result, calendar_raw=calendar_raw)

    def _admit(self, *, state, target, current, domain, packets, result, calendar_raw):
        """Default strict admission never attaches a release to null evidence."""
        root = self.root
        if self.release_path is None or self.release_sha is None:
            return dict(status="WAIT_POLICY_RELEASE", signal=None,
                        reason="APPROVED_SERVER_RELEASE_NOT_CONFIGURED",
                        reviewed_securities=sorted(domain["securities"]))
        require(result["receipt"].get("release_sha256") == self.release_sha,
                "REVIEWED_PARENT_POLICY_BINDING_REQUIRED")
        receipt_raw = canonical(result["receipt"])
        verified = verify_daily_signal_bundle(
            state=state, target=target, now=current.isoformat(),
            release_bytes=pinned(root, dict(path=self.release_path, sha256=self.release_sha)),
            trusted_release_sha256=self.release_sha, receipt_bytes=receipt_raw,
            trusted_receipt_sha256=sha256(receipt_raw).hexdigest(),
            files=result["files"], calendar_bytes=calendar_raw)
        if verified["status"] == "DAILY_SIGNAL_READY":
            require(self.archive_root is not None, "DAILY_EVIDENCE_ARCHIVE_REQUIRED")
            archive = archive_rebound_evidence(root=self.archive_root,
                                              receipt_bytes=receipt_raw, files=result["files"])
            verified["signal"]["evidence_archive"] = archive
        return dict(verified, reason=verified["status"])
