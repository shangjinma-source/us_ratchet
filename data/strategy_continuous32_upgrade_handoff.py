"""Read-only archive overlay with validated successor handoff.

The supplied base_provider must authenticate its active release. This wrapper
does not publish a release or authorize old-month execution.
"""
from copy import deepcopy
from pathlib import Path

from core.strategy_account_ledger import require
from data.strategy_daily_session_capture import pinned
from data.strategy_profiled_runtime_archive import _document, configuration_for_target


def upgrade_handoff_snapshot_provider(*, root, package_path, package_sha256,
                                      base_provider, target_provider, validate_code):
    root = Path(root)

    def read(reference):
        return _document(pinned(root, reference))

    def document(snapshot, kind):
        return read(dict(path=snapshot[kind + "_path"],
                         sha256=snapshot[kind + "_sha256"]))

    def registry_history(value):
        profiles = value.get("profiles", [])
        if value.get("schema") == "PROFILED_MONTHLY_RELEASES_V1":
            value = read(value["original_registry"])
        require(type(value.get("entries")) is list, "UPGRADE_REGISTRY_INVALID")
        return value["entries"], profiles

    def snapshot():
        validate_code()
        package = read(dict(path=package_path, sha256=package_sha256))
        require(package["schema"] == "CONTINUOUS32_RESEARCH_UPGRADE_V1"
                and package["purpose"] ==
                "EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION",
                "UPGRADE_PURPOSE_REQUIRED")
        base = deepcopy(base_provider())
        original = package["base_snapshot"]
        overlay_archive = read(package["upgrade_archive"])
        original_archive = document(original, "archive")
        require(overlay_archive["schema"] == "PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1"
                and all(row in overlay_archive["entries"] for row in original_archive["entries"]),
                "UPGRADE_ARCHIVE_HISTORY_CHANGED")
        upgraded = dict(configuration_path=package["upgraded_configuration"]["path"],
                        configuration_sha256=package["upgraded_configuration"]["sha256"])
        require(upgraded in overlay_archive["entries"], "UPGRADE_RUNTIME_NOT_ARCHIVED")
        read(package["upgraded_configuration"])
        if base == original:
            result = dict(base, archive_path=package["upgrade_archive"]["path"],
                          archive_sha256=package["upgrade_archive"]["sha256"])
        else:
            require(type(base.get("revision")) is int
                    and base["revision"] > original["revision"], "UPGRADE_SUCCESSOR_REVISION_REQUIRED")
            successor = document(base, "archive")
            require(successor["schema"] == "PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1"
                    and all(row in successor["entries"] for row in overlay_archive["entries"]),
                    "UPGRADE_SUCCESSOR_ARCHIVE_HISTORY_CHANGED")
            old_entries, old_profiles = registry_history(document(original, "registry"))
            new_entries, new_profiles = registry_history(document(base, "registry"))
            require(all(row in new_entries for row in old_entries)
                    and all(row in new_profiles for row in old_profiles),
                    "UPGRADE_SUCCESSOR_REGISTRY_HISTORY_CHANGED")
            result = base
        target = deepcopy(target_provider())
        if target is not None:
            configuration_for_target(root=root, archive_path=result["archive_path"],
                                     archive_sha256=result["archive_sha256"], target=target)
        validate_code()
        require(base_provider() == base and target_provider() == target,
                "UPGRADE_HANDOFF_SNAPSHOT_CHANGED")
        return result

    return snapshot
