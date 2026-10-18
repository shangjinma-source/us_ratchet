import json
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_return_six_period_conditional_execution_v2_20260923 as m


def state():
    prepared=dict(calendar=['fixture'],schedule=[{'targets':{'a':1}}],columns={'a':'SID_a'},
                  contract=dict(m.CONTRACT),normalization_evidence={},price_conversion_evidence={},engine_input_validation={},arguments={},normalized=[])
    return dict(prepared=prepared,sources={},runtime={'test':1},resolution={})


class IndependentReview(unittest.TestCase):
    def test_preflight_calls_real_frozen_price_validator(self):
        target,price,identity=[m.read(m.reference(role)) for role in ('schedule','price','identity')]
        validator=m.engine.repair._strict_price_index
        with patch.object(m.engine.repair,'_strict_price_index',wraps=validator) as checked, \
                patch.object(m.engine,'simulate_dynamic_frozen_execution_research') as engine:
            prepared=m.assemble(target,price,identity)
            self.assertEqual(checked.call_count,2)
            self.assertEqual(set(prepared['columns']),{r['security_id'] for r in identity['rows']})
            self.assertTrue(all(column==column.upper() for column in prepared['columns'].values()))
            engine.assert_not_called()
        broken=prepared['arguments']['opens'].copy()
        broken.columns=[column.lower() for column in broken.columns]
        with self.assertRaises(ValueError):validator(broken,'opens')

    def test_saved_inputs_keep_six_clocks_full_prices_and_distinct_classes(self):
        target,price,identity=[m.read(m.reference(role)) for role in ('schedule','price','identity')]
        prepared=m.assemble(target,price,identity)
        self.assertEqual(len(prepared['calendar']),107)
        self.assertEqual([(r['decision_date'],r['execution_date']) for r in prepared['schedule']],m.CLOCK)
        self.assertEqual(prepared['contract']['initial_cash_usd'],25000)
        self.assertEqual(prepared['contract']['minimum_cash_buffer_usd'],100)
        self.assertEqual(prepared['contract']['transaction_cost_bps'],10)
        self.assertEqual(prepared['price_conversion_evidence']['cell_count'],1712)
        for marks in prepared['prices'].values():
            for value in marks.values():
                for field in ('open','close'):
                    self.assertEqual(m.independent.number(value[field]),value[field])
        classes={row['ticker']:sid for sid,row in prepared['labels'].items()}
        self.assertNotEqual(prepared['columns'][classes['GOOG']],prepared['columns'][classes['GOOGL']])
        self.assertEqual(prepared['labels'][classes['GOOG']]['issuer_id'],prepared['labels'][classes['GOOGL']]['issuer_id'])
        self.assertEqual(prepared['schedule'],target['schedule'])
        for original,submitted in zip(target['schedule'],prepared['arguments']['schedule']):
            self.assertEqual({sid:v['target_weight'] for sid,v in original['targets'].items()},
                             {sid:v['target_weight'] for sid,v in submitted['targets'].items()})
        for mutate in (lambda p:p['calendar'].pop(),lambda p:p.update(price_cell_count=1711),
                       lambda p:p['matrices']['open'][p['calendar'][0]].update(AVGO=True)):
            changed=deepcopy(price);mutate(changed)
            with self.assertRaises(ValueError):m.assemble(target,changed,identity)

    def test_raw_saved_before_source_failure_and_no_reexecution(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt';checks=[None,None,ValueError('source drift')]
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=state()),patch.object(m,'check',side_effect=checks), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={'sentinel':1}) as engine:
                with self.assertRaisesRegex(ValueError,'source drift'):m.run(output,True)
                self.assertEqual(json.loads((output/'raw_execution.json').read_bytes())['execution'],{'sentinel':1})
                self.assertTrue((output/'failure.json').exists())
                with self.assertRaises(ValueError):m.run(output,True)
                self.assertEqual(engine.call_count,1)

    def test_audit_failure_can_recover_saved_raw_without_engine(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=state()),patch.object(m,'check'), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine, \
                    patch.object(m,'restore_and_audit',side_effect=ValueError('audit failed')):
                with self.assertRaisesRegex(ValueError,'audit failed'):m.run(output,True)
                failure=json.loads((output/'failure.json').read_bytes())
                with patch.object(m,'restore_and_audit',return_value=({},{})):
                    result=m.recover(output,failure['started_reference']['sha256'],failure['raw_reference']['sha256'])
                self.assertTrue(Path(result['path']).exists());self.assertEqual(engine.call_count,1)

    def test_bool_execution_and_external_recovery_hash_required(self):
        for invalid in (1,0,'yes',None):
            with self.assertRaises(ValueError):m.run('unused',invalid)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m,'OUTPUT',Path(folder)):
                with self.assertRaises(ValueError):m.recover(folder,None,None)

    def test_sibling_namespace_cannot_create_second_account(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'authorized'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare') as prepare:
                with self.assertRaises(ValueError):m.run(Path(folder)/'sibling',True)
                with self.assertRaises(ValueError):m.recover(Path(folder)/'sibling','a'*64,'b'*64)
                prepare.assert_not_called()

    def test_recovery_cannot_upgrade_raw_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);fixture=state()
            started=m.publish(output/'started.json',m.started_value(fixture))
            raw=m.raw_value(fixture,started,{})
            raw['promotion_allowed']=True
            saved=m.publish(output/'raw_execution.json',raw)
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=fixture),patch.object(m,'check'), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research') as engine:
                with self.assertRaisesRegex(ValueError,'Raw attempt envelope'):
                    m.recover(output,started['sha256'],saved['sha256'])
                engine.assert_not_called()

    def test_orphan_created_during_execution_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            def engine(**kwargs):
                (output/'unknown.json').write_text('{}');return {}
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=state()),patch.object(m,'check'), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',side_effect=engine), \
                    patch.object(m,'restore_and_audit',return_value=({},{})):
                with self.assertRaises(ValueError):m.run(output,True)


if __name__=='__main__':unittest.main()

