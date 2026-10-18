import copy
import unittest
from scripts import ndx_current101_conditional_issuer_map_20260919 as module


class Tests(unittest.TestCase):
    def test_real_full_denominator_dated_layers_and_dual_class(self):
        report=module.build()
        self.assertEqual(report['security_observation_count'],101)
        self.assertEqual(report['conditional_unique_issuer_count'],100)
        self.assertEqual(set(report['issuer_to_observed_tickers']['issuer:0001652044']),{'GOOG','GOOGL'})
        self.assertEqual(report['current_submission_ticker_count'],9)
        self.assertEqual(len(report['latest_sec_refresh_candidate_tickers']),92)
        self.assertFalse(report['complete_current_same_cutoff_sec_identity_verified'])
        self.assertFalse(report['dated_crosswalk_metadata'][1]['sidecar_row_count_matches_actual'])

    def test_same_issuer_multiple_classes_count_once(self):
        table=module.parse_table({'fields':['cik','name','ticker','exchange'],'data':[[1,'Issuer','A','Nasdaq'],[1,'Issuer','B','Nasdaq']]},['A','B'])
        rows,issuers=module.assemble(['A','B'],[table,table],{})
        self.assertEqual(len(rows),2);self.assertEqual(len(issuers),1)

    def test_names_never_bind_and_conflicts_rejected(self):
        body={'fields':['cik','name','ticker','exchange'],'data':[[1,'A','OTHER','Nasdaq']]}
        with self.assertRaises(ValueError):module.parse_table(body,['A'])
        body['data']=[[1,'Issuer','A','NYSE']]
        with self.assertRaises(ValueError):module.parse_table(body,['A'])
        body['data']=[[1,'Issuer','A','Nasdaq']]*2
        with self.assertRaises(ValueError):module.parse_table(body,['A'])
        table={'A':{'cik':'0000000001'}};other=copy.deepcopy(table);other['A']['cik']='0000000002'
        with self.assertRaises(ValueError):module.assemble(['A'],[table,other],{})
        with self.assertRaises(ValueError):module.assemble(['A'],[table,table],{'A':{'current_reported_cik':'0000000002','reported_exchange':'Nasdaq'}})


if __name__=='__main__':unittest.main()
