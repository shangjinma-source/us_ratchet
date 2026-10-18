from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from scripts import ndx_saved_conditional_evidence_links_20261002 as module


def fixture():
    references = {role: {'path': role, 'sha256': 'a' * 64} for role in module.PINS}
    rows = [{'ticker': f'T{i}', 'already_wired_conditional_coordinate': i < 25,
             'original_wiring_row': {'coordinate': {'saved': i} if i < 25 else None}, 'all_parent_evidence': [i]}
            for i in range(101)]
    queue, choices, extractions, documents, document_references = [], [], [], {}, {}
    for i in range(53):
        index = i + 25
        ticker = rows[index]['ticker']
        digest = module.sha(ticker.encode())
        reference = {'path': 'document/' + digest, 'sha256': 'b' * 64}
        review_reference = {'path': 'review', 'sha256': 'c' * 64, 'json_pointer': '/decisions/' + str(i)}
        review = {'selection_date': '2026-07-13', 'evidence_available_date': '2026-02-01', 'effective_from': '2026-02-01'}
        item = {'ticker': ticker, 'inventory_row_index': index, 'raw_reference': {'path': 'raw/' + ticker, 'sha256': digest},
                'review_match': {'decision': review, 'reference': review_reference}}
        queue.append(item)
        choices.append({'ticker': ticker, 'inventory_row_index': index, 'raw_sha256': digest,
                        'document_reference': reference, 'selected_group_indexes': [0], 'selected_title_fact_index': 1,
                        'selected_group_pointer': '/extraction/same_context_security_groups/0',
                        'selected_title_fact_pointer': '/extraction/dei_facts/1',
                        'supporting_evidence': {'review_reference': review_reference, **review,
                            'early_window_review_availability_verified': False, 'local_first_available_at': None,
                            'review_selection_postdates_window_start': True}, **module.FLAGS})
        extractions.append({'original_queue_item': deepcopy(item), 'document_sha256': digest,
                            'status': 'EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION'})
        documents[digest] = {'original': ticker}
        document_references[digest] = reference
    inventory = {'rows': rows, 'extraction_queue': queue, 'historical_denominators': [{'old_date': i} for i in range(15)],
                 'summary': {'original_summary': True}}
    batch = {'schema': 'FULL_POOL_SAVED_EVIDENCE_BATCH_V1', 'inventory_preserved': inventory,
             'document_references': document_references, 'extraction_rows': extractions, **module.FLAGS}
    selection = {'schema': 'SAVED_SEC_CONDITIONAL_SELECTION_CONTRACT_V1', 'assumed_window': deepcopy(module.WINDOW),
                 'batch_reference': references['batch'], 'research_only': True, 'row_count': 53, 'rows': choices, **module.FLAGS}
    linker = Mock(return_value={'schema': 'mock', **module.FLAGS})
    return batch, selection, documents, references, linker


class WrapperTests(unittest.TestCase):
    def test_full_denominators_and_saved_coordinates_not_rewritten(self):
        args = fixture()
        parent = deepcopy(args[0])
        result = module.assemble(*args)
        self.assertEqual(args[4].call_count, 53)
        self.assertEqual(args[0], parent)
        self.assertEqual([row['original_inventory_row'] for row in result['rows']], parent['inventory_preserved']['rows'])
        self.assertEqual(result['historical_denominators'], parent['inventory_preserved']['historical_denominators'])
        self.assertEqual(result['summary']['preserved_existing_coordinate_count'], 25)
        self.assertEqual(result['summary']['unlinked_source_lead_count'], 23)
        self.assertIsNone(result['summary']['verified_pit_eligible_count'])
        self.assertEqual(result['links'][0]['selection_contract']['reviewed_contract_reference']['json_pointer'], '/rows/0')

    def test_invalid_contract_and_source_mapping_rejected_before_linker(self):
        for mutation in (
            lambda b, s: s['rows'][0].update(inventory_row_index=True),
            lambda b, s: s['rows'][0].update(selected_group_indexes=[False]),
            lambda b, s: s['rows'][0].update(selected_title_fact_pointer='/extraction/dei_facts/999'),
            lambda b, s: s['rows'][0]['supporting_evidence'].update(selection_date='2026-01-01'),
            lambda b, s: s.update(promotion_allowed=True),
            lambda b, s: b['inventory_preserved']['historical_denominators'].pop(),
        ):
            args = fixture()
            mutation(args[0], args[1])
            with self.assertRaises(ValueError):
                module.assemble(*args)
            args[4].assert_not_called()

    def test_linker_authority_upgrade_rejected(self):
        args = fixture()
        args[4].return_value['provider_binding_verified'] = True
        with self.assertRaisesRegex(ValueError, 'authority'):
            module.assemble(*args)

    def test_immutable_namespace_and_durable_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(module, 'OUTPUT', path), patch.object(module.importlib, 'import_module') as load:
                with self.assertRaisesRegex(ValueError, 'exists'):
                    module.run()
                load.assert_not_called()
            reference = module.write_new(path / 'test.json', {'saved': True})
            self.assertEqual(module.sha(Path(reference['path']).read_bytes()), reference['sha256'])
            with self.assertRaises(FileExistsError):
                module.write_new(path / 'test.json', {'saved': False})


if __name__ == '__main__':
    unittest.main()
