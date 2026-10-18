from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_full_ndx_multidecision_selector_research as m


def fixture():
    ref=dict(path='registration.json',sha256='a'*64)
    universe=[dict(security_id='A',issuer_id='I1',ticker='AAA',sector='ENERGY'),dict(security_id='B',issuer_id='I1',ticker='BBB',sector='ENERGY'),dict(security_id='C',issuer_id='I2',ticker='CCC',sector='HEALTHCARE'),dict(security_id='D',issuer_id='I3',ticker='DDD',sector='UTILITIES')]
    calendar=[];d=date(2023,1,2)
    while d<=date(2026,8,31):
        if d.weekday()<5:calendar.append(d.isoformat())
        d+=timedelta(days=1)
    registration=dict(schema='FULL_NDX_MULTIDECISION_SELECTION_REGISTRATION_V1',policy_id=m.POLICY,registration_reference=ref,scope_reference=ref,universe_scope='ALL_CONDITIONAL_NDX_MEMBERS_ALL_INDUSTRIES',sector_filter_applied=False,decision_cutoffs=list(m.CUTOFFS),fx_modes=list(m.MODES),universe=universe,all_k_denominators=[dict(holding_count=1,combination_count=4),dict(holding_count=2,combination_count=5),dict(holding_count=3,combination_count=2)],coordinates=[])
    records=[]
    for cutoff in m.CUTOFFS:
        end=calendar.index(cutoff);days=calendar[end-504:end+1]
        for mode in m.MODES:
            ids=[cutoff+'/'+mode+'/'+str(i) for i in range(3)]
            registration['coordinates'].append(dict(cutoff=cutoff,decision_date=cutoff,fx_mode=mode,expected_job_ids=ids,source_status='READY_FOR_SCORING',source_blockers=[],training_semantics_sha256='b'*64,budget_reference=ref,scoring_price_dates=days,budget_coverage=dict(full_combination_count=11,full_three_spec_task_denominator=33,registered_task_count=3,unscored_full_domain_task_count=30,pre_registered_exclusions=[])))
            for i,sid in enumerate(('A','C','D')):
                task=dict(job_id=ids[i],cutoff=cutoff,decision_date=cutoff,fx_mode=mode,security_ids=[sid],holding_count=1,tickers=universe[{'A':0,'C':2,'D':3}[sid]]['ticker'],weight_spec='equal_weight')
                result={k:deepcopy(task[k]) for k in ('security_ids','holding_count','tickers','weight_spec')}
                result.update(return_p50=[.3,.2,.1][i],return_p10=[.1,.2,.05][i],max_drawdown_p50=[.3,.2,.01][i],max_drawdown_p90=[.4,.3,.02][i],target_012922_distance=[.2,.1,.3][i])
                windows=[]
                for w in range(13):
                    l=w*21;windows.append(dict(window_index=w,status='COMPLETE',fit_return_count=126,evaluation_return_count=126,fit_price_predecessor=days[l],fit_first_return_end=days[l+1],fit_last_return_end=days[l+126],evaluation_price_predecessor=days[l+126],evaluation_first_return_end=days[l+127],evaluation_last_return_end=days[l+252]))
                records.append(dict(task=task,result=result,status='EVALUATED',training_semantics_sha256='b'*64,evidence_reference=ref,eligibility=dict.fromkeys(m.GATES,True),scoring_windows=windows))
    return registration,records


