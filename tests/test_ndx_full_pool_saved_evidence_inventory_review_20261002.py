from copy import deepcopy
import unittest
from test_ndx_full_pool_saved_evidence_inventory_20261002 import fixture,m

class InventoryIndependentReview(unittest.TestCase):
    def test_reporter_not_issuer_mismatch_remains_only_source_lead(self):
        d,refs=fixture();decision=d['review']['decisions'][0]
        decision.update(issuer_id='issuer:0000000002',accession_number='0000000002-26-000001',document_url='https://www.sec.gov/Archives/edgar/data/2/000000000226000001/a.htm')
        r=m.assemble_inventory(d,refs);row=r['rows'][0]
        self.assertFalse(row['review_matches'][0]['review_issuer_matches_resolved_identity_index'])
        self.assertFalse(row['review_matches'][0]['matching_ticker_authenticates_identity'])
        self.assertEqual(r['extraction_queue'][0]['review_match']['decision'],decision)
        for n in row['identity_matches'][0]['nport_matches']:
            self.assertFalse(n['nport_reporter_is_security_issuer']);self.assertEqual(n['row']['source_locator'],'fund/1067839')
        self.assertIsNone(row['formal_eligible_security_count_contribution'])
        for key in m.FLAGS:self.assertIs(row[key],False)

    def test_unresolved_empty_cusip_does_not_join_and_all_history_retained(self):
        d,refs=fixture();original=deepcopy(d)
        unresolved=deepcopy(d['identities'][0]);unresolved.update(cusip='',identity_status='unresolved_cusip',security_id='security:0000000001:unresolved:T0')
        d['identities'].append(unresolved);d['identity_manifest']['row_count']+=1
        d['nport'].append(dict(cusip='',ticker='T0',source_locator='fund/not_subject'));d['nport_manifest']['row_count']+=1
        r=m.assemble_inventory(d,refs)
        self.assertEqual(r['rows'][0]['identity_matches'][-1]['nport_matches'],[])
        self.assertEqual(r['rows'][0]['identity_matches'][-1]['row'],unresolved)
        self.assertEqual([x['source_row'] for x in r['historical_denominators']],original['historical_coverage']['dates'])
        self.assertEqual(len(r['rows']),101);self.assertEqual(r['saved_exact_event_rows'],original['exact_events'])
        self.assertFalse(r['current_rows_replace_historical_denominators'])

    def test_all_blocks_and_ambiguous_review_not_dropped(self):
        d,refs=fixture();d['review']['decisions'].append(deepcopy(d['review']['decisions'][0]))
        d['channels']['rows'][100].update(status='BLOCKED_PRICE_INPUT',channel_input=None,reasons=['PERMANENT_COMPLEX_PRICE','UNRESOLVED_PARTITION'])
        d['channels']['rows'][99]['channel_input']['liquidity']['status']='BLOCKED_VOLUME_UNIT_UNKNOWN'
        r=m.assemble_inventory(d,refs)
        self.assertEqual(r['extraction_queue'],[]);self.assertEqual(r['rows'][0]['accepted_review_count'],2)
        self.assertEqual(r['rows'][100]['channel_state']['reasons'],['PERMANENT_COMPLEX_PRICE','UNRESOLVED_PARTITION'])
        self.assertEqual(r['summary']['blocked_price_count'],1);self.assertEqual(r['summary']['blocked_volume_unit_count'],1)
        d['historical_coverage']['dates'].pop()
        with self.assertRaises(ValueError):m.assemble_inventory(d,refs)

    def test_raw_path_cannot_escape_or_use_reporter(self):
        d,_=fixture();entry=d['review']['decisions'][0]
        for url in ('https://www.sec.gov/Archives/edgar/data/1067839/000000000126000001/a.htm','https://www.sec.gov/Archives/edgar/data/1/000000000126000001/../a.htm','https://www.sec.gov/Archives/edgar/data/1/000000000126000001/%2e%2e.htm'):
            e=deepcopy(entry);e['document_url']=url
            with self.assertRaises(ValueError):m.raw_reference(e)

if __name__=='__main__':unittest.main()
