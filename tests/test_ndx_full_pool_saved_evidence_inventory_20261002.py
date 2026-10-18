from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('inventory_owner', Path(__file__).resolve().parents[1] / 'scripts/ndx_full_pool_saved_evidence_inventory_20261002.py')
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

def fixture():
    refs = {k: {'path': k, 'sha256': 'a'*64} for k in m.PINS}
    flags = {'point_in_time_verified':False,'legal_training_input_admitted':False,'promotion_allowed':False}
    members=['T'+str(i) for i in range(101)]
    docs={'wiring':{'schema':'NEW_CUTOFF_101_DATED_IDENTITY_RISK_WIRING_V6','rows':[{'ticker':t,'coordinate':None,**flags} for t in members],**flags},
      'channels':{'schema':'NEW_CUTOFF_CONDITIONAL_CHANNELS_V1','rows':[{'ticker':t,'status':'CONDITIONAL_NUMERIC_RESULT','channel_input':{'liquidity':{'status':'CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE'}},'reasons':[],'raw_reference':{'path':'quote'},'receipt_reference':{'path':'receipt'},'volume_units_independently_certified':False,**flags} for t in members],**flags},
      'observation':{'schema':'ndx_current_quote_list_observation_v1','rows':[{'symbol':t} for t in members],'point_in_time_membership_verified':False,'historical_backfill_allowed':False},
      'review':{'research_only':True,'decisions':[]},'identities':[],'nport':[],
      'exact_events':[{'ticker':'GRAL','action':'ADD'}],
      'exact_manifest':{'files':{'exact_events':{'sha256':'a'*64,'rows':1}}},
      'historical_coverage':{'schema':'ndx_full_membership_coverage_research_v1','date_count':15,'exact_daily_membership_verified':False,'dates':[{'coordinate':{'selection_date':'2023-01-'+str(i+1).zfill(2)},'membership_unknown':True} for i in range(15)]},
      'scope':{'membership_contract':{'permitted_status':'VERIFIED_POINT_IN_TIME_MEMBER','unknown_membership_policy':'EXCLUDE_AND_REPORT_NOT_ACCEPT','source_hash_alone_proves_membership':False,'current_snapshot_historical_backfill_allowed':False}}}
    for i,t in enumerate(members):
        cik=str(i+1).zfill(10); cusip=str(i).zfill(9)
        docs['identities'].append({'ticker':t,'cik':cik,'cusip':cusip,'security_id':'security:'+cik+':'+cusip,'issuer_id':'issuer:'+cik,'identity_status':'resolved'})
    docs['review']['decisions']=[{'ticker':'T0','tickers':['T0'],'issuer_id':'issuer:0000000001','accession_number':'0000000001-26-000001','document_url':'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/a.htm','raw_sha256':'b'*64,'status':'accepted','selection_date':'2026-07-13'}]
    docs['nport']=[{'ticker':'DIFFERENT','cusip':'000000000','source_locator':'fund/1067839','report_date':'2022-12-31'},{'ticker':'T0','cusip':'000000000','source_locator':'fund/1067839','report_date':'2023-03-31'}]
    for role,manifest in [('identities','identity_manifest'),('nport','nport_manifest')]: docs[manifest]={'content_sha256':'a'*64,'row_count':len(docs[role])}
    return docs,refs

class InventoryTests(unittest.TestCase):
    def test_full_denominators_reports_and_no_mutation(self):
        d,r=fixture(); original=deepcopy(d); out=m.assemble_inventory(d,r)
        self.assertEqual(d,original); self.assertEqual(len(out['rows']),101); self.assertEqual(len(out['historical_denominators']),15)
        self.assertEqual(len(out['extraction_queue']),1); self.assertEqual(len(out['rows'][0]['identity_matches'][0]['nport_matches']),2)
        self.assertEqual(out['saved_exact_event_rows'],d['exact_events']);self.assertIsNone(out['summary']['verified_pit_eligible_count'])
    def test_multi_sid_and_unresolved_not_collapsed(self):
        d,r=fixture(); other=deepcopy(d['identities'][0]);other.update(cusip='OTHER',security_id='security:0000000001:OTHER');d['identities'].append(other)
        unresolved=deepcopy(other);unresolved.update(cusip='',security_id='security:0000000001:unresolved:T0',identity_status='unresolved');d['identities'].append(unresolved);d['identity_manifest']['row_count']+=2
        out=m.assemble_inventory(d,r);self.assertEqual(out['rows'][0]['identity_match_count'],3);self.assertEqual(out['rows'][0]['resolved_coordinate_count'],2);self.assertEqual(out['extraction_queue'],[])
    def test_blocks_and_parent_reuse(self):
        for kind in ['volume','price','wired']:
            d,r=fixture()
            if kind=='volume':d['channels']['rows'][0]['channel_input']['liquidity']['status']='BLOCKED_VOLUME_UNIT_UNKNOWN'
            if kind=='price':d['channels']['rows'][0].update(status='BLOCKED_PRICE_INPUT',channel_input=None,reasons=['COMPLEX'])
            if kind=='wired':d['wiring']['rows'][0]['coordinate']={'security_id':'saved'}
            out=m.assemble_inventory(d,r);self.assertEqual(out['extraction_queue'],[])
    def test_authority_manifest_and_order_failclosed(self):
        for mutate in [lambda d:d['wiring'].update(promotion_allowed=True),lambda d:d['identity_manifest'].update(row_count=True),lambda d:d['observation']['rows'].reverse()]:
            d,r=fixture();mutate(d)
            with self.assertRaises(ValueError):m.assemble_inventory(d,r)
    def test_raw_path_issuer_binding(self):
        d,r=fixture();decision=d['review']['decisions'][0];self.assertTrue(m.raw_reference(decision)['path'].endswith('a.htm'))
        decision['document_url']='https://www.sec.gov/Archives/edgar/data/1067839/000000000126000001/a.htm'
        with self.assertRaises(ValueError):m.raw_reference(decision)
    def test_existing_namespace_does_not_load(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)),patch.object(m,'read_inputs') as read:
            with self.assertRaises(ValueError):m.run()
            read.assert_not_called()

if __name__=='__main__':unittest.main()
