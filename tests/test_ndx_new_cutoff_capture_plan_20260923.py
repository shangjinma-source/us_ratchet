import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_capture_plan_20260923 as m


class CapturePlanTests(unittest.TestCase):
    def test_actual_complete_plan_no_http(self):
        v=m.build()
        self.assertEqual(len(v['queue']),104)
        self.assertEqual(len({r['ticker'] for r in v['queue']}),104)
        self.assertEqual(sum(r['original_incumbent_channel'] for r in v['queue']),8)
        self.assertEqual(sum(r['prior_receipt'] is not None for r in v['queue']),102)
        self.assertTrue(all(v[k] is False for k in m.FALSE))
        self.assertEqual([r['ticker'] for r in v['queue'] if not r['prior_url_inventory_complete']],['QQQ','SPY'])
        self.assertEqual(v['benchmark_nav']['network_budget'],0)

    def test_utc_midnight_gate_not_regular_close_assumption(self):
        for instant in ['2026-09-23T03:59:59+00:00','2026-09-24T04:00:00+00:00','2026-09-23T12:00:00']:
            with self.assertRaises(ValueError):m.validate_start(datetime.fromisoformat(instant))
        m.validate_start(datetime(2026,9,23,4,tzinfo=timezone.utc))

    def test_ambiguous_prior_query_rejected(self):
        receipt=dict(ticker='TSM',attempt_count=1,request_url='https://query1.finance.yahoo.com/v8/finance/chart/TSM?period1=1640995200&period2=1&interval=1d&events=div,splits')
        self.assertEqual(m.prior_url(receipt,'TSM'),1)
        for suffix in ['&period2=','&events=div,splits','&unknown=1']:
            with self.assertRaises(ValueError):m.prior_url(dict(receipt,request_url=receipt['request_url']+suffix),'TSM')
        with self.assertRaises(ValueError):m.prior_url(dict(receipt,attempt_count=True),'TSM')

    def test_publisher_cannot_upgrade_to_execution_ready(self):
        value=dict(executable_runner_verified=False,source_hashes={})
        with patch.object(m,'build',return_value=value):
            with self.assertRaises(ValueError):m.publish_verified('never-created.json',dict(value,executable_runner_verified=True))


if __name__=='__main__':unittest.main()
