from copy import deepcopy
import unittest
from scripts.extract_sec_quarter_events_v1 import extract


class ExtractionTests(unittest.TestCase):
    def fixture(self):
        rows=[dict(accn='old',form='10-Q',start='2024-04-01',end='2024-06-30',val=120),
              dict(accn='old',form='10-Q',start='2023-04-01',end='2023-06-30',val=100)]
        facts=dict(cik=1,facts={'us-gaap':{'NetIncomeLoss':{'units':{'USD':rows}}}})
        metadata=dict(cik='0001',filings={'recent':dict(accessionNumber=['old'],form=['10-Q'],
            reportDate=['2024-06-30'],acceptanceDateTime=['2024-08-01T20:01:00Z'])})
        return facts,metadata,rows

    def run_case(self,facts,metadata,**kwargs):
        return extract(facts,[metadata],concepts=['NetIncomeLoss'],**kwargs)

    def test_acceptance_cutoff_excludes_future_comparatives_and_ignores_frame(self):
        f,m,rows=self.fixture()
        future=[dict(r,accn='future',val=900,frame='CY2024Q2') for r in rows]
        rows.extend(future)
        for key,value in [('accessionNumber','future'),('form','10-Q'),('reportDate','2024-06-30'),('acceptanceDateTime','2025-08-01T20:00:00Z')]:
            m['filings']['recent'][key].append(value)
        result=self.run_case(f,m,cutoff='2024-08-01T20:01:00Z')
        self.assertEqual(len(result['events']),1)
        self.assertEqual(result['events'][0]['yoy_fraction'],'1/5')
        self.assertIn('AFTER_CUTOFF',[r['reason'] for r in result['rejected']])
        self.assertEqual(self.run_case(f,m,cutoff='2024-08-01T20:00:59Z')['events'],[])

    def test_no_filed_date_fallback_or_ytd_subtraction(self):
        for mutation,reason in [('time','EXACT_ACCEPTANCE_REQUIRED'),('ytd','DIRECT_QUARTER_MISSING_NO_YTD_DERIVATION'),('conflict','CONFLICTING_SAME_PERIOD_VALUES')]:
            f,m,rows=self.fixture()
            if mutation=='time':m['filings']['recent']['acceptanceDateTime']=['2024-08-01']
            elif mutation=='ytd':rows[0]['start']='2024-01-01'
            else:rows.append(dict(rows[0],val=121))
            with self.subTest(mutation=mutation):
                result=self.run_case(f,m)
                self.assertFalse(result['events'])
                self.assertIn(reason,[r['reason'] for r in result['rejected']])

    def test_negative_profit_and_exact_duplicate(self):
        f,m,rows=self.fixture();rows[0]['val']=-80;rows[1]['val']=-100
        rows.append(deepcopy(rows[0]));result=self.run_case(f,m)
        event=result['events'][0]
        self.assertEqual(event['absolute_change'],'20')
        self.assertIsNone(event['yoy_fraction'])
        self.assertFalse(event['signal']);self.assertFalse(event['original_filing_text_verified'])

    def test_wrong_issuer_unit_or_accession_not_joined(self):
        f,m,rows=self.fixture();m['cik']=2
        with self.assertRaisesRegex(ValueError,'ISSUER_CIK_MISMATCH'):self.run_case(f,m)
        m['cik']=1;rows[1]['accn']='another'
        self.assertFalse(self.run_case(f,m)['events'])
        self.assertFalse(self.run_case(f,m,unit='shares')['events'])


if __name__=='__main__':unittest.main()
