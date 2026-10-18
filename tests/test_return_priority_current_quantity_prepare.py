import unittest
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from scripts.return_priority_current_quantity_prepare import build


def fixture():
    end = date(2026,10,13)
    days = [(end-timedelta(days=252-i)).isoformat() for i in range(253)]
    panel = dict(calendar=days,stocks=[dict(ticker=f'T{i}',values=[[None,None,None,str(100+j),None] for j in range(253)]) for i in range(101)])
    accepted = [dict(ticker=f'T{i}',security_id=f's{i}',issuer_id='shared' if i<2 else f'i{i}') for i in range(101)]
    return panel,accepted


class CurrentQuantityPrepareTests(unittest.TestCase):
    def test_cli_requires_and_verifies_approval_evidence(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='quantity_prepare_synthetic_',dir=root/'tmp') as directory:
            folder=Path(directory);panel,accepted=fixture()
            panel_path=folder/'panel.json';panel_path.write_text(json.dumps(panel),encoding='utf8')
            evidence=folder/'identity.txt';evidence.write_text('synthetic identity',encoding='utf8')
            digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            approval=dict(status='ROOT_REVIEWED_EXPLICIT_DOMAIN',decision_date='2026-10-13',
                panel_sha256=digest(panel_path),accepted_metadata=accepted,excluded_reasons={})
            approval_path=folder/'acceptance.json';output=folder/'output.json'
            def invoke():
                approval_path.write_text(json.dumps(approval),encoding='utf8')
                return subprocess.run([sys.executable,str(root/'scripts/return_priority_current_quantity_prepare.py'),
                    '--panel',str(panel_path),'--panel-sha256',digest(panel_path),
                    '--acceptance',str(approval_path),'--acceptance-sha256',digest(approval_path),
                    '--output',str(output)],capture_output=True,text=True)
            self.assertNotEqual(invoke().returncode,0)
            self.assertFalse(output.exists())
            approval['source_hashes']={str(evidence.relative_to(root)):'0'*64}
            self.assertNotEqual(invoke().returncode,0)
            self.assertFalse(output.exists())
            approval['source_hashes']={str(evidence.relative_to(root)):digest(evidence)}
            result=invoke();self.assertEqual(result.returncode,0,result.stderr)
            prepared=json.loads(output.read_text())
            self.assertEqual(prepared['source_hashes'][str(evidence.resolve())],digest(evidence))

    def test_full_domain_exact_scenarios_shared_issuer_no_extra_gates(self):
        p,a=fixture();r=build(p,a,{})
        self.assertEqual(r['accepted_count'],101)
        self.assertEqual(len(r['search_arguments']['prices']),101)
        self.assertEqual(r['search_arguments']['metadata']['s0']['issuer_id'],r['search_arguments']['metadata']['s1']['issuer_id'])
        self.assertEqual(Fraction(r['search_arguments']['training_scenarios'][0]['s0']),Fraction(121,100))
        self.assertEqual(r['scenario_end_dates'][-1],'2026-10-13')

    def test_missing_close_blocks_never_silently_shrinks(self):
        p,a=fixture();p['stocks'][0]['values'][10][3]=None
        r=build(p,a,{})
        self.assertIsNone(r['search_arguments'])
        self.assertEqual(r['accepted_count'],101)
        self.assertEqual(r['coverage'][0]['missing_close_dates'],[p['calendar'][10]])

    def test_explicit_exclusion_retains_full_coverage(self):
        p,a=fixture();r=build(p,a[1:],{'T0':['ROOT_IDENTITY_UNRESOLVED']})
        self.assertEqual(len(r['coverage']),101)
        self.assertEqual(len(r['search_arguments']['prices']),100)
        with self.assertRaises(ValueError):build(p,a[1:],{})

    def test_dates_duplicate_sid_and_identity(self):
        p,a=fixture();p['calendar'][-1]='2026-10-14'
        with self.assertRaises(ValueError):build(p,a,{})
        p,a=fixture();a[1]['security_id']=a[0]['security_id']
        with self.assertRaises(ValueError):build(p,a,{})
        p,a=fixture();a[0].pop('issuer_id');r=build(p,a,{})
        self.assertIsNone(r['search_arguments'])
        self.assertIn('ACCEPTED_IDENTITY_INSUFFICIENT',r['coverage'][0]['preparation_blockers'])


if __name__=='__main__':unittest.main()
