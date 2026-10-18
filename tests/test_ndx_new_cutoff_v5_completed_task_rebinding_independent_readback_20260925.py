"""Synthetic 300-task nested reference contract; never actual rebinding."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_v4_completed_task_rebinding_independent_readback_20260925 as previous
from scripts import ndx_new_cutoff_v5_completed_task_rebinding_independent_readback_20260925 as m

SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection')
KEYS=('preserved_evidence_sidecar_reference','preserved_incremental_evidence_sidecar_reference','preserved_v3_incremental_evidence_sidecar_reference','preserved_v4_incremental_evidence_sidecar_reference','preserved_v5_incremental_evidence_sidecar_reference')


def fixture():
    docs,panel=previous.fixture()
    old_index=docs['completed_index']
    with patch.object(previous.m.codec,'decode_frames',return_value=panel):
        nested=previous.m.reconstruct_rows(docs)
    plan=docs['plan']['plan'];ctx=plan['context'];records=panel['universe'].to_dict('records');by={r['security_id']:r for r in records}
    old_groups=[g for g in plan['canonical_groups'] if 'BKNG_SID' not in g['security_ids']]
    rows=[]
    for k in range(4,21):
        for local in range(2):
            selected_sids=[g['security_ids'][0] for g in old_groups[:k-1]]+['BKNG_SID']
            if local:selected_sids[-2]=old_groups[k-1]['security_ids'][0]
            selected={s:{name:by[s][name] for name in ('ticker','issuer_id','risk_chain')} for s in sorted(selected_sids)}
            tickers=[v['ticker'] for v in selected.values()]
            matrix=dict(dates=[d.date().isoformat() for d in panel['returns'].index],tickers=tickers,returns=panel['returns'][tickers].values.tolist())
            for spec in m.SPECS:
                ident=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=k,selected=selected,weight_spec=spec,parameters=deepcopy(ctx['parameters']),requested_previous_target_weights=None,fit_data_sha256=m.digest(matrix),fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
                loc=dict(synthetic_old_location=True,k=k,local=local,spec=spec)
                task=dict(numerical_identity=ident,numerical_task_id=m.digest(ident),location_identity=loc,location_id=m.digest(loc),expected_fitter_previous_target_weights={})
                row=dict(numerical_task_id=task['numerical_task_id'],full_task=task,fit_data_sha256=m.digest(matrix),status='FITTED_FIVE_RISKS_PASSED')
                for key in ('started_reference','raw_reference','postcheck_reference','independent_readback_reference'):row[key]=dict(path='synthetic/'+key,sha256='a'*64)
                rows.append(row)
    docs['completed_index'].update(schema='NEW_CUTOFF_BKNG_COMPLETED_TASK_INDEX_V1',batch_saved_attempt_and_readback_count=300,new_tasks=rows,externally_completed_rebound_rows=nested)
    records.append(dict(security_id='ORLY_SID',issuer_id='I00B',ticker='ORLY',risk_chain='automotive'))
    panel['universe']=m.codec.pd.DataFrame(records);panel['returns']['ORLY']=.039
    panel.update(schema='LATEST_CONDITIONAL_TYPED_PANEL_V5',conditional_security_count=23,conditional_issuer_count=22,observed_provenance_and_missing=[dict(synthetic=i) for i in range(101)])
    groups={}
    for r in records:groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
    plan['canonical_groups']=[dict(issuer_id=i,security_ids=sorted(v)) for i,v in sorted(groups.items())]
    ctx.update(panel_reference=m.ref('panel'),panel_audit_reference=m.ref('audit'),group_fingerprint=m.digest(dict(order_version=m.ORDER,groups=[(i,sorted(v)) for i,v in sorted(groups.items())])))
    plan['plan_id']=m.digest(ctx);plan.update(planned_canonical_task_count=18868155,remaining_canonical_task_count=18868155);plan['shards']=[]
    for k in range(4,21):
        total=m.suffix_count([len(g['security_ids']) for g in plan['canonical_groups']],0,k);identity=dict(ctx,k=k,start=0,stop=total)
        plan['shards'].append(dict(identity,plan_id=plan['plan_id'],shard_id=m.digest(identity),completed_canonical_task_count=0,remaining_canonical_task_count=3*total,status='PLANNED_NOT_ENUMERATED'))
    docs['plan'].update(schema='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V5',input_references=dict(panel=m.ref('panel'),audit=m.ref('audit')),external_completed_index_reference=m.ref('completed_index'),complete_observed_provenance_and_missing=deepcopy(panel['observed_provenance_and_missing']))
    docs['audit'].update(candidate_reference=m.ref('panel'),original_twenty_two_five_frames_exact=True)
    for key,pointer in zip(KEYS,SIDECARS):docs['plan'][key]=dict(m.ref('panel'),json_pointer='/'+pointer);docs['panel'][pointer]=[{'synthetic':pointer}]
    return docs,panel


class Tests(unittest.TestCase):
    def test_all300_numeric_ids_and_nested_reference_layers_preserved(self):
        docs,panel=fixture();before=deepcopy(docs)
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        self.assertEqual(len(rows),300);self.assertEqual(docs,before)
        self.assertEqual(rows[102]['original_index_row'],docs['completed_index']['externally_completed_rebound_rows'][0])
        self.assertEqual(rows[-1]['prior_rebinding_row'],docs['completed_index']['externally_completed_rebound_rows'][-1])
        self.assertIn('prior_rebinding_row',rows[-1]['prior_rebinding_row'])
        self.assertTrue(all(r['new_wrapper_call_attempt_count']==0 for r in rows))

    def test_nested_contract_gap_and_source_attacks(self):
        for attack in ('oldmissing','nestedid','matrix','source','prior','gap','sidecar'):
            docs,panel=fixture()
            if attack=='oldmissing':docs['completed_index']['externally_completed_rebound_rows'].pop()
            elif attack=='nestedid':docs['completed_index']['externally_completed_rebound_rows'][0]['numerical_task_id']='0'*64
            elif attack=='matrix':panel['returns'].iloc[0,0]=.8
            elif attack=='source':docs['plan']['plan']['fitter_source_hashes']={}
            elif attack=='prior':docs['plan']['plan']['context']['previous_target_weights']={}
            elif attack=='gap':docs['plan']['complete_observed_provenance_and_missing'].pop()
            else:docs['plan'][KEYS[-1]]['json_pointer']='/wrong'
            with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(docs)

    def test_full_envelope_rejects_nested_evidence_or_completion_claim(self):
        docs,panel=fixture()
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        value=dict(schema='NEW_CUTOFF_V5_COMPLETED_TASK_REBINDING_V1',input_references={k:m.ref(k) for k in m.BOUND},rows=rows,externally_rebound_task_count=300,externally_rebound_combination_count=100,full_plan_task_denominator=18868155,remaining_uncompleted_task_count=18867855,new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,rank_calculation_performed=True,combination_enumeration_performed=False,complete_observed_provenance_and_missing=docs['plan']['complete_observed_provenance_and_missing'],preserved_sidecar_references=[docs['plan'][key] for key in KEYS],source_hashes={},**dict.fromkeys(m.PRODUCER_FALSE,False))
        with patch.object(m.codec,'decode_frames',return_value=panel),patch.object(m,'producer_sources',return_value={}):
            self.assertEqual(len(m.verify_candidate(value,docs)),300)
            for attack in ('nested','count','sidecar'):
                bad=deepcopy(value)
                if attack=='nested':bad['rows'][-1]['prior_rebinding_row']['prior_rebinding_row']={}
                elif attack=='count':bad['new_fit_count']=False
                else:bad['preserved_sidecar_references'].pop()
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_candidate(bad,docs)

    def test_tiny_rank_order_and_same_issuer_refusal(self):
        groups=[dict(issuer_id='A',security_ids=['z']),dict(issuer_id='B',security_ids=['a','b']),dict(issuer_id='C',security_ids=['x'])]
        expected=[['z','a'],['z','b'],['z','x'],['a','x'],['b','x']]
        self.assertEqual([m.independent_rank(groups,s) for s in expected],list(range(5)))
        with self.assertRaises(ValueError):m.independent_rank(groups,['a','b'])

    def test_hard_parent_bytes_and_missing_actual_pin(self):
        for role in m.BOUND:
            r=m.ref(role);self.assertEqual(m.codec.sha(Path(r['path']).read_bytes()),r['sha256'])
        with patch.object(m,'PRODUCER_SHA',None),patch.object(m,'guard') as guard:
            with self.assertRaises(ValueError):m.build()
            guard.assert_not_called()


if __name__=='__main__':unittest.main()
