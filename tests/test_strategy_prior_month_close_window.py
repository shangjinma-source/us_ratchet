from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_security_domain_v1 import aggregate_security_packets
from data.strategy_monthly_supplement_capture_v2 import capture_supplement,review_supplement_packets,prepare_supplement_request
from data.strategy_daily_first_window_v6 import SOURCES,review_first_window
import test_strategy_daily_first_window_v3 as fixture

class PriorMonthCloseWindowTests(unittest.TestCase):
    def test_current_window_retains_identity_baseline_and_explicit_epoch(self):
        with TemporaryDirectory() as folder:
            c,config,captured=fixture.FirstWindowTests().case(folder)
            root=Path(folder);pins=[]
            for name in SOURCES:
                body=(fixture.ROOT/name).read_bytes();p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
                pins.append(dict(path=name,sha256=sha256(body).hexdigest()))
            config.update(schema='SERVER_FIRST_DAILY_WINDOW_V6',source_pins=pins,monthly_decision_date='2026-10-30')
            calendar=json.loads((root/'calendar.json').read_bytes());window=calendar['sessions'][-21:-1]
            receipt=json.loads(captured['daily.receipt.json']);receipt['requested_from']=(datetime.fromisoformat(window[0]['open'])-timedelta(days=1)).isoformat()
            captured['daily.receipt.json']=canonical(receipt);raw=canonical(config)
            result=review_first_window(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
                capture_files=captured,state=c.state,target=c.target,clock=lambda:c.clock[0])
            self.assertIsNotNone(result['receipt'],result)
            inputs=json.loads(result['files'][result['receipt']['normalized_inputs_path']])
            self.assertEqual(inputs['base_target']['monthly_decision_date'],'2026-10-30')
            self.assertFalse(result['policy_approved'])
            captured_at=c.clock[0]-timedelta(seconds=10)
            preparation=dict(root=root,state=c.state,target=c.target,identity_reference=config['identity'],
                calendar_reference=config['calendar'],unit_source_paths=config['unit_source_paths'],source_pins=pins,
                security_ids=['B'],decision_date='2026-10-30')
            prepared=prepare_supplement_request(**preparation,now=captured_at)
            self.assertEqual(prepared['status'],'SUPPLEMENT_REQUEST_PREPARED')
            later=prepare_supplement_request(**preparation,now=c.clock[0])
            self.assertEqual(prepared['request'],later['request'])
            missing=prepare_supplement_request(**dict(preparation,security_ids=['A']),now=c.clock[0])
            self.assertEqual(missing['status'],'WAIT_UNIT_BASELINE')
            closed=prepare_supplement_request(**preparation,now=datetime.fromisoformat(calendar['sessions'][-1]['close']))
            self.assertEqual(closed['status'],'WAIT_SUPPLEMENT_SESSION')
            binding=prepared['binding'];request=prepared['request']
            capture=capture_supplement(directory=root/'supplement',request=request,binding=binding,read_binding=lambda:binding,
                execute=True,clock=lambda:captured_at,fetch_daily=lambda *args:dict(status=200,body=captured['daily.response.bin']),
                fetch_official=lambda:dict(status=200,body=captured['official.response.bin']))
            native=review_supplement_packets(root=root,capture=capture,request=request,binding=binding,state=c.state,target=c.target,
                configurations=prepared['configurations'],clock=lambda:c.clock[0])
            packet=native['packets']['B'];receipt=json.loads(packet['receipt_bytes'])
            self.assertEqual(sha256(packet['receipt_bytes']).hexdigest(),packet['trusted_receipt_sha256'])
            self.assertIn(receipt['monthly_history_inputs_path'],packet['files'])
            self.assertTrue(any(name.startswith('supplement-original/') for name in packet['files']))
            for name,hash_value in receipt['source_sha256'].items():self.assertEqual(sha256(packet['files'][name]).hexdigest(),hash_value)
            self.assertFalse(native['policy_approved'])
            # Fixture also has an open order in another security: a new SID
            # packet alone must not bypass the complete-account-domain check.
            with self.assertRaisesRegex(ValueError,'AGGREGATE_REQUIRED_DOMAIN_CHANGED'):
                aggregate_security_packets(domain=dict(account_id=c.state['account_id'],account_revision=c.state['revision'],
                    target_id=c.target['target_id'],securities={'B':{}}),packets=native['packets'],state=c.state,target=c.target,now=c.clock[0].isoformat())

if __name__=='__main__':unittest.main()
