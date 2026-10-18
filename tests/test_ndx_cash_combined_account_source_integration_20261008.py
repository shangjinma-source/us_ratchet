"""Temporary synthetic upstream -> real source dispatch -> independent readback."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_cash_neighbor_combined_selected_paths_20261008 as producer
from scripts import ndx_cash_neighbor_combined_selected_paths_independent_readback_20261008 as reader
from test_ndx_cash_neighbor_selected_path_requests_research import fixture


class PhysicalSourceIntegration(unittest.TestCase):
    def test_full_forty_source_roundtrip_and_reader_never_dispatches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection = root / 'selection'
            selection.mkdir()
            output = root / 'accounts'
            cases = fixture()['cases']
            save = producer.save
            paired = save(root / 'paired.json', dict(schema='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1', rows=[case['old_paired_row'] for case in cases], source_hashes={}))
            paired_publication = save(root / 'paired_publication.json', dict(account_reference=paired, source_hashes={}))
            entries, prepared_rows, contract_sources = [], [], {}
            for index, case in enumerate(cases):
                case['selection']['schema'] = 'CASH_NEIGHBOR_COMBINED_STREAM_SCENARIO_SELECTION_V1'
                folder = selection / f'scenario-{index:02d}'
                folder.mkdir()
                case['selection']['old_selected_path']['reference'] = dict(paired, json_pointer=f'/rows/{index}/paths/candidate')
                contract = save(root / f'contract-{index}.json', case['prepared'])
                contract_sources[contract['path']] = contract['sha256']
                prepared_rows.append(dict(scenario_id=case['selection']['scenario_id'], contract_reference=contract))
                ledger = save(folder / 'ledger.jsonl', {})
                started = save(folder / 'started.json', {})
                selected = save(folder / 'selection.json', dict(schema='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1', scenario_index=index, selection=case['selection'], ledger_reference=ledger, requires_final_publication=True))
                publication = save(folder / 'publication.json', dict(schema='CASH_NEIGHBOR_SELECTION_CASE_RECEIPT_V1', status='PENDING_FINAL_SOURCE_CLOSURE', selection_reference=selected, ledger_reference=ledger, started_reference=started, requires_final_publication=True))
                entries.append(dict(scenario_index=index, scenario_id=case['selection']['scenario_id'], status=case['selection']['status'], selection_reference=selected, publication_reference=publication, ledger_reference=ledger))
            preparation = save(root / 'preparation.json', dict(rows=prepared_rows))
            limits = dict(risk_recomputed=False, account_executed=False, point_in_time_verified=False, promotion_allowed=False)
            common = dict(cases=entries, scenario_count=40, total_candidate_count=304305, **limits)
            index_reference = save(selection / 'index.json', dict(common, schema='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_INDEX_V1', status='COMPLETE_DECLARED_UNION_SELECTION', source_hashes=contract_sources, input_references=dict(paired=paired, paired_publication=paired_publication, preparation=preparation)))
            publication_reference = save(selection / 'publication.json', dict(schema='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_PUBLICATION_V1', status='PUBLISHED_COMPLETE_DECLARED_UNION_SELECTION', index_reference=index_reference, source_hashes=contract_sources, **limits))
            selection_reader = Path(producer.BOUND['selection_reader'][0])
            selection_reader_hash = producer.sha(selection_reader.read_bytes())
            audit = save(root / 'selection_audit.json', dict(common, schema='CASH_NEIGHBOR_COMBINED_SELECTION_INDEPENDENT_READBACK_V1', status='PASS', index_reference=index_reference, publication_reference=publication_reference, reader_sha256=selection_reader_hash, complete_saved_score_order_independently_verified=True))
            inputs = dict(producer.BOUND)
            inputs.update({role: (value['path'], value['sha256']) for role, value in dict(selection=index_reference, selection_publication=publication_reference, selection_audit=audit, paired=paired, paired_publication=paired_publication, preparation=preparation).items()})
            inputs['selection_reader'] = (str(selection_reader), selection_reader_hash)
            with patch.object(producer, 'BOUND', inputs), patch.object(producer, 'SEL', selection), patch.object(producer, 'OUTPUT', output):
                result = producer.run(execute=True)
            result_document = json.loads(Path(result['path']).read_bytes())
            self.assertIsNone(result_document['failure'])
            self.assertEqual(len(result_document['completed_rows']), 40)
            publication_path = output / 'publication.json'
            reader_bound = dict(result=(result['path'], result['sha256']), publication=(str(publication_path), producer.sha(publication_path.read_bytes())), producer=(str(producer.SOURCE), producer.LOADED))
            with patch.object(reader, 'BOUND', reader_bound), patch.object(reader, 'INPUT_BOUND', inputs), patch.object(reader, 'SEL', selection), patch.object(reader, 'PARENT', output), patch.object(reader, 'OUTPUT', root / 'readback'), patch.object(producer, 'run', side_effect=AssertionError('Reader must not dispatch')), patch.object(producer, 'execute_requests', side_effect=AssertionError('Reader must not execute')):
                audit_reference = reader.readback(execute=True)
            audit_document = json.loads(Path(audit_reference['path']).read_bytes())
            self.assertEqual(audit_document['status'], 'PASS_SAVED_PATH_ARITHMETIC')
            self.assertEqual(len(audit_document['cases']), 40)
            self.assertTrue(audit_document['paired_bytes_verified_once_at_eof'])
            self.assertFalse(audit_document['account_core_called'])


if __name__ == '__main__':
    unittest.main()
