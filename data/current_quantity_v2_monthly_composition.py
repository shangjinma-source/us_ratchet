"""Server-owned monthly configuration. No IO, fetching or account creation at construction.

The optional descriptor pins an explicit current training package and independent
paper-rights reviews. It never turns the October snapshot into a later decision.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_difference_service import document
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_monthly_decision import QuantityV2MonthlyDecisionRegistry
from data.current_quantity_v2_monthly_research_service import QuantityV2MonthlyResearchService
from data.current_quantity_v2_monthly_bounded_review import MonthlyBoundedUnitReview
from data.current_quantity_v2_monthly_origins import MonthlyOriginReader
from data.current_quantity_v2_monthly_factory import attach_monthly_services
from data.current_quantity_v2_monthly_continuation_sources import QuantityV2MonthlyContinuationSources
from data.current_quantity_v2_monthly_continuation_factory import attach_monthly_continuation
from data.current_research_intraday_execution import fetch_intraday_chart
from scripts.current_research_official_alert_capture import fetch_official_feed


class MonthlyFileConfiguration:
    def __init__(self,*,root,path,sha256_value,clock):
        CurrentQuantityV2CurrentCashSources._path(path)
        require(type(sha256_value)is str and re.fullmatch('[a-f0-9]{64}',sha256_value),'INVALID_MONTHLY_CONFIGURATION')
        self.root=Path(root);self.path=path;self.sha256_value=sha256_value;self.clock=clock

    def _read(self,path,expected,limit=32*1024*1024):
        CurrentQuantityV2CurrentCashSources._path(path)
        require(type(expected)is str and re.fullmatch('[a-f0-9]{64}',expected),'INVALID_MONTHLY_CONFIGURATION')
        root=self.root.resolve();target=root/path
        require(not target.is_symlink() and target.resolve().is_relative_to(root),'MONTHLY_SOURCE_UNAVAILABLE')
        require(target.is_file() and target.stat().st_size<=limit,'MONTHLY_SOURCE_UNAVAILABLE')
        with target.open('rb') as source:raw=source.read(limit+1)
        require(len(raw)<=limit and sha256(raw).hexdigest()==expected,'REGISTRY_SOURCE_CHANGED')
        return raw

    def _config(self):
        value=document(self._read(self.path,self.sha256_value,1024*1024))
        require(type(value)is dict,'INVALID_MONTHLY_CONFIGURATION')
        key='training_entries' if value.get('schema')=='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V1' else 'market_entries'
        require(value.get('schema') in ('QUANTITY_V2_MONTHLY_SERVER_INPUTS_V1','QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2')
            and set(value)=={'schema',key,'account_reviews'} and type(value[key])is list and len(value[key])<=100
            and type(value['account_reviews'])is list and len(value['account_reviews'])<=1000,'INVALID_MONTHLY_CONFIGURATION')
        return value

    def _package(self,pins):
        require(type(pins)is dict and 0<len(pins)<=2000,'INVALID_MONTHLY_CONFIGURATION')
        files={};total=0
        for path,h in pins.items():
            raw=self._read(path,h);total+=len(raw)
            require(total<=128*1024*1024,'SOURCE_BYTES_LIMIT');files[path]=raw
        return dict(files=files,source_hashes=deepcopy(pins),documents={})

    def training_reader(self,state):
        ledger=state['ledger'];month=stamp(self.clock()).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
        rows=[r for r in self._config()['training_entries'] if r.get('account_id')==ledger['account_id']
            and r.get('state_revision')==ledger['revision'] and r.get('target_month')==month]
        require(len(rows)==1,'MONTHLY_SOURCE_UNAVAILABLE');row=rows[0]
        keys={'account_id','state_revision','target_month','source_hashes','manifest_path','calendar_path','account_review_path','identities_path','held_bar_sources'}
        require(set(row)==keys,'INVALID_MONTHLY_CONFIGURATION')
        package=self._package(row['source_hashes'])
        for key in ('manifest_path','calendar_path','account_review_path','identities_path'):
            require(row[key] in package['files'],'MONTHLY_SOURCE_UNAVAILABLE')
        calendar=document(package['files'][row['calendar_path']])
        require(calendar['target_month']==month,'MONTHLY_SOURCE_UNAVAILABLE')
        return dict(source_package=package,**{k:deepcopy(row[k]) for k in ('manifest_path','calendar_path','account_review_path','identities_path','held_bar_sources')})

    def market_reader(self,state):
        value=self._config();require(value['schema']=='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2','INVALID_MONTHLY_CONFIGURATION')
        month=stamp(self.clock()).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
        rows=[r for r in value['market_entries'] if isinstance(r,dict) and r.get('target_month')==month]
        require(len(rows)==1,'MONTHLY_SOURCE_UNAVAILABLE');row=rows[0]
        require(set(row)=={'target_month','decision_date','source_hashes','manifest_path','calendar_path','identities_path','held_bar_sources'},'INVALID_MONTHLY_CONFIGURATION')
        from datetime import date
        require(type(row['decision_date'])is str and date.fromisoformat(row['decision_date']).isoformat()==row['decision_date'],'INVALID_MONTHLY_CONFIGURATION')
        package=self._package(row['source_hashes'])
        for key in ('manifest_path','calendar_path','identities_path'):
            require(row[key] in package['files'],'MONTHLY_SOURCE_UNAVAILABLE')
        calendar=document(package['files'][row['calendar_path']]);manifest=document(package['files'][row['manifest_path']])
        require(calendar['target_month']==month and calendar['decision_date']==manifest['decision_date']==row['decision_date'],'MONTHLY_SOURCE_UNAVAILABLE')
        require(type(row['held_bar_sources'])is dict and all(type(s)is str and p in package['files'] for s,p in row['held_bar_sources'].items()),'MONTHLY_SOURCE_UNAVAILABLE')
        return dict(source_package=package,**{k:deepcopy(row[k]) for k in ('manifest_path','calendar_path','identities_path','held_bar_sources')})

    def account_review_reader(self,snapshot):
        ledger=snapshot['state']['ledger']
        rows=[r for r in self._config()['account_reviews'] if r.get('account_id')==ledger['account_id'] and r.get('state_revision')==ledger['revision']]
        require(len(rows)==1,'EXPLICIT_ACCOUNT_REVIEW_REQUIRED');row=rows[0]
        require(set(row)=={'account_id','state_revision','source_hashes','account_review_path'},'INVALID_MONTHLY_CONFIGURATION')
        package=self._package(row['source_hashes']);require(row['account_review_path'] in package['files'],'EXPLICIT_ACCOUNT_REVIEW_REQUIRED')
        # Actual review fields/rights/time are checked again by the pure ledger.
        return dict(package,account_review_path=row['account_review_path'])


class UnconfiguredMonthlyResearch:
    def __init__(self,reason='MONTHLY_CONFIGURATION_REQUIRED'):self.reason=reason
    def generate(self,**request):raise ValueError(self.reason)
    def read(self,**request):raise ValueError(self.reason)
    def current(self,*,account_id):
        return dict(status='UNAVAILABLE',account_id=account_id,registration_id=None,decision_id=None,research_id=None,
            selected_for_current_account=False,account_mutated=False,orders_created=False,research_only=True,
            execution_blocked=True,real_account=False,automatic_retry=False,reason=self.reason,
            configuration_status='NOT_CONFIGURED' if self.reason=='MONTHLY_CONFIGURATION_REQUIRED' else 'INVALID_CONFIGURATION',worker_liveness='UNKNOWN',portfolio=None)


def create_services(*,root,paper_service,storage_root,config_path=None,config_sha256=None,
                    fetch=fetch_intraday_chart,rss_fetch=fetch_official_feed,
                    execution_review_mode='STATIC_EXPLICIT',action_evidence_reader=None,baseline_reader=None,
                    pullback_policy=None,pullback_cap_store=None):
    """Explicit server startup composition; no saved inputs are opened here."""
    if config_path is None and config_sha256 is None:
        return dict(paper=paper_service,research=UnconfiguredMonthlyResearch(),configuration=None,configured=False)
    clock=paper_service.clock;storage=Path(storage_root)
    try:
        require(execution_review_mode in ('STATIC_EXPLICIT','DERIVED_PAPER_BOUNDED'),'INVALID_MONTHLY_CONFIGURATION')
        require(config_path is not None and config_sha256 is not None,'INVALID_MONTHLY_CONFIGURATION')
        configuration=MonthlyFileConfiguration(root=root,path=config_path,sha256_value=config_sha256,clock=clock)
    except ValueError as error:
        if str(error) not in {'INVALID_MONTHLY_CONFIGURATION','SAFE_SOURCE_PATH_REQUIRED'}:raise
        return dict(paper=paper_service,research=UnconfiguredMonthlyResearch('INVALID_MONTHLY_CONFIGURATION'),configuration=None,configured=False)
    registry=QuantityV2MonthlyDecisionRegistry(storage_root=storage/'registry',clock=clock)
    def derived_provider():
        from data.current_quantity_v2_paper_review_provider import DerivedPaperReviewProvider
        from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
        return DerivedPaperReviewProvider(storage_root=storage/'paper-reviews',
            evidence_reader=action_evidence_reader or PaperActionEvidenceSources(rss_fetch=rss_fetch,clock=clock),baseline_reader=baseline_reader,clock=clock)
    market_training=None
    def training_reader(state):
        nonlocal market_training
        if configuration._config()['schema']=='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V1':return configuration.training_reader(state)
        if market_training is None:
            from data.current_quantity_v2_monthly_training_reader import MonthlyMarketTrainingReader
            market_training=MonthlyMarketTrainingReader(market_reader=configuration.market_reader,paper_review_provider=derived_provider(),clock=clock)
        return market_training(state)
    research=QuantityV2MonthlyResearchService(store=paper_service.store,registry=registry,
        selection_root=storage/'selection',training_reader=training_reader,clock=clock)
    blobs=storage/'captures'/'blobs'
    def reviewer():
        account_reader=configuration.account_review_reader
        if execution_review_mode=='DERIVED_PAPER_BOUNDED':
            account_reader=derived_provider()
        return MonthlyBoundedUnitReview(account_review_reader=account_reader,
            origin_reader=MonthlyOriginReader(monthly_blob_root=blobs),fetch=rss_fetch,clock=clock)
    first=attach_monthly_services(paper_service,storage_root=storage/'captures',decision_reader=research.decision_reader,
        review_reader=reviewer(),fetch=fetch,clock=clock,
        pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store)
    source=QuantityV2MonthlyContinuationSources(storage_root=storage/'continuations',monthly_blob_root=blobs,
        review_reader=reviewer(),fetch=fetch,clock=clock,
        pullback_policy=pullback_policy,pullback_cap_store=pullback_cap_store)
    daily=attach_monthly_continuation(paper_service,monthly_sources=source)
    return dict(paper=daily['paper'],research=research,configuration=configuration,configured=True,
        monthly=first,continuation=daily)
