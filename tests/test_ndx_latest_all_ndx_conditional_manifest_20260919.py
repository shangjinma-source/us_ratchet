import copy,json,unittest
import yaml
from scripts import ndx_latest_all_ndx_conditional_manifest_20260919 as m

def fixture():
    return {k:yaml.safe_load(p.read_bytes()) if k=='scope' else json.loads(p.read_bytes()) for k,(p,h) in m.ANCHORS.items()}

class ManifestTests(unittest.TestCase):
    def test_full_observed_denominator_and_issuer_share_classes(self):
        result=m.assemble(**fixture())
        self.assertEqual(result['counts']['conditional_price_channels'],99)
        self.assertEqual(result['counts']['fit127_date_coverage'],96)
        self.assertEqual(result['counts']['desired505_date_coverage'],91)
        self.assertEqual(result['issuer_to_observed_tickers']['issuer:0001652044'],['GOOG','GOOGL'])
        self.assertTrue(all(r['security_id'] is None and r['share_class'] is None for r in result['rows']))
        self.assertEqual({r['ticker'] for r in result['rows'] if r['history_failures']},{'CMCSA','TRI','HON','HONA','SPCX'})
        self.assertFalse(result['industry_filter_applied']);self.assertFalse(result['legal_training_input_admitted'])

    def test_missing_duplicate_class_count_and_prior_alias_rejected(self):
        for defect in ('missing','duplicate','issuer','position','future','coverage','eligibility','industry'):
            docs=fixture()
            if defect=='missing':docs['prices']['rows'].pop()
            if defect=='duplicate':docs['issuers']['rows'][-1]=copy.deepcopy(docs['issuers']['rows'][0])
            if defect=='issuer':docs['issuers']['rows'][0]['conditional_issuer_id']='issuer:0000000001'
            if defect=='position':docs['issuers']['rows'][0]['reported_ticker_exchange_position']=True
            if defect=='future':docs['prices']['rows'][0]['calendar'][-1]='2026-09-18'
            if defect=='coverage':docs['readiness']['rows'][0]['coverage']['fit_return_pairs_with_both_prices']=125
            if defect=='eligibility':docs['readiness']['rows'][0]['legal_fit_input_ready']=True
            if defect=='industry':docs['scope']['scope_change']['industry_filter_applied']=True
            with self.subTest(defect=defect),self.assertRaises((ValueError,IndexError)):m.assemble(**docs)

    def test_no_common_calendar_compression_or_event_deletion(self):
        docs=fixture();docs['readiness']['observed_reference_calendar']=docs['prices']['common_99_provider_calendar']
        with self.assertRaises(ValueError):m.assemble(**docs)
        result=m.assemble(**fixture());rows={r['ticker']:r for r in result['rows']}
        self.assertEqual(rows['MNST']['returned_events_on_or_after_liquidity_start'][0]['session'],'2026-08-11')
        self.assertEqual(rows['CRWD']['returned_events_on_or_after_liquidity_start'][0]['session'],'2026-07-02')
        self.assertEqual(rows['KLAC']['returned_events_in_fit_price_window'][0]['session'],'2026-06-12')
        self.assertEqual(rows['HON']['coverage']['fit_return_pairs_with_both_prices'],56)

if __name__=='__main__':unittest.main()
