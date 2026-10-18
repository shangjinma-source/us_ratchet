import json
import unittest
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

from backtest.current_quantity_v2_daily_simulation import run_daily
from backtest.current_quantity_v2_simulated_settlement import register_valuation
from backtest.current_quantity_v2_simulated_settlement import _references, settle
from test_current_quantity_v2_simulated_settlement import evidence_for
from test_current_quantity_v2_simulated_settlement import mark
from test_current_quantity_v2_monthly_simulation import setup as monthly_setup
from backtest.current_quantity_v2_simulated_settlement import create_simulation
from backtest.current_quantity_v2_monthly_simulation import digest
from backtest.current_quantity_v2_simulation_store import SimulationStore
from test_current_quantity_v2_continuation_simulation import daily_arguments, cash_review
import test_current_quantity_v2_continuation_simulation as continuation_fixture
import test_current_quantity_v2_current_cash_plan as cash_fixture
from test_current_quantity_v2_daily_settlement_simulation import reviews


class DailySimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cash_fixture.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):cash_fixture.CurrentCashTests.tearDownClass()

    def arguments(self,folder,missing=False):
        state=continuation_fixture.ContinuationSimulationTests.cash_simulation(self)
        dates=['2026-10-15','2026-10-16']
        calendar=dict(session_dates=dates,closes={d:d+'T16:00:00-04:00' for d in dates},source_references=['synthetic-calendar'])
        state=register_valuation(simulation=state,calendar=calendar,initial_marks={},
            registered_at=state['chain']['ledger']['acceptance']['accepted_at'])
        daily,calls,clock=daily_arguments(folder,state,'2026-10-16')
        root=Path(cash_fixture.CurrentCashTests.temp.name)
        (root/'daily-schedule.json').write_bytes((Path(folder)/'daily-schedule.json').read_bytes())
        daily.update(root=root,unit_review_reader=cash_review)
        captures=[];saved={}
        def fetch(url):
            captures.append(url);q=parse_qs(urlparse(url).query);ticker=urlparse(url).path.rsplit('/',1)[1]
            times=[] if missing else list(range(int(q['period1'][0]),int(q['period2'][0]),60))
            row=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',dataGranularity='1m',exchangeTimezoneName='America/New_York'),
                timestamp=times,events={},indicators=dict(quote=[dict(**{k:[1]*len(times) for k in ('open','high','low','close')},volume=[1]*len(times))]))
            return json.dumps(dict(chart=dict(error=None,result=[row]))).encode()
        def capture_args(simulation,day):
            return dict(fees={oid:'0' for oid in simulation['chain']['ledger']['orders']},
                calendar_source_reference='synthetic-calendar',directory=Path(folder)/'captures',fetch=fetch)
        def review(simulation,prepared):
            result=reviews(prepared,simulation);result.pop('evaluated_at');saved.update(prepared=prepared,review=result)
            return result
        def close_args(simulation,day):
            directory=Path(saved['prepared']['directory']);held={s for s,q in simulation['chain']['ledger']['shares'].items() if q}
            review=deepcopy(saved['review']);paths={}
            for sid in held:
                paths[sid]={k:digest(sid)+'/'+name for k,name in [('raw','response.bin'),('receipt','receipt.json'),('minutes','minutes.json')]}
                for name in paths[sid].values():review['source_hashes'][name]=sha256((directory/name).read_bytes()).hexdigest()
            return dict(root=directory,captures=paths,**review)
        def continuation(simulation,day):
            return {k:v for k,v in daily.items() if k not in ('store','simulation_id','expected_revision','operation_id','session','triggered_at','clock')}
        def monthly(*_):self.fail('same month must not research')
        args=dict(store=daily['store'],simulation_id=state['simulation_id'],session='2026-10-16',
            triggered_at=daily['triggered_at'],clock=daily['clock'],capture_arguments=capture_args,
            settlement_review=review,close_arguments=close_args,continuation_arguments=continuation,monthly_arguments=monthly)
        return args,captures,calls,clock

    def test_real_prior_settlement_close_then_continuation_and_restart(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.arguments(folder)
            result=run_daily(**args)
            self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
            state=result['simulation'];self.assertEqual(state['valuation']['records'][0]['status'],'COMPLETE')
            self.assertTrue(all(o['closed']=='FILLED' for o in state['chain']['ledger']['orders'].values()))
            self.assertEqual(len(captures),2);self.assertEqual(len(calls),2)
            again=run_daily(**dict(args,store=SimulationStore(args['store'].path)))
            self.assertEqual(again['daily_status'],'ALREADY_COMPLETED')
            self.assertEqual(len(captures),2);self.assertEqual(len(calls),2)

    def test_unknown_stops_before_close_and_accept_and_retry_does_not_capture(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.arguments(folder,missing=True)
            result=run_daily(**args)
            self.assertEqual(result['daily_status'],'BLOCKED_UNRESOLVED_ORDERS')
            self.assertEqual(result['simulation']['valuation']['records'],[]);self.assertEqual(calls,[])
            again=run_daily(**args)
            self.assertEqual(again['daily_status'],'BLOCKED_UNRESOLVED_ORDERS');self.assertEqual(len(captures),2)

    def test_late_after_catchup_does_not_accept(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.arguments(folder)
            provider=args['close_arguments']
            def close(*values):
                result=provider(*values);clock[0]=datetime.fromisoformat('2026-10-16T10:01:00-04:00');return result
            result=run_daily(**dict(args,close_arguments=close))
            self.assertEqual(result['daily_status'],'LATE_NO_NEW_DECISION');self.assertEqual(calls,[])

    def test_prepared_recovery_and_started_refusal_before_sources(self):
        for mode in ('prepared','started'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args,captures,calls,clock=self.arguments(folder)
                store=args['store'];current=store.read(args['simulation_id'])
                operation=dict(simulation_id=args['simulation_id'],expected_revision=current['revision'],
                    operation_id='synthetic-interruption',request=dict(kind='SYNTHETIC_TEST_IDENTITY'))
                if mode=='prepared':
                    with patch.object(store,'_commit',side_effect=RuntimeError('interruption')):
                        with self.assertRaises(RuntimeError):store.apply(**operation,transform=lambda value:value)
                    result=run_daily(**args)
                    self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
                    self.assertTrue(store.inspect_operations(args['simulation_id'])['operations'][0]['recovered'])
                else:
                    def interrupted(_):raise KeyboardInterrupt()
                    with self.assertRaises(KeyboardInterrupt):store.apply(**operation,transform=interrupted)
                    with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'):run_daily(**args)
                    self.assertEqual(captures,[]);self.assertEqual(calls,[])

    def test_closed_orders_skip_capture_missing_marks_persist_before_no_order_continuation(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.arguments(folder)
            state=args['store'].read(args['simulation_id'])['simulation']
            evidence,at=evidence_for(state['chain'],_references(state['chain']))
            state=settle(simulation=state,evidence=evidence,observed_through=at,evaluated_at=at)
            store=SimulationStore(Path(folder)/'already-settled.sqlite3');store.create(state)
            args.update(store=store,close_arguments=lambda *_:dict(status='MISSING_CLOSE_EVIDENCE',reason='Synthetic unavailable close'))
            result=run_daily(**args)
            self.assertEqual(captures,[])
            self.assertEqual(result['daily_status'],'CONTINUATION_COMPLETE')
            self.assertEqual(result['continuation_status'],'NO_ORDERS')
            self.assertEqual(result['simulation']['valuation']['records'][0]['status'],'BLOCKED')
            self.assertEqual(result['simulation']['valuation']['performance']['status'],'INCOMPLETE')

    def test_slow_decision_provider_cannot_start_after_window(self):
        with TemporaryDirectory() as folder:
            args,captures,calls,clock=self.arguments(folder)
            provider=args['continuation_arguments']
            def slow(*values):
                arguments=provider(*values)
                clock[0]=datetime.fromisoformat('2026-10-16T10:01:00-04:00')
                return arguments
            result=run_daily(**dict(args,continuation_arguments=slow))
            self.assertEqual(result['daily_status'],'LATE_NO_NEW_DECISION');self.assertEqual(calls,[])

    def test_real_monthly_worker_after_multiple_declared_historical_closes(self):
        with TemporaryDirectory() as folder:
            monthly,calls,clock=monthly_setup(folder)
            original=monthly['simulation']
            state=create_simulation(chain=original['origin'],simulation_id=original['simulation_id'],model=original['model'])
            accepted=state['chain']['ledger']['acceptance']['accepted_at']
            dates=['2026-10-15','2026-10-16','2026-12-01']
            calendar=dict(session_dates=dates,source_references=['synthetic-declared-sparse-test-calendar'],
                closes={day:day+('T16:00:00-05:00' if day.startswith('2026-12') else 'T16:00:00-04:00') for day in dates})
            state=register_valuation(simulation=state,calendar=calendar,initial_marks={'X':mark('X','XXX','50',accepted)},registered_at=accepted)
            for batch in original['batches']:state=settle(simulation=state,**batch['request'])
            self.assertEqual(state['chain'],original['chain'])
            store=SimulationStore(Path(folder)/'dispatcher.db');store.create(state);closed=[]
            def missing(state,day):
                closed.append(day)
                return dict(status='MISSING_CLOSE_EVIDENCE',reason='Synthetic absent historical close')
            def forbidden(*_):self.fail('monthly dispatch must not recapture settled orders or continue old month')
            kwargs={k:v for k,v in monthly.items() if k not in ('simulation','session','triggered_at','clock')}
            arguments=dict(store=store,simulation_id=state['simulation_id'],session=monthly['session'],triggered_at=monthly['triggered_at'],
                clock=monthly['clock'],capture_arguments=forbidden,settlement_review=forbidden,close_arguments=missing,
                continuation_arguments=forbidden,monthly_arguments=lambda *_:kwargs)
            result=run_daily(**arguments)
            self.assertEqual(result['daily_status'],'MONTHLY_COMPLETE')
            self.assertEqual(closed,dates[:2])
            self.assertEqual([r['session'] for r in result['simulation']['valuation']['records']],dates[:2])
            self.assertEqual(set(result['simulation']['chain']['ledger']['target_quantities']),{'B'})
            self.assertEqual(calls,['AAA','BBB'])
            with patch('subprocess.run',side_effect=AssertionError('retry must not search')):
                self.assertEqual(run_daily(**arguments)['daily_status'],'ALREADY_COMPLETED')
            self.assertEqual(closed,dates[:2]);self.assertEqual(calls,['AAA','BBB'])


if __name__=='__main__':unittest.main()
