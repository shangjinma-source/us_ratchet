"""Read-only ROA holding charts, independent of obsolete V27 proposals."""
from hashlib import sha256
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import require
from data.strategy_latest_display_charts_v1 import LatestDisplayChartsV1
from data.strategy_monthly_target_charts import StrategyMonthlyTargetCharts


def build_display(*, root, account, signal, specification, validate_sources, clock):
    reader = StrategyMonthlyTargetCharts(root=root, target_service=None)
    def context(security_id):
        validate_sources()
        state = account.store.read()
        require(state is not None, 'DISPLAY_NOT_HELD')
        projected = account.project(state)['account']
        matches = [f for f in projected['fills'] if f['security_id'] == security_id]
        require(bool(matches), 'DISPLAY_NO_RECORDED_TRADES')
        tickers = {f['ticker'] for f in matches}
        require(len(tickers) == 1, 'DISPLAY_IDENTITY_MISMATCH')
        ticker = matches[0]['ticker']
        roster = {r['security_id']:r for r in signal.frozen_roster()}
        identity = roster.get(security_id) or account.resolver(ticker)
        require(identity['security_id'] == security_id and identity['ticker'] == ticker, 'DISPLAY_IDENTITY_MISMATCH')
        manifest = json.loads(reader._read(specification['path'], specification['sha256']))
        rows = [r for r in manifest['candidates'] if r['security_id'] == security_id]
        require(len(rows) == 1 and rows[0]['ticker'] == ticker and rows[0]['status'] == 'READY_CONDITIONAL', 'DISPLAY_BASELINE_REQUIRED')
        source = rows[0]['training_source']
        baseline = reader._read(source, manifest['source_hashes'][source])
        return dict(account_revision=state['revision'], target_id=None, security_id=security_id,
                    ticker=ticker, identity=identity, baseline=baseline,
                    baseline_sha256=sha256(baseline).hexdigest(),
                    reviewed_split_through=manifest['decision_date'],
                    first_fill_session=min(datetime.fromisoformat(f['executed_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat() for f in account.project(state)['account']['fills'] if f['security_id']==security_id))
    return LatestDisplayChartsV1(context_reader=context, validate_sources=validate_sources,
        output_root=root/'data/strategy_display/roa_latest', clock=clock)
