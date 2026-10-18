import json
import unittest
from copy import deepcopy
from test_ndx_latest_amat_input_independent_review import fixture as amat_fixture
from scripts import ndx_latest_goog_input_sample_20260919 as m


def fixture():
    args,body,days=amat_fixture();data=body['chart']['result'][0];data['meta']['symbol']='GOOG'
    data['events']['splits']={'1658151000':dict(date=1658151000,numerator=20.0,denominator=1.0,splitRatio='20:1')}
    for row in args['quote_rows']:row['ticker']='GOOG'
    args['decoded']=json.dumps(body).encode();return args,body


class Tests(unittest.TestCase):
    def test_historical_event_retained_but_postevent_daily_ratio_one(self):
        args,body=fixture();result=m.calculate(**args)
        self.assertEqual(result['observed_historical_split']['new_shares'],20)
        self.assertEqual(len(result['price_returns']['rows']),126)
        self.assertEqual(result['price_returns']['rows'][-1]['price_return'],-.5)
        self.assertTrue(all(r['new_shares']==1 for r in result['input_payload']['daily_share_ratios']))
        json.dumps(result)

    def test_deleted_changed_or_extra_event_rejected(self):
        for defect in ('delete','ratio','day','extra','bool'):
            args,body=fixture();events=body['chart']['result'][0]['events']['splits'];event=events['1658151000']
            if defect=='delete':events.clear()
            if defect=='ratio':event['numerator']=10
            if defect=='day':event['date']+=86400
            if defect=='extra':events['unknown']=deepcopy(event)
            if defect=='bool':event['denominator']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.calculate(**dict(args,decoded=json.dumps(body).encode()))

    def test_bound_official_approved_and_executed_facts(self):
        path,sha=m.ANCHORS['split_history'];manifest=json.loads((m.BASE/path).read_bytes())
        self.assertEqual(m.hashlib.sha256((m.BASE/path).read_bytes()).hexdigest(),sha)
        docs={r['name']:m.Path(r['response_path']).read_bytes() for r in manifest['probes']}
        for row in manifest['probes']:self.assertEqual(m.hashlib.sha256(docs[row['name']]).hexdigest(),row['response_sha256'])
        fact=m.extract_split_facts(docs);self.assertEqual(fact['separately_reported_execution_date'],'2022-07-15')
        key='sec_goog_split_executed_2022';body=docs[key];body=m.gzip.decompress(body) if body[:2]==b'\x1f\x8b' else body
        docs[key]=body.replace(b'20-for-one',b'10-for-one')
        with self.assertRaises(ValueError):m.extract_split_facts(docs)


if __name__=='__main__':unittest.main()
