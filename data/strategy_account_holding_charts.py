"""Recorded holding history; no target creation, market fetch, or account writes."""
from datetime import date, datetime
import copy
import json
import re
from core.strategy_account_ledger import require
from data.strategy_monthly_target_charts import StrategyMonthlyTargetCharts, BASIS
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.current_portfolio_preview import _group_bars


class StrategyAccountHoldingCharts:
    def __init__(self, *, root, account_store, account_id, training_manifest, training_sha256, display_sources=None):
        self.accounts, self.account_id = account_store, account_id
        self.manifest, self.manifest_hash = training_manifest, training_sha256
        require(display_sources is None or type(display_sources) is dict, 'CHART_DISPLAY_CONFIG_INVALID')
        self.display_sources = copy.deepcopy(display_sources or {})
        # Reuse only bounded, path-safe, hash-verified file reading. No target is fabricated.
        self.reader = StrategyMonthlyTargetCharts(root=root, target_service=None)

    def bars(self, *, account_revision, security_id, interval='day', bars=90):
        require(type(account_revision) is str and re.fullmatch('[0-9a-f]{64}', account_revision), 'CHART_ACCOUNT_REVISION_REQUIRED')
        require(type(security_id) is str and interval in ('day','week','month')
                and type(bars) is int and 1 <= bars <= 260, 'CHART_ARGUMENTS_INVALID')
        state = self.accounts.read()
        require(state is not None and state['account_id'] == self.account_id, 'ACCOUNT_SCOPE_MISMATCH')
        require(state['revision'] == account_revision, 'STALE_REVISION')
        quantity = state['shares'].get(security_id)
        require(type(quantity) is int and quantity > 0, 'CHART_NOT_HELD')
        names = {row['payload']['identity_evidence']['ticker'] for row in state['events']
                 if row['payload'].get('identity_evidence',{}).get('security_id') == security_id}
        require(len(names) == 1, 'CHART_RECORDED_IDENTITY_REQUIRED')
        ticker = next(iter(names))
        def pairs(items):
            result = {}
            for key,value in items:
                require(key not in result, 'CHART_DUPLICATE_JSON_FIELD'); result[key]=value
            return result
        manifest = json.loads(self.reader._read(self.manifest,self.manifest_hash),object_pairs_hook=pairs)
        cutoff = manifest['decision_date']
        require(date.fromisoformat(cutoff).isoformat() == cutoff, 'CHART_CUTOFF_INVALID')
        rows = [row for row in manifest['candidates'] if row.get('security_id') == security_id]
        require(len(rows) == 1 and rows[0]['ticker'] == ticker and rows[0]['status'] == 'READY_CONDITIONAL', 'CHART_IDENTITY_MISMATCH')
        source = rows[0]['training_source']; digest = manifest['source_hashes'].get(source)
        display = self.display_sources.get(security_id)
        if display is not None:
            require(type(display) is dict and set(display) == {'ticker','path','sha256','as_of','captured_at'},
                    'CHART_DISPLAY_CONFIG_INVALID')
            require(display['ticker'] == ticker, 'CHART_IDENTITY_MISMATCH')
            cutoff = display['as_of']
            require(type(cutoff) is str and date.fromisoformat(cutoff).isoformat() == cutoff, 'CHART_CUTOFF_INVALID')
            captured = datetime.fromisoformat(display['captured_at'])
            require(captured.tzinfo is not None and captured.date().isoformat() >= cutoff,
                    'CHART_CAPTURE_TIME_INVALID')
            source, digest = display['path'], display['sha256']
        raw = self.reader._read(source,digest)
        channel = parse_provider_ohlc(raw,ticker)
        if display is not None:
            metadata = json.loads(raw,object_pairs_hook=pairs)['chart']['result'][0]['meta']
            require(metadata.get('exchangeName') in ('NMS','NGM','NCM')
                    and metadata.get('fullExchangeName') in ('NasdaqGS','NasdaqGM','NasdaqCM'),
                    'CHART_DISPLAY_EXCHANGE_INVALID')
            require(channel['dates'][-1] == cutoff, 'CHART_DISPLAY_AS_OF_MISMATCH')
        daily, missing = [], []
        for session,values in zip(channel['dates'],channel['values']):
            if session > cutoff: continue
            if any(value is None for value in values[:4]): missing.append(session)
            else: daily.append(dict(zip(('date','open','high','low','close','volume'),[session]+values)))
        require(daily and daily[-1]['date'] == cutoff, 'CHART_CUTOFF_OHLC_MISSING')
        current = self.accounts.read()
        require(current is not None and current['account_id'] == self.account_id and current['revision'] == account_revision, 'STALE_REVISION')
        return dict(status='AVAILABLE',scope='RECORDED_HOLDING_HISTORY',account_revision=account_revision,
            security_id=security_id,ticker=ticker,quantity=quantity,interval=interval,bars=_group_bars(daily,interval)[-bars:],
            daily_as_of=cutoff,as_of=cutoff,currency='USD',price_basis=BASIS,adjustment_basis=BASIS,
            stale=None,missing_sessions=missing,no_missing_fill=True,calendar_completeness_verified=False,
            last_period_may_be_partial=interval!='day',limit_line_coordinate_confirmed=False,
            historical_only=True,execution_blocked=True,orders_created=False,source_sha256=digest,
            display_source_independent=display is not None,
            captured_at=display['captured_at'] if display else None,
            corporate_actions_completeness_verified=False)
