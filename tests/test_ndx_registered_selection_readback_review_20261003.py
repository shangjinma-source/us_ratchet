from copy import deepcopy
from pathlib import Path
from io import BytesIO
import hashlib
import unittest
import test_ndx_registered_scoring_selection_independent_readback_20261003 as author
from scripts import ndx_registered_scoring_selection_independent_readback_20261003 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args,cls.prepared,cls.refs=author.fixture()

    def test_fixed_independent_rank_source_pin_matches_consumed_code(self):
        self.assertRegex(m.RANK_INSPECTOR_SHA,r'^[0-9a-f]{64}$')
        self.assertEqual(hashlib.sha256(Path(m.RANK_INSPECTOR).read_bytes()).hexdigest(),m.RANK_INSPECTOR_SHA)
        for path,h in m.CODES.values():self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),h)

    def test_last_source_metric_and_record_locator_not_author_snapshot(self):
        for attack in ('source_metric','source_locator','last_missing','risk_gate'):
            a=deepcopy(self.args);p=deepcopy(self.prepared)
            if attack=='source_metric':a['projections'][-1]['score']['metrics']['return_p50']+=0.001
            elif attack=='source_locator':a['projections'][-1]['score_reference']['record_locator']['byte_start']+=1
            elif attack=='last_missing':a['projections'].pop()
            else:p['records'][-1]['eligibility']['fractional_risk_passed']=0
            p['content_sha256']=m.sha(m.enc({k:v for k,v in p.items() if k!='content_sha256'}))
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_projected_inputs(p,a['budget_plan'],self.refs,a['projections'])

    def test_blocked_denominator_and_journal_eof_never_hidden(self):
        p=deepcopy(self.prepared);p['registration']['coordinates'][0]['expected_job_ids'].pop()
        p['content_sha256']=m.sha(m.enc({k:v for k,v in p.items() if k!='content_sha256'}))
        with self.assertRaises(ValueError):m.inspect_projected_inputs(p,self.args['budget_plan'],self.refs,self.args['projections'])
        blob,r,locations=author.record_fixture()
        iterator=m.read_scored_records(BytesIO(blob+b'{}\n'),r,locations)
        self.assertEqual(next(iterator)[1]['weights'],[0,.25,.75])
        with self.assertRaises(ValueError):list(iterator)


if __name__=='__main__':unittest.main()
