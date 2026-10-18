"""Fresh statistics, immature/missing outcomes and fake12-fit ordering only."""
from pathlib import Path
from datetime import date,timedelta
import hashlib,importlib.util,json,math,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'tmp/run_price_predictor_fixed_calibration_root_20261013_v1.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='6101fdee67223ace2bbd05f2cdc9f10551178652c26294b8eae5b8edb1c9eb35'
spec=importlib.util.spec_from_file_location('independent_fixedexperiment',SOURCE);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


class IndependentFixedExperiment(unittest.TestCase):
    def test_hand_metrics_signzero_average_ties_grouping(self):
        pred=[1.,1.,3.,4.];actual=[2.,4.,4.,0.];m=s.metric(pred,actual)
        self.assertEqual(s.ranks(pred),[1.5,1.5,3.,4.]);self.assertEqual(s.ranks(actual),[2.,3.5,3.5,1.])
        self.assertAlmostEqual(m['mae_log21'],2.25);self.assertAlmostEqual(m['rmse_log21'],math.sqrt(6.75));self.assertEqual(m['direction_accuracy'],.75)
        self.assertAlmostEqual(m['pearson_log21'],-4.5/math.sqrt(74.25));self.assertAlmostEqual(m['spearman_average_ranks'],-.5)
        self.assertEqual(s.metric([0.,1.,-1.],[0.,-1.,1.])['direction_accuracy'],1/3)
        degenerate=s.metric([0.,0.],[1.,2.]);self.assertIsNone(degenerate['pearson_log21']);self.assertIsNone(degenerate['spearman_average_ranks']);self.assertEqual(degenerate['correlation_degenerate_reason'],'ZERO_PREDICTION_VARIANCE')
        self.assertEqual(s.metric([],[])['correlation_degenerate_reason'],'FEWER_THAN_TWO_ROWS')
        calendar=[str(i)for i in range(22)];tickers=['ZZ','AA','CC','DD'];stocks=[dict(ticker=t,raw_close=[1.]*21+[math.exp(v)])for t,v in zip(tickers,actual)]
        forecast={'training_examples':[{'target_log_change_21':.2}], 'forecasts':[dict(ticker=t,status='CONDITIONAL_MODEL_PROJECTION',reasons=[],features=[.3,0,0,0],projection={'predicted_log_change_21':v})for t,v in zip(tickers,pred)]}
        diagnosis=s.diagnostics(forecast,{'calendar':calendar,'stocks':stocks,'controls':[]},0);groups=diagnosis['prediction_groups_low_to_high']
        self.assertEqual([g['tickers']for g in groups],[['AA'],['ZZ'],['CC'],['DD'],[]])
        self.assertAlmostEqual(groups[0]['mean_actual_log_price_change_21'],4.);self.assertAlmostEqual(groups[0]['mean_actual_simple_price_change_21'],math.expm1(4.));self.assertIsNone(groups[4]['mean_actual_log_price_change_21'])

    def test_future_unmatured_and_missing22prices_stay_null_before_reads(self):
        class Unreadable:
            def __getitem__(self,index):raise AssertionError('Unmatured future read')
        pending=s.outcome(Unreadable(),8,list(range(20)));self.assertEqual(pending['status'],'PENDING_21_OBSERVED_SESSIONS_NOT_MATURE');self.assertIsNone(pending['actual_log_change_21'])
        prices=[100.]*24;prices[11]=None;calendar=[f'd{i}'for i in range(24)]
        missing=s.outcome(prices,1,calendar);self.assertIsNone(missing['actual_log_change_21']);self.assertEqual(missing['missing_dates'],['d11'])
        prices[11]=100.;prices[22]=125.;observed=s.outcome(prices,1,calendar);self.assertAlmostEqual(observed['actual_log_change_21'],math.log(1.25));self.assertAlmostEqual(observed['actual_simple_price_change_21'],.25)

    def test_fake_one_extraction_all12saved_before_evaluation_and_latest_pending(self):
        calendar=[(date(2025,10,1)+timedelta(days=i)).isoformat()for i in range(377)]
        calendar=calendar[:calendar.index('2026-10-12')+1]
        panel=dict(target='2026-10-12',calendar=calendar,price_basis='CONDITIONAL_FAKE_ONLY',fixed_references={},stocks=[dict(ticker=f'X{i}',raw_close=[100.]*len(calendar),reasons=[],missing_dates=[],null_close_dates=[],unavailable_prefix_sessions=0,events_reference={})for i in range(101)],controls=[dict(ticker=t,raw_close=[100.]*len(calendar))for t in ('TSM','QQQ','SPY')])
        adapter_code=('import json\nPANEL=json.loads('+repr(json.dumps(panel))+')\nextractions=0\nFIXED_REFERENCES={}\ndef _read_fixed(*args):return b""\ndef load_current_close_panel(*,execute=False):\n global extractions\n extractions+=1\n if extractions>1:raise ValueError("second extraction")\n return PANEL\n').encode()
        predictor_code=b'calls=[]\ndef fit_predict_price_projection(**kw):\n calls.append(kw["cutoff_index"])\n if len(calls)>12:raise ValueError("fit13")\n if len(kw["prices_by_ticker"])!=101 or any(t in kw["prices_by_ticker"] for t in ("TSM","QQQ","SPY")):raise ValueError("controls leaked")\n return dict(status="FAKE_NOT_REAL_FIT",training_examples=[dict(target_log_change_21=0.)],forecasts=[dict(ticker=t,status="FAKE",reasons=[],features=[0.,0.,0.,0.],projection=dict(predicted_log_change_21=0.)) for t in sorted(kw["prices_by_ticker"])])\n'
        plan={'schema':'ROOT_FIXED_REAL_PRICE_PREDICTION_EXPERIMENT_V1','experiment':{'maximum_fit_calls':12,'maximum_actual_adapter_extractions':1,'outer_dates':['2026-03-20','2026-07-22','2026-10-12'],'inner_offsets_common_observations':[-84,-63,-42]}}
        def take(path,digest):
            if path==s.PLAN[0]:return json.dumps(plan).encode()
            if path==s.CODE['data.current_research_close_panel'][0]:return adapter_code
            if path==s.CODE['backtest.return_priority_price_predictor_research'][0]:return predictor_code
            return b'{}'
        with tempfile.TemporaryDirectory()as td:
            output=Path(td)/'output';diagnostic_calls=[];original=s.diagnostics
            def diagnosis(forecast,submitted,index):
                self.assertEqual(len(list(output.glob('fit_*_predictions.json'))),12)
                frozen=json.loads((output/'prediction_freeze_receipt.json').read_bytes());self.assertEqual(frozen['evaluation_calls_so_far'],0);self.assertEqual(len(frozen['references']),12)
                for ref in frozen['references']:self.assertEqual(hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest(),ref['sha256'])
                diagnostic_calls.append(index);return original(forecast,submitted,index)
            with patch.object(s,'OUT',output),patch.object(s,'take',side_effect=take),patch.object(s,'diagnostics',side_effect=diagnosis),patch.object(sys,'argv',['fixed','--execute-root-approved-fixed-predictor-experiment']),patch.dict(sys.modules,{},clear=False):s.main()
            result=json.loads((output/'result.json').read_bytes());self.assertEqual(result['actual_model_fit_calls'],12);self.assertEqual(result['source_extractions'],1);self.assertEqual(len(diagnostic_calls),12);self.assertEqual(result['portfolio_optimizer_calls'],0)
            latest=json.loads((output/'fit_12_diagnostics.json').read_bytes());self.assertEqual(latest['model_metrics']['count'],0);self.assertTrue(all(row['observed']['actual_log_change_21']is None for row in latest['rows']));self.assertTrue((output/'extracted_close_panel.json').exists())
            self.assertFalse(result['parameters_reselected']);self.assertFalse(result['current_adoption_allowed'])


if __name__=='__main__':unittest.main()
