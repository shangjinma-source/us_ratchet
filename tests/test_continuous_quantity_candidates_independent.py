from fractions import Fraction as F
import unittest
from backtest.continuous_quantity_candidates import generate_candidates


class IndependentContinuousTests(unittest.TestCase):
    def args(self):
        return dict(prices={'A':'3','B':'7'},metadata={'A':dict(ticker='A',issuer_id='a'),
            'B':dict(ticker='B',issuer_id='b')},entered_cash='100',fee_bps='1000',minimum_cash_buffer='13',
            training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}],iterations=12)

    def test_fee_in_gradient_cash_vertex(self):
        args=self.args();args['training_scenarios']=[{'A':'21/20','B':'101/100'}]
        result=generate_candidates(**args)
        self.assertEqual(result['candidate_count'],1)
        self.assertTrue(all(row['vertex']is None for row in result['trace']))

    def test_exact_fee_buffer_and_independent_first_steps(self):
        args=self.args();result=generate_candidates(**args)
        self.assertEqual([r['vertex']for r in result['trace'][:2]],['A','B'])
        self.assertEqual(result['candidates'][1]['quantities'],{'A':26})
        self.assertEqual(result['candidates'][2]['quantities'],{'A':8,'B':7})
        for row in result['candidates']:
            cost=sum(F(args['prices'][s])*q for s,q in row['quantities'].items())
            self.assertEqual(F(row['residual_cash'])+cost+F(row['fees']),F(100))
            self.assertEqual(F(row['fees']),cost/10)
            self.assertGreaterEqual(F(row['residual_cash']),F(13))

    def test_permutation_stability_and_issuer_conflict_cleanup(self):
        args=self.args();args['metadata']['B']['issuer_id']='a'
        result=generate_candidates(**args)
        self.assertTrue(all(r['actual_k']<=1 for r in result['candidates']))
        args['prices']=dict(reversed(list(args['prices'].items())))
        args['metadata']=dict(reversed(list(args['metadata'].items())))
        args['training_scenarios']=[dict(reversed(list(r.items()))) for r in reversed(args['training_scenarios'])]
        self.assertEqual(generate_candidates(**args),result)

    def test_buffer_exceeds_cash_and_unaffordable_shares(self):
        args=self.args();args['minimum_cash_buffer']='101'
        self.assertEqual(generate_candidates(**args)['candidate_count'],1)
        args['minimum_cash_buffer']='0';args['prices']={'A':'100000','B':'100000'}
        self.assertEqual(generate_candidates(**args)['candidate_count'],1)

    def test_invalid_and_small_positive_rationals(self):
        args=self.args()
        for value in ['NaN','Infinity',True,'0','-1']:
            args['prices']['A']=value
            with self.assertRaises(ValueError):generate_candidates(**args)
        args['prices']['A']='1/100000000000000000000000000000000000000000000000000'
        result=generate_candidates(**args)
        self.assertTrue(all(F(r['residual_cash'])>=0 for r in result['candidates']))


if __name__=='__main__':unittest.main()
