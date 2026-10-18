"""Read-only performance endpoint over verified paper history and saved sources."""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from data.current_portfolio_preview import ROOT
from data.current_research_paper_service import SERVICE as PAPER_SERVICE
from data.current_research_fill_ledger import (review_paper_ledger,initialize_paper_ledger,apply_paper_fill,apply_paper_order_event,activate_paper_plan)
from data.current_research_successor_inputs import SuccessorInputLoader,DEFAULT_REGISTRY,REGISTRY_SCHEMA,validate_successor_time_chain
from data.current_research_paper_performance_sources import build_saved_paper_performance

DEFAULT_CONFIG='data/research_paper/performance_source_config.json'
NY=ZoneInfo('America/New_York')


def _require(value,reason):
    if not value:raise ValueError(reason)


def _prefix_pairs(state):
    current=initialize_paper_ledger(state['plans'][0],state['account_id'])
    pairs={(current['revision'],current['plan']['plan_id'])}
    for event in state['events']:
        kind=event.get('event_type','FILL')
        if kind=='FILL':current=apply_paper_fill(current,event)
        elif kind=='ACTIVATE_PLAN':current=activate_paper_plan(current,event['new_plan'],{k:v for k,v in event.items() if k!='new_plan'})
        else:current=apply_paper_order_event(current,event)
        pairs.add((current['revision'],current['plan']['plan_id']))
    _require(current==state,'PREFIX_REPLAY_MISMATCH')
    return pairs


