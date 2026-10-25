from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
import json
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_monthly_supplement_capture import merge_supplement_packets
import test_strategy_daily_security_domain_v1 as fixture

class SupplementMergeTests(unittest.TestCase):
    def test_complete_account_includes_open_order_and_preserves_monthly_history(self):
        with TemporaryDirectory() as folder:
            f=fixture.DynamicDomainTests();c=f.case(folder);packets=f.packets(c,folder)
            new=deepcopy(packets['B']);receipt=json.loads(new['receipt_bytes'])
            name='full-monthly-B.json';new['files'][name]=new['files'][receipt['normalized_inputs_path']]
            receipt['monthly_history_inputs_path']=name;receipt['source_sha256'][name]=sha256(new['files'][name]).hexdigest()
            new['receipt_bytes']=canonical(receipt);new['trusted_receipt_sha256']=sha256(new['receipt_bytes']).hexdigest()
            before=c.store.path.read_bytes()
            def run(existing,supplements):return merge_supplement_packets(existing=existing,supplements=supplements,
                state=c.state,target=c.target,now=c.clock[0])
            missing=run({}, {'B':new});self.assertEqual(missing['status'],'WAIT_COMPLETE_SECURITY_DOMAIN');self.assertEqual(missing['missing'],['A'])
            result=run({'A':packets['A']},{'B':new})
            self.assertIsNotNone(result.get('receipt'),result)
            self.assertEqual(result['receipt']['full_domain_security_ids'],['A','B'])
            reference=result['receipt']['monthly_history_inputs']['B']
            self.assertEqual(sha256(result['files'][reference['path']]).hexdigest(),reference['sha256'])
            self.assertEqual(c.store.path.read_bytes(),before)
            conflict=deepcopy(new);r=json.loads(conflict['receipt_bytes']);path=r['normalized_inputs_path'];inputs=json.loads(conflict['files'][path])
            inputs['histories']['B']['closes'][-1]['close']='999'
            conflict['files'][path]=canonical(inputs);r['source_sha256'][path]=sha256(conflict['files'][path]).hexdigest()
            conflict['receipt_bytes']=canonical(r);conflict['trusted_receipt_sha256']=sha256(conflict['receipt_bytes']).hexdigest()
            with self.assertRaisesRegex(ValueError,'SUPPLEMENT_PRICE_CONFLICT'):run(packets,{'B':conflict})

if __name__=='__main__':unittest.main()
