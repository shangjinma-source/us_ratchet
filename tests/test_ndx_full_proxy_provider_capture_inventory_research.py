import unittest
from scripts import ndx_full_proxy_provider_capture_inventory_research as inventory


class FullProxyCaptureInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=inventory.build()

    def test_all_fifteen_dates_include_middle_only_splk(self):
        report=self.report
        self.assertEqual((report['date_count'],report['proxy_rows'],report['union_ticker_count'],report['union_security_count'],report['union_issuer_count']),
            (15,1515,112,112,111))
        self.assertEqual(report['middle_dates_not_in_prior_first_last_asset_matrix'],['SPLK'])
        splk=next(row for row in report['candidate_rows'] if row['ticker']=='SPLK')
        self.assertEqual([row['selection_date'] for row in splk['date_appearances']],['2024-04-01','2024-05-01'])
        self.assertEqual(len(splk['local_csv_assets']),2)
        self.assertEqual(splk['provider_capture_paths'],[])

    def test_raw_denominator_vs_legacy_use_and_full_training(self):
        report=self.report
        self.assertEqual(len(report['candidate_tickers_with_raw_capture']),25)
        self.assertEqual(len(report['no_raw_provider_capture_tickers']),87)
        self.assertEqual(len(report['no_raw_and_only_root_or_valuation_csv_tickers']),80)
        self.assertEqual(report['no_raw_but_old_execution_csv_tickers'],['AMZN','CSGP','FISV','JD','LCID','PDD','RIVN'])
        self.assertEqual(report['provider_channels_outside_proxy_union'],['TSM'])
        partial=[row['ticker'] for row in report['candidate_rows'] if row['raw_capture_status'].endswith('MISSING')]
        self.assertEqual(partial,['ASML','CEG','GEHC','MSFT','MU'])
        self.assertEqual(len(report['complete_observed_2022_start_raw_tickers']),15)

    def test_provider_ticker_and_incomplete_receipt_not_promoted(self):
        rows=[row for row in self.report['raw_captures'].values() if row['provider_request_ticker'] in ('FTNT','GOOGL')]
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertFalse(row['exact_receipt_available'])
            self.assertEqual(row['completion_cutoff_source'],'SAVED_TIME_ONLY_RECEIPT_UNKNOWN')
            self.assertTrue(row['request_symbol_is_not_historical_ticker_identity'])
        self.assertTrue(all(not row['historical_ticker_continuity_certified'] for row in self.report['candidate_rows']))
        self.assertFalse(self.report['new_network_requests_performed'])
        self.assertFalse(self.report['training_performed'])


if __name__=='__main__':unittest.main()
