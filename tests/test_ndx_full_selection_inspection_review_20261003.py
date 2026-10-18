from copy import deepcopy
import hashlib
import unittest
import test_ndx_full_ndx_multidecision_selector_research as source
from backtest import ndx_full_ndx_selection_inspection_research as m


def seal(d):
    d['content_sha256']=hashlib.sha256(m.encoded({k:v for k,v in d.items() if k!='content_sha256'})).hexdigest()
    return d


def manual():
    reg,records=source.fixture()
    rows=[]
    for ci,c in enumerate(reg['coordinates']):
        choices=[]
        # Fixture economics: AAA highest median; CCC best tail/target distance;
        # DDD smallest drawdown. This expectation does not invoke the selector.
        for lane,local in zip(('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE'),(0,1,2,1)):
            i=ci*3+local
            choices.append(dict(lane=lane,status='SELECTED_REQUIRES_NEW_CUTOFF_REFIT',selected=dict(job_id=records[i]['task']['job_id'],record_index=i,record_preserved=deepcopy(records[i]))))
        rows.append(dict(coordinate_preserved=deepcopy(c),expected_task_count=3,received_task_count=3,source_blocked_task_count=0,unreceived_job_ids=[],input_errors=[],rejections=[],eligible_count=3,choices=choices))
    d=dict(schema='FULL_NDX_MULTIDECISION_FOUR_LANE_SELECTION_V1',policy_id=m.POLICY,registration_preserved=deepcopy(reg),records_preserved=deepcopy(records),rows=rows,global_input_errors=[],all_k_denominators_preserved=deepcopy(reg['all_k_denominators']),cutoff_refit_required=True,portfolio_track='portfolio_optimization',evaluation_tracks=['continuous','whole_lot'],ranking_arithmetic='EXACT_FRACTION_OF_SAVED_NUMERIC_LITERAL_NOT_RECOMPUTED_SCORES',**dict.fromkeys(m.FALSE,False))
    return reg,records,seal(d)


class IndependentReview(unittest.TestCase):
    def test_manual_four_lane_expected_without_selector_oracle(self):
        r,rows,d=manual();before=m.encoded((r,rows,d))
        out=m.inspect_complete_selection(registration=r,records=rows,saved_selection=d)
        self.assertEqual(out['selected_lane_count'],48)
        self.assertFalse(out['upstream_scoring_windows_reaudited'])
        self.assertEqual(before,m.encoded((r,rows,d)))

    def test_resigned_wrong_lane_and_large_exact_score_difference(self):
        r,rows,d=manual()
        d['rows'][-1]['choices'][0]['selected']=deepcopy(d['rows'][-1]['choices'][2]['selected'])
        with self.assertRaises(ValueError):m.inspect_complete_selection(registration=r,records=rows,saved_selection=seal(d))
        r,rows,d=manual();rows[1]['result']['return_p50']=2**60+1;rows[0]['result']['return_p50']=2**60
        d['records_preserved']=deepcopy(rows)
        # Keep old AAA winner, but refresh record copies so this attacks ranking.
        for choice in d['rows'][0]['choices']:
            i=choice['selected']['record_index'];choice['selected']['record_preserved']=deepcopy(rows[i])
        with self.assertRaises(ValueError):m.inspect_complete_selection(registration=r,records=rows,saved_selection=seal(d))

    def test_false_count_and_issuer_polynomial_not_relabelled(self):
        for mode in ('count','flag','polynomial'):
            r,rows,d=manual()
            if mode=='count':d['rows'][0]['source_blocked_task_count']=False
            elif mode=='flag':d['execution_authorized']=0
            else:
                r['all_k_denominators'][1]['combination_count']=6
                d['registration_preserved']=deepcopy(r);d['all_k_denominators_preserved']=deepcopy(r['all_k_denominators'])
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_complete_selection(registration=r,records=rows,saved_selection=seal(d))


if __name__=='__main__':unittest.main()
