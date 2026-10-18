import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_full_pool_saved_evidence_batch_20261002 import fixture, module

class IndependentBatchReview(unittest.TestCase):
    def test_same_bytes_different_paths_preserve_every_review(self):
        inventory,outcomes,extractor=fixture()
        original=copy.deepcopy(inventory)
        for index,item in enumerate(inventory['extraction_queue']):
            path='other.html' if index%2 else 'raw.html'
            item['raw_reference']['path']=path
            item['review_match']['decision']['source_phrase']='phrase '+str(index)
        outcomes['other.html']=copy.deepcopy(outcomes['raw.html'])
        saved=copy.deepcopy(inventory)
        result,documents=module.assemble_batch(inventory,outcomes,extractor)
        self.assertEqual(extractor.call_count,1)
        doc=next(iter(documents.values()))
        self.assertEqual(len(doc['raw_references']),53)
        self.assertEqual(doc['original_review_matches'],[q['review_match'] for q in saved['extraction_queue']])
        self.assertEqual(len(doc['review_envelope']['phrase_queries']),53)
        self.assertEqual(result['inventory_preserved'],saved)
        self.assertEqual(inventory,saved)
        self.assertEqual(result['inventory_preserved']['rows'],original['rows'])
        self.assertEqual(sum(result['status_counts'].values()),53)
        self.assertTrue(all(row[flag] is False for row in result['extraction_rows'] for flag in module.FLAGS))

    def test_mixed_missing_mismatch_success_and_wrong_extractor_hash(self):
        inventory,outcomes,extractor=fixture()
        for index,path in ((0,'missing.html'),(1,'mismatch.html')):
            inventory['extraction_queue'][index]['raw_reference']['path']=path
        outcomes['missing.html']={'status':'MISSING_SOURCE'}
        outcomes['mismatch.html']={'status':'RAW_SHA_MISMATCH','actual_sha256':'f'*64}
        result,documents=module.assemble_batch(inventory,outcomes,extractor)
        self.assertEqual(result['status_counts']['MISSING_SOURCE'],1)
        self.assertEqual(result['status_counts']['RAW_SHA_MISMATCH'],1)
        self.assertEqual(result['status_counts']['EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION'],51)
        self.assertEqual([r['queue_index'] for r in result['extraction_rows']],list(range(53)))
        extractor.return_value={'raw_sha256':'a'*64}
        result,documents=module.assemble_batch(inventory,outcomes,extractor)
        self.assertEqual(result['status_counts']['EXTRACTION_ERROR_NOT_ELIGIBLE'],51)
        self.assertFalse(next(iter(documents.values()))['legal_training_input_admitted'])

    def test_guard_drift_missing_appearance_and_failure_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source'; source.write_bytes(b'original')
            missing=root/'missing'
            hashes={str(source):module.sha(b'original')}
            module.guard(hashes,[str(missing)])
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Source drift'): module.guard(hashes,[str(missing)])
            source.write_bytes(b'original');missing.write_bytes(b'appeared')
            with self.assertRaisesRegex(ValueError,'appeared'): module.guard(hashes,[str(missing)])
            namespace=root/'failed';namespace.mkdir();(namespace/'failure.json').write_text('{}')
            with patch.object(module,'OUTPUT',namespace),patch.object(module.importlib,'import_module') as imported:
                with self.assertRaisesRegex(ValueError,'no retry'):module.run()
                imported.assert_not_called()

if __name__=='__main__':unittest.main()
