import ast
from copy import deepcopy
from decimal import localcontext,Inexact
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_prospective_observation_independent_readback_20261003 as m
from test_ndx_prospective_observation_independent_readback_20261003 import fixture


class Tests(unittest.TestCase):
    def test_no_writer_or_core_import_or_call_and_hostile_context(self):
        a=fixture();before=deepcopy(a)
        tree=ast.parse(m.SOURCE.read_text())
        modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names]
        self.assertFalse(any(n.startswith(('scripts','backtest')) for n in modules))
        with patch('backtest.ndx_prospective_observation_receipt_research.prepare_observation_payload',side_effect=AssertionError('No self proof')):
            with localcontext() as ctx:
                ctx.prec=2;ctx.traps[Inexact]=True;result=m.inspect(*a)
        self.assertEqual(a,before);self.assertEqual(result['new_observation_count'],1)
        self.assertFalse(result['clock_authenticity_verified']);self.assertFalse(result['final_durable_completion_time_verified'])

    def test_full_original_bytes_row_positions_and_clock_boundaries(self):
        for mutation in (
            lambda a:a[0]['source_row_locations']['QQQ'].__setitem__('original_data_row_index',0),
            lambda a:a[0]['selected_original_rows']['SPY'].__setitem__('Close','999'),
            lambda a:a[0]['full_original_sources_preserved']['SPY']['baseline_sources'].__setitem__('original_csv_bytes_base64',''),
            lambda a:a[1].__setitem__('publication_check_at_utc',a[0]['writer_started_at_utc']),
            lambda a:a[1].__setitem__('month_first_actual_observation',1),
            lambda a:a[0].__setitem__('sequence',66.0),
        ):
            a=fixture();mutation(a)
            with self.assertRaises(ValueError):m.inspect(*a)
        blob=b'Date,Open,High,Low,Close,Volume\n2015-03-30,8,11,9,10,100\n2026-10-02,10,11,9,10,100\n'
        rows,diag=m.parse_csv(blob,'2026-07-01');self.assertEqual(len(rows),2);self.assertEqual(diag[0]['original_data_row_index'],0)
        with self.assertRaises(ValueError):m.parse_csv(blob.replace(b'2026-10-02,10',b'2026-10-02,8'),'2026-07-01')
        with self.assertRaises(ValueError):m.parse_csv(blob.replace(b'2015-03-30',b'not-a-date'),'2026-07-01')

    def test_prior_unknown_failed_observation_keeps_month_slot(self):
        for status in ('UNKNOWN','FAILED'):
            a=fixture();known=a[3]['parent']['projection_inputs']['known_rows']
            self.assertEqual(known[-1]['session'],'2026-10-01')
            known[0].update(kind='MISSED_OBSERVATION',seal_status='NOT_ATTEMPTED')
            known[-1].update(kind='SEALED_PARENT_OBSERVED_SESSION',seal_status=status)
            a[0]['known_typed_rows_preserved']=deepcopy(known)
            a[0].update(first_actual_observed_session_of_month='2026-10-01',month_first_actual_observation=False)
            a[1].update(month_first_actual_observation=False,publication_check_at_utc='2026-10-05T13:30:00+00:00',timing_classification='LATE_OBSERVATION')
            result=m.inspect(*a);self.assertFalse(result['month_first_actual_observation']);self.assertEqual(result['timing_classification'],'LATE_OBSERVATION')
            self.assertFalse(result['candidate_seal_allowed'])

if __name__=='__main__':unittest.main()
