import unittest
import pandas as pd
from scripts.ndx_historical_lineage_all_dates import _verify_universe, _merge


class AllDateLineageTests(unittest.TestCase):
    def test_shared_issuer_retained_and_one_invalid_not_dropped(self):
        universe=pd.DataFrame([dict(security_id='s1',issuer_id='i',ticker='A'),dict(security_id='s2',issuer_id='i',ticker='B')])
        def verifier(**kwargs):
            security=next(iter(kwargs['securities']))
            if security=='s2':raise ValueError('expired evidence')
            return dict(source_hashes={},securities=[dict(security_id=security,status='LINKED',historical_artifact_verified=True)])
        result=_verify_universe(universe,dict(selection_date='2024-02-01',universe_track='strict_technology'),{},verifier)
        self.assertEqual(len(result),2)
        self.assertEqual(result[1]['status'],'INPUT_INVALID')
        self.assertEqual(result[1]['current_technology_qualification'],'UNKNOWN')

    def test_duplicate_security_and_source_conflict_rejected(self):
        universe=pd.DataFrame([dict(security_id='s',issuer_id='i',ticker='A')]*2)
        with self.assertRaises(ValueError):_verify_universe(universe,{}, {})
        with self.assertRaises(ValueError):_merge({'a':'1'},{'a':'2'})


if __name__=='__main__':unittest.main()
