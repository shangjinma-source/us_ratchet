from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_bulk_history_requirements_research as module


def args():
    days=[];day=date(2026,9,21)
    while len(days)<520:
        if day.weekday()<5:days.append(day.isoformat())
        day-=timedelta(days=1)
    days.reverse();universe=[dict(security_id='S'+str(i),issuer_id='I'+str(max(0,i-1)),ticker='AAPL' if i==0 else 'T'+str(i)) for i in range(77)]
    ref=dict(path='/synthetic/source.json',sha256='a'*64)
    observations={r['ticker']:dict(observation_rows=[dict(session=d,missing_fields=[]) for d in days],raw_reference=ref,
        receipt_reference=dict(path='/synthetic/receipt.json',sha256='b'*64),decoded_sha256='c'*64,bridge_reference=ref,
        event_policy_bridge=dict(regular_floor=None,events=[]),identity_assumed_window=module.WINDOW.copy(),extra_original=dict(unknown_timestamp=None)) for r in universe}
    return dict(universe=universe,observed_provenance_and_missing=[dict(ticker=r['ticker'],original=True) for r in universe]+[dict(ticker='X'+str(i)) for i in range(24)],
        reference_calendar=dict(ticker='AAPL',dates=days,source_reference=ref),ticker_observations=observations,window_contract=deepcopy(module.CONTRACT))


class RequirementsTests(unittest.TestCase):
    def test_exact_window_boundaries_and_preservation(self):
        values=args();before=deepcopy(values);result=module.prepare_history_requirements(**values)
        self.assertEqual(values,before);self.assertEqual(result['ticker_observations_preserved'],values['ticker_observations'])
        for scenario,count,length in zip(result['scenarios'],(1,13),(253,505)):
            self.assertEqual(scenario['constructed_window_count'],count);self.assertEqual(scenario['expected_adjacent_return_count'],length-1)
            self.assertEqual(len(scenario['security_rows']),77)
            for w in scenario['windows']:
                self.assertEqual(len(w['training_return_end_dates']),126);self.assertEqual(len(w['evaluation_return_end_dates']),126)
                self.assertFalse(set(w['training_return_end_dates'])&set(w['evaluation_return_end_dates']))
                self.assertEqual(w['training_freeze_close_date'],w['evaluation_initial_close_date'])
                self.assertEqual(w['evaluation_return_predecessors'][0]['previous_session'],w['training_freeze_close_date'])
                self.assertFalse(w['final_cutoff_fitted_targets_may_be_reused'])
        self.assertEqual(result['scenarios'][1]['windows'][-1]['start_price_index'],252)
        self.assertEqual(result['scenarios'][0]['windows'][0]['required_price_dates'],result['scenarios'][1]['windows'][-1]['required_price_dates'])
        self.assertTrue(all(result[k] is False for k in module.FLAGS))

    def test_missing_shared_freeze_close_affects_both_roles_without_compression(self):
        values=args();day=values['reference_calendar']['dates'][-127]
        item=values['ticker_observations']['T1'];item['observation_rows']=[r for r in item['observation_rows'] if r['session']!=day]
        result=module.prepare_history_requirements(**values);scenario=result['scenarios'][0];row=scenario['security_rows'][1]['requirements'][0]
        self.assertEqual(row['missing_price_dates'],[day]);self.assertEqual(len(row['training_return_pairs_with_missing_close']),1)
        self.assertEqual(len(row['evaluation_return_pairs_with_missing_close']),1)
        self.assertIn(day,scenario['windows'][0]['required_price_dates']);self.assertEqual(len(scenario['security_rows']),77)

    def test_floor_checks_first_predecessor_and_fields_are_preserved(self):
        values=args();initial=values['reference_calendar']['dates'][-253];floor=values['reference_calendar']['dates'][-252]
        item=values['ticker_observations']['T1'];item['event_policy_bridge']['regular_floor']=floor
        next(r for r in item['observation_rows'] if r['session']==floor)['missing_fields']=['volume']
        row=module.prepare_history_requirements(**values)['scenarios'][0]['security_rows'][1]['requirements'][0]
        self.assertEqual(row['forbidden_pre_partition_price_dates'],[initial]);self.assertEqual(len(row['training_return_pairs_crossing_or_before_partition']),1)
        self.assertTrue(row['saved_close_metadata_complete']);self.assertFalse(row['saved_date_and_field_metadata_complete'])
        self.assertTrue(row['identity_assumption_extension_required']);self.assertTrue(row['risk_assumption_extension_required'])

    def test_bad_lengths_duplicates_implicit_extension_and_refused_filter(self):
        mutations=[lambda v:v['window_contract'].update(fit_return_rows=True),
            lambda v:v['window_contract'].update(price_window_lengths=[253,506]),
            lambda v:v['universe'].pop(),lambda v:v['observed_provenance_and_missing'].pop(),
            lambda v:v['ticker_observations']['T1']['observation_rows'].append(v['ticker_observations']['T1']['observation_rows'][-1]),
            lambda v:v['ticker_observations']['T1'].update(identity_assumed_window={'first':'2020-01-01','last':'2026-09-21'}),
            lambda v:v['reference_calendar']['dates'].pop(0)]
        for mutate in mutations:
            values=args();mutate(values)
            with self.assertRaises((ValueError,KeyError)):module.prepare_history_requirements(**values)

    def test_calendar_shortfall_retains_every_security(self):
        values=args();days=values['reference_calendar']['dates'][-253:];values['reference_calendar']['dates']=days
        values['ticker_observations']['AAPL']['observation_rows']=values['ticker_observations']['AAPL']['observation_rows'][-253:]
        result=module.prepare_history_requirements(**values);long=result['scenarios'][1]
        self.assertFalse(long['reference_calendar_complete']);self.assertEqual(long['constructed_window_count'],0)
        self.assertEqual(len(long['security_rows']),77);self.assertTrue(all(r['reference_price_date_deficit']==252 for r in long['security_rows']))
        self.assertEqual(result['scenarios'][0]['constructed_window_count'],1)


if __name__=='__main__':unittest.main()