class CurrentPaperPerformanceService:
    def __init__(self,*,root=ROOT,account_reader=None,clock=None,config=None,config_path=DEFAULT_CONFIG,registry_path=DEFAULT_REGISTRY):
        self.root=Path(root).resolve();self.account_reader=account_reader or PAPER_SERVICE._read_account
        self.clock=clock or (lambda:datetime.now(timezone.utc));self.config=deepcopy(config)
        self.config_path=config_path;self.registry_path=registry_path

    def performance(self,account_id,expected_revision,through_date=None):
        _require(isinstance(account_id,str) and account_id and isinstance(expected_revision,str) and expected_revision,'ACCOUNT_AND_REVISION_REQUIRED')
        now=self.clock();_require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_SERVER_CLOCK_REQUIRED')
        if through_date is not None:
            _require(isinstance(through_date,str) and date.fromisoformat(through_date).isoformat()==through_date,'INVALID_THROUGH_DATE')
            _require(through_date<=now.astimezone(NY).date().isoformat(),'FUTURE_THROUGH_DATE_REJECTED')
        state=self.account_reader(account_id);review_paper_ledger(state)
        _require(state['account_id']==account_id and state['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
        first=state['plans'][0];start=first['causal_inputs']['decision_date']
        if through_date is not None:_require(through_date>=start,'THROUGH_BEFORE_GENESIS')
        snapshot=first['causal_inputs']['research_snapshot']
        envelope=dict(account_id=account_id,revision=state['revision'],expected_revision=expected_revision,
                      genesis_research_id=snapshot['research_id'],current_plan_id=state['plan']['plan_id'],
                      plan_research_ids=[p['causal_inputs']['research_snapshot']['research_id'] for p in state['plans']],
                      plan_methods=[p['causal_inputs']['research_snapshot'].get('method') for p in state['plans']],
                      research_only=True,execution_blocked=True,requested_through_date=through_date,
                      return_scope='PRICE_AND_RECORDED_FILL_FEES_ONLY',total_return_certified=False,
                      start_date=start,through_date=through_date,initial_cash=first['available_cash'],
                      genesis_baseline=dict(session=start,cash=first['available_cash'],
                          equity=first['available_cash'] if not any(first['causal_inputs']['shares'].values()) else None,
                          scope='INITIAL_LEDGER_CAPITAL_NOT_AN_OBSERVED_RETURN'))
        def finish(result):
            _require(self.account_reader(account_id)['revision']==expected_revision,'STALE_ACCOUNT_REVISION')
            result.update({k:v for k,v in envelope.items() if k not in ('through_date','initial_cash')})
            return result
        def incomplete(reason):
            return finish(dict(envelope,status='INCOMPLETE',total_return=None,annualized_return=None,
                annualization_unavailable_reason='INCOMPLETE_PERIOD',maximum_close_drawdown=None,
                drawdown_peak_date=None,drawdown_trough_date=None,recorded_fees=None,recorded_fill_count=None,
                daily_ledger=[],issues=[dict(reason=reason)],generated_fill_count=0,external_cash_flows='0',
                history_basis='RECONSTRUCTED_FROM_CURRENT_REVISION_NOT_AS_KNOWN_HISTORY',calendar_verified=False,source_verified=False))
        loader=SuccessorInputLoader(root=self.root,registry_path=self.registry_path)
        try:
            config=deepcopy(self.config)
            if config is None:
                path=loader._path(self.config_path)
                if not path.is_file():return incomplete('PERFORMANCE_SOURCE_CONFIG_NOT_REGISTERED')
                raw=path.read_bytes();config=json.loads(raw);envelope['configuration_sha256']=sha256(raw).hexdigest()
            _require(config.get('schema')=='PAPER_PERFORMANCE_SOURCE_CONFIG_V1','INVALID_PERFORMANCE_SOURCE_CONFIG')
            calendar_path=config['calendar_path'];pins=config['calendar_source_hashes']
            _require(isinstance(pins,dict) and calendar_path in pins,'CALENDAR_NOT_PINNED')
            for path,digest in pins.items():_require(sha256(loader._path(path).read_bytes()).hexdigest()==digest,'CALENDAR_SOURCE_CHANGED')
            calendar=json.loads(loader._path(calendar_path).read_bytes())
            _require(calendar.get('schema')=='SCHEDULED_REGULAR_SESSIONS_V1','CALENDAR_SCHEMA_INVALID')
            days=calendar['calendar'];sessions={s['date']:s for s in calendar['sessions']}
            _require(days and days==sorted(set(days)) and len(sessions)==len(calendar['sessions']) and set(days)==set(sessions),'CALENDAR_DOMAIN_INVALID')
            for day in days:_require(date.fromisoformat(day).isoformat()==day,'INVALID_CALENDAR_DATE')
            envelope.update(calendar_first_session=days[0],calendar_last_session=days[-1],calendar_source_hashes=pins)
            if through_date is None:
                _require(now.astimezone(NY).date().isoformat()<=days[-1],'CALENDAR_COVERAGE_ENDED_CURRENT_CUTOFF_UNKNOWN')
                completed=[]
                for day in days:
                    closing=datetime.fromisoformat(sessions[day]['close_at']);_require(closing.tzinfo is not None,'NAIVE_CALENDAR_CLOSE')
                    if closing<=now:completed.append(day)
                _require(completed,'NO_COMPLETED_REGISTERED_SESSION')
                through_date=completed[-1]
            _require(through_date in sessions and start in sessions and through_date>=start,'CALENDAR_RANGE_MISSING')
            closing=datetime.fromisoformat(sessions[through_date]['close_at'])
            _require(closing.tzinfo is not None,'NAIVE_CALENDAR_CLOSE')
            # Explicit unclosed date is an input error, never silently clipped to yesterday.
            if closing>now:raise _UncompletedDate('THROUGH_SESSION_NOT_COMPLETED')
            envelope['through_date']=through_date
            pairs=_prefix_pairs(state);input_ids=[];excluded=[];seen={}
            registry_file=loader._path(self.registry_path)
            if registry_file.is_file():
                raw=registry_file.read_bytes();registry=json.loads(raw)
                _require(registry.get('schema')==REGISTRY_SCHEMA and isinstance(registry.get('entries'),dict),'INVALID_SUCCESSOR_REGISTRY')
                envelope['registry_sha256']=sha256(raw).hexdigest()
                for input_id,entry in registry['entries'].items():
                    _require(isinstance(entry,dict),'INVALID_SUCCESSOR_REGISTRY_ENTRY')
                    if entry.get('account_id')!=account_id:continue
                    if (entry.get('revision'),entry.get('parent_plan_id')) not in pairs:
                        excluded.append(dict(input_id=input_id,reason='NOT_A_VERIFIED_HISTORY_PREFIX'));continue
                    bundle=loader(input_id)
                    day=bundle['decision_date']
                    if day<start or day>through_date:
                        excluded.append(dict(input_id=input_id,reason='OUTSIDE_REQUESTED_PERIOD'));continue
                    validate_successor_time_chain(bundle,root=self.root,now=now)
                    _require(day not in seen,'AMBIGUOUS_SESSION_OBSERVATIONS')
                    seen[day]=input_id;input_ids.append(input_id)
            else:envelope['registry_status']='NOT_PRESENT_NO_OBSERVATIONS_CREATED'
            envelope['excluded_registered_inputs']=excluded
            result=build_saved_paper_performance(state,root=self.root,input_ids=input_ids,calendar_path=calendar_path,
                        calendar_source_hashes=pins,through_date=through_date,now=now,registry_path=self.registry_path)
            return finish(result)
        except _UncompletedDate:
            raise ValueError('THROUGH_SESSION_NOT_COMPLETED')
        except (ValueError,KeyError,TypeError,OSError) as error:
            if str(error)=='STALE_ACCOUNT_REVISION':raise
            return incomplete(str(error))


class _UncompletedDate(ValueError):pass

SERVICE=CurrentPaperPerformanceService()
