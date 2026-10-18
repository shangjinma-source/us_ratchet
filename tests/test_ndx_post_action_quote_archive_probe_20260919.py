from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from scripts import ndx_post_action_quote_archive_probe_20260919 as m
from test_ndx_post_action_quote_research import fixture,run


class Tests(unittest.TestCase):
    def test_strict_decimal_boolean_factor_and_row_count_rejected(self):
        body,args=fixture();result=run(body,args);raw=json.dumps(body).encode()
        self.assertEqual(m.strict_decimal_audit(raw,result)['cells_checked'],4)
        for kind in ('factor','count'):
            changed=deepcopy(result)
            if kind=='factor':changed['rows'][0]['factor']=True
            else:changed['row_count']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.strict_decimal_audit(raw,changed)

    def test_real_readonly_preflight_no_quote_core_or_old_verifier(self):
        with (patch.object(m.core,'reconstruct_post_action_quote',side_effect=AssertionError('No real quote run')),
             patch.object(m.capture.gap,'partition',side_effect=AssertionError('No old current-gap verifier'))):
            row,raw,receipt,request,evidence,sources,value=m.prepare('EXC')
        self.assertEqual(row['ticker'],'EXC')
        self.assertEqual(value['archive_resolutions'],[])
        self.assertEqual(value['historical_gap_observations'],[])
        contract=m.archive.load_contract()
        self.assertEqual(len(contract['rows']),111)
        self.assertEqual(sum(r['historical_expected_bytes_preserved'] for r in contract['rows'].values()),85)
        self.assertFalse(set(contract['rows'])&set(sources))
        self.assertFalse(set(contract['rows'])&set(value['live_verified_source_hashes']))

    def test_unknown_root_dependency_and_changed_strict_source_rejected(self):
        contract=m.archive.load_contract();p,row=next(iter(contract['rows'].items()))
        with self.assertRaisesRegex(ValueError,'Unexpected historical'):m.partition({p:row['expected_historical_sha256']})
        with self.assertRaises(ValueError):m.partition({str(m.archive.SOURCE):'0'*64})


if __name__=='__main__':unittest.main()
