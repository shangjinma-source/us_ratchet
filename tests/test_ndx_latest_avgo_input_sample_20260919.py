import json
import unittest
from unittest.mock import patch
from test_ndx_latest_amat_input_independent_review import fixture as base_fixture
from scripts import ndx_latest_avgo_input_sample_20260919 as m


def fixture():
    args,body,days=base_fixture();data=body['chart']['result'][0];data['meta']['symbol']='AVGO'
    data['events']['splits']={'1721050200':dict(date=1721050200,numerator=10.0,denominator=1.0,splitRatio='10:1')}
    for row in args['quote_rows']:row['ticker']='AVGO'
    args['decoded']=json.dumps(body).encode();return args,body


class Tests(unittest.TestCase):
    def test_declared_effective_date_requires_its_actual_clause(self):
        from pypdf import PdfReader
        from io import BytesIO
        path,sha=m.ANCHORS['split_history'];manifest=json.loads((m.BASE/path).read_bytes())
        row,=[r for r in manifest['probes'] if r['name']=='avgo_official_20240612_split_faq'];raw=m.Path(row['response_path']).read_bytes()
        text=' '.join(' '.join(page.extract_text() for page in PdfReader(BytesIO(raw)).pages).split()).replace('\u2010','-')
        self.assertIn('July 12, 2024 Effective Date',text)
        from types import SimpleNamespace
        fake=SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text.replace('July 12, 2024 Effective Date','July 13, 2024 Effective Date'))])
        with patch('pypdf.PdfReader',return_value=fake),self.assertRaises(ValueError):m.extract_split_facts({row['name']:raw})

    def test_actual_split_faq_and_postsplit_input_units(self):
        path,sha=m.ANCHORS['split_history'];manifest=json.loads((m.BASE/path).read_bytes())
        self.assertEqual(m.hashlib.sha256((m.BASE/path).read_bytes()).hexdigest(),sha)
        row,=[r for r in manifest['probes'] if r['name']=='avgo_official_20240612_split_faq'];raw=m.Path(row['response_path']).read_bytes()
        self.assertEqual(m.hashlib.sha256(raw).hexdigest(),row['response_sha256'])
        fact=m.extract_split_facts({row['name']:raw})
        self.assertEqual(fact['first_adjusted_session'],'2024-07-15');self.assertFalse(fact['actual_execution_independently_reconfirmed'])
        args,body=fixture();result=m.calculate(**args)
        self.assertEqual(len(result['price_returns']['rows']),126);self.assertEqual(result['price_returns']['rows'][-1]['price_return'],-.5)
        self.assertEqual(result['median_dollar_volume_usd'],'100000000.0');json.dumps(result)

    def test_removed_wrong_nonpositive_or_extra_event_reject(self):
        for defect in ('delete','day','ratio','negative','zero','bool','extra','factor'):
            args,body=fixture();events=body['chart']['result'][0]['events']['splits'];event=events['1721050200']
            if defect=='delete':events.clear()
            if defect=='day':event['date']-=86400
            if defect=='ratio':event['numerator']=20
            if defect=='negative':event.update(numerator=-10,denominator=-1)
            if defect=='zero':event['denominator']=0
            if defect=='bool':event['denominator']=True
            if defect=='extra':events['extra']=dict(event)
            if defect=='factor':args['quote_rows'][-1]['split_factor']=10
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.calculate(**dict(args,decoded=json.dumps(body).encode()))


if __name__=='__main__':unittest.main()
