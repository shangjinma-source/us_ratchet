from copy import deepcopy
import unittest
from backtest.ndx_forward_source_capture_scoped_research import plan_scoped_forward_source_capture
from scripts import ndx_forward_source_capture_scoped_20261002 as module
from test_ndx_forward_source_capture_scoped_research import args


class ScopedWrapperTests(unittest.TestCase):
    def validate(self,result,a):
        raw={'baseline_'+ticker:value for ticker,value in a['baseline_csv_bytes'].items()}
        raw['tzif']=a['tzif_bytes']
        module.validate_result(result,a['frontier'],a['source_csv_bytes'],raw,a['capture_started_at_utc'],a['observed_at_utc'])

    def test_exact_original_derived_and_clock_linkage(self):
        a=args(); result=plan_scoped_forward_source_capture(**a); self.validate(result,a)
        self.assertFalse(result['frozen_capture_consumed_full_original_csv'])

    def test_changed_derivation_bytes_or_permission_rejected(self):
        a=args(); result=plan_scoped_forward_source_capture(**a)
        for kind in ('derived','original','permission','dependency'):
            value=deepcopy(result)
            if kind=='derived': value['csv_scope_evidence']['source']['QQQ']['scoped_csv_utf8']+='\n'
            elif kind=='original': value['csv_scope_evidence']['source']['QQQ']['original_csv_bytes_base64']='eA=='
            elif kind=='permission': value['scope_chosen_from_prices']=0
            else: value['frozen_capture_source_sha256']='0'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError): self.validate(value,a)


if __name__=='__main__': unittest.main()
