from copy import deepcopy
import unittest
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.build_historical_sec_event_inventory_v1 import merge_facts, build
from scripts.extract_sec_quarter_events_v2 import extract


class InventoryTests(unittest.TestCase):
    def fixture(self):
        rows=[dict(accn='a',form='10-Q',start='2024-02-04',end='2024-05-04',val=120),
              dict(accn='a',form='10-Q',start='2023-01-29',end='2023-04-29',val=100),
              dict(accn='a',form='10-Q',start='2023-11-01',end='2024-05-04',val=500)]
        f=dict(cik=1,facts={'us-gaap':{'Revenues':{'units':{'USD':rows}}}})
        s=dict(cik=1,filings={'recent':dict(accessionNumber=['a'],form=['10-Q'],reportDate=['2024-05-04'],acceptanceDateTime=['2024-05-10T20:00:00Z'])})
        return f,s,rows

    def run_case(self,f,s):return extract(f,[s],concepts=['Revenues'])

    def test_fiscal_week_shift_and_ytd_ignored(self):
        f,s,rows=self.fixture();result=self.run_case(f,s)
        self.assertEqual(result['events'][0]['yoy_fraction'],'1/5')
        self.assertEqual(result['events'][0]['current_period']['start'],'2024-02-04')

    def test_53_week_quarter_extra_week_but_not_more(self):
        f,s,rows=self.fixture();rows[0]['start']='2024-01-28'
        self.assertEqual(len(self.run_case(f,s)['events']),1)
        rows[0]['start']='2024-01-27'
        self.assertFalse(self.run_case(f,s)['events'])

    def test_ambiguous_current_and_prior_fail(self):
        for field,value in [('current','2024-02-05'),('previous','2023-01-30')]:
            f,s,rows=self.fixture();rows.append(dict(rows[0 if field=='current' else 1],start=value))
            with self.subTest(field=field):self.assertFalse(self.run_case(f,s)['events'])

    def test_multi_cache_conflict_is_not_latest_wins(self):
        f,s,rows=self.fixture();other=deepcopy(f);other['facts']['us-gaap']['Revenues']['units']['USD'][0]['val']=999
        result=self.run_case(merge_facts('1',[f,other]),s)
        self.assertFalse(result['events']);self.assertEqual(result['rejected'][0]['reason'],'CONFLICTING_SAME_PERIOD_VALUES')
        self.assertEqual(len(self.run_case(merge_facts('1',[f,f]),s)['events']),1)

    def test_archive_requires_official_receipt_and_parent_listing(self):
        f,s,rows=self.fixture();archive=s['filings']['recent']
        with self.assertRaisesRegex(ValueError,'ARCHIVE_BINDING_REQUIRED'):
            extract(f,[archive],concepts=['Revenues'])
        parent=dict(cik=1,filings=dict(recent={},files=[dict(name='CIK0000000001-submissions-001.json')]))
        raw=json.dumps(archive,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        binding=dict(url='https://data.sec.gov/submissions/CIK0000000001-submissions-001.json',
                     document_sha256=sha256(raw).hexdigest(),source_sha256=sha256(raw).hexdigest())
        self.assertEqual(len(extract(f,[parent,archive],concepts=['Revenues'],archive_bindings=[binding])['events']),1)
        with self.assertRaisesRegex(ValueError,'ARCHIVE_BINDING_REQUIRED'):
            extract(f,[parent,archive],concepts=['Revenues'],archive_bindings=[dict(binding,source_sha256='bad')])

    def test_ytd_only_and_far_prior_not_derived(self):
        f,s,rows=self.fixture();rows.pop(0)
        self.assertFalse(self.run_case(f,s)['events'])

    def test_supplement_rejects_unbound_archive_and_changed_hash(self):
        coverage=dict(windows=[dict(window='test', start='2021-01-01',end='2023-12-31',rows=[
            dict(security_id='research:test',in_price_domain=True,cik='0000000001')])])
        with TemporaryDirectory() as directory:
            root=Path(directory);raw=json.dumps(dict(accessionNumber=[])).encode();(root/'archive.json').write_bytes(raw)
            ref=dict(path='archive.json',sha256=sha256(raw).hexdigest(),status=200,
                     url='https://data.sec.gov/submissions/CIK0000000001-submissions-001.json')
            with self.assertRaisesRegex(ValueError,'ARCHIVE_PARENT_BINDING'):
                build(coverage,root=root,supplements=[ref])
            with self.assertRaisesRegex(ValueError,'INPUT_BYTES_CHANGED'):
                build(coverage,root=root,supplements=[dict(ref,sha256='0'*64)])
        f,s,rows=self.fixture();rows[1]['start']='2022-01-29';rows[1]['end']='2022-04-29'
        self.assertFalse(self.run_case(f,s)['events'])


if __name__=='__main__':unittest.main()
