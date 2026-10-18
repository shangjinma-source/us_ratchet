from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backtest.current_quantity_v2_continuation_simulation import apply_continuation
from backtest.current_quantity_v2_monthly_simulation import observe_monthly, digest
from backtest.current_quantity_v2_simulated_settlement import create_simulation, settle, MODEL
from backtest.current_quantity_v2_simulation_store import SimulationStore
from data.current_quantity_v2_current_cash_plan import canonical, BASIS
from data.current_quantity_v2_paper_chain import create_chain
from data.current_quantity_v2_paper_ledger import accept_proposal
from test_current_quantity_v2_current_cash_ledger import frozen_fixture
import test_current_quantity_v2_current_cash_plan as cash_fixture
from test_current_quantity_v2_monthly_simulation import setup as monthly_setup


def expire_all(simulation):
    ledger=simulation['chain']['ledger'];evidence={}
    active=ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']
    securities=active.get('securities',active['causal_inputs'].get('securities'))
    close=None
    for oid,order in ledger['orders'].items():
        at=datetime.fromisoformat(order['accepted_at']);close=datetime.fromisoformat(order['session_close'])
        start=at.replace(second=0,microsecond=0)+timedelta(minutes=1)
        identity=dict(security_id=order['security_id'],ticker=securities[order['security_id']]['ticker'],session=at.date().isoformat())
        price=str(Fraction(order['limit_price'])* (2 if order['side']=='BUY' else Fraction(1,2)))
        bars=[]
        while start<close:
            end=start+timedelta(minutes=1)
            bars.append(dict(identity,start=start.isoformat(),end=end.isoformat(),open=price,high=price,low=price,close=price));start=end
        evidence[oid]=dict(identity,fees='0',source_reference='synthetic-complete-day',minutes=bars)
    return settle(simulation=simulation,evidence=evidence,observed_through=close.isoformat(),evaluated_at=close.isoformat()) if evidence else simulation


def daily_arguments(folder,simulation,session):
    root=Path(folder);clock=[datetime.fromisoformat(session+'T10:00:30-05:00')];calls=[]
    if session[:7]=='2026-10':clock[0]=datetime.fromisoformat(session+'T10:00:30-04:00')
    offset=clock[0].strftime('%z');offset=offset[:3]+':'+offset[3:]
    schedule=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',sessions=[dict(date=session,
        open_at=session+'T09:30:00'+offset,close_at=session+'T16:00:00'+offset)])
    raw=canonical(schedule);(root/'daily-schedule.json').write_bytes(raw)
    store=SimulationStore(root/'daily.sqlite3');initial=store.create(simulation)
    def fetch(ticker):
        calls.append(ticker);clock[0]+=timedelta(seconds=1);now=clock[0];t=int(now.timestamp());price=10
        return canonical({'chart':{'error':None,'result':[{'meta':dict(symbol=ticker,currency='USD',instrumentType='EQUITY',
            exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=price,regularMarketTime=t-1,
            currentTradingPeriod={'regular':{'start':int(now.replace(hour=9,minute=30,second=0).timestamp()),'end':int(now.replace(hour=16,minute=0,second=0).timestamp())}}),
            'timestamp':[int(now.replace(second=0).timestamp())-60],
            'indicators':{'quote':[dict(open=[price],high=[11],low=[9],close=[price],volume=[10])]}}]}})
    def guard(pins):
        assert pins and all(isinstance(v,str) and len(v)==64 for v in pins.values())
    return dict(store=store,simulation_id=simulation['simulation_id'],expected_revision=initial['revision'],
        operation_id=simulation['simulation_id']+':daily-continuation:'+session,root=root,schedule_path='daily-schedule.json',schedule_sha256=sha256(raw).hexdigest(),
        session=session,triggered_at=session+'T10:00:00'+offset,storage_directory=root/'daily',
        source_admission_guard=guard,fetch=fetch,clock=lambda:clock[0]),calls,clock


