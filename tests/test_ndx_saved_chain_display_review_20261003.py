from copy import deepcopy
from fractions import Fraction
import unittest
from backtest import ndx_saved_risk_chain_display_research as m
from backtest import ndx_dated_path_risk_display_research as projection
from test_ndx_dated_path_risk_display_research import fixture


def positive():
    args=fixture()
    day=args['document']['comparison']['tracks']['candidate_integer']['original_account_preserved']['daily'][1]
    day.update(shares={'candidate1':2,'candidate0':0},cash_usd=10000.,total_value_usd=25000.,risk={'actual_weights':{'candidate1':0.9999999999999999,'candidate0':0.0},'checks':{'MAX_SINGLE_WEIGHT':False}},risk_chains={'candidate1':None,'candidate0':'unclassified'},risk_chain_observation_dates={'candidate1':'2026-03-20','candidate0':'2026-03-20'})
    return projection.project_saved_comparison(**args)

class ReviewTests(unittest.TestCase):
    def test_exact_saved_total_unknown_zero_and_cash_not_risk_recompute(self):
        args=positive();before=deepcopy(args);result=m.project_chain_display(args)
        row=result['tracks']['candidate_integer']['rows'][1]
        self.assertEqual(row['aggregation']['saved_literal_total'],m.ratio(Fraction('0.9999999999999999')))
        self.assertEqual(row['aggregation']['security_count'],2)
        self.assertEqual(row['cash_fraction_display'],m.ratio(Fraction(2,5)))
        self.assertFalse(row['saved_risk']['checks']['MAX_SINGLE_WEIGHT'])
        self.assertFalse(result['risk_gate_recomputed']);self.assertEqual(args,before)

    def test_saved_sid_value_and_label_links_cannot_drift(self):
        for mode in ('weight','label','sid','empty','riskbool'):
            args=positive();risk=args['tracks']['candidate_integer']['risk_rows'][1]
            if mode=='weight':risk['security_exposures'][0]['saved_stock_weight']=0.5
            elif mode=='label':risk['security_exposures'][0]['risk_chain']='CERTIFIED_OTHER'
            elif mode=='sid':risk['security_exposures'][0]['security_id']='other'
            elif mode=='riskbool':risk['saved_risk']['checks']['MAX_SINGLE_WEIGHT']=0
            else:risk['security_exposures']=[]
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.project_chain_display(args)

    def test_missing_calendar_and_flags_are_not_caller_authority(self):
        for mode in ('missingday','missingvalue','invaliddate','normalized','source','executed'):
            args=projection.project_saved_comparison(**fixture(missing=True))
            if mode=='missingday':args['tracks']['candidate_integer']['calendar_slots'].pop()
            elif mode=='missingvalue':args['tracks']['candidate_integer']['calendar_slots'][0]['value']=0
            elif mode=='invaliddate':args['calendar'][0]='2026-03-00'
            elif mode=='normalized':args['weights_normalized']=True
            elif mode=='source':args['source_bytes_authenticated']=True
            else:args['account_executed']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.project_chain_display(args)

    def test_duplicate_sid_and_bool_denominator(self):
        entries=[dict(security_id='same',risk_chain=None,saved_value=0),dict(security_id='same',risk_chain='chain',saved_value=1)]
        with self.assertRaises(ValueError):m.grouped(entries)
        with self.assertRaises(ValueError):m.grouped([],defined=0)
        args=projection.project_saved_comparison(**fixture())
        args['tracks']['candidate_continuous']['path'][1]['security_rows'].append(deepcopy(args['tracks']['candidate_continuous']['path'][1]['security_rows'][0]))
        with self.assertRaises(ValueError):m.project_chain_display(args)

if __name__=='__main__':unittest.main()
