from copy import deepcopy
import json
import unittest
from scripts import ndx_latest_tsm_readiness_addon_20260919 as m


class Tests(unittest.TestCase):
    def inputs(self):
        return json.loads(m.PARENT.read_bytes()),json.loads(m.QUOTE.read_bytes())

    def test_real_coverage_only_preserves_other_seven_and_original(self):
        parent,quote=self.inputs();unchanged=deepcopy(parent);result=m.summarize(parent,quote)
        self.assertEqual(parent,unchanged)
        self.assertEqual(result['newly_covered_old_fit_missing_dates'],['2026-09-11','2026-09-14','2026-09-15','2026-09-16','2026-09-17'])
        self.assertTrue(result['original8_all_fit_price_dates_covered'])
        self.assertEqual(result['new_tsm_coverage']['fit_return_pairs_with_both_prices'],126)
        for before,after in zip(parent['dual_benchmark_readiness']['original8']['securities'],result['updated_original8_securities']):
            if before['ticker']!='TSM':self.assertEqual(before,after)
            else:
                for k in before:
                    if k not in ('coverage','price_source_status'):self.assertEqual(before[k],after[k])
        self.assertFalse(result['legal_comparison_ready']);self.assertFalse(result['returns_generated'])

    def test_cutoff_duplicate_identity_upgrade_rejected(self):
        for mode in ('cutoff','duplicate','upgrade','count_bool'):
            parent,quote=self.inputs()
            if mode=='cutoff':quote['cutoff']='2026-09-18'
            if mode=='duplicate':quote['calendar'].append(quote['calendar'][-1])
            if mode=='upgrade':quote['price_identity_verified']=True
            if mode=='count_bool':quote['reconstruction']['row_count']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.summarize(parent,quote)

    def test_missing_internal_price_blocks_adjacent_pairs(self):
        parent,quote=self.inputs();day=parent['observed_reference_calendar'][-3]
        quote['calendar'].remove(day);quote['reconstruction']['rows']=[r for r in quote['reconstruction']['rows'] if r['session']!=day]
        quote['reconstruction']['row_count']-=1
        result=m.summarize(parent,quote)
        self.assertEqual(result['new_tsm_coverage']['fit_return_pairs_with_both_prices'],124)
        self.assertFalse(result['original8_all_fit_price_dates_covered'])


if __name__=='__main__':unittest.main()
