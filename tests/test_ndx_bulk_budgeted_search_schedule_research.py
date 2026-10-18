from copy import deepcopy
from itertools import combinations,product
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import bulk_all_k_plan_20261003 as fixture
from backtest import ndx_bulk_budgeted_search_schedule_research as module


def plan(n=7):
    return fixture.prepare_lazy_plan(groups=[(f'I{i:03}',[f'S{i:03}']+(['ALT'] if i==0 else [])) for i in range(n)],
        panel_reference=dict(path=str(Path('synthetic_panel').resolve()),sha256='a'*64),
        panel_audit_reference=dict(path=str(Path('synthetic_audit').resolve()),sha256='b'*64),
        decision_cutoff='2026-09-21',parameters=fixture.PARAMETERS.copy(),
        fitter_source_hashes={str(Path('synthetic_fitter').resolve()):'c'*64},previous_target_weights=None,shard_size=1000)


def args(n=7):
    saved=plan(n)
    return dict(lazy_plan=saved,seed_hex='d'*64,combinations_per_k={row['k']:min(8,row['combination_count']) for row in saved['cardinalities'] if row['planned_combination_count']},
        max_proposals=4096,existing_completed_reference=dict(path=str(Path('synthetic_completed').resolve()),sha256='e'*64))


class ScheduleTests(unittest.TestCase):
    def test_small_domain_cover_determinism_and_independent_coordinates(self):
        values=args();result=module.plan_budgeted_positions(**values)
        self.assertEqual(result['status'],'PLANNED_NOT_ATTEMPTED')
        self.assertTrue(result['combination_enumeration_performed'])
        self.assertFalse(result['full_domain_enumeration_performed'])
        self.assertEqual(result['enumerated_position_count'],len(result['positions']))
        self.assertEqual(result,module.plan_budgeted_positions(**values))
        index=module.validate_lazy_plan(values['lazy_plan'])
        for k,count in values['combinations_per_k'].items():
            expected=[]
            for issuer_positions in combinations(range(7),k):
                for sids in product(*(index.security_groups[i] for i in issuer_positions)):
                    expected.append(tuple(zip((index.issuer_ids[i] for i in issuer_positions),sids)))
            expected.sort()
            rows=[row for row in result['positions'] if row['k']==k]
            self.assertEqual(len(rows),count)
            self.assertEqual(len({row['rank'] for row in rows}),count)
            self.assertEqual(set().union(*(set(row['prefix_security_ids']) for row in rows)),{sid for group in index.security_groups for sid in group})
            for row in rows:self.assertEqual(row['prefix_security_ids'],[sid for _,sid in expected[row['rank']]])
        changed=deepcopy(values);changed['existing_completed_reference']['sha256']='f'*64
        self.assertEqual(result['positions'],module.plan_budgeted_positions(**changed)['positions'])

    def test_no_eager_or_slice_and_complete_tiny_domain(self):
        values=args(4);values['combinations_per_k']={4:2}
        with (patch.object(module.contracts,'prepare_issuer_shards',side_effect=AssertionError('eager')),
             patch.object(module.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('slice'))):
            result=module.plan_budgeted_positions(**values)
        self.assertEqual({row['rank'] for row in result['positions']},{0,1})
        self.assertEqual(result['unselected_planned_combination_count'],0)

    def test_global_exhaustion_is_not_materializable(self):
        values=args();values['max_proposals']=1;result=module.plan_budgeted_positions(**values)
        self.assertEqual(result['status'],'INCOMPLETE_POINT_SELECTION')
        self.assertFalse(result['materialization_allowed']);self.assertEqual(result['proposal_count'],1)
        self.assertLess(result['selected_position_count'],result['requested_position_count'])

    def test_resigned_plan_mutations_fail_before_unrank(self):
        for mutation in (lambda p:p.update(completed_canonical_task_count=False),
                         lambda p:p['cardinalities'][3].update(first_global_shard_ordinal=1),
                         lambda p:p['context']['weight_specs'].pop(),
                         lambda p:p['fitter_source_hashes'].update({str(Path('new').resolve()):'f'*64}),
                         lambda p:p.update(promotion_allowed=0)):
            values=args();saved=values['lazy_plan'];mutation(saved)
            saved['plan_id']=module.digest(saved['context']);saved.pop('content_sha256');saved['content_sha256']=module.digest(saved)
            with patch.object(module.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('early unrank')):
                with self.assertRaises(ValueError):module.plan_budgeted_positions(**values)

    def test_budget_types_and_insufficient_cover(self):
        for field,value in [('max_proposals',True),('seed_hex','x'*64),('combinations_per_k',{4:True})]:
            values=args();values[field]=value
            with self.assertRaises(ValueError):module.plan_budgeted_positions(**values)
        values=args();values['combinations_per_k'][4]=1
        with self.assertRaises(ValueError):module.plan_budgeted_positions(**values)

    def test_large_synthetic_exact_integer_positions(self):
        # Synthetic IDs only; no actual 77-SID panel/plan or fitter is read.
        values=args(80);values['combinations_per_k']={k:32 for k in values['combinations_per_k']}
        result=module.plan_budgeted_positions(**values)
        self.assertEqual(result['status'],'PLANNED_NOT_ATTEMPTED')
        self.assertTrue(any(row['rank']>2**53 for row in result['positions']))
        self.assertTrue(all(type(row['rank']) is int for row in result['positions']))
        self.assertLessEqual(result['proposal_count'],4096)


if __name__=='__main__':unittest.main()
