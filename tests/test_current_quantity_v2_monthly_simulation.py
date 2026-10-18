from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest
from unittest.mock import patch

from backtest.current_quantity_v2_monthly_simulation import observe_monthly
from data.current_quantity_v2_current_cash_plan import canonical
from scripts.publish_monthly_market_configuration import publish
from test_publish_monthly_market_configuration import inputs
from test_current_quantity_v2_simulated_settlement import fixture, run
from test_current_quantity_v2_monthly_retarget import fixture as retarget_fixture
import test_current_quantity_v2_difference_plan as difference_fixture
from data.current_quantity_v2_difference_plan import build_account_difference_plan
from data.current_quantity_v2_paper_ledger import accept_proposal
from data.current_quantity_v2_paper_chain import create_chain
from backtest.current_quantity_v2_simulated_settlement import create_simulation, MODEL


def setup(folder, already_holds_candidate=False):
    root = Path(folder)
    simulation, evidence, original = fixture()
    if already_holds_candidate:
        def rename(value):
            if isinstance(value,dict): return {('B' if k=='A' else k):rename(v) for k,v in value.items()}
            if isinstance(value,list): return [rename(v) for v in value]
            return {'A':'B','AAA':'BBB','ia':'IB'}.get(value,value) if isinstance(value,str) else value
        original=rename(original); evidence=rename(evidence)
    original['source_hashes']['source'] = sha256(b'synthetic review source').hexdigest()
    if already_holds_candidate:
        original['capital_decision']['binding']['source_hashes']=deepcopy(original['source_hashes'])
        for key in ('execution_references','unit_continuity'):
            for row in original[key].values():
                row['source_hashes' if key=='execution_references' else 'reference_source_hashes']=deepcopy(original['source_hashes'])
    difference_fixture.DifferenceTests.rebind(None, original)
    proposal = build_account_difference_plan(**original)
    assert proposal['status']=='READY', proposal
    ledger = accept_proposal(proposal, account_state=original['account_state'], now=original['now'])
    simulation = create_simulation(chain=create_chain(ledger), simulation_id='monthly-test', model=MODEL)
    by_sid = {v['security_id']:v for v in evidence.values()}
    evidence = {oid:by_sid[order['security_id']] for oid,order in ledger['orders'].items()}
    simulation = run(simulation, evidence)
    state = simulation['chain']
    request = inputs(folder)
    identities = json.loads((root/'new-identities.json').read_bytes())
    if not already_holds_candidate:
        identities['securities']['A'] = deepcopy(original['securities']['A'])
    raw = canonical(identities); (root/'new-identities.json').write_bytes(raw)
    request['supplemental_hashes']['new-identities.json'] = sha256(raw).hexdigest()
    published = publish(**request)
    clock = [datetime.fromisoformat('2026-12-01T10:00:30-05:00')]
    calls = []
    def account_review():
        return dict(account_id=state['ledger']['account_id'], state_revision=state['ledger']['revision'],
            pending_rights=[], reviewed_at=clock[0].isoformat(), source_references=['synthetic-evidence.json'])
    class AccountReview:
        def capture(self, snapshot):
            assert snapshot['state'] == state
            raw = canonical(account_review())
            return dict(files={'account.json':raw}, source_hashes={'account.json':sha256(raw).hexdigest()},
                        account_review_path='account.json')
    def fetch(ticker):
        calls.append(ticker); clock[0] += timedelta(seconds=1)
        now = clock[0]; timestamp = int(now.timestamp())
        minute = int(now.replace(second=0).timestamp())-60
        price=353 if already_holds_candidate else 10
        return canonical({'chart':{'error':None,'result':[{'meta':dict(symbol=ticker,currency='USD',
            instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',
            regularMarketPrice=price,regularMarketTime=timestamp-1,currentTradingPeriod={'regular':{
                'start':int(now.replace(hour=9,minute=30,second=0).timestamp()),
                'end':int(now.replace(hour=16,minute=0,second=0).timestamp())}}),
            'timestamp':[minute],'indicators':{'quote':[dict(open=[price],high=[price+1],low=[price],close=[price],volume=[10])]}}]}})
    # Reuse the real retarget fixture's strict review schema; bind each field to
    # the actual registered decision and captured bytes, not mocked primitives.
    seed=deepcopy(original)
    if already_holds_candidate:
        for key in ('securities','execution_references','unit_continuity'):
            seed[key]['A']=deepcopy(seed[key]['B'])
    _, template, _ = retarget_fixture((state, seed), day='2026-11-02', at=clock[0].isoformat())
    saved_review = [None]
    class Review:
        def capture(self, snapshot):
            units = deepcopy(template['unit_continuity']); held = deepcopy(template['held_unit_continuity'])
            if already_holds_candidate:
                units={'B':units['B']}
                held={'B':dict(held['A'],security_id='B')}
            decision = snapshot['capital_decision']; basis = 'CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'
            for sid, row in units.items():
                row.update(capital_decision_id=decision['decision_id'], price_basis=basis,
                    valuation_source_references=['new-held.json' if sid=='A' else next(
                        p for p in snapshot['base_files'] if p.endswith('BBB.response.bin'))],
                    reference_source_hashes=snapshot['current_receipts'][sid]['source_hashes'],
                    covered_through=snapshot['current_receipts'][sid]['captured_at'],
                    reviewed_at=snapshot['current_receipts'][sid]['captured_at'])
            for sid, row in held.items():
                row.update(reference_source_hashes=snapshot['current_receipts'][sid]['source_hashes'],
                    covered_through=snapshot['current_receipts'][sid]['captured_at'],
                    reviewed_at=snapshot['current_receipts'][sid]['captured_at'])
            files={}; docs={}
            for key,value in [('unit_continuity',units),('held_unit_continuity',held),('account_review',account_review())]:
                docs[key]='review-'+key+'.json'; files[docs[key]]=canonical(value)
            # Existing template cites "source"; retain a declared synthetic proof.
            files['source']=b'synthetic review source'
            result=dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},documents=docs)
            saved_review[0]=result; return deepcopy(result)
        def read(self, snapshot): return deepcopy(saved_review[0])
    args=dict(simulation=simulation,root=root,configuration_path=published['config_path'],
        configuration_sha256=published['config_sha256'],schedule_path='schedule.json',
        session='2026-12-01',triggered_at='2026-12-01T10:00:00-05:00',storage_directory=root/'isolated',
        paper_review_provider=AccountReview(),review_reader=Review(),fetch=fetch,clock=lambda:clock[0])
    return args, calls, clock


