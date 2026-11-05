"""Target-bound operation admission; never caches a monthly execution provider."""
from copy import copy
from functools import partial
from zoneinfo import ZoneInfo
from data.strategy_halt_gzip_capture_v1 import HaltGzipMarketCaptureV1 as HaltMarketCaptureV1
from data.strategy_recent_minute_retry_v1 import build_execution_limits
from data.strategy_halt_aware_pullback_cap_store_v2 import PullbackCapStore
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider as OriginalProvider
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_rss_gzip_capture_v1 import GzipActionCapture as StrategyAccountActionCaptureV6
from core.strategy_account_ledger import require
from data.strategy_daily_market_capture_v3 import DailyMarketCaptureV3
from data.strategy_account_monthly_release import validate_account_identity_coverage
from docs.candidates.split_three_clock_daily_composition_20261105 import SavedFrontierDailyComposition

from copy import deepcopy
from types import FunctionType
from hashlib import sha256
from core.strategy_account_split_v1 import replay
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture as SplitMarket
from data.strategy_account_market_capture_v2 import StrategyAccountMarketCaptureV2
from data import strategy_halt_aware_execution_limits_v1 as halt_limits
from data import strategy_recent_minute_retry_v1 as retry
from docs.candidates.split_three_clock_coordinates_20261105 import review_timing
from data.strategy_account_target_inputs import stamp
import json


def bind(function,**dependencies):
    value=FunctionType(function.__code__,dict(function.__globals__,**dependencies),function.__name__,function.__defaults__,function.__closure__)
    value.__kwdefaults__=function.__kwdefaults__
    return value


class SplitTimedMarket(StrategyAccountMarketCaptureV2):
    capture=bind(StrategyAccountMarketCaptureV2.capture,StrategyAccountMarketCapture=SplitMarket)


class SplitDailyMarketCapture(DailyMarketCaptureV3,SplitTimedMarket):
    """Preserve V3 transport evidence over the split-aware ledger replay."""


def build_timed_limits(*,timing_slot,**kwargs):
    timing=timing_slot['timing'];state=kwargs['state'];package=kwargs['market_capture'];review=kwargs['unit_review']
    action=next(r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED' and r['payload']['action_id']==timing['review']['action_id'])
    proof=review_timing(action=action,timing=timing,now=kwargs['now'])
    require(review['recorded_split_review']['timing_sha256']==proof['timing_sha256'],'LIMIT_TIMING_REVIEW_BINDING')
    sid=action['security_id'];mark=package['marks'].get(sid)
    if mark is not None:
        require(mark.get('unit_id')==action['new_unit_id'] and stamp(mark['observed_at'])>=stamp(proof['quote_unit_effective_at']),'LIMIT_QUOTE_UNIT_TIME')
        # Require the regular minute history to start in the derived new coordinate.
        paths=[p for p in mark['source_references'] if p.endswith('.receipt.json')]
        require(len(paths)==1,'MARK_RECEIPT_REQUIRED')
        receipt=json.loads(package['files'][paths[0]])
        series=json.loads(package['files'][receipt['raw_path']])['chart']['result'][0]
        from datetime import datetime,timezone
        opening=datetime.fromtimestamp(series['meta']['currentTradingPeriod']['regular']['start'],timezone.utc)
        require(opening>=stamp(proof['quote_bar_boundary_at']),'LIMIT_MIXED_UNIT_SESSION')
    original=bind(halt_limits.build_execution_limits,replay=replay)
    protected=bind(retry.build_execution_limits,original_limits=original)
    result=protected(**kwargs)
    if sid in result['limits']:result['limits'][sid]['unit_id']=action['new_unit_id']
    return result



class SplitProductionRollingAdmission:
    def __init__(self, *, monthly, monthly_view, reader, clock, validate_code,
                 policy_execution_enabled=False, policy_id=None):
        require(type(policy_execution_enabled) is bool, "DAILY_ENABLED_FLAG_REQUIRED")
        self.monthly, self.reader, self.clock = monthly, reader, clock
        self.monthly_view = monthly_view
        self.validate_code = validate_code
        self.enabled, self.policy_id = policy_execution_enabled, policy_id

    def preview(self, *, expected_revision, target_id, expected_proposal_id):
        with self.monthly.snapshot_operation():
            self.validate_code()
            proposal = self.monthly_view.require_proposal(target_id=target_id, expected_proposal_id=expected_proposal_id)
            target = self.monthly.current()
            require(target is not None and target["target_id"] == target_id, "STALE_TARGET")
            state = self.monthly.accounts.read()
            require(state is not None and state["revision"] == expected_revision, "STALE_REVISION")
            # _for_target authenticates the archived configuration bound to this
            # exact target, then verifies its actual executing runtime sources.
            runtime, configuration = self.monthly._for_target(target)
            bind(validate_account_identity_coverage,replay=replay)(self.monthly.root, configuration, state)
            original = runtime.execution_provider
            require(getattr(original, '__func__', None) is OriginalProvider.execution,
                    'DAILY_REAL_PROVIDER_REQUIRED')
            provider = object.__new__(StrategyAccountEvidenceProvider)
            provider.__dict__.update(original.__self__.__dict__)
            market = provider.market
            provider.market = SplitDailyMarketCapture(identity_resolver=market.identity,
                fetch=market.fetch,clock=market.clock,max_workers=market.workers,max_mark_age=market.max_mark_age)
            provider.market = HaltMarketCaptureV1(provider.market, clock=self.clock)
            require(isinstance(provider.limits, partial) and 'cap_store' in provider.limits.keywords,
                    'HALT_ORIGINAL_CAP_STORE_REQUIRED')
            legacy = provider.limits.keywords['cap_store']
            require(legacy.path.is_file(), 'HALT_LEGACY_CAP_STORE_MISSING')
            session = self.clock().astimezone(ZoneInfo('America/New_York')).date().isoformat()
            caps = PullbackCapStore(legacy.path.with_name('halt_pullback_caps_v2_' + session + '.sqlite3'),
                legacy_path=legacy.path, clock=legacy.clock,
                max_history_rows=legacy.max_history_rows, max_history_bytes=legacy.max_history_bytes)
            timing_slot={}
            provider.limits = partial(build_timed_limits, cap_store=caps, timing_slot=timing_slot)
            actions = provider.actions
            provider.actions = StrategyAccountActionCaptureV6(fetch=actions.fetch,
                rss_fetch=actions.rss_fetch, clock=actions.clock, max_workers=actions.workers)
            def reader(*args,**kwargs):
                result=self.reader(*args,**kwargs)
                if result.get('signal') is not None:
                    timing_slot['timing']=result['transition']['payload']['timing_bundle']
                return result
            service = SavedFrontierDailyComposition(monthly_service=self.monthly, monthly_view=self.monthly_view, evidence_reader=reader,
                execution_provider=provider.execution, fee_bps=runtime.selection.fees,
                clock=self.clock, policy_execution_enabled=self.enabled, policy_id=self.policy_id)
            result = service.preview(expected_revision=expected_revision, target_id=target_id,
                                     expected_proposal_id=expected_proposal_id)
            require(self.monthly_view.require_proposal(target_id=target_id, expected_proposal_id=expected_proposal_id) == proposal,
                    "FRONTIER_PROPOSAL_CHANGED")
            self.validate_code()
            return result
