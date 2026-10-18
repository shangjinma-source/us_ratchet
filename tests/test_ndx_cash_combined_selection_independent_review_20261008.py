"""Independent saved-ledger ordering and split-journal boundary counterexamples."""
from copy import deepcopy
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import test_ndx_cash_neighbor_combined_selection_20261008 as author

source = author.source
reader = author.reader


def case(tie=False):
    args = author.combined(author.fixture())
    if tie:
        record = args['new_records'][0]
        for post in (record['postcheck'], record['shard_audit']['document']['detail']['task_results'][0]):
            post['original_target_stock_weight_l1']['distance']['numerator'] = 2
    rows = []
    selected = author.new.select_scenario_stream(**args, emit_ledger_row=rows.append)
    envelopes = []
    for row in rows:
        index = row['merged_candidate_index']
        locator = dict(row_index=0, json_pointer_within_selected_row=f'/evaluation/branches/0/evaluated_plans/{index}') if row['origin'] == 'OLD' else dict(task_id=row['identity']['task_id'])
        envelopes.append(dict(selection_ledger_row=row, source_locator=locator))
    raw = b''.join(reader.enc(row) + b'\n' for row in envelopes)
    reference = dict(path='synthetic-ledger', sha256=reader.sha(raw))
    selection = dict(schema='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1', consumption_status='PENDING_FINAL_SOURCE_CLOSURE', requires_final_publication=True, scenario_index=0, selection=selected, ledger_row_count=len(rows), ledger_bytes=len(raw), ledger_reference=reference, **reader.FLAGS)
    entry = dict(scenario_index=0, scenario_id='s', ledger_row_count=len(rows), ledger_reference=reference, status=selected['status'])
    return raw, selection, entry, args['prepared']['contract']


class Tests(unittest.TestCase):
    def test_independent_saved_minimum_and_original_tie_order(self):
        for tie, expected in ((False, 2), (True, 0)):
            raw, selection, entry, contract = case(tie)
            answer = reader.inspect_case(io.BytesIO(raw), selection, entry, contract)
            self.assertEqual(answer['selected_merged_candidate_index'], expected)
            bad = deepcopy(selection)
            # No file integrity trick: an internally canonical saved winner is wrong.
            alternate = 0 if expected == 2 else 2
            bad['selection']['selected'] = reader.loads(raw.splitlines()[alternate])['selection_ledger_row']
            with self.assertRaises(ValueError):
                reader.inspect_case(io.BytesIO(raw), bad, entry, contract)

    def test_resigned_complete_ledger_reordering_and_truncation_rejected(self):
        raw, selection, entry, contract = case()
        lines = raw.splitlines(keepends=True)
        for changed in (b''.join(lines[:2]), b''.join((lines[1], lines[0], lines[2]))):
            selected = deepcopy(selection)
            linked = deepcopy(entry)
            selected['ledger_bytes'] = len(changed)
            selected['ledger_reference']['sha256'] = reader.sha(changed)
            linked['ledger_reference'] = deepcopy(selected['ledger_reference'])
            with self.assertRaises(ValueError):
                reader.inspect_case(io.BytesIO(changed), selected, linked, contract)

    def test_real_split_boundary_rejects_wrong_position_extra_post_and_raw_locator(self):
        original = source.saved_journal
        for attack in ('position', 'extra_post', 'raw_locator'):
            old_reads = 0
            def changed(reference, sources, streamed):
                nonlocal old_reads
                rows = original(reference, sources, streamed)
                if Path(reference['path']).name == 'new' and attack == 'position':
                    rows[0][0]['original_shard_task_position'] = 162
                if Path(reference['path']).name == 'old':
                    old_reads += 1
                    if attack == 'extra_post':
                        extra = deepcopy(rows[-1])
                        extra[0]['stage'] = 'POSTCHECK'
                        rows.append(extra)
                    elif attack == 'raw_locator':
                        # Alter only consumer read, after fixture captured the exact sidecar anchor.
                        if old_reads > 1:
                            rows[-1][1]['byte_start'] += 1
                return rows
            with self.subTest(attack=attack), patch.object(source, 'saved_journal', side_effect=changed):
                with self.assertRaises(ValueError):
                    author.Tests('test_real_partial_sidecar_and_recovery_shapes_preserved').test_real_partial_sidecar_and_recovery_shapes_preserved()


if __name__ == '__main__':
    unittest.main()
