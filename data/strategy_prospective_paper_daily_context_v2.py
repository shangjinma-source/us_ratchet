"""Server daily-context callback for the V2 runner. Never initializes accounts."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import canonical
from backtest.current_strategy_prospective_paper_book_v2 import _context, replay
from data.strategy_paper_application_descriptor_v2 import require
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target,verify_empty_paper_target
from data.strategy_prospective_paper_daily_capture_v2 import capture_prospective_daily, capture_domain
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_daily_session_capture import reject_links

SOURCE='data/strategy_prospective_paper_daily_context_v2.py'


class CapturedPaperDailyContext:
    def __init__(self, *, root, authority, admission_store, selection_loader,
                 request_templates, release_path, clock=None, fetch_daily=None, fetch_official=None,
                 snapshot_reader=None):
        self.root=Path(root).absolute()
        self.authority=deepcopy(authority)
        self.admissions=admission_store
        self.selection_loader=selection_loader
        self.templates=deepcopy(request_templates)
        self.release_path=release_path
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.fetch_daily=fetch_daily;self.fetch_official=fetch_official
        self.snapshot_reader=snapshot_reader
        app=_context(self.authority,self.clock())
        require(SOURCE in app['code_sha256'],'PAPER_DAILY_CONTEXT_CODE_SCOPE')
        require(admission_store.authority==authority,'PAPER_DAILY_CONTEXT_AUTHORITY')
        self.directory=self.root/app['storage']['evidence']/'daily-context'
        self.risk=MonthlyPeakExitStore(self.directory.parent/'risk.sqlite3')
        reject_links(self.risk.path)
        require(self.risk.path.is_file(),'PAPER_DAILY_CONTEXT_RISK_RECOVERY_REQUIRED')

    def __call__(self, book, target_id):
        admitted=self.admissions.load()
        self.admissions.validate_risk_store(self.risk,admitted)
        current=replay(book,authority=self.authority,admitted_decisions=admitted['decisions'],
                       admitted_settlements=admitted['settlements'])
        selection=self.selection_loader(target_id)
        result=selection['selection_result'];arguments=selection['selection_arguments']
        require(arguments['authority']==self.authority,'PAPER_DAILY_CONTEXT_SELECTION_AUTHORITY')
        selected=verify_prospective_target(result,**arguments)
        require(selected['target_id']==target_id,'PAPER_DAILY_CONTEXT_TARGET_CHANGED')
        if not any(selected['target_quantities'].values()) and not any(current['shares'].values()) and not any(
                order['closed'] is None for order in current['orders'].values()):
            empty_arguments=dict(book=current,authority=self.authority,admitted_decisions=admitted['decisions'],
                admitted_settlements=admitted['settlements'],selection_result=result,selection_arguments=arguments)
            return dict(verify_empty_paper_target(**empty_arguments),empty_arguments=empty_arguments)
        binding=result['payload']['input_binding']
        namespace='paper-cap-exit:'+sha256(canonical(dict(account_id=binding['account_id'],
            registration=binding['registration_sha256'],descriptor=binding['paper_application_sha256']))).hexdigest()
        previous=self.risk.read(namespace)
        epoch=(previous['decision_date'] if previous and previous.get('target_month')==selected['target_month']
               else datetime.fromisoformat(binding['valuation_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat())
        needed=capture_domain(current,selected,binding,self.risk,epoch)
        require(needed <= set(self.templates),'PAPER_DAILY_CONTEXT_SOURCE_MISSING')
        day=self.clock().astimezone(ZoneInfo('America/New_York')).date().isoformat()
        key=sha256(canonical(dict(revision=current['revision'],target=target_id,session=day))).hexdigest()[:24]
        directory=self.directory/key
        reject_links(directory)
        require(not directory.exists(),'PAPER_DAILY_CONTEXT_PARTIAL_REQUIRES_RECOVERY')
        requests={}
        for sid in sorted(needed):
            request=deepcopy(self.templates[sid])
            raw=request['configuration_bytes']
            require(sha256(raw).hexdigest()==request['configuration_sha256'],'PAPER_DAILY_CONTEXT_TEMPLATE_CHANGED')
            config=json.loads(raw)
            config.update(monthly_decision_date=epoch,
                output_root=(directory/'captures'/sha256(sid.encode()).hexdigest()[:16]).relative_to(self.root).as_posix())
            request['configuration_bytes']=canonical(config)
            request['configuration_sha256']=sha256(request['configuration_bytes']).hexdigest()
            requests[sid]=request
        def read_binding():
            require(callable(self.snapshot_reader),'PAPER_FIRST_SERVER_SNAPSHOT_READER_REQUIRED')
            snapshot=self.snapshot_reader()
            return dict(snapshot,session=self.clock().astimezone(ZoneInfo('America/New_York')).date().isoformat())
        captured=capture_prospective_daily(root=self.root,book=current,authority=self.authority,
            admitted_decisions=admitted['decisions'],admitted_settlements=admitted['settlements'],
            selection_result=result,selection_arguments=arguments,release_path=self.release_path,
            capture_requests=requests,output_directory=directory/'archive',clock=self.clock,
            fetch_daily=self.fetch_daily,fetch_official=self.fetch_official,
            monthly_decision_date=epoch,risk_store=self.risk,read_binding=read_binding,
            parent_loader=self.admissions.latest_daily_parent)
        self.admissions.register_daily_source('daily-source:'+captured['receipt_sha256'],
            daily_arguments=captured['daily_arguments'],directory=captured['directory'],
            trusted_complete_sha256=captured['archive_complete_sha256'])
        return dict(directory=captured['directory'],trusted_complete_sha256=captured['archive_complete_sha256'],
                    daily_arguments=captured['daily_arguments'])
