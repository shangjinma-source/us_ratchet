"""Synthetic 198 nested references only; no real rebinding or fit."""
from copy import deepcopy
from itertools import combinations, product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_v3_completed_task_rebinding_independent_readback_20260925 as old
import test_ndx_new_cutoff_cprt_single_task_independent_readback_20260925 as cprt
from scripts import ndx_new_cutoff_v4_completed_task_rebinding_independent_readback_20260925 as m


def fixture():
    legacy, _ = old.fixture()
    source, panel, _ = cprt.authorized_fixture()
    plan = deepcopy(source['plan']['plan'])
    context = plan['context']
    panel = deepcopy(panel)
    panel['returns']['BKNG'] = .031
    records = panel['universe'].to_dict('records') + [dict(security_id='BKNG_SID', ticker='BKNG', issuer_id='I00A', risk_chain='travel_hospitality')]
    panel['universe'] = m.codec.pd.DataFrame(records)
    panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V4', conditional_security_count=22, conditional_issuer_count=21)
    groups = {}
    for r in records: groups.setdefault(r['issuer_id'], []).append(r['security_id'])
    plan['canonical_groups'] = [dict(issuer_id=i, security_ids=sorted(v)) for i,v in sorted(groups.items())]
    context.update(panel_reference=m.ref('panel'), panel_audit_reference=m.ref('audit'), group_fingerprint=m.digest(dict(order_version=m.ORDER, groups=[(i,sorted(v)) for i,v in sorted(groups.items())])))
    plan['plan_id'] = m.digest(context)
    plan.update(planned_canonical_task_count=9431859, remaining_canonical_task_count=9431859, completed_canonical_task_count=0)
    plan['shards'] = []
    for k in range(4,21):
        total = m.suffix_count([len(g['security_ids']) for g in plan['canonical_groups']],0,k)
        identity = dict(context,k=k,start=0,stop=total)
        plan['shards'].append(dict(identity,plan_id=plan['plan_id'],shard_id=m.digest(identity),completed_canonical_task_count=0,remaining_canonical_task_count=3*total,status='PLANNED_NOT_ENUMERATED'))
    def references(row):
        for name in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):
            row[name] = dict(path='synthetic/'+name,sha256='a'*64)
        return row
    recent = [references(dict(full_task=deepcopy(task),numerical_task_id=task['numerical_task_id'],fit_data_sha256=combo['fit_data_sha256'],status='FITTED_FIVE_RISKS_PASSED')) for value in source['queue']['new_materializations'] for combo in value['combinations'] for task in combo['tasks']]
    nested = []
    for row in legacy['completed_index']['new_tasks'] + legacy['completed_index']['old_completed_tasks']:
        row = references(deepcopy(row))
        location = dict(synthetic='prior V3 location', task=row['numerical_task_id'])
        nested.append(dict(numerical_task_id=row['numerical_task_id'],old_completed_row=row,status='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND',new_wrapper_call_attempt_count=0,verified_fit_data_sha256=row['fit_data_sha256'],new_location_identity=location,new_location_id=m.digest(location)))
    index = dict(schema='NEW_CUTOFF_CPRT_COMPLETED_TASK_INDEX_V1',batch_saved_attempt_and_readback_count=198,new_tasks=recent,externally_completed_rebound_rows=nested)
    docs = dict(plan=dict(schema='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V4',plan=plan,input_references=dict(panel=m.ref('panel'),audit=m.ref('audit')),external_completed_index_reference=m.ref('completed_index'),completed_task_rebinding_verified=False,external_completed_tasks_deducted=0), panel={'panel':{}}, audit=dict(status='PASSED',candidate_reference=m.ref('panel'),original_twenty_one_five_frames_exact=True,panel_content_sha256=panel['panel_content_sha256']),completed_index=index)
    for d in docs.values():
        d.update(promotion_allowed=False,execution_authorized=False,legal_training_input_admitted=False,point_in_time_verified=False,full_transitive_source_closure_reverified=False)
    return docs,panel


