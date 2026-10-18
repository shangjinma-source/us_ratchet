import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from scripts import ndx_full_pool_saved_evidence_batch_20261002 as module


def fixture():
    raw=b'<html>saved source</html>'; digest=module.sha(raw)
    rows=[{'ticker':'T'+str(index),'original_evidence':{'unchanged':index}} for index in range(101)]
    queue=[]
    for index in range(53):
        ref={'path':'raw.html','sha256':digest}
        decision={'raw_sha256':digest,'source_phrase':'saved source','risk_chain':'late saved risk'}
        queue.append({'ticker':rows[index]['ticker'],'inventory_row_index':index,'raw_reference':ref,
            'review_match':{'decision':decision,'raw_reference':ref,'reference':{'path':'review.yaml','json_pointer':'/decisions/'+str(index)}}})
    inventory={'schema':'FULL_POOL_SAVED_EVIDENCE_INVENTORY_V1','rows':rows,'extraction_queue':queue,
               'historical_denominators':[{'original':index} for index in range(15)],**module.FLAGS}
    outcomes={'raw.html':{'status':'HASH_MATCHED','raw_bytes':raw}}
    extractor=Mock(return_value={'raw_sha256':digest,'facts':[]})
    return inventory,outcomes,extractor


class BatchTests(unittest.TestCase):
    def test_complete_denominators_and_unique_document_once(self):
        inventory,outcomes,extractor=fixture(); original=copy.deepcopy(inventory)
        batch,documents=module.assemble_batch(inventory,outcomes,extractor)
        self.assertEqual(extractor.call_count,1);self.assertEqual(len(documents),1)
        self.assertEqual(batch['inventory_preserved'],original);self.assertEqual(inventory,original)
        self.assertEqual(len(batch['extraction_rows']),53)
        envelope=extractor.call_args.args[2]
        self.assertEqual(len(envelope['original_review_decisions']),53)
        self.assertEqual(envelope['phrase_queries'],['saved source'])
        self.assertFalse(batch['legal_training_input_admitted'])

    def test_missing_mismatch_and_exception_never_eligible(self):
        for outcome in ({'status':'MISSING_SOURCE'},{'status':'RAW_SHA_MISMATCH','actual_sha256':'0'*64}):
            inventory,_,extractor=fixture()
            result,documents=module.assemble_batch(inventory,{'raw.html':outcome},extractor)
            extractor.assert_not_called();self.assertEqual(documents,{})
            self.assertEqual(result['status_counts'][outcome['status']],53)
        inventory,outcomes,extractor=fixture();extractor.side_effect=ValueError('broken source')
        result,documents=module.assemble_batch(inventory,outcomes,extractor)
        self.assertEqual(result['status_counts']['EXTRACTION_ERROR_NOT_ELIGIBLE'],53)
        self.assertEqual(next(iter(documents.values()))['error'],'broken source')

    def test_source_and_row_binding_attacks(self):
        for mutate in (lambda i,o:i['extraction_queue'][0].update(inventory_row_index=True),
                       lambda i,o:i['extraction_queue'][0].update(ticker='WRONG'),
                       lambda i,o:o['raw.html'].update(raw_bytes=b'changed'),
                       lambda i,o:i['historical_denominators'].pop()):
            inventory,outcomes,extractor=fixture();mutate(inventory,outcomes)
            with self.assertRaises(ValueError): module.assemble_batch(inventory,outcomes,extractor)
            extractor.assert_not_called()

    def test_namespace_pending_and_durable_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination=Path(temporary)
            with patch.object(module,'OUTPUT',destination),patch.object(module.importlib,'import_module') as load:
                with self.assertRaisesRegex(ValueError,'exists'): module.run()
                load.assert_not_called()
            ref=module.write_new(destination/'test.json',{'saved':True})
            self.assertEqual(module.sha(Path(ref['path']).read_bytes()),ref['sha256'])
            with self.assertRaises(FileExistsError): module.write_new(destination/'test.json',{'saved':False})


if __name__=='__main__': unittest.main()
