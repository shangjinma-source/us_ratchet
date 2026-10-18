import copy
import unittest
from backtest import ndx_conditional_channel_independent_audit_research as m
from test_ndx_conditional_channel_input_research import fixture,build_channel_input


def case(index=None,kind='ORDINARY_SPLIT',floor=None):
    inputs=fixture(index,kind,floor)
    output=build_channel_input(**inputs)  # Test data only; oracle never imports producer.
    return dict(output=output,**{k:inputs[k] for k in ('raw_bytes','quote_rows','calendar','event_policy','exclude_on_or_after','regular_floor')})


class AuditTests(unittest.TestCase):
    def test_no_event_in_window_and_later_event_independent_arithmetic(self):
        for index in (None,40,80,127):
            with self.subTest(index=index):
                result=m.audit(**case(index))
                self.assertEqual(result['return_count'],126)
                self.assertEqual(result['liquidity_count'],0 if index in (80,127) else 63)
        self.assertEqual(m.audit(**case(0,'BEFORE_PARTITION_UNMODELLED',0))['return_count'],126)

    def test_output_cannot_hide_wrong_return_units_scope_or_source_open(self):
        for defect in ('return','sid','scope','volume','open','error','event'):
            args=case();out=args['output']
            if defect=='return':out['price_returns'][0]['price_return']=.99
            if defect=='sid':out['security_id']='invented'
            if defect=='scope':out['security_identity_verified']=True
            if defect=='volume':out['liquidity']['rows'][0]['raw_volume']*=2
            if defect=='open':args['quote_rows'][0]['nominal_open']+=1
            if defect=='error':out['maximum_nominal_reconstruction_error']='1'
            if defect=='event':out['returned_events']['dividends']={'fake':{}}
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit(**args)

    def test_full_policy_floor_and_volume_block_required(self):
        for defect in ('policy','floor','volume','bool'):
            args=case(80)
            if defect=='policy':args['event_policy']=[]
            if defect=='floor':args['regular_floor']=args['calendar'][1]
            if defect=='volume':args['output']['liquidity']['numerical_threshold_passed']=True
            if defect=='bool':args['event_policy'][0]['denominator']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit(**args)


if __name__=='__main__':unittest.main()