class MonthlySimulationTests(unittest.TestCase):
    def test_real_publication_worker_capture_and_simulated_accept_retry(self):
        with TemporaryDirectory() as folder:
            args,calls,clock=setup(folder); before=deepcopy(args['simulation'])
            with patch('data.current_quantity_v2_monthly_decision.subprocess.run', wraps=subprocess.run) as worker:
                result=observe_monthly(**args)
                self.assertEqual(worker.call_count,1)
            self.assertEqual(result['status'],'SIMULATED_MONTHLY_ACCEPTED')
            self.assertGreater(result['accepted_at'],result['triggered_at'])
            self.assertEqual(calls,['AAA','BBB'])
            self.assertEqual(args['simulation'],before)
            for key in ('cash','shares','recorded_fees','events'):
                self.assertEqual(result['simulation']['chain']['ledger'][key], before['chain']['ledger'][key])
            self.assertEqual(set(result['simulation']['chain']['ledger']['target_quantities']),{'B'})
            with patch('subprocess.run',side_effect=AssertionError('retry search')):
                self.assertEqual(observe_monthly(**args),result)
                args['simulation']=result['simulation']
                self.assertEqual(observe_monthly(**args),result)
            self.assertEqual(calls,['AAA','BBB'])

    def test_before_trigger_missing_source_and_failed_attempt_do_not_retry(self):
        with TemporaryDirectory() as folder:
            args,calls,clock=setup(folder)
            clock[0]=datetime.fromisoformat('2026-12-01T09:59:00-05:00')
            with self.assertRaisesRegex(ValueError,'SIMULATION_CLOCK_OUTSIDE_SESSION'):
                observe_monthly(**args)
            self.assertEqual(calls,[])
            self.assertFalse(Path(args['storage_directory']).exists())
            clock[0]=datetime.fromisoformat('2026-12-01T10:00:30-05:00')
            args['paper_review_provider']=None
            with self.assertRaises(AttributeError): observe_monthly(**args)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'): observe_monthly(**args)
            self.assertEqual(calls,[])

    def test_late_trigger_and_same_month_without_configuration(self):
        with TemporaryDirectory() as folder:
            args,calls,clock=setup(folder)
            args['triggered_at']='2026-12-01T11:00:00-05:00'
            with self.assertRaisesRegex(ValueError,'TRIGGER_OUTSIDE_WINDOW'): observe_monthly(**args)
            args.update(session='2026-10-16',triggered_at='2026-10-16T10:00:00-04:00',
                        configuration_path='missing.json')
            with patch('subprocess.run', side_effect=AssertionError('same month search')):
                result=observe_monthly(**args)
            self.assertEqual(result['status'],'SAME_MONTH_NO_RESELECTION')
            self.assertEqual(result['simulation'],args['simulation'])
            self.assertEqual(calls,[])

    def test_backward_actual_clock_rejected_before_worker(self):
        with TemporaryDirectory() as folder:
            args,calls,clock=setup(folder)
            def backwards():
                value=clock[0]; clock[0]-=timedelta(seconds=1); return value
            args['clock']=backwards
            with patch('subprocess.run', side_effect=AssertionError('backwards search')):
                with self.assertRaisesRegex(ValueError,'CLOCK_OUTSIDE_SESSION'): observe_monthly(**args)
            self.assertEqual(calls,[])

    def test_same_candidate_monthly_refresh_accepts_without_orders(self):
        with TemporaryDirectory() as folder:
            args,calls,_=setup(folder,already_holds_candidate=True)
            result=observe_monthly(**args)
            ledger=result['simulation']['chain']['ledger']
            self.assertEqual(result['status'],'SIMULATED_MONTHLY_ACCEPTED')
            self.assertEqual(ledger['target_quantities'],{'B':20})
            self.assertEqual(ledger['orders'],{})
            self.assertEqual(ledger['shares'],args['simulation']['chain']['ledger']['shares'])
            self.assertEqual(ledger['cash'],args['simulation']['chain']['ledger']['cash'])
            self.assertEqual(calls,['BBB'])


if __name__=='__main__': unittest.main()
