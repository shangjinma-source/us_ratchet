"""Independent synthetic adversarial checks; no real completion reconstruction."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_v4_completed_task_rebinding_independent_readback_20260925 as owner
from scripts import ndx_new_cutoff_v4_completed_task_rebinding_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    def test_real_pins_bytes_only_no_actual_reconstruction(self):
        for path,expected in [(m.PRODUCER,m.PRODUCER_SHA),(m.CANDIDATE,m.CANDIDATE_SHA)]+[(m.BASE/p,h) for p,h in m.BOUND.values()]:
            self.assertEqual(m.codec.sha(path.read_bytes()),expected)

    def test_rehashed_new_location_or_lost_nested_wrapper_rejected(self):
        docs,panel=owner.fixture()
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        value=dict(schema='NEW_CUTOFF_V4_COMPLETED_TASK_REBINDING_V1',input_references={k:m.ref(k) for k in m.BOUND},rows=rows,
            externally_rebound_task_count=198,externally_rebound_combination_count=66,full_plan_task_denominator=9431859,
            remaining_uncompleted_task_count=9431661,new_wrapper_call_attempt_count=0,new_fit_count=0,
            old_full_tasks_and_completion_references_preserved=True,rank_calculation_performed=True,combination_enumeration_performed=False,
            **dict.fromkeys(m.PRODUCER_FALSE,False),source_hashes={})
        for attack in ('rank','drop_wrapper','reference'):
            bad=deepcopy(value)
            if attack=='rank':
                bad['rows'][102]['new_location_identity']['rank']+=1
                bad['rows'][102]['new_location_id']=m.digest(bad['rows'][102]['new_location_identity'])
            elif attack=='drop_wrapper':bad['rows'][102]['prior_rebinding_row']=None
            else:bad['rows'][102]['original_index_row_reference']=bad['rows'][102]['old_completed_row_reference']
            with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),patch.object(m,'producer_sources',return_value={}),self.assertRaises(ValueError):
                m.verify_candidate(bad,docs)

    def test_same_issuer_two_classes_rejected_even_with_new_task_digest(self):
        docs,panel=owner.fixture();plan=docs['plan']['plan']
        pair=next(g['security_ids'] for g in plan['canonical_groups'] if len(g['security_ids'])==2)
        by={r['security_id']:r for r in panel['universe'].to_dict('records')}
        row=docs['completed_index']['new_tasks'][0];task=row['full_task'];identity=task['numerical_identity']
        chosen=pair+[sid for sid in sorted(by) if by[sid]['issuer_id']!=by[pair[0]]['issuer_id']][:2]
        selected={sid:{k:by[sid][k] for k in ('ticker','issuer_id','risk_chain')} for sid in sorted(chosen)}
        tickers=[selected[s]['ticker'] for s in sorted(selected)]
        h=m.digest(dict(dates=[d.date().isoformat() for d in panel['returns'].index],tickers=tickers,returns=panel['returns'][tickers].values.tolist()))
        identity.update(selected=selected,fit_data_sha256=h,holding_count=4)
        task['numerical_task_id']=row['numerical_task_id']=m.digest(identity);row['fit_data_sha256']=h
        with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaisesRegex(ValueError,'One security per issuer'):
            m.reconstruct_rows(docs)

    def test_shard_overlap_and_pending_bool_are_not_valid_locations(self):
        for attack in ('overlap','completed_bool','remaining_bool'):
            docs,panel=owner.fixture();plan=docs['plan']['plan']
            if attack=='overlap':plan['shards'].append(deepcopy(plan['shards'][0]))
            elif attack=='completed_bool':plan['completed_canonical_task_count']=False
            else:plan['shards'][0]['remaining_canonical_task_count']=False
            with self.subTest(attack=attack),patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):
                m.reconstruct_rows(docs)

    def test_original_outer_reference_cannot_be_lost_and_source_conflict_rejected(self):
        docs,panel=owner.fixture()
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        self.assertEqual(rows[102]['original_index_row_reference']['json_pointer'],'/externally_completed_rebound_rows/0')
        self.assertEqual(rows[102]['old_completed_row_reference']['json_pointer'],'/externally_completed_rebound_rows/0/old_completed_row')
        self.assertEqual(rows[102]['prior_rebinding_row'],rows[102]['original_index_row'])
        first=next(iter(m.LOADED))
        with self.assertRaisesRegex(ValueError,'Source conflict'):m.guard({first:'f'*64})
        source=m.SOURCE.read_text()
        self.assertNotIn('import ndx_new_cutoff_v4_completed_task_rebinding_20260925',source)
        self.assertNotIn('from backtest',source)

if __name__=='__main__':unittest.main()
