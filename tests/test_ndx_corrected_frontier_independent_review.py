from copy import deepcopy
import random
import unittest
import test_ndx_corrected_complete_date_frontier_research as fixtures
from backtest import ndx_corrected_complete_date_frontier_research as module


class IndependentReview(unittest.TestCase):
    def test_random_eight_dimensional_bruteforce_and_order_ties(self):
        rng=random.Random(803)
        for trial in range(30):
            args=fixtures.fixture();vectors=[]
            for i,record in enumerate(args['complete_overlay']['records']):
                vector=[rng.uniform(-.2,.2) for _ in range(8)]
                vector[4:6]=sorted(vector[4:6],reverse=True)
                vector[6:8]=sorted(vector[6:8])
                if i==1:vector=list(vectors[0])
                vectors.append(vector)
                for name,value in zip(module.previous.ECONOMIC_COLUMNS,vector):record['result'][name]=value
                if i<3:args['original_parent']['records'][i]=deepcopy(record)
            for key in ('complete_overlay','original_parent'):args[key]['records_sha256']=module.digest(args[key]['records'])
            oriented=[[v*(1 if j in (0,1,4,5) else -1) for j,v in enumerate(row)] for row in vectors]
            expected={str(i) for i,row in enumerate(oriented) if not any(all(a>=b for a,b in zip(other,row)) and any(a>b for a,b in zip(other,row)) for k,other in enumerate(oriented) if k!=i)}
            report=module.analyze_complete_corrected_date(**args)
            self.assertEqual({r['job_id'] for r in report['raw_frontier']},expected)
            args['complete_overlay']['records'].reverse();args['complete_overlay']['records_sha256']=module.digest(args['complete_overlay']['records'])
            shuffled=module.analyze_complete_corrected_date(**args)
            self.assertEqual({r['job_id'] for r in shuffled['raw_frontier']},expected)

    def test_risk_failure_is_kept_in_complete_raw_denominator(self):
        args=fixtures.fixture();row=args['complete_overlay']['records'][-1]
        row['result']['portfolio_min_median_dollar_volume_usd']=50.0
        row['result']['liquidity_constraint_passed']=False
        args['complete_overlay']['records_sha256']=module.digest(args['complete_overlay']['records'])
        report=module.analyze_complete_corrected_date(**args)
        self.assertEqual(len(report['candidate_diagnostics']),4)
        self.assertEqual(len(report['raw_frontier']),4)
        self.assertNotIn('3',{r['job_id'] for r in report['risk_liquidity_frontier']})
        self.assertIsNone(report['winner'])
        self.assertFalse(report['training_performed'])


if __name__=='__main__':unittest.main()