def cash_review(snapshot):
    evidence='synthetic-units.json';units={}
    for sid,origin in snapshot['origins'].items():
        sec=snapshot['securities'][sid];current=snapshot['current_receipts'][sid]
        units[sid]=dict(security_id=sid,ticker=sec['ticker'],security_class=sec['security_class'],
            price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',initial_price_basis=BASIS,
            status='NO_UNPROCESSED_ACTIONS',initial_execution_target_id=snapshot['execution_target_id'],
            initial_reference_source_hashes=origin['source_hashes'],reference_source_hashes=current['source_hashes'],
            covered_from=origin['captured_at'],covered_through=current['captured_at'],reviewed_at=current['captured_at'],source_references=[evidence])
    files={evidence:canonical({'synthetic':True}),'daily-units.json':canonical(units)}
    return dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},unit_continuity_path='daily-units.json')


class MonthlyReview:
    def capture(self,snapshot):
        state=snapshot['state'];ledger=state['ledger'];active=ledger['active_monthly_acceptance']['proposal'];old=active['causal_inputs']
        units=deepcopy(old['unit_continuity']);held=deepcopy(old['held_unit_continuity'])
        for sid,row in units.items():
            current=snapshot['current_receipts'][sid]
            row.update(reference_source_hashes=current['source_hashes'],covered_through=current['captured_at'],reviewed_at=current['captured_at'])
        for sid,row in held.items():
            current=snapshot['current_receipts'][sid];prior=old['execution_references'][sid]
            row.update(prior_revision=ledger['revision'],prior_active_proposal_id=active['proposal_id'],
                prior_reference_source_hashes=prior['source_hashes'],prior_price_basis=prior['price_basis'],covered_from=prior['captured_at'],
                reference_source_hashes=current['source_hashes'],covered_through=current['captured_at'],reviewed_at=current['captured_at'])
        review=dict(account_id=ledger['account_id'],state_revision=ledger['revision'],pending_rights=[],
            reviewed_at=max(r['captured_at'] for r in snapshot['current_receipts'].values()),source_references=['source'])
        docs={k:'daily-review/'+k+'.json' for k in ('unit_continuity','held_unit_continuity','account_review')}
        files={docs[k]:canonical(v) for k,v in [('unit_continuity',units),('held_unit_continuity',held),('account_review',review)]}
        self.saved=dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},documents=docs)
        return deepcopy(self.saved)
    def read(self,snapshot):return deepcopy(self.saved)


class ContinuationSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cash_fixture.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):cash_fixture.CurrentCashTests.tearDownClass()
    def cash_simulation(self):
        proposal,args=frozen_fixture(cash_fixture.CurrentCashTests.args)
        chain=create_chain(accept_proposal(proposal,account_state=args['account_state'],now=args['now']))
        return create_simulation(chain=chain,simulation_id='cash-daily',model=MODEL)

    def test_cash_fixed_targets_next_day_and_completed_retry_zero_fetch(self):
        with TemporaryDirectory() as folder:
            original=expire_all(self.cash_simulation());args,calls,_=daily_arguments(folder,original,'2026-10-16')
            args.update(root=Path(cash_fixture.CurrentCashTests.temp.name),unit_review_reader=cash_review)
            # Calendar is an explicit external source in the same fixture root.
            (args['root']/'daily-schedule.json').write_bytes((Path(folder)/'daily-schedule.json').read_bytes())
            with patch('subprocess.run',side_effect=AssertionError('continuation must not search')):
                result=apply_continuation(**args)
                again=apply_continuation(**args)
            self.assertEqual(calls,['AAA','BBB']);self.assertTrue(again['replayed'])
            ledger=result['simulation']['chain']['ledger']
            self.assertEqual(ledger['target_quantities'],original['chain']['ledger']['target_quantities'])
            self.assertEqual(ledger['cash'],original['chain']['ledger']['cash'])
            self.assertEqual(len(result['simulation']['batches']),len(original['batches'])+1)
            self.assertGreater(result['simulation']['batches'][-1]['request']['accepted_at'],args['triggered_at'])
            with self.assertRaisesRegex(ValueError,'SESSION_OPERATION_REQUIRED'):
                apply_continuation(**dict(args,operation_id='retry-with-new-id'))
            with self.assertRaisesRegex(ValueError,'OPERATION_CONFLICT'):
                apply_continuation(**dict(args,expected_revision=result['revision']))
            self.assertEqual(calls,['AAA','BBB'])

    def test_real_cash_genesis_fill_identity_and_failed_capture_preserve_state(self):
        simulation=self.cash_simulation();ledger=simulation['chain']['ledger'];proposal=ledger['acceptance']['proposal'];evidence={}
        for oid,order in ledger['orders'].items():
            start=datetime.fromisoformat(order['accepted_at']).replace(second=0,microsecond=0)+timedelta(minutes=1)
            end=start+timedelta(minutes=1)
            identity=dict(security_id=order['security_id'],ticker=proposal['securities'][order['security_id']]['ticker'],session=start.date().isoformat())
            evidence[oid]=dict(identity,fees='0',source_reference='synthetic-cross',minutes=[dict(identity,
                start=start.isoformat(),end=end.isoformat(),open='1',high='1',low='1',close='1')])
        filled=settle(simulation=simulation,evidence=evidence,observed_through=end.isoformat(),evaluated_at=end.isoformat())
        self.assertTrue(all(o['closed']=='FILLED' for o in filled['chain']['ledger']['orders'].values()))
        self.assertEqual(filled['chain']['ledger']['shares'],ledger['target_quantities'])
        with TemporaryDirectory() as folder:
            expired=expire_all(simulation);args,calls,_=daily_arguments(folder,expired,'2026-10-16')
            args.update(root=Path(cash_fixture.CurrentCashTests.temp.name),unit_review_reader=cash_review)
            (args['root']/'daily-schedule.json').write_bytes((Path(folder)/'daily-schedule.json').read_bytes())
            def failed(ticker):calls.append(ticker);raise OSError('synthetic unavailable')
            args['fetch']=failed
            with self.assertRaises(OSError):apply_continuation(**args)
            self.assertEqual(args['store'].read(expired['simulation_id'])['simulation'],expired)
            self.assertEqual(calls,['AAA'])
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'):apply_continuation(**args)
            self.assertEqual(calls,['AAA'])

    def test_open_orders_and_absent_or_withdrawn_guard_before_fetch(self):
        for mode in ('open','missing','withdrawn'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                simulation=self.cash_simulation()
                if mode!='open':simulation=expire_all(simulation)
                args,calls,_=daily_arguments(folder,simulation,'2026-10-16')
                args['unit_review_reader']=cash_review
                if mode=='missing':args['source_admission_guard']=None
                if mode=='withdrawn':
                    def denied(pins):raise ValueError('RESEARCH_SOURCE_WITHDRAWN')
                    args['source_admission_guard']=denied
                with self.assertRaisesRegex(ValueError,{'open':'PRIOR_ORDERS_OPEN','missing':'GUARD_REQUIRED','withdrawn':'SOURCE_WITHDRAWN'}[mode]):apply_continuation(**args)
                self.assertEqual(calls,[]);self.assertEqual(args['store'].read(simulation['simulation_id'])['simulation'],simulation)

    def test_monthly_scope_fixed_target_no_sale_credit_and_no_order_no_accept(self):
        for no_orders in (False,True):
            with self.subTest(no_orders=no_orders),TemporaryDirectory() as folder:
                monthly,_,_=monthly_setup(folder,already_holds_candidate=no_orders)
                adopted=observe_monthly(**monthly);simulation=expire_all(adopted['simulation'])
                args,calls,_=daily_arguments(folder,simulation,'2026-12-02')
                args.update(monthly_blob_root=adopted['capture_receipt']['root']+'/blobs',monthly_review_reader=MonthlyReview())
                with patch('subprocess.run',side_effect=AssertionError('daily search')):result=apply_continuation(**args)
                ledger=result['simulation']['chain']['ledger'];before=simulation['chain']['ledger']
                self.assertEqual(ledger['target_quantities'],before['target_quantities'])
                self.assertEqual(ledger['cash'],before['cash'])
                self.assertLessEqual(Fraction(ledger['reserved_cash']),Fraction(before['cash']))
                if no_orders:
                    self.assertEqual(result['continuation_status'],'NO_ORDERS')
                    self.assertEqual(result['simulation'],simulation)
                else:self.assertEqual(result['continuation_status'],'SIMULATED_CONTINUATION_ACCEPTED')
                count=len(calls);self.assertTrue(apply_continuation(**args)['replayed']);self.assertEqual(len(calls),count)


if __name__=='__main__':unittest.main()
