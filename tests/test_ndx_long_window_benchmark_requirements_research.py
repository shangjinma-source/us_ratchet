"""Synthetic metadata-only tests; no saved prices/accounts consumed."""
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction
import unittest
from backtest import ndx_long_window_benchmark_requirements_research as core


def ref(path):
    return {'path':path,'sha256':'a'*64}


def fixture():
    days=[];d=date(2025,1,1)
    while len(days)<253:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    securities=[];stocks={}
    for ticker in ['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']:
        sid='security:incumbent_overlay:TSM' if ticker=='TSM' else 'security:'+ticker
        securities.append(dict(ticker=ticker,security_id=sid,issuer_id='issuer:'+ticker,risk_chain='risk:'+ticker,target_weight='0.12500000000000001'))
        raw=ref(ticker+'.raw')
        stocks[ticker]=dict(security_id=sid,raw_reference=raw,receipt_reference=ref(ticker+'.receipt'),observation_reference=ref('observations'),receipt_binding=dict(ticker=ticker,raw_reference=deepcopy(raw)),observation_rows=[dict(session=x,missing_fields=[]) for x in days],identity_evidence=[ref(ticker+'.identity')],risk_evidence=[])
    navref=ref('nav.csv')
    return dict(reference_calendar=dict(ticker='AAPL',dates=days,source_reference=ref('calendar')),original_control=dict(source_reference=ref('control'),securities=securities,definition={'capital':25000}),stock_metadata=stocks,nav_metadata=dict(source_reference=navref,manifest_reference=ref('nav.manifest'),snapshot_reference=ref('nav.snapshot'),rows=[dict(date=x,row_index=i,source_reference=deepcopy(navref)) for i,x in enumerate(days)],publication_time_known=False,selected_value_column='Close'),fx_metadata=dict(bound=False,source_reference=None))


class RequirementsTests(unittest.TestCase):
    def test_preserves_full_contract_and_split(self):
        args=fixture();saved=deepcopy(args);out=core.prepare_benchmark_requirements(**args)
        self.assertEqual(args,saved)
        self.assertEqual(out['original_control_preserved'],args['original_control'])
        self.assertEqual(out['original_control_order'],[r['ticker'] for r in args['original_control']['securities']])
        self.assertEqual(Fraction(out['original_target_weight_sum_exact']),Fraction('0.12500000000000001')*8)
        self.assertFalse(out['weights_normalized']);self.assertEqual(out['stock_date_requirement_count'],2024)
        self.assertEqual(len(out['training_return_end_dates']),126);self.assertEqual(len(out['evaluation_return_end_dates']),126)
        self.assertEqual(out['training_freeze_close_date'],args['reference_calendar']['dates'][126])
        self.assertFalse(set(out['training_return_end_dates'])&set(out['evaluation_return_end_dates']))
        self.assertTrue(next(r for r in out['stock_requirements'] if r['original_security']['ticker']=='TSM')['control_only'])
        for key in core.FLAGS:self.assertIs(out[key],False)

    def test_missing_stock_dates_and_fields_not_compressed(self):
        args=fixture();missing=args['stock_metadata']['NVDA']['observation_rows'].pop(126)['session']
        args['stock_metadata']['TSM']['observation_rows'][0]['missing_fields']=['open','close']
        out=core.prepare_benchmark_requirements(**args);stock=out['stock_requirements'][0]
        self.assertEqual(len(stock['requirements']),253);self.assertEqual(stock['missing_observation_dates'],[missing])
        self.assertIsNone(stock['requirements'][126]['saved_missing_fields'])
        self.assertEqual(out['stock_requirements'][4]['requirements'][0]['saved_missing_fields'],['open','close'])
        self.assertFalse(out['holdings_converted'])

    def test_nav_backward_only_and_no_prior(self):
        args=fixture();days=args['reference_calendar']['dates'];rows=args['nav_metadata']['rows']
        rows.pop(2);rows.pop(0)
        for i,row in enumerate(rows):row['row_index']=i
        out=core.prepare_benchmark_requirements(**args);mapped=out['nav_date_mappings']
        self.assertIsNone(mapped[0]['nav_date']);self.assertIsNone(mapped[0]['mapped_row_reference'])
        self.assertEqual(mapped[2]['nav_date'],days[1]);self.assertGreater(mapped[2]['lag_calendar_days'],0)
        for row in mapped:
            self.assertTrue(row['nav_date'] is None or row['nav_date']<=row['session'])
            self.assertIsNone(row['available_at']);self.assertFalse(row['publication_time_known'])

    def test_bad_dates_indexes_and_source_bindings(self):
        mutations=[lambda a:a['nav_metadata']['rows'][1].update(date=a['nav_metadata']['rows'][0]['date']),lambda a:a['nav_metadata']['rows'][0].update(row_index=False),lambda a:a['nav_metadata']['rows'][0].update(source_reference=ref('other.csv')),lambda a:a['stock_metadata']['NVDA']['receipt_binding'].update(ticker='TXN'),lambda a:a['stock_metadata']['NVDA']['raw_reference'].update(sha256='b'*64),lambda a:a['reference_calendar']['dates'].reverse()]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                args=fixture();mutate(args)
                with self.assertRaises(ValueError):core.prepare_benchmark_requirements(**args)

    def test_weight_boolean_nonfinite_and_source_conflict(self):
        for value in [True,float('nan'),float('inf'),'-0.1']:
            args=fixture();args['original_control']['securities'][0]['target_weight']=value
            with self.assertRaises(ValueError):core.prepare_benchmark_requirements(**args)
        args=fixture();args['original_control']['securities'][0]['target_weight']=0.125
        self.assertEqual(core.prepare_benchmark_requirements(**args)['original_control_preserved'],args['original_control'])
        args=fixture();args['nav_metadata']['manifest_reference']=dict(path='calendar',sha256='b'*64)
        with self.assertRaises(ValueError):core.prepare_benchmark_requirements(**args)

if __name__=='__main__':unittest.main()
