from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from scripts import ndx_legacy_twelve_price_only_20260923 as m


class IndependentPriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents={};cls.raws={}
        for role,(name,sha) in m.BOUND.items():
            raw=(m.BASE/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Frozen fixture drift')
            if role.endswith('_raw'):cls.raws[role[:-4]]=raw
            else:cls.documents[role]=json.loads(raw)

    def test_real_1070_new_cells_1498_parent_cells_and_dividends(self):
        before=deepcopy(self.documents)
        result=m.assemble(self.documents,self.raws)
        self.assertEqual(before,self.documents)
        self.assertEqual(sum(len(row) for matrix in result['matrices'].values() for row in matrix.values()),2568)
        self.assertTrue(all(result[key] is False for key in m.FALSE))
        calendar=result['calendar'];channels={c['ticker']:c for c in result['channels']}
        for ticker in m.NEW:
            raw=self.raws[ticker]
            if raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
            chart=json.loads(raw,parse_float=Decimal)['chart']['result'][0]
            by_day={datetime.fromtimestamp(t,timezone.utc).astimezone(m.NY).date().isoformat():i for i,t in enumerate(chart['timestamp'])}
            quote=chart['indicators']['quote'][0]
            for day in calendar:
                for kind in ('open','close'):
                    self.assertEqual(result['matrices'][kind][day][ticker],str(quote[kind][by_day[day]]))
            expected_events=chart.get('events',{}).get('dividends',{})
            expected_dates={datetime.fromtimestamp(e['date'],timezone.utc).astimezone(m.NY).date().isoformat():str(e['amount']) for e in expected_events.values()}
            self.assertEqual({e['session']:e['amount'] for e in channels[ticker]['dividend_events']},expected_dates)
            self.assertEqual({e['session']:e['amount'] for e in channels[ticker]['window_dividend_events']},
                {day:value for day,value in expected_dates.items() if calendar[0]<=day<=calendar[-1]})
            self.assertEqual(len(expected_events),19 if ticker in ('QCOM','ADI','TXN') else 0)
        for ticker in m.OLD:
            parent=self.documents['enph']['price_projection'] if ticker=='ENPH' else self.documents['parent']
            for kind in ('open','close'):
                for day in calendar:self.assertEqual(result['matrices'][kind][day][ticker],parent['matrices'][kind][day][ticker])

    def test_inherited_matrix_row_disagreement_and_permission_upgrade(self):
        for attack in ('matrix','channel','permission','final'):
            docs=deepcopy(self.documents)
            if attack=='matrix':docs['parent']['matrices']['open'][docs['benchmark']['calendar'][0]]['AVGO']='1'
            elif attack=='channel':docs['parent']['channels'].append(deepcopy(next(c for c in docs['parent']['channels'] if c['ticker']=='AVGO')))
            elif attack=='permission':docs['enph']['point_in_time_verified']=True
            else:docs['parent_final']['raw_reference']['sha256']='0'*64
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs,self.raws)

    def test_receipt_clock_hash_or_identity_scope_change_is_rejected(self):
        for field,value in (('raw_sha256','0'*64),('started_at_utc','2026-09-18T18:13:29+00:00'),
            ('historical_identity_verified',True),('credentials_sent',True)):
            metadata=deepcopy(self.documents['QCOM_meta']);metadata[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                m.decode('QCOM',self.raws['QCOM'],metadata,self.documents['benchmark']['calendar'])


if __name__=='__main__':unittest.main()
