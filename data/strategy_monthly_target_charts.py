"""Read-only OHLC from the current real target's pinned training sources.

Historical quote coordinates are not an execution quote or a verified coordinate
for drawing today's limit line. No provider calls, selection, or ledger writes.
"""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re

from core.strategy_account_ledger import canonical, require
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.current_portfolio_preview import _group_bars

BASIS = 'CONDITIONAL_PROVIDER_QUOTE_CLOSE_NOT_AUTHENTICATED_NOMINAL_OR_TOTAL_RETURN'


class StrategyMonthlyTargetCharts:
    def __init__(self, *, root, target_service):
        self.root = Path(root).absolute()
        self.targets = target_service

    def _read(self, name, digest):
        require(type(name) is str and '\\' not in name and ':' not in name
                and not PurePosixPath(name).is_absolute()
                and all(part not in ('', '.', '..') for part in name.split('/')),
                'CHART_SOURCE_PATH_INVALID')
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'CHART_SOURCE_HASH_REQUIRED')
        path = self.root / name
        for parent in [path, *path.parents]:
            require(not parent.is_symlink() and not (parent.exists() and
                    getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400), 'CHART_SOURCE_LINK_REFUSED')
        require(path.is_file(), 'CHART_SOURCE_MISSING')
        with path.open('rb') as stream:
            raw = stream.read(32 * 1024 * 1024 + 1)
        require(len(raw) <= 32 * 1024 * 1024, 'CHART_SOURCE_TOO_LARGE')
        require(sha256(raw).hexdigest() == digest, 'CHART_SOURCE_CHANGED')
        return raw

    def bars(self, *, target_id, security_id, interval='day', bars=90):
        require(type(target_id) is str and re.fullmatch('[0-9a-f]{64}', target_id), 'CHART_TARGET_REQUIRED')
        require(type(security_id) is str and interval in ('day', 'week', 'month')
                and type(bars) is int and 1 <= bars <= 260, 'CHART_ARGUMENTS_INVALID')
        target = self.targets.current()
        require(target is not None and target['target_id'] == target_id, 'STALE_TARGET')
        payload = target['payload']
        require(sha256(canonical(payload)).hexdigest() == target_id, 'CHART_TARGET_CHANGED')
        decision = payload['decision']
        require(sha256(canonical(decision['payload'])).hexdigest() == decision['decision_id'], 'CHART_DECISION_CHANGED')
        binding = decision['payload']['input_binding']
        require(sha256(canonical(binding)).hexdigest() == decision['payload']['input_id'], 'CHART_INPUT_CHANGED')
        quantities = payload['target_quantities']
        require(quantities == decision['payload']['target_quantities'], 'CHART_TARGET_QUANTITIES_CHANGED')
        require(type(quantities.get(security_id)) is int and quantities[security_id] > 0, 'CHART_NOT_SELECTED')
        ticker = binding['search_arguments']['metadata'][security_id]['ticker']
        cutoff = binding['training_cutoff_date']
        require(date.fromisoformat(cutoff).isoformat() == cutoff, 'CHART_CUTOFF_INVALID')
        pins = binding['source_hashes']
        manifest_path = binding['documents']['training_manifest']
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, 'CHART_DUPLICATE_JSON_FIELD')
                result[key] = value
            return result
        manifest = json.loads(self._read(manifest_path, pins.get(manifest_path)), object_pairs_hook=pairs)
        require(manifest['decision_date'] == cutoff, 'CHART_CUTOFF_MISMATCH')
        rows = [row for row in manifest['candidates'] if row.get('security_id') == security_id]
        require(len(rows) == 1 and rows[0]['ticker'] == ticker and rows[0]['status'] == 'READY_CONDITIONAL',
                'CHART_IDENTITY_MISMATCH')
        source = rows[0]['training_source']
        require(source in pins and manifest['source_hashes'].get(source) == pins[source], 'CHART_SOURCE_BINDING_MISMATCH')
        channel = parse_provider_ohlc(self._read(source, pins[source]), ticker)
        daily, missing = [], []
        for session, values in zip(channel['dates'], channel['values']):
            if session > cutoff:
                continue
            if any(value is None for value in values[:4]):
                missing.append(session)
            else:
                daily.append(dict(zip(('date', 'open', 'high', 'low', 'close', 'volume'), [session] + values)))
        require(daily and daily[-1]['date'] == cutoff, 'CHART_CUTOFF_OHLC_MISSING')
        current = self.targets.current()
        require(current is not None and current['target_id'] == target_id, 'STALE_TARGET')
        return dict(status='AVAILABLE', target_id=target_id, security_id=security_id, ticker=ticker,
                    interval=interval, daily_as_of=cutoff, as_of=cutoff, currency='USD',
                    bars=_group_bars(daily, interval)[-bars:], price_basis=BASIS, adjustment_basis=BASIS,
                    stale=None, missing_sessions=missing, no_missing_fill=True,
                    calendar_completeness_verified=False, last_period_may_be_partial=interval != 'day',
                    limit_line_coordinate_confirmed=False, source_sha256=pins[source],
                    historical_only=True, execution_blocked=True, orders_created=False)
