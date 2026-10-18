"""No real engine or complete prepare calls; validate the frozen input boundary."""
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bad_tail_six_period_conditional_execution_20260923 as module


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target=module.read(module.reference('schedule'))
        cls.projection=module.read(module.reference('projection'))

    def assemble(self,target=None,projection=None):
        with patch.object(module.engine,'simulate_dynamic_frozen_execution_research',side_effect=AssertionError('No engine in tests')):
            return module.assemble(target or self.target,projection or self.projection)

    def test_actual_uppercase_validator_and_decimal_1070_boundary(self):
        prepared=self.assemble()
        self.assertEqual(len(prepared['labels']),5)
        self.assertTrue(all(c==c.upper() and c.startswith('SID_') for c in prepared['columns'].values()))
        self.assertEqual(prepared['price_conversion_evidence']['cell_count'],1070)
        self.assertTrue(all(isinstance(v[k],Decimal) for day in prepared['prices'].values() for v in day.values() for k in ('open','close')))
        self.assertTrue(prepared['engine_input_validation']['frozen_price_index_validators_called'])
        args=copy.deepcopy(prepared['arguments'])
        for field in ('opens','closes'):args[field].columns=[c.lower() for c in args[field].columns]
        with self.assertRaises(ValueError):module.validate_engine_inputs(args)

    def test_future_chain_cannot_be_imported_to_april(self):
        target=copy.deepcopy(self.target)
        target['risk_chains_by_decision']['2023-03-31']['security:0000813672:127387108']='eda_ip'
        with self.assertRaises(ValueError):self.assemble(target=target)

    def test_selection_or_clock_drift_rejected(self):
        target=copy.deepcopy(self.target);target['schedule'][-1]['execution_date']='2023-09-05'
        with self.assertRaises(ValueError):self.assemble(target=target)
        projection=copy.deepcopy(self.projection);projection['execution_risk_chain_union_verified']=True
        with self.assertRaises(ValueError):self.assemble(projection=projection)

    def test_old_holding_survives_multiple_rejections_with_old_observation(self):
        p=self.assemble();sid='security:0001262039:34959E109'
        self.assertEqual(p['risk_chain_evidence']['2023-07-31']['observation_dates'][sid],'2023-05-31')
        selected={r['decision_date']:r for r in p['schedule']};execution=dict(decisions=[],daily=[],
            executions=[dict(session=day,status='REJECTED',shares_before={sid:10},shares_after={sid:10})
                        for day in ('2023-07-03','2023-08-01')],trades=[])
        active=None
        for day in p['calendar']:
            if day in selected:active=p['risk_chain_evidence'][day]
            shares={} if day=='2023-03-31' else {sid:10}
            if day in selected:
                union=set(shares)|set(selected[day]['targets'])
                execution['decisions'].append(dict(decision_date=day,shares_before=shares,
                    risk_chains={s:active['chains'][s] for s in union},
                    risk_chain_observation_dates={s:active['observation_dates'][s] for s in union}))
            execution['daily'].append(dict(session=day,shares=shares,
                risk_chains={s:active['chains'][s] for s in shares},
                risk_chain_observation_dates={s:active['observation_dates'][s] for s in shares}))
        self.assertTrue(module.verify_ledger_risk_history(execution,p)['actual_holdings_chain_dates_checked'])
        row=next(r for r in execution['daily'] if r['session']=='2023-08-01')
        self.assertEqual(row['shares'],{sid:10})
        self.assertEqual(row['risk_chain_observation_dates'][sid],'2023-05-31')
        row['risk_chain_observation_dates'][sid]='2023-08-31'
        with self.assertRaises(ValueError):module.verify_ledger_risk_history(execution,p)

    def test_fixed_namespace_and_existing_attempt_stop_before_prepare(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'prepare') as prepare:
            with self.assertRaises(ValueError):module.run(Path(directory)/'other',execute=True)
            with patch.object(module,'OUTPUT',Path(directory)):
                with self.assertRaises(ValueError):module.run(Path(directory),execute=True)
            prepare.assert_not_called()

    def test_recovery_requires_external_raw_and_no_orphans(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(module,'OUTPUT',Path(directory)),patch.object(module,'prepare') as prepare:
            with self.assertRaises(ValueError):module.recover(directory,'','')
            (Path(directory)/'started.json').write_text('{}')
            with self.assertRaises(ValueError):module.recover(directory,'a'*64,'b'*64)
            prepare.assert_not_called()


if __name__=='__main__':unittest.main()
