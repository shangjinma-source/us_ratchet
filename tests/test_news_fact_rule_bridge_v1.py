import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from scripts.research.news_fact_rule_bridge_v1 import bridge


class BridgeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.run=self.root/'run';self.run.mkdir()
        text='FY2021 product 100ug deliveries temporarily delayed.'
        source=self.root/'source.json';source.write_text(text)
        digest=sha256(source.read_bytes()).hexdigest()
        self.input={'source_type':'FULL_PUBLIC_ISSUER_LINKED_RELEASES','records':[dict(id='x',url='https://example.test/release',text=text,text_sha256=digest,original_sha256=digest)]}
        self.answer={'records':[dict(id='x',classification='TEMPORARY_DELIVERY_CONSTRAINT',year='FY2021',product='product',dose='100ug',evidence_quote=text,uncertainty='Needs review')]}
        self.review={'records':[dict(id='x',source_path='source.json',source_original_sha256=digest,source_text_sha256=digest,source_url='https://example.test/release',evidence_quote=text,reviewed_classification='TEMPORARY_DELIVERY_CONSTRAINT',scope=dict(year='FY2021',product='product',dose='100ug'),comparative=dict(status='NOT_PROVEN',reason='capacity is not deliveries'))]}
        self.save()

    def save(self):
        for name,obj in [('input',self.input),('answer',self.answer)]:
            p=self.run/(name+'.json');p.write_text(json.dumps(obj));self.review[name+'_sha256']=sha256(p.read_bytes()).hexdigest()
        receipt=dict(status='FACT_EXTRACTION_QUOTE_BOUND_SEMANTIC_REVIEW_REQUIRED',source_input_sha256=self.review['input_sha256'],rule_admitted=False,semantic_review_required=True)
        p=self.run/'receipt.json';p.write_text(json.dumps(receipt));self.review['receipt_sha256']=sha256(p.read_bytes()).hexdigest()
        self.reviewpath=self.root/'review.json';self.reviewpath.write_text(json.dumps(self.review))

    def check(self):return bridge(self.root,self.run,self.reviewpath)

    def test_comparative_absent_no_cut_even_approval_boolean(self):
        self.review['records'][0]['cut_admitted']=True;self.save()
        result=self.check();self.assertFalse(result['rule_admitted']);self.assertEqual(result['events'],[])
        self.assertEqual(result['decisions'][0]['reason'],'COMPARABLE_LOWER_EVIDENCE_NOT_VERIFIED')

    def test_other_cannot_be_repair(self):
        self.answer['records'][0]['classification']='OTHER';self.review['records'][0]['reviewed_classification']='OTHER'
        self.review['records'][0]['repair_admitted']=True;self.save()
        self.assertEqual(self.check()['events'],[])

    def test_answer_hash_tamper_rejected(self):
        (self.run/'answer.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'REVIEW_RUN_HASH'):self.check()

    def test_original_tamper_blocks(self):
        (self.root/'source.json').write_text('changed')
        result=self.check();self.assertEqual(result['events'],[])
        self.assertEqual(result['decisions'][0]['reason'],'ORIGINAL_SOURCE_HASH_MISMATCH')
        self.assertFalse(result['validation_complete'])

    def test_missing_source_path_is_invalid_not_rule_rejection(self):
        del self.review['records'][0]['source_path'];self.save()
        result=self.check()
        self.assertEqual(result['status'],'INVALID_INPUT')
        self.assertFalse(result['validation_complete'])
        self.assertTrue(result['input_errors'])

    def test_invented_quote_rejected(self):
        self.answer['records'][0]['evidence_quote']='fabricated';self.save()
        with self.assertRaisesRegex(ValueError,'EXACT_QUOTE'):self.check()

    def test_source_bound_positive_uses_tracked_key(self):
        current_text='FY2021 Moderna COVID-19 vaccine 100ug global deliveries temporarily delayed: 700 to 800 million doses'
        prior_text='FY2021 Moderna COVID-19 vaccine 100ug global deliveries: 800 to 1000 million doses'
        sources={};values=[]
        for name,text,low,high,published in [('prior',prior_text,'800','1000','2021-08-05T11:00:00Z'),('source',current_text,'700','800','2021-11-04T11:00:00Z')]:
            path=self.root/(name+'.json');path.write_text(text);digest=sha256(text.encode()).hexdigest()
            sources[digest]=dict(text_path=path.name,text=text,url='https://example.test/'+name,issuer_cik='0001682852',publication_datetime=published)
            start=text.index(':')+1;lo=text.index(low,start);hi=text.index(high,lo+len(low))
            values.append(dict(issuer_cik='0001682852',metric='Vaccine Dose Deliveries',currency='DOSES',unit_scale='1000000',basis='DELIVERIES',fiscal_period_start='2021-01-01',fiscal_period_end='2021-12-31',status='FORWARD_GUIDANCE',low=low,high=high,publication_datetime=published,source_url=sources[digest]['url'],source_sha256=digest,quote_start=0,quote_end=len(text),low_span=[lo,lo+len(low)],high_span=[hi,hi+len(high)]))
        current=values[1];digest=current['source_sha256']
        self.input['records'][0].update(text=current_text,text_sha256=digest,original_sha256=digest,url=current['source_url'])
        self.answer['records'][0].update(product='Moderna COVID-19 vaccine',evidence_quote=current_text)
        record=self.review['records'][0]
        record.update(source_original_sha256=digest,source_text_sha256=digest,source_url=current['source_url'],evidence_quote=current_text,available_at='2021-11-04T11:00:00Z',
            scope=dict(issuer_cik='0001682852',security_id='research:security:mrna',year='FY2021',product='Moderna COVID-19 vaccine',dose='100ug',metric='Vaccine Dose Deliveries',geography='GLOBAL',period_end='2021-12-31'),
            comparative=dict(status='VERIFIED_SAME_SCOPE_STRICT_LOWER',numeric_comparison=dict(previous=values[0],current=values[1],verified_sources=sources)))
        self.save();result=self.check()
        self.assertTrue(result['rule_admitted'])
        self.assertEqual(result['events'][0]['comparison_key'],'MRNA_FY2021_100UG_GLOBAL_DELIVERY_DELAY')


if __name__=='__main__':unittest.main()
