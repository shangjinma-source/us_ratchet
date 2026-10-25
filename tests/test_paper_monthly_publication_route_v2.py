from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_account_evidence_provider import REQUIRED_PINS
from data.strategy_paper_monthly_publication_route_v2 import load_published_month
import test_build_real_monthly_release_entry as producer_fixture


class MonthlyPublicationRouteTests(unittest.TestCase):
    def test_actual_producer_to_policy_routed_training_and_failed_source(self):
        with TemporaryDirectory() as folder:
            fixture=producer_fixture.EntryTests();root,args=fixture.setup_package(folder)
            complete=json.loads((root/args['complete_path']).read_bytes());binding=complete['binding']
            def reference(digest):
                matches=[p for p in root.rglob('*.json') if sha256(p.read_bytes()).hexdigest()==digest]
                self.assertEqual(len(matches),1)
                return dict(path=matches[0].relative_to(root).as_posix(),sha256=digest)
            slot=dict(complete_path=args['complete_path'],expected_binding=binding,
                producer_inputs=dict(coordinator=reference(binding['coordinator_sha256']),
                    bootstrap=reference(binding['bootstrap_sha256']),policy=dict(path=binding['policy_path'],sha256=binding['policy_sha256'])),
                runtime_descriptor=dict(path=args['descriptor_path'],sha256=args['descriptor_sha256']))
            raw=canonical(dict(schema='PAPER_MONTHLY_PUBLICATION_ROUTE_V2',authorization='READ_COMPLETED_MARKET_ONLY',
                slots={'2026-12':slot}))
            (root/'paper-policy.json').write_bytes(raw)
            pins={}
            for name in REQUIRED_PINS:
                body=(Path(__file__).resolve().parents[1]/name).read_bytes()
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
                pins[name]=sha256(body).hexdigest()
            request=dict(root=root,policy_reference=dict(path='paper-policy.json',sha256=sha256(raw).hexdigest()),
                runtime_pins=pins,output_root=root/'paper-route',
                clock=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00'))
            loaded=load_published_month(**request)
            self.assertEqual(loaded['target_month'],'2026-12')
            self.assertEqual(loaded['producer_complete_sha256'],args['complete_sha256'])
            self.assertFalse((root/'data/strategy_account').exists())
            repeated=load_published_month(**request)
            self.assertEqual(repeated['registry_reference'],loaded['registry_reference'])
            completion=root/args['complete_path'];original=completion.read_bytes()
            changed=json.loads(original);changed['binding']['bootstrap_sha256']='0'*64
            completion.write_bytes(canonical(changed))
            with self.assertRaisesRegex(ValueError,'COMPLETION_BINDING'):
                load_published_month(**request)
            completion.write_bytes(original)
            policy_raw=(root/'paper-policy.json').read_bytes()
            (root/'paper-policy.json').write_bytes(policy_raw+b' ')
            with self.assertRaises(ValueError):load_published_month(**request)
            (root/'paper-policy.json').write_bytes(policy_raw)
            # A successful-looking completion cannot hide a retained failure marker.
            (root/'real-market/failed.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'FAILED_PRESERVED'):
                load_published_month(**request)
            request['clock']=lambda:datetime.fromisoformat('2027-01-04T15:00:00+00:00')
            with self.assertRaisesRegex(ValueError,'NOT_SCHEDULED'):
                load_published_month(**request)


if __name__=='__main__':unittest.main()
