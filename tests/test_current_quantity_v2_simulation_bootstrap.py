from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest.current_quantity_v2_simulation_bootstrap import bootstrap
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_simulated_settlement import MODEL
from test_current_quantity_v2_current_cash_ledger import frozen_fixture
import test_current_quantity_v2_current_cash_plan as base


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.CurrentCashTests.setUpClass();cls.args=deepcopy(base.CurrentCashTests.args)
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()

    def arguments(self,folder):
        proposal,args=frozen_fixture(self.args);now=datetime.fromisoformat(args['now'])+timedelta(seconds=1)
        ref=next(iter(proposal['execution_references'].values()));session=ref['session']
        expected=deepcopy(proposal['causal_inputs']['frozen_execution_package']['source_hashes']);calls=[]
        def guard(pins):self.assertEqual(pins,expected);calls.append(pins)
        return dict(store=SimulationStore(Path(folder)/'isolated.sqlite3'),simulation_id='explicit-bootstrap',
            proposal=proposal,account_state=args['account_state'],initial_cash=args['account_state']['cash'],
            model=MODEL,calendar=dict(session_dates=[session],closes={session:ref['session_close']},
            source_references=['synthetic-declared-calendar']),source_admission_guard=guard,clock=lambda:now),calls

    def test_actual_cash_proposal_registers_at_acceptance_and_duplicate_rejected(self):
        with TemporaryDirectory() as folder:
            args,calls=self.arguments(folder);before=deepcopy(args['proposal']);result=bootstrap(**args)
            simulation=result['simulation'];accepted=simulation['origin']['ledger']['acceptance']['accepted_at']
            self.assertEqual(simulation['valuation']['registration']['registered_at'],accepted)
            self.assertEqual(simulation['valuation']['initial_equity'],args['initial_cash'])
            self.assertEqual(simulation['origin']['ledger']['shares'],{})
            self.assertFalse(simulation['forward_activated']);self.assertEqual(len(calls),1)
            self.assertEqual(args['proposal'],before)
            args['clock']=lambda:self.fail('duplicate cannot read new clock')
            with self.assertRaisesRegex(ValueError,'BOOTSTRAP_ALREADY_EXISTS'):bootstrap(**args)
            self.assertEqual(args['store'].read(args['simulation_id']),result)

    def test_all_preflight_failures_leave_database_absent(self):
        for mode in ('cash','shares','guard','missing_guard','expired','calendar','model'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args,_=self.arguments(folder)
                if mode=='cash':args['initial_cash']='20000'
                elif mode=='shares':args['account_state']['shares']={'A':1}
                elif mode=='guard':args['source_admission_guard']=lambda _:False
                elif mode=='missing_guard':args['source_admission_guard']=None
                elif mode=='expired':args['clock']=lambda:datetime.fromisoformat(self.args['now'])+timedelta(minutes=5)
                elif mode=='calendar':args['calendar']['session_dates']=[]
                else:args['model']='UNKNOWN_MODEL'
                with self.assertRaises(ValueError):bootstrap(**args)
                self.assertFalse(args['store'].path.exists())


if __name__=='__main__':unittest.main()
