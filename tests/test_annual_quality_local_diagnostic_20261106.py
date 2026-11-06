import unittest
from copy import deepcopy
from scripts.research.describe_annual_quality_local_20261106 import select,acceptance_class,cik_matches

def facts():
    out={}
    for concept,value in [('NetIncomeLoss',10),('NetCashProvidedByUsedInOperatingActivities',15),('Assets',100)]:
        row={'form':'10-K','filed':'2025-02-01','accn':'a','end':'2024-12-31','val':value}
        if concept!='Assets':row['start']='2024-01-01'
        out[concept]={'units':{'USD':[row]}}
    return out
class AnnualLocal(unittest.TestCase):
    def test_companyfacts_identity_must_match_numeric_cik(self):
        self.assertTrue(cik_matches('0000320193',320193))
        self.assertFalse(cik_matches('0000320193',320194))
        self.assertFalse(cik_matches('0000320193',None))
        self.assertFalse(cik_matches('0000320193','CIK320193'))
    def test_exact_same_version_values(self):
        x=select(facts(),{'a':'2025-02-01T12:00:00Z'},'2025-03-31')
        self.assertEqual(x['ratios'],{'net_income_over_ending_assets':'1/10','operating_cash_flow_over_ending_assets':'3/20','ni_minus_ocf_over_ending_assets':'-1/20'})
        self.assertEqual(x['availability_layer'],'EXACT_ACCEPTANCE_PRIOR_DATE')
    def test_future_accession_cannot_fill_missing_field(self):
        f=facts();r=f['NetCashProvidedByUsedInOperatingActivities']['units']['USD'][0];r.update(accn='future',filed='2025-04-01')
        x=select(f,{},'2025-03-31');self.assertEqual(x['status'],'NO_COMPATIBLE_ANNUAL_SAME_ACCESSION');self.assertTrue(any(r['reason']=='FILED_NOT_BEFORE_CUTOFF' for r in x['rejected_versions']))
    def test_versions_and_periods_not_spliced(self):
        for field,value in [('accn','different'),('start','2024-01-02')]:
            f=facts();f['NetCashProvidedByUsedInOperatingActivities']['units']['USD'][0][field]=value
            self.assertEqual(select(f,{},'2025-03-31')['status'],'NO_COMPATIBLE_ANNUAL_SAME_ACCESSION')
    def test_conflicts_and_nonpositive_assets_rejected(self):
        f=facts();r=deepcopy(f['Assets']['units']['USD'][0]);r['val']=101;f['Assets']['units']['USD'].append(r)
        self.assertEqual(select(f,{},'2025-03-31')['status'],'NO_COMPATIBLE_ANNUAL_SAME_ACCESSION')
        f=facts();f['Assets']['units']['USD'][0]['val']=0;self.assertEqual(select(f,{},'2025-03-31')['status'],'NO_COMPATIBLE_ANNUAL_SAME_ACCESSION')
    def test_acceptance_future_and_timezone(self):
        self.assertEqual(select(facts(),{'a':'2025-04-01T01:00:00Z'},'2025-03-31')['status'],'NO_COMPATIBLE_ANNUAL_SAME_ACCESSION')
        self.assertEqual(acceptance_class('2025-03-31T01:00:00Z','2025-03-31')[0],'EXACT_ACCEPTANCE_PRIOR_DATE')
        self.assertEqual(acceptance_class('2025-02-01T12:00:00','2025-03-31')[0],'FILED_ONLY_ACCEPTANCE_TIMEZONE_UNSPECIFIED')
if __name__=='__main__':unittest.main()
