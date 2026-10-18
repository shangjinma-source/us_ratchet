from copy import deepcopy
import unittest
from backtest import ndx_dated_comparison_results_summary_research as m
from test_ndx_dated_economic_comparison_research import fixture_comparison

def fixture():
    rows=[]
    for k in range(4,21):
        for spec in m.SPECS:
            for i in range(32):rows.append(dict(numerical_task_id=format(len(rows)+1,'064x'),k=k,weight_spec=spec))
    rows[0]['numerical_task_id']=m.FIRST
    return dict(task_summary=dict(schema='DATED_BATCH_SAVED_READBACK_SUMMARY_V1',materialized_task_count=1632,full_new_cutoff_task_denominator=m.FULL,rows=rows),task_summary_reference=dict(path='summary',sha256='a'*64),comparisons_by_task={})
def saved(task,*,first=False,missing=False,decision='FROZEN',execution='REJECTED'):
    tid=task['numerical_task_id'];k=task['k'];positions=[dict(security_id='SID'+str(i),ticker='T'+str(i),issuer_id='I'+str(i),target_weight=0.0 if missing and i==0 else 1/k) for i in range(k)]
    ref=dict(path=tid+'.json',sha256='b'*64);auditref=dict(path=tid+'.audit',sha256='c'*64)
    flags=dict.fromkeys(('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','winner_selected'),False)
    ms={key:dict(exact='0',decimal='0',unit='ratio') for key in m.METRICS}
    account=dict(decisions=[{'status':decision}],executions=[] if execution is None else [{'status':execution}])
    tracks={}
    for name in m.TRACKS:
        tracks[name]=dict(status='AVAILABLE',metrics=deepcopy(ms),source_reference=deepcopy(ref),value_encoding='SAVED',original_account_preserved=deepcopy(account),original_track_preserved=dict(positions_preserved=deepcopy(positions)))
    if missing:tracks['candidate_integer']=dict(status='NOT_EXECUTED_NONPOSITIVE_TARGET',metrics=None,stored_values_exact=None,source_reference=None,original_account_preserved=None,missing_evidence=dict(reason='Original zero target',audit_reference=auditref))
    distance={mode:{kind:{key:dict(candidate_absolute_distance=None if missing and kind=='integer' else {'exact':'0'},incumbent_absolute_distance={'exact':'0'},candidate_minus_incumbent_distance=None if missing and kind=='integer' else {'exact':'0'}) for key in ('annualized_return','maximum_drawdown')} for kind in ('integer','continuous')} for mode in m.MODES}
    calendar=fixture_comparison()['nav_metrics']['reference_calendar']['dates']
    c=dict(schema='DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1' if first else 'DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1',status='SINGLE_PATH_DIAGNOSTIC_ONLY' if first else ('PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE' if missing else 'ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY'),valuation_point_count=127,return_interval_count=126,calendar=calendar,mode_order=list(m.MODES),nav_modes={mode:dict(metrics=deepcopy(ms),source_reference=deepcopy(ref)) for mode in m.MODES},modes_retained_separately=True,tracks=tracks,absolute_distance_comparisons=distance,source_references_preserved={'original':'preserved'},candidate_integer_status_preserved=dict(status='NOT_EXECUTED_NONPOSITIVE_TARGET' if missing else 'AVAILABLE'),saved_paths_preserved={role:dict(integer_account=deepcopy(account),continuous_track=dict(positions_preserved=deepcopy(positions))) for role in ('candidate','incumbent')},**flags)
    doc=dict(schema='SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' if first else 'SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1',numerical_task_id=tid,comparison=c,original_task_preserved={'numerical_task_id':tid},**flags)
    audit=dict(schema='DATED_COMPARISON_INDEPENDENT_READBACK_V1' if first else 'DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',numerical_task_id=tid,comparison_reference=deepcopy(ref),**flags)
    return dict(document=doc,document_reference=ref,audit=audit,audit_reference=auditref,original_targets=positions)

class Tests(unittest.TestCase):
    def test_both_schemas_full_domain_original_order_two_modes(self):
        a=fixture()
        for i in (0,1):t=a['task_summary']['rows'][i];a['comparisons_by_task'][t['numerical_task_id']]=saved(t,first=i==0)
        before=deepcopy(a);out=m.summarize_comparisons(**a);self.assertEqual(a,before);self.assertEqual(out['supplied_comparison_count'],2);self.assertEqual(out['not_supplied_count'],1630);self.assertEqual(len(out['k_spec_coverage']),51);self.assertEqual(len(out['rows']),1632);self.assertEqual(len(out['rows'][0]['nav_modes']),2);self.assertEqual(out['rows'][0]['tracks']['candidate_integer']['execution_statuses'],['REJECTED']);self.assertFalse(out['cohort_statistics_computed'])
    def test_zero_missing_and_no_plan_separate(self):
        a=fixture()
        for i in (1,2):
            t=a['task_summary']['rows'][i];a['comparisons_by_task'][t['numerical_task_id']]=saved(t,missing=i==1,decision='NO_PLAN' if i==2 else 'FROZEN',execution=None if i==2 else 'REJECTED')
        out=m.summarize_comparisons(**a);missing=out['rows'][1];self.assertIsNone(missing['tracks']['candidate_integer']['metrics']);self.assertEqual(missing['original_targets'][0]['target_weight'],0.0);self.assertEqual(out['rows'][2]['tracks']['candidate_integer']['decision_status'],'NO_PLAN');self.assertEqual(out['rows'][2]['tracks']['candidate_integer']['execution_statuses'],[])
    def test_target_refs_authority_and_missing_mode_attacks(self):
        for modify in (lambda e:e['original_targets'][0].update(ticker='WRONG'),lambda e:e['audit']['comparison_reference'].update(sha256='f'*64),lambda e:e['document']['comparison'].update(winner_selected=0),lambda e:e['document']['comparison']['nav_modes'].pop(m.MODES[1])):
            a=fixture();t=a['task_summary']['rows'][1];e=saved(t);modify(e);a['comparisons_by_task'][t['numerical_task_id']]=e
            with self.assertRaises(ValueError):m.summarize_comparisons(**a)
    def test_denominator_type_and_no_foreign_or_colliding_source(self):
        a=fixture();a['task_summary']['materialized_task_count']=True
        with self.assertRaises(ValueError):m.summarize_comparisons(**a)
        a=fixture();a['comparisons_by_task']['f'*64]={}
        with self.assertRaises(ValueError):m.summarize_comparisons(**a)
        a=fixture();t=a['task_summary']['rows'][1];e=saved(t);e['audit_reference']=dict(path=e['document_reference']['path'],sha256='d'*64);a['comparisons_by_task'][t['numerical_task_id']]=e
        with self.assertRaises(ValueError):m.summarize_comparisons(**a)
if __name__=='__main__':unittest.main()
