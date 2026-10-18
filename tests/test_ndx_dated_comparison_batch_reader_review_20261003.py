"""Independent synthetic metadata and partial-result checks; no real readback."""
from copy import deepcopy
import unittest
from scripts import ndx_dated_comparison_batch_independent_readback_20261003 as module
from test_ndx_dated_comparison_batch_independent_readback_20261003 import fixture


def comparison_fixture(missing=False):
    numeric = dict(cutoff='2026-03-20', requested_previous_target_weights=None)
    tid = module.sha(module.enc(numeric))
    ref = lambda name: dict(path=name, sha256='a'*64)
    parents = {k: ref(k) for k in ('inputs', 'account_readback', 'continuous', 'continuous_readback')}
    refs = {k: ref(k) for k in ('comparison', 'publication', 'independent_readback')}
    flags = dict.fromkeys(('fit_performed', 'account_executed', 'point_in_time_verified', 'promotion_allowed', 'formal_comparison_passed', 'winner_selected', 'future_independent_oos', 'untouched_holdout'), False)
    document = dict(schema='SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1', numerical_task_id=tid,
        original_task_preserved=dict(numerical_task_id=tid, numerical_identity=numeric),
        input_references=dict(inputs=parents['inputs'], account_audit=parents['account_readback'],
                              continuous=parents['continuous'], continuous_audit=parents['continuous_readback']),
        original_provenance_and_missing=[{}]*101, preserved_evidence_sidecars={str(i): {} for i in range(7)},
        comparison=dict(schema='DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1',
            candidate_integer_status_preserved=dict(status='NOT_EXECUTED_NONPOSITIVE_TARGET' if missing else 'AVAILABLE'),
            status='PARTIAL_CANDIDATE_INTEGER_UNAVAILABLE' if missing else 'ALL_FOUR_SAVED_TRACKS_DIAGNOSTIC_ONLY',
            tracks=dict(candidate_integer=dict(metrics=None, stored_values_exact=None, original_account_preserved=None))),
        source_hashes={'synthetic': 'b'*64}, **flags)
    publication = dict(schema='DATED_PER_TASK_ECONOMIC_COMPARISON_PUBLICATION_V1',
        status='PUBLISHED_SINGLE_PATH_DIAGNOSTIC_ONLY', comparison_reference=refs['comparison'],
        source_hashes=deepcopy(document['source_hashes']), **flags)
    audit = dict(schema='DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1', status='PASS', numerical_task_id=tid,
        reader_sha256=module.READER_SHA, comparison_reference=refs['comparison'], publication_reference=refs['publication'],
        counts=dict(path_count=5 if missing else 6, observation_count=635 if missing else 762,
                    available_distance_cell_count=4 if missing else 8), **flags)
    return tid, document, publication, audit, refs, parents


class Review(unittest.TestCase):
    def test_complete_partial_and_missing_do_not_fabricate_integer_account(self):
        for missing in (False, True):
            args = comparison_fixture(missing)
            before = deepcopy(args)
            result = module.validate_comparison(*args)
            self.assertEqual(result['integer_account_available'], not missing)
            self.assertTrue(result['pipeline_complete'])
            self.assertEqual(args, before)
            tid, doc, pub, audit, refs, parents = args
            result = module.validate_comparison(tid, doc, None, None, refs, parents, complete=False)
            self.assertFalse(result['pipeline_complete'])
            with self.assertRaises(ValueError):
                module.validate_comparison(tid, doc, None, None, refs, parents)
        args = list(comparison_fixture(True))
        args[1]['comparison']['tracks']['candidate_integer']['metrics'] = {'made_up_cash': 0}
        with self.assertRaises(ValueError):
            module.validate_comparison(*args)

    def test_counts_reader_source_links_and_dated_identity_attacks(self):
        for mutate in (
            lambda a: a[3]['counts'].update(path_count=True),
            lambda a: a[3].update(reader_sha256='f'*64),
            lambda a: a[2]['comparison_reference'].update(sha256='f'*64),
            lambda a: a[1]['input_references'].update(account_audit=dict(path='wrong', sha256='a'*64)),
            lambda a: a[1]['original_task_preserved']['numerical_identity'].update(cutoff='2026-09-21'),
            lambda a: a[1].update(future_independent_oos=0),
            lambda a: a[1]['comparison']['candidate_integer_status_preserved'].update(status='TECHNICAL_MISSING'),
        ):
            args = deepcopy(comparison_fixture())
            # Avoid fixture aliasing external references when mutating the receipt.
            args = tuple(deepcopy(value) for value in args)
            mutate(args)
            with self.assertRaises(ValueError):
                module.validate_comparison(*args)

    def test_context_driver_and_failure_prefix_cannot_change_domain(self):
        for mutate in (
            lambda a,b: b['context'].update(minimum_free_disk_bytes=True),
            lambda a,b: b['context']['source_hashes'].pop(module.ref('driver')['path']),
            lambda a,b: b['context']['input_references'].pop('economic_audit'),
            lambda a,b: b.update(formal_comparison_passed=0),
        ):
            parents, batch = fixture()
            mutate(parents, batch)
            with self.assertRaises(ValueError):
                module.partition(parents['summary'], parents['initial'], batch)
        parents, batch = fixture()
        remaining = [row['numerical_task_id'] for row in batch['new_completed_rows']]
        batch.update(status='STOPPED_WITH_EVIDENCE', new_completed_rows=[], new_completed_count=0,
            unresolved_task_ids=remaining[:1], undispatched_task_ids=remaining[1:],
            failure=dict(ordinal=0, numerical_task_id=remaining[0], task_stage_invoked=True,
                current_stage_invoked=False, stage_may_have_written_evidence=True, retry_allowed=False,
                completed_stage_references={'comparison': dict(path='saved', sha256='a'*64)}, stage='independent_readback'))
        module.partition(parents['summary'], parents['initial'], batch)
        batch['failure']['completed_stage_references'] = {'independent_readback': dict(path='saved', sha256='a'*64)}
        with self.assertRaises(ValueError):
            module.partition(parents['summary'], parents['initial'], batch)


if __name__ == '__main__':
    unittest.main()
