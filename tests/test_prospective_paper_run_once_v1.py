"""Real modules, synthetic transport only. No live registration or collection."""
from datetime import datetime
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest
from core.strategy_account_ledger import canonical
import test_strategy_prospective_paper_daily_capture_v1 as fixture
from test_strategy_paper_execution_preview_v1 import capture as market_fixture
from data.strategy_prospective_paper_daily_capture_v1 import capture_prospective_daily
from data.strategy_prospective_paper_selection_v1 import verify_prospective_target,select_prospective_target
from data.strategy_prospective_paper_cap_store_v1 import ProspectivePersistentCaps
from data.strategy_prospective_paper_source_capture_v1 import CODE_PATHS as CAPTURE
from data.strategy_prospective_paper_unit_review_v1 import CODE_PATHS as UNITS
from data.strategy_prospective_paper_settlement_v1 import CODE_PATHS as SETTLEMENT
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL
from backtest.current_strategy_prospective_paper_admission_store_v1 import ProspectivePaperAdmissionStore,SOURCE as ADMISSION
from backtest.current_strategy_prospective_paper_admission_reader_v1 import SOURCE as READER
from backtest.current_strategy_prospective_paper_coordinator_v1 import ProspectivePaperCoordinator,SOURCE as COORD
from backtest.current_strategy_prospective_paper_store_v1 import SOURCE as STORE
from backtest.current_strategy_prospective_paper_run_once_v1 import ProspectivePaperRunOnce,SOURCE


class RunOnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        with patch.object(fixture,'CODE_PATHS',fixture.CODE_PATHS|CAPTURE|UNITS|SETTLEMENT|{SOURCE,READER,ADMISSION,COORD,STORE}):
            args,_=fixture.arguments(self.root)
        captured=capture_prospective_daily(**args);self.daily=captured['daily_arguments']
        self.context=dict(directory=captured['directory'],trusted_complete_sha256=captured['archive_complete_sha256'],daily_arguments=self.daily)
        self.authority=self.daily['authority'];self.now='2026-11-03T15:00:00+00:00';self.calls=[]
        self.admissions=ProspectivePaperAdmissionStore(root=self.root,authority=self.authority,clock=self.clock)
        self.admissions.initialize()
        self.coordinator=ProspectivePaperCoordinator(root=self.root,authority=self.authority,
            admission_loader=self.admissions.load,target_verifier=lambda r:verify_prospective_target(r,**self.daily['selection_arguments']),clock=self.clock)
        self.coordinator.initialize();self.now='2026-11-03T15:00:03+00:00'
        self.coordinator.publish_target(self.daily['selection_result'],expected_book_revision=self.daily['book']['revision'],previous_target_id=None)
        caps=ProspectivePersistentCaps(root=self.root,book=self.daily['book'],authority=self.authority,
            admitted_decisions={},clock=lambda:self.now,initialize=True);caps.close()
        identity=b'fixture identity B';(self.root/'identity-source').write_bytes(identity)
        manifest=canonical(dict(candidates=[dict(ticker='B',security_id='B',status='READY_CONDITIONAL',identity_reviewed=True,
            identity_source_references=['identity-source'])],source_hashes={'identity-source':sha256(identity).hexdigest()}))
        (self.root/'identity-manifest').write_bytes(manifest)
        self.identity=PinnedStrategyIdentity(self.root,'identity-manifest',sha256(manifest).hexdigest())
        review=json.loads(self.daily['selection_arguments']['source_package']['files']['review.paper.json'])
        self.training={k:review[k] for k in ('training_manifest_sha256','historical_search_arguments_sha256','training_closed_at')}
        self.training['historical_price_basis']=review['securities']['B']['historical_price_basis']
        self.now='2026-11-03T15:00:10+00:00';self.batch='initial';self.incomplete=False

    def clock(self):return datetime.fromisoformat(self.now)

    def market(self,ticker):
        self.calls.append('market');return market_fixture(self.daily['book'],self.clock())[0]['files'][ticker+'.raw']

    def halt(self):
        self.calls.append('halt');raw=market_fixture(self.daily['book'],self.clock())[0]['files']['halt.raw']
        return dict(url=SOURCE_URL,status=200,body=raw)

    def actions(self,ticker,start,end):
        self.calls.append('actions');return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(
            meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))

    def rss(self):
        self.calls.append('rss');return dict(status=200,body=b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Tue, 03 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>')

    def minutes(self,url):
        self.calls.append('minutes');opening=datetime.fromisoformat('2026-11-03T14:30:00+00:00');closing=datetime.fromisoformat('2026-11-03T21:00:00+00:00')
        times=list(range(int(opening.timestamp()),int(closing.timestamp()),60));n=len(times)
        if self.incomplete:times=times[:30];n=len(times)
        return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol='B',currency='USD',instrumentType='EQUITY',
            dataGranularity='1m',exchangeTimezoneName='America/New_York'),timestamp=times,
            indicators=dict(quote=[dict(open=[990]*n,high=[1010]*n,low=[900]*n,close=[990]*n,volume=[10]*n)]))])))

    def runner(self,fault=None):
        return ProspectivePaperRunOnce(root=self.root,authority=self.authority,coordinator=self.coordinator,
            admission_store=self.admissions,daily_context=lambda book,target:self.context,identity_resolver=self.identity,
            securities={'B':{'ticker':'B'}},training_context=self.training,clock=self.clock,market_fetch=self.market,
            halt_fetch=self.halt,action_fetch=self.actions,rss_fetch=self.rss,minute_fetch=self.minutes,
            settlement_batch=lambda pending:self.batch,fault=fault)

    def test_actual_modules_accept_pending_close_settle_reopen(self):
        result=self.runner().run_once();self.assertEqual(result['status'],'PAPER_OPERATION_RECORDED')
        calls=list(self.calls);self.assertEqual(self.runner().run_once()['status'],'WAIT_PENDING_SESSION_CLOSE');self.assertEqual(calls,self.calls)
        self.now='2026-11-03T21:01:00+00:00';result=self.runner().run_once()
        self.assertEqual(result['status'],'PAPER_OPERATION_RECORDED');self.assertEqual(self.coordinator.read()['shares'],{'B':10})
        calls=list(self.calls);self.assertEqual(self.runner().run_once()['status'],'WAIT_OR_MISSED_DECISION_WINDOW');self.assertEqual(self.calls,calls)

    def test_admission_commit_before_accept_recovery_does_not_recapture(self):
        def fault(phase):raise RuntimeError('lost after admission')
        with self.assertRaisesRegex(RuntimeError,'lost after admission'):self.runner(fault).run_once()
        self.assertFalse(self.coordinator.read()['orders']);calls=list(self.calls)
        result=self.runner().run_once();self.assertEqual(result['status'],'PAPER_OPERATION_RECORDED');self.assertEqual(calls,self.calls)

    def test_expired_registered_decision_is_never_backfilled(self):
        with self.assertRaises(RuntimeError):self.runner(lambda _:(_ for _ in ()).throw(RuntimeError('crash'))).run_once()
        self.now='2026-11-03T15:01:00+00:00';calls=list(self.calls)
        self.assertEqual(self.runner().run_once()['status'],'REGISTERED_DECISION_EXPIRED_NOT_ACCEPTED')
        self.assertEqual(self.calls,calls);self.assertFalse(self.coordinator.read()['orders'])

    def test_unknown_same_evidence_no_write_then_complete_new_batch_fills(self):
        self.runner().run_once();self.now='2026-11-03T21:01:00+00:00';self.incomplete=True
        result=self.runner().run_once();self.assertEqual(result['status'],'PAPER_OPERATION_RECORDED')
        unknown=self.coordinator.read();self.assertEqual(unknown['shares'],{})
        calls=list(self.calls);self.assertEqual(self.runner().run_once()['status'],'SETTLEMENT_ALREADY_RECORDED')
        self.assertEqual(calls,self.calls);self.assertEqual(unknown,self.coordinator.read())
        self.batch='source-repair-1';self.now='2026-11-03T21:02:00+00:00'
        self.assertEqual(self.runner().run_once()['status'],'WAIT_NEW_SETTLEMENT_EVIDENCE')
        self.assertEqual(unknown,self.coordinator.read())
        self.batch='source-repair-2';self.incomplete=False;self.now='2026-11-03T21:03:00+00:00'
        self.assertEqual(self.runner().run_once()['status'],'PAPER_OPERATION_RECORDED')
        self.assertEqual(self.coordinator.read()['shares'],{'B':10})

    def test_target_changes_after_capture_coordinator_cas_rejects(self):
        def publish_new(phase):
            args=deepcopy(self.daily['selection_arguments']);args['now']='2026-11-03T15:00:11+00:00'
            result=select_prospective_target(clock=lambda:args['now'],**args)
            self.now=args['now'];contexts={self.daily['selection_result']['decision_id']:self.daily['selection_arguments'],result['decision_id']:args}
            self.coordinator.target_verifier=lambda r:verify_prospective_target(r,**contexts[r['decision_id']])
            self.coordinator.publish_target(result,expected_book_revision=self.daily['book']['revision'],
                previous_target_id=self.daily['selection_result']['decision_id'])
        with self.assertRaisesRegex(ValueError,'TARGET'):
            self.runner(publish_new).run_once()
        self.assertFalse(self.coordinator.read()['orders'])

    def test_bad_daily_anchor_and_missing_registry_never_initialize_or_fetch(self):
        self.context['trusted_complete_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ARCHIVE_COMPLETE_HASH'):self.runner().run_once()
        self.assertEqual(self.calls,[]);self.assertEqual(self.admissions.load(),dict(decisions={},settlements={}))
        old=self.admissions.path;old.rename(old.with_suffix('.preserved'))
        with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):self.runner().run_once()
        self.assertFalse(old.exists());self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
