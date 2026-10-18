from copy import deepcopy
from decimal import Context,Inexact,localcontext
from fractions import Fraction
import unittest
from backtest import ndx_nav_usd_observation_alignment_research as m


def ref(path):return dict(path=path,sha256='a'*64)

def fixture():
    navref=ref('nav.csv');raw=ref('official.html')
    nav=[dict(date=d,nav_cny_decimal=v,source_reference=dict(navref,row_index=i),available_at=None) for i,(d,v) in enumerate([('2026-03-20','70'),('2026-03-24','77')])]
    fx=[dict(date=d,status='NOT_AVAILABLE_ND' if v is None else 'REPORTED_RATE',rate_decimal=v,rate_literal='ND' if v is None else v,historical_available_at=None,source_reference=dict(raw,table_row_index=i)) for i,(d,v) in enumerate([('2026-03-20','7'),('2026-03-23','5'),('2026-03-24',None),('2026-03-25','7')])]
    return dict(session_dates=['2026-03-20','2026-03-23','2026-03-24','2026-03-25'],nav_rows=nav,fx_rows=fx,nav_reference=navref,fx_reference=ref('official-readback.json'),fx_context=dict(rate_direction='CNY_PER_USD',historical_available_at_verified=False,page_release_label='Current vintage',limitations=['CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE','OBSERVATION_DATE_NOT_PUBLICATION_TIMESTAMP','NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX'],source_references=dict(china_history=dict(raw=raw))))


class AlignmentTests(unittest.TestCase):
    def test_two_modes_session_denominator_not_nav_date(self):
        args=fixture();before=deepcopy(args);r=m.align_nav_usd_observations(**args);self.assertEqual(args,before)
        self.assertEqual(r['rows'][1]['conversions'][m.MODES[0]]['nav_usd_exact'],'14')
        self.assertEqual(r['rows'][1]['nav_date_fx_diagnostic_only']['same_date']['rate_exact'],'7')
        nd=r['rows'][2];self.assertIsNone(nd['conversions'][m.MODES[0]]['nav_usd_exact']);self.assertEqual(nd['conversions'][m.MODES[1]]['nav_usd_exact'],'77/5')
        self.assertEqual(nd['session_fx']['backward_valid']['lag_calendar_days'],1)
        self.assertEqual(nd['session_fx']['skipped_nd_rows'][0]['original_row'],args['fx_rows'][2])
        self.assertEqual(r['fx_rows_preserved'],args['fx_rows'])
        for k in m.FLAGS:self.assertIs(r[k],False)

    def test_absent_date_and_future_never_filled(self):
        a=fixture();a['session_dates']=['2026-03-19','2026-03-20','2026-03-26'];r=m.align_nav_usd_observations(**a)
        self.assertIsNone(r['rows'][0]['nav_observation']);self.assertIsNone(r['rows'][0]['session_fx']['backward_valid'])
        self.assertEqual(r['rows'][-1]['conversions'][m.MODES[0]]['reason'],'NO_SAME_SESSION_FX_ROW')
        self.assertEqual(r['rows'][-1]['conversions'][m.MODES[1]]['nav_usd_exact'],'11')

    def test_context_and_long_decimal_exact(self):
        a=fixture();a['nav_rows'][0]['nav_cny_decimal']='70.0000000000000000000001'
        expected=m.align_nav_usd_observations(**a);context=Context(prec=2);context.traps[Inexact]=True
        with localcontext(context):actual=m.align_nav_usd_observations(**a)
        self.assertEqual(actual,expected);self.assertEqual(Fraction(actual['rows'][0]['conversions'][m.MODES[0]]['nav_usd_exact']),Fraction(a['nav_rows'][0]['nav_cny_decimal'])/7)

    def test_dates_values_directions_refs_authority_reject(self):
        changes=[lambda a:a['fx_rows'][1].update(date=a['fx_rows'][0]['date']),lambda a:a['nav_rows'].reverse(),lambda a:a['fx_rows'][0].update(rate_decimal=True),lambda a:a['nav_rows'][0].update(nav_cny_decimal=float('nan')),lambda a:a['fx_context'].update(rate_direction='USD_PER_CNY'),lambda a:a['fx_context'].update(historical_available_at_verified=True),lambda a:a['fx_rows'][0]['source_reference'].update(path='other.html'),lambda a:a['nav_rows'][0]['source_reference'].update(sha256='b'*64),lambda a:a['fx_rows'][2].update(rate_decimal='7'),lambda a:a['fx_rows'][0].update(historical_available_at='2026-03-20')]
        for change in changes:
            with self.subTest(change=change):
                a=fixture();change(a)
                with self.assertRaises(ValueError):m.align_nav_usd_observations(**a)

if __name__=='__main__':unittest.main()
