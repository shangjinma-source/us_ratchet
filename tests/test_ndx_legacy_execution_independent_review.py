"""Synthetic account-boundary review, no actual engine or audit."""
from copy import deepcopy
from decimal import Decimal,localcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_legacy_six_period_conditional_execution_20260923 as fixtures

m=fixtures.m


class IndependentReview(unittest.TestCase):
    def test_class_sale_buy_restores_labels_without_coalescing_or_audit_twice(self):
        old='security:0001652044:02079K305';new='security:0001652044:02079K107'
        columns={old:'SID_0001652044_02079K305',new:'SID_0001652044_02079K107'}
        prepared=dict(labels={old:dict(ticker='GOOGL'),new:dict(ticker='GOOG')},columns=columns,calendar=[],normalized=[],prices={},
            arguments=dict(risk_chains_by_decision={}),contract=dict(m.CONTRACT))
        raw=dict(decisions=[dict(targets={new:dict(ticker=columns[new])})],trades=[
            dict(security_id=old,ticker=columns[old],share_delta=-7,transaction_cost_usd=.7),
            dict(security_id=new,ticker=columns[new],share_delta=8,transaction_cost_usd=.8)],
            daily=[dict(shares={old:2,new:8},tickers=columns.copy())])
        before=deepcopy(raw)
        with patch.object(m,'verify_ledger_risk_history'),patch.object(m.independent,'audit',return_value={'ok':True}) as audit:
            result,_=m.restore_and_audit(raw,prepared)
            self.assertEqual(audit.call_count,1)
        self.assertEqual(raw,before)
        self.assertEqual([(r['security_id'],r['ticker'],r['share_delta']) for r in result['trades']],[(old,'GOOGL',-7),(new,'GOOG',8)])
        self.assertEqual(result['daily'][0]['tickers'],{old:'GOOGL',new:'GOOG'})

    def test_decimal_context_original_schedule_and_action_free_contract(self):
        args=fixtures.inputs()
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research') as engine:
            a=m.assemble(*args)
            with localcontext() as ctx:
                ctx.prec=3;b=m.assemble(*args)
            engine.assert_not_called()
        self.assertEqual(a['price_conversion_evidence'],b['price_conversion_evidence'])
        self.assertEqual(a['prices'],b['prices'])
        self.assertEqual(a['schedule'],args[0]['schedule'])
        self.assertEqual(a['price_conversion_evidence']['cell_count'],2568)
        self.assertTrue(all(isinstance(v['open'],Decimal) for row in a['prices'].values() for v in row.values()))
        self.assertEqual(a['arguments']['identity_events'],[])
        self.assertEqual(a['contract']['transaction_cost_bps'],10)
        self.assertFalse(a['action_free_assumption']['identity_class_conversion_assumed'])

    def test_shared_chain_and_old_identity_window_cannot_be_relabelled(self):
        for attack in ('chain','window','rename'):
            target,prices,identity,lane=fixtures.inputs()
            if attack=='window':identity['enph_original_conditional_window']['end']='2023-09-01'
            if attack=='rename':identity['goog_googl_relationship']='SAME_SECURITY_RENAME'
            if attack=='chain':
                sid='security:0001463101:29355A107'
                for choice,decision in zip(identity['saved_lane_choices'],lane['decisions']):
                    if sid in choice['saved_candidate']['selected']:
                        choice['saved_candidate']['selected'][sid]['risk_chain']='separate_solar'
                        decision['lanes']['LEGACY_TARGET_DISTANCE'][0]['selected'][sid]['risk_chain']='separate_solar'
                        identity['selected_risk_chains_by_decision'][choice['decision_date']][sid]='separate_solar'
                        target['risk_chains_by_decision'][choice['decision_date']][sid]='separate_solar'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(target,prices,identity,lane)

    def test_raw_saved_when_guard_fails_and_orphan_prevents_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=fixtures.state()), \
                    patch.object(m,'check',side_effect=[None,None,ValueError('source drift')]), \
                    patch.object(m,'reference',side_effect=lambda role:dict(path=role,sha256='a'*64)), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine:
                with self.assertRaisesRegex(ValueError,'source drift'):m.run(output,True)
                failure=json.loads((output/'failure.json').read_bytes());self.assertTrue((output/'raw_execution.json').exists())
                self.assertFalse(failure['numerical_failure_is_economic_infeasibility'])
                (output/'orphan').write_text('x')
                with self.assertRaises(ValueError):m.recover(output,failure['started_reference']['sha256'],failure['raw_reference']['sha256'])
                self.assertEqual(engine.call_count,1)


if __name__=='__main__':unittest.main()
