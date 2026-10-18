"""Adversarial review using synthetic inputs and temporary evidence only."""
from copy import deepcopy
from decimal import localcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_drawdown_six_period_conditional_execution_20260923 as fixtures

m=fixtures.m


class IndependentReview(unittest.TestCase):
    def test_shared_energy_cannot_be_consistently_relabelled(self):
        target,assembly=fixtures.inputs();sid='security:0001463101:29355A107'
        for day,_ in m.CLOCK:
            target['risk_chains_by_decision'][day][sid]='solar_only'
            assembly['selected_risk_chains_by_decision'][day][sid]='solar_only'
        for row in assembly['saved_lane_choices']:
            row['saved_candidate']['selected'][sid]['risk_chain']='solar_only'
        with self.assertRaises(ValueError):m.assemble(target,assembly)

    def test_identity_scope_and_permission_upgrades_rejected(self):
        for attack in ('old_window','assumption','pit','target_admission'):
            target,assembly=fixtures.inputs()
            if attack=='old_window':assembly['identity_projection']['enph_original_conditional_window']['end']='2023-09-01'
            if attack=='assumption':assembly['identity_projection']['interval_stability_assumption']='CERTIFIED'
            if attack=='pit':assembly['point_in_time_verified']=True
            if attack=='target_admission':assembly['target_schedule_validity_verified']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(target,assembly)

    def test_decimal_context_and_frozen_contract(self):
        target,assembly=fixtures.inputs()
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research') as engine:
            normal=m.assemble(target,assembly)
            with localcontext() as ctx:
                ctx.prec=3
                low=m.assemble(target,assembly)
            engine.assert_not_called()
        self.assertEqual(normal['price_conversion_evidence'],low['price_conversion_evidence'])
        self.assertEqual(normal['prices'],low['prices'])
        self.assertEqual(normal['schedule'],target['schedule'])
        self.assertEqual(normal['contract']['initial_cash_usd'],25000)
        self.assertEqual(normal['contract']['minimum_cash_buffer_usd'],100)
        self.assertEqual(normal['contract']['transaction_cost_bps'],10)
        self.assertEqual(normal['arguments']['corporate_actions'],[])
        self.assertEqual(normal['arguments']['identity_events'],[])
        self.assertEqual(normal['price_conversion_evidence']['cell_count'],856)
        self.assertTrue(all(v is False for v in m.FALSE_FLAGS.values()))

    def test_raw_precedes_guard_failure_and_orphan_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=fixtures.state()), \
                    patch.object(m,'check',side_effect=[None,None,ValueError('source drift')]), \
                    patch.object(m,'reference',side_effect=lambda role:dict(path=role,sha256='a'*64)), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine:
                with self.assertRaisesRegex(ValueError,'source drift'):m.run(output,True)
                failure=json.loads((output/'failure.json').read_bytes())
                self.assertTrue((output/'raw_execution.json').exists())
                self.assertFalse(failure['numerical_failure_is_economic_infeasibility'])
                (output/'orphan.json').write_text('{}')
                with self.assertRaises(ValueError):m.recover(output,failure['started_reference']['sha256'],failure['raw_reference']['sha256'])
                with self.assertRaises(ValueError):m.run(Path(folder)/'sibling',True)
                self.assertEqual(engine.call_count,1)

    def test_mutated_raw_envelope_rejected_even_with_matching_external_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=fixtures.state()),patch.object(m,'check'), \
                    patch.object(m,'reference',side_effect=lambda role:dict(path=role,sha256='a'*64)), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine, \
                    patch.object(m,'restore_and_audit',side_effect=ValueError('audit')):
                with self.assertRaisesRegex(ValueError,'audit'):m.run(output,True)
                failure=json.loads((output/'failure.json').read_bytes())
                raw_path=output/'raw_execution.json';raw=json.loads(raw_path.read_bytes())
                raw['promotion_allowed']=True;raw_path.write_bytes(m.encoded(raw))
                raw_sha=hashlib.sha256(raw_path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError,'Raw attempt envelope differs'):
                    m.recover(output,failure['started_reference']['sha256'],raw_sha)
                self.assertEqual(engine.call_count,1)


if __name__=='__main__':unittest.main()
