import json
import unittest
from datetime import datetime
from test_ndx_latest_amat_input_independent_review import fixture
from scripts import ndx_latest_amat_input_sample_20260919 as m


class Tests(unittest.TestCase):
    def test_later_bar_excluded_and_exact_two_windows(self):
        args,body,days=fixture()
        baseline=m.calculate(**args)
        data=body['chart']['result'][0]
        data['indicators']['quote'][0]['open']=list(data['indicators']['quote'][0]['open'])
        data['timestamp'].append(int(datetime.fromisoformat('2026-09-18T14:30:00+00:00').timestamp()))
        for name in ('open','close','volume'):data['indicators']['quote'][0][name].append(999999999)
        observed=m.calculate(**dict(args,decoded=json.dumps(body).encode()))
        self.assertEqual(baseline,observed)
        self.assertEqual(observed['input_payload']['calendar'],days[-127:])
        self.assertEqual([r['session'] for r in observed['liquidity_rows']],days[-63:])
        self.assertEqual(observed['price_returns']['rows'][0]['previous_session'],days[-127])

    def test_missing_null_boolean_and_mismatched_raw_reject(self):
        for defect in ('missing','null','bool','price','currency'):
            args,body,days=fixture()
            if defect=='missing':args['quote_rows'].pop(-70)
            if defect=='null':body['chart']['result'][0]['indicators']['quote'][0]['close'][-70]=None
            if defect=='bool':args['quote_rows'][-1]['split_factor']=True
            if defect=='price':args['quote_rows'][-1]['nominal_close']=51
            if defect=='currency':body['chart']['result'][0]['meta']['currency']='EUR'
            args['decoded']=json.dumps(body).encode()
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.calculate(**args)


if __name__=='__main__':unittest.main()
