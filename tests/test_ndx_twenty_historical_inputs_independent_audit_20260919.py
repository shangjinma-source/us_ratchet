import copy,json,hashlib,unittest
from datetime import datetime,timezone,timedelta
from scripts import ndx_twenty_historical_inputs_independent_audit_20260919 as m


def fixture():
    days=[(datetime(2025,9,16)+timedelta(days=i)).date().isoformat() for i in range(253)]
    stamps=[int(datetime.fromisoformat(d+'T16:00:00+00:00').timestamp()) for d in days]
    event=dict(date=stamps[50],numerator=10,denominator=1,splitRatio='10:1')
    events={'splits':{str(stamps[50]):event},'dividends':{'irrelevant':{'amount':5}}}
    raw=json.dumps({'chart':{'result':[{'meta':{'symbol':'NFLX','currency':'USD'},'timestamp':stamps,'indicators':{'quote':[{'open':[10.]*253,'close':[10.]*253}]},'events':events}]}}).encode()
    rows=[dict(session=d,nominal_open=100. if i<50 else 10.,nominal_close=100. if i<50 else 10.) for i,d in enumerate(days)]
    submitted=[dict(session=days[50],new_shares='10',old_shares='1',event_kind='ORDINARY_SHARE_SPLIT',provider_event_key=str(stamps[50]),original_provider_fields=event)]
    prices=dict(calendar=days,returns={'columns':['NFLX'],'data':[[0.] for _ in range(252)]},nominal_open={'data':[[r['nominal_open']] for r in rows]},nominal_close={'data':[[r['nominal_close']] for r in rows]},submitted_full_split_events={'NFLX':submitted},effective_day_share_ratios={'NFLX':['10' if i==50 else '1' for i in range(1,253)]},applied_fit_split_events={'NFLX':[dict(previous_session=days[49],session=days[50],share_ratio='10',split_neutral_price_return='0')]})
    evidence=dict(decoded_sha256=hashlib.sha256(raw).hexdigest(),all_original_returned_events=events,maximum_absolute_decimal_error='0',
        quote_reference={'path':'quote','sha256':'q'},raw_reference={'path':'raw','sha256':'r'},received_at_utc='2026-09-19T01:00:00Z',receipt_day_excluded='2026-09-18',
        sealed_specific_event_witnesses=[],raw_provider_session_count=253,fixed_selected_price_count=253,decimal_open_close_cells=506,
        provider_identity_authenticated=False,quote_basis_independently_authenticated=False,complete_actions_verified=False)
    return prices,raw,rows,evidence


class LongAuditTests(unittest.TestCase):
    def test_independent_split_neutral_and_dividend_exclusion(self):
        p,r,rows,e=fixture();result=m.audit_channel('NFLX',p,r,rows,e)
        self.assertEqual(result['return_rows'],252);self.assertEqual(result['maximum_return_decimal_error'],'0')
        for defect in ('return','price','events'):
            bad=copy.deepcopy(p)
            if defect=='return':bad['returns']['data'][49][0]=-.9
            elif defect=='price':bad['nominal_close']['data'][0][0]=10.
            else:bad['submitted_full_split_events']['NFLX']=[]
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_channel('NFLX',bad,r,rows,e)

    def test_backward_nav_never_uses_future_observation(self):
        raw=b'Date,Close\n2026-01-01,1\n2026-01-03,2\n'
        value=dict(rows=[dict(session='2026-01-02',nav_source_date='2026-01-01',nav='1',same_date=False,known_published_by_us_session_cutoff=False)],returns=[],same_date_missing_count=1,alignment='BACKWARD_OBSERVATION_DATE_ONLY_NOT_PUBLICATION_TIME',future_nav_observation_used=False,original_currency_only=True,fx_applied=False,publication_time_verified=False,legal_comparison_ready=False)
        m.audit_nav(value,raw,['2026-01-02'])
        bad=copy.deepcopy(value);bad['rows'][0].update(nav_source_date='2026-01-03',nav='2')
        with self.assertRaises(ValueError):m.audit_nav(bad,raw,['2026-01-02'])

    def test_failclosed_before_artifact_sealed(self):
        with self.assertRaises(ValueError):m.build('unsealed','0'*64)
        p,r,rows,e=fixture();bad=copy.deepcopy(p);bad['calendar'].pop(40)
        with self.assertRaises(ValueError):m.audit_channel('NFLX',bad,r,rows,e)


if __name__=='__main__':unittest.main()
