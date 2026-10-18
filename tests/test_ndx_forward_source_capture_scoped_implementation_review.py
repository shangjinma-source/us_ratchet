import base64
import csv
from decimal import Inexact, localcontext
import hashlib
import io
import unittest
from unittest.mock import patch
from backtest import ndx_forward_source_capture_scoped_research as module
from test_ndx_forward_source_capture_scoped_research import args


class ScopedIndependentTests(unittest.TestCase):
    def test_all_original_rows_and_bytes_accounted_derived_only_consumed(self):
        value=args()
        actual=module.capture.plan_forward_source_capture
        with patch.object(module.capture,'plan_forward_source_capture',wraps=actual) as call:
            result=module.plan_scoped_forward_source_capture(**value)
        self.assertEqual(call.call_count,1)
        for role,argument in [('source','source_csv_bytes'),('baseline','baseline_csv_bytes')]:
            for ticker in ('QQQ','SPY'):
                evidence=result['csv_scope_evidence'][role][ticker]
                raw=base64.b64decode(evidence['original_csv_bytes_base64'])
                self.assertEqual(raw,value[argument][ticker])
                original=list(csv.DictReader(io.StringIO(raw.decode())))
                self.assertEqual([r['raw_csv_row'] for r in evidence['original_rows']],original)
                self.assertEqual([r['original_data_row_index'] for r in evidence['original_rows']],list(range(len(original))))
                self.assertEqual(sorted(evidence['included_original_row_indexes']+evidence['excluded_original_row_indexes']),list(range(len(original))))
                scoped=evidence['scoped_csv_utf8'].encode()
                self.assertEqual(call.call_args.kwargs[argument][ticker],scoped)
                self.assertEqual(hashlib.sha256(scoped).hexdigest(),evidence['scoped_sha256'])
                self.assertNotEqual(scoped,raw)
                self.assertEqual(evidence['excluded_before_scope_ohlc_diagnostics'][0]['raw_csv_row'],original[0])

    def test_old_bounds_diagnostic_but_required_bad_and_old_nonfinite_rejected(self):
        result=module.plan_scoped_forward_source_capture(**args())
        self.assertFalse(result['out_of_scope_ohlc_anomalies_repaired'])
        for replacement in (b'2026-09-24,10,9,8,10,100',b'2026-09-24,10,12,11,10,100'):
            value=args(); value['baseline_csv_bytes']['SPY']=value['baseline_csv_bytes']['SPY'].replace(b'2026-09-24,10,12,8,10,100',replacement)
            with self.assertRaises(ValueError): module.plan_scoped_forward_source_capture(**value)
        value=args(); value['source_csv_bytes']['QQQ']=value['source_csv_bytes']['QQQ'].replace(b'205.74',b'Infinity')
        with self.assertRaises(ValueError): module.plan_scoped_forward_source_capture(**value)

    def test_hostile_decimal_context_and_no_price_based_scope(self):
        value=args(); value['source_csv_bytes']['QQQ']=value['source_csv_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10.00000000000000001,12,8,10,100')
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            result=module.plan_scoped_forward_source_capture(**value)
        self.assertEqual(result['scope_start'],value['frontier']['known_accounted_rows'][0]['session'])
        self.assertFalse(result['scope_chosen_from_prices'])
        self.assertFalse(result['source_bytes_authenticated_by_this_module'])
        self.assertEqual(result['csv_scope_evidence']['source']['QQQ']['included_original_row_indexes'],[1,2])
        self.assertEqual(result['capture_plan']['revisions'][0]['current_evidence']['normalized_ohlcv']['Open'],'10.00000000000000001')


if __name__=='__main__': unittest.main()
