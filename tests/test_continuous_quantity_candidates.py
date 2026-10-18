from fractions import Fraction
from itertools import product
import math
import unittest
from backtest.continuous_quantity_candidates import generate_candidates


class ContinuousCandidateTests(unittest.TestCase):
    def inputs(self):
        return dict(prices={'A':'10','B':'10'},metadata={'A':dict(ticker='AAA',issuer_id='a'),'B':dict(ticker='BBB',issuer_id='b')},
                    entered_cash='100',fee_bps=0,minimum_cash_buffer=0,
                    training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}],iterations=12)

    def test_small_exhaustive_reference_and_determinism(self):
        args=self.inputs();result=generate_candidates(**args)
        def score(q):
            cash=100-sum(10*v for v in q.values())
            return math.prod(cash+sum(10*v*Fraction(s[sid]) for sid,v in q.items()) for s in args['training_scenarios'])
        feasible=[dict(A=a,B=b) for a,b in product(range(11),repeat=2) if a+b<=10]
        optimum=max(map(score,feasible));actual=max(score(c['quantities']) for c in result['candidates'])
        self.assertLessEqual(actual,optimum);self.assertGreater(actual,score({'A':10}))
        self.assertFalse(result['global_optimum_established']);self.assertEqual(result['iterations_completed'],12)
        self.assertLessEqual(result['candidate_count'],13)
        args['prices']=dict(reversed(list(args['prices'].items())))
        args['metadata']=dict(reversed(list(args['metadata'].items())))
        args['training_scenarios']=[dict(reversed(list(r.items()))) for r in args['training_scenarios']]
        self.assertEqual(result,generate_candidates(**args))

    def test_fees_buffer_issuer_floor_and_cash(self):
        args=self.inputs();args.update(fee_bps=125,minimum_cash_buffer=17)
        args['metadata']['B']['issuer_id']='a'
        for candidate in generate_candidates(**args)['candidates']:
            q=candidate['quantities'];self.assertLessEqual(len(q),1)
            self.assertTrue(all(type(v)is int and v>0 for v in q.values()))
            notional=sum(Fraction(args['prices'][s])*v for s,v in q.items())
            self.assertEqual(notional+Fraction(candidate['fees'])+Fraction(candidate['residual_cash']),100)
            self.assertGreaterEqual(Fraction(candidate['residual_cash']),17)
        args.update(minimum_cash_buffer=101)
        self.assertEqual(generate_candidates(**args)['candidates'][0]['quantities'],{})
        self.assertEqual(generate_candidates(**args)['candidate_count'],1)
        args=self.inputs();args.update(fee_bps=100,training_scenarios=[{'A':'1005/1000','B':'1'}])
        result=generate_candidates(**args);self.assertEqual(result['candidate_count'],1)
        self.assertTrue(all(t['vertex']is None for t in result['trace']))

    def test_invalid_numbers_domains_and_budget(self):
        for bad in (True,float('nan'),float('inf'),'NaN','1/0',-1):
            args=self.inputs();args['entered_cash']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):generate_candidates(**args)
        for bad in (0,257,True,1.5):
            args=self.inputs();args['iterations']=bad
            with self.assertRaises(ValueError):generate_candidates(**args)
        args=self.inputs();args['training_scenarios'][0].pop('B')
        with self.assertRaises(ValueError):generate_candidates(**args)
        args=self.inputs();args['metadata']['B']['ticker']='AAA'
        with self.assertRaises(ValueError):generate_candidates(**args)


if __name__=='__main__':unittest.main()
