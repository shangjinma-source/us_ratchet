import copy,json,unittest
from scripts import ndx_three_cusip_web_transcription_readback_20260919 as m

class TranscriptionTests(unittest.TestCase):
    def fixture(self,t):
        row=next(r for r in json.loads(m.TRANSCRIPT.read_bytes())['rows'] if r['ticker']==t)
        a,d,_,doc,_=m.EXPECTED[t];fact=m.prior.FACTS[t]
        sub=dict(cik=int(fact['cik']),filings=dict(recent=dict(accessionNumber=[a],filingDate=[d],primaryDocument=[doc],form=['SC 13G/A'])))
        cover=dict(cik=fact['cik'],ticker=t,security_class_title=fact['security_class'])
        return row,sub,cover

    def test_three_dated_subjects_and_distinct_event_date(self):
        for t in m.EXPECTED:
            value=m.inspect(*self.fixture(t))
            self.assertFalse(value['local_http_original_bytes_available']);self.assertFalse(value['point_in_time_verified'])
        self.assertEqual(m.inspect(*self.fixture('ADI'))['event_date'],'2022-12-30')

    def test_wrong_reporter_class_url_event_and_accession_rejected(self):
        for t in m.EXPECTED:
            for field,value in [('event_date','2023-01-01'),('accession','0001306550-23-000000'),('url','https://example.com/')]:
                row,sub,cover=self.fixture(t);row[field]=value
                with self.assertRaises(ValueError):m.inspect(row,sub,cover)
            row,sub,cover=self.fixture(t);sub['cik']=1364742
            with self.assertRaises(ValueError):m.inspect(row,sub,cover)
            row,sub,cover=self.fixture(t);row['excerpts'][1]['verbatim_value']='Class B Common Stock'
            with self.assertRaises(ValueError):m.inspect(row,sub,cover)
            row,sub,cover=self.fixture(t);cover['ticker']='OTHER'
            with self.assertRaises(ValueError):m.inspect(row,sub,cover)

    def test_actual_hard_sources_and_complete_denominator(self):
        report=m.build();self.assertEqual(report['security_count'],3)
        self.assertEqual(report['raw_http_verified_count'],0)
        self.assertEqual(report['web_transcription_accession_links_checked'],3)

if __name__=='__main__':unittest.main()