class Tests(unittest.TestCase):
    def test_source_blocked_keeps_registered_denominator_and_cannot_rank(self):
        reg,records=fixture();coordinate=reg['coordinates'][0]
        coordinate.update(source_status='SOURCE_BLOCKED',source_blockers=[dict(reason_code='TARGET_FULL13_BLOCKED',evidence_reference=reg['registration_reference'])])
        out=m.select_full_ndx_lanes(registration=reg,records=records[3:]);row=out['rows'][0]
        self.assertEqual(row['source_blocked_task_count'],3)
        self.assertEqual(row['unreceived_job_ids'],coordinate['expected_job_ids'])
        self.assertEqual(row['input_errors'],[])
        self.assertTrue(all(c['status']=='SOURCE_BLOCKED' and c['selected'] is None for c in row['choices']))
        self.assertTrue(all(c['selected'] is not None for c in out['rows'][1]['choices']))
        out=m.select_full_ndx_lanes(registration=reg,records=records)
        self.assertTrue(all(c['status']=='INPUT_INVALID' for c in out['rows'][0]['choices']))
        coordinate['source_blockers']=[]
        with self.assertRaises(ValueError):m.select_full_ndx_lanes(registration=reg,records=records[3:])

    def test_four_lanes_all_industries_and_exact_issuer_domain(self):
        reg,records=fixture();out=m.select_full_ndx_lanes(registration=reg,records=records)
        self.assertEqual([x['selected']['record_preserved']['task']['tickers'] for x in out['rows'][0]['choices']],['AAA','CCC','DDD','CCC'])
        self.assertEqual([x['combination_count'] for x in out['all_k_denominators_preserved']],[4,5,2]);self.assertEqual(len(out['rows']),12)
        self.assertEqual(out['records_preserved'],records);self.assertFalse(out['prior_resolved']);self.assertFalse(out['complete_ndx_universe_verified'])
    def test_expected_set_missing_partial_error_and_mode_isolation(self):
        reg,records=fixture()
        for change in (lambda x:x.pop(0),lambda x:x[0]['task'].update(job_id='foreign'),lambda x:x[0]['scoring_windows'].pop(),lambda x:x[0]['result'].update(return_p50=True),lambda x:x[0].update(status='EVALUATION_EXCEPTION'),lambda x:x[0]['scoring_windows'][0].update(evaluation_last_return_end='2026-09-21')):
            bad=deepcopy(records);change(bad);out=m.select_full_ndx_lanes(registration=reg,records=bad)
            self.assertTrue(out['rows'][0]['input_errors']);self.assertTrue(all(x['selected'] is None for x in out['rows'][0]['choices']))
            self.assertTrue(all(x['selected'] is not None for x in out['rows'][1]['choices']))
    def test_gate_rejections_and_class_collision_not_cash(self):
        reg,records=fixture()
        for r in records[:3]:r['eligibility']['liquidity_passed']=False
        out=m.select_full_ndx_lanes(registration=reg,records=records);self.assertEqual(len(out['rows'][0]['rejections']),3);self.assertEqual(out['rows'][0]['choices'][0]['status'],'NO_ELIGIBLE_CANDIDATE')
        records[3]['task'].update(security_ids=['A','B'],holding_count=2,tickers='AAA;BBB');records[3]['result'].update(security_ids=['A','B'],holding_count=2,tickers='AAA;BBB')
        out=m.select_full_ndx_lanes(registration=reg,records=records);self.assertTrue(out['rows'][1]['input_errors'])
    def test_duplicate_semantic_and_negative_distance_block(self):
        reg,records=fixture()
        for mode in ('duplicate','negative'):
            bad=deepcopy(records)
            if mode=='duplicate':
                identity=bad[1]['task']['job_id'];bad[1]=deepcopy(bad[0]);bad[1]['task']['job_id']=identity
            else:bad[0]['result']['target_012922_distance']=-1
            out=m.select_full_ndx_lanes(registration=reg,records=bad)
            self.assertTrue(out['rows'][0]['input_errors']);self.assertTrue(all(c['selected'] is None for c in out['rows'][0]['choices']))

    def test_empty_registered_domain_preserves_full_inventory(self):
        reg,records=fixture();reg['coordinates'][0]['expected_job_ids']=[]
        reg['coordinates'][0]['budget_coverage'].update(registered_task_count=0,unscored_full_domain_task_count=33)
        out=m.select_full_ndx_lanes(registration=reg,records=records[3:])
        self.assertTrue(all(x['status']=='NO_REGISTERED_CANDIDATES' and x['selected'] is None for x in out['rows'][0]['choices']))
        self.assertEqual(out['rows'][0]['coordinate_preserved']['budget_coverage']['full_three_spec_task_denominator'],33)

    def test_tie_jobid_and_budget_exclusions(self):
        reg,records=fixture();a=deepcopy(records[0])
        for row in records[1:3]:
            for key in m.METRICS:row['result'][key]=a['result'][key]
        out=m.select_full_ndx_lanes(registration=reg,records=list(reversed(records)))
        self.assertEqual(out['rows'][0]['choices'][0]['selected']['job_id'],a['task']['job_id'])
        reg['coordinates'][0]['budget_coverage']['pre_registered_exclusions']=[dict(reason_code='UNKNOWN_MDV_UNITS',security_ids=['B'],holding_counts=[],evidence_reference=reg['registration_reference'])]
        out=m.select_full_ndx_lanes(registration=reg,records=records);self.assertEqual(len(out['registration_preserved']['universe']),4)
        reg['all_k_denominators'][1]['combination_count']=6
        with self.assertRaises(ValueError):m.select_full_ndx_lanes(registration=reg,records=records)

if __name__=='__main__':unittest.main()
