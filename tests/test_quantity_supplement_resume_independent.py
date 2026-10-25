from copy import deepcopy
from hashlib import sha256
import unittest
from random import Random
from backtest.quantity_supplement_frontier_resume import resume,verify,verify_transition
from backtest.quantity_box_supplemental_certificate import supplement
from test_quantity_box_supplemental_certificate import sources,raw
from test_quantity_integer_box_certificate_independent import oracle

class IndependentContinuationTests(unittest.TestCase):
    def test_twenty_tiny_domains_against_cartesian_oracle(self):
        rng=Random(419)
        for index in range(20):
            ids=['A','B'];args=dict(prices={s:str(rng.randint(1,3)) for s in ids},metadata={s:dict(ticker=s,issuer_id='same' if index%2 else s) for s in ids},entered_cash=str(rng.randint(3,7)),fee_bps=str(rng.choice([0,100,500])),minimum_cash_buffer=str(rng.randint(0,2)),training_scenarios=[{s:str(rng.choice([0.5,1,1.5,2])) for s in ids} for _ in range(2)])
            bound=sources(args);s=raw(supplement(**bound));ctx=dict(supplement_raw=s,expected_supplement_sha256=sha256(s).hexdigest(),bound_sources=bound)
            first=resume(**ctx,additional_node_budget=1);prior=raw(first)
            result=resume(**ctx,additional_node_budget=100,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest())
            self.assertTrue(result['objective_value_optimal'])
            self.assertEqual(result['lower_product'],str(max(v for _,v in oracle(args))))
            self.assertEqual(result['upper_product'],result['lower_product'])
            self.assertFalse(result['tie_break_optimality_established']);verify_transition(result,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest(),**ctx)
            changed=deepcopy(result);changed['parent_continuation_raw_sha256']='0'*64
            with self.assertRaises(ValueError):verify_transition(changed,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest(),**ctx)

    def test_fifo_scope_types_and_false_completion(self):
        from test_quantity_supplement_frontier_resume import setup
        ctx=setup();result=resume(**ctx,additional_node_budget=1)
        self.assertGreater(len(result['unsearched_frontier']),1)
        for kind in ['fifo','scope','bool','completion','anchor']:
            c=deepcopy(result)
            if kind=='fifo':c['unsearched_frontier'].reverse()
            elif kind=='scope':c['scope']='GLOBAL_FUTURE_RETURN_OPTIMAL'
            elif kind=='bool':c['processed_nodes']=True
            elif kind=='completion':c['objective_value_optimal']=True
            else:c['unsearched_frontier'][0]['bound']['binding']['incumbent']={'A':True}
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify(c,**ctx)

if __name__=='__main__':unittest.main()