class Tests(unittest.TestCase):
    def test_independent_rank_small_exhaustive(self):
        groups=[dict(issuer_id='A',security_ids=['x','z']),dict(issuer_id='B',security_ids=['a']),dict(issuer_id='C',security_ids=['b','c'])]
        for k in range(1,4):
            rows=[]
            for chosen in combinations(groups,k):
                for sids in product(*(g['security_ids'] for g in chosen)):
                    rows.append(tuple(zip([g['issuer_id'] for g in chosen],sids)))
            rows.sort()
            self.assertEqual([m.independent_rank(groups,[s for _,s in row]) for row in rows],list(range(len(rows))))
        with self.assertRaises(ValueError):m.independent_rank(groups,['x','z'])

    def test_all198_preserves_nested_index_rows_and_original_tasks(self):
        docs,panel=fixture();before=deepcopy(docs)
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        self.assertEqual(len(rows),198);self.assertEqual(docs,before)
        self.assertIsNone(rows[0]['prior_rebinding_row'])
        self.assertEqual(rows[102]['original_index_row'],docs['completed_index']['externally_completed_rebound_rows'][0])
        self.assertTrue(rows[102]['old_completed_row_reference']['json_pointer'].endswith('/0/old_completed_row'))
        self.assertEqual(len({r['new_location_id'] for r in rows}),198)
        self.assertTrue(all(r['new_wrapper_call_attempt_count']==0 for r in rows))

    def test_nested_alias_source_prior_matrix_attacks(self):
        for attack in ('partial','nestedid','nestedmatrix','location','source','prior','fullpanel','risk'):
            docs,panel=fixture();nested=docs['completed_index']['externally_completed_rebound_rows']
            if attack=='partial':nested.pop()
            elif attack=='nestedid':nested[0]['numerical_task_id']=nested[1]['numerical_task_id']
            elif attack=='nestedmatrix':nested[0]['verified_fit_data_sha256']='0'*64
            elif attack=='location':nested[0]['new_location_identity']['fake']=True
            elif attack=='source':docs['plan']['plan']['fitter_source_hashes']={}
            elif attack=='prior':docs['plan']['plan']['context']['previous_target_weights']={}
            elif attack=='fullpanel':panel['returns'].iloc[0,-1]=float('nan')
            else:panel['universe'].loc[0,'risk_chain']='changed'
            with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(docs)

    def test_full_envelope_exact_and_no_198_refit(self):
        docs,panel=fixture()
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        value=dict(schema='NEW_CUTOFF_V4_COMPLETED_TASK_REBINDING_V1',input_references={k:m.ref(k) for k in m.BOUND},rows=rows,externally_rebound_task_count=198,externally_rebound_combination_count=66,full_plan_task_denominator=9431859,remaining_uncompleted_task_count=9431661,new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,rank_calculation_performed=True,combination_enumeration_performed=False,**dict.fromkeys(m.PRODUCER_FALSE,False),source_hashes={})
        with patch.object(m.codec,'decode_frames',return_value=panel),patch.object(m,'producer_sources',return_value={}):
            self.assertEqual(len(m.verify_candidate(value,docs)),198)
            for key, changed in [('remaining_uncompleted_task_count',0),('new_fit_count',False),('all_plan_tasks_completed',True)]:
                bad=deepcopy(value);bad[key]=changed
                with self.subTest(key=key),self.assertRaises(ValueError):m.verify_candidate(bad,docs)
            bad=deepcopy(value);bad['rows'][102]['prior_rebinding_row']['old_completed_row']['independent_readback_reference']['sha256']='f'*64
            with self.assertRaises(ValueError):m.verify_candidate(bad,docs)

    def test_pending_and_namespace_refuse_before_work(self):
        with patch.object(m,'PRODUCER_SHA',None),patch.object(m,'guard') as guard:
            with self.assertRaises(ValueError):m.build()
            guard.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'independent_readback.json';out.write_text('{}')
            with patch.object(m,'OUTPUT',out),patch.object(m,'build') as build:
                with self.assertRaises(ValueError):m.publish()
                build.assert_not_called()


if __name__=='__main__':unittest.main()
