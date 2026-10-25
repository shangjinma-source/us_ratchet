"""Latest display context bound to persisted frontier proposals."""
from copy import deepcopy
from hashlib import sha256
import json
from core.strategy_account_ledger import require
from data.strategy_latest_display_charts_v1 import LatestDisplayChartsV1


def frontier_display_context(view, security_id, expected_proposal_id):
    monthly = view.monthly
    """A server-owned resolver; the client never supplies ticker or source paths."""
    with monthly.snapshot_operation() as snapshot:
        state = deepcopy(monthly.accounts.read())
        target = deepcopy(view.current())
        require(state is not None and target is not None, "DISPLAY_SAVED_TARGET_REQUIRED")
        require(target["proposal_id"] == expected_proposal_id, "STALE_FRONTIER_PROPOSAL")
        quantities = target["risk_monthly_targets"]
        require(state["shares"].get(security_id, 0) > 0 or quantities.get(security_id, 0) > 0,
                "DISPLAY_SECURITY_NOT_HELD_OR_SELECTED")
        runtime, configuration = monthly._for_target(target)
        provider = runtime.execution_provider.__self__
        raw = provider._read(provider.manifest_path, provider.manifest_hash)
        manifest = json.loads(raw)
        rows = [row for row in manifest["candidates"]
                if row.get("security_id") == security_id and row.get("status") == "READY_CONDITIONAL"]
        require(len(rows) == 1, "DISPLAY_BASELINE_REQUIRED")
        row = rows[0]
        identity = monthly.resolve_identity(row["ticker"])
        require(identity["security_id"] == security_id, "DISPLAY_IDENTITY_MISMATCH")
        path = row["training_source"]
        baseline = provider._read(path, manifest["source_hashes"][path])
        return dict(proposal_id=expected_proposal_id, account_revision=state["revision"], target_id=target["target_id"],
                    security_id=security_id, ticker=row["ticker"], identity=identity,
                    snapshot=dict(snapshot), baseline=baseline,
                    baseline_sha256=sha256(baseline).hexdigest(),
                    manifest_sha256=provider.manifest_hash)


class FrontierLatestDisplayChartsV1:
    def __init__(self, *, view, **display_options):
        self.view = view
        self.display_options = display_options

    def bars(self, *, security_id, expected_proposal_id, interval="day", bars=90):
        # Each request owns its resolver so concurrent proposals cannot overwrite it.
        service = LatestDisplayChartsV1(
            context_reader=lambda sid: frontier_display_context(
                self.view, sid, expected_proposal_id), **self.display_options)
        result = service.bars(security_id=security_id, interval=interval, bars=bars)
        result["proposal_id"] = expected_proposal_id
        return result
