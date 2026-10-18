import copy,json,unittest
from pathlib import Path
from backtest import ndx_conditional_single_window_account_arguments_research as m


def fixture(k=4):
    source=json.loads(Path('data/cache/research/latest_twenty_historical_inputs_20260919_v1/inputs.json').read_bytes())
    rows=source['candidate_coordinate_and_risk_rows'][:k]
    schedule=[dict(decision_date='2026-03-18',execution_date='2026-03-19',targets={r['security_id']:dict(ticker=r['ticker'],issuer_id=r['issuer_id'],target_weight=1./k) for r in rows})]
    risk={'2026-03-18':{r['security_id']:r['risk_chain'] for r in rows}}
    return dict(inputs=source,schedule=schedule,risk_chains_by_decision=risk)


class AccountArgumentsTests(unittest.TestCase):
    def test_real_source_dynamic_subset_original_control_exact_no_engine(self):
        for k in (1,4,14):
            args=fixture(k);value=m.assemble_account_arguments(**args)
            self.assertEqual(len(value['calendar']),127);self.assertEqual(value['calendar'][0],'2026-03-18')
            self.assertEqual(value['candidate']['arguments']['opens'].shape,(127,k))
            self.assertEqual(value['incumbent']['arguments']['opens'].shape,(127,8))
            expected={r['security_id']:r['target_weight'] for r in args['inputs']['incumbent_original_securities']}
            actual={sid:r['target_weight'] for sid,r in value['incumbent']['original_schedule'][0]['targets'].items()}
            self.assertEqual(actual,expected);self.assertFalse(value['incumbent']['risk_is_order_gate'])
            self.assertNotIn('identity_events',value['incumbent']['arguments'])
            self.assertEqual(value['contract'],m.CONTRACT)

    def test_wrong_identity_risk_clock_or_missing_price_rejected(self):
        for defect in ('issuer','risk','latest','missing','null','split'):
            args=fixture();sid=next(iter(args['schedule'][0]['targets']))
            if defect=='issuer':args['schedule'][0]['targets'][sid]['issuer_id']='wrong'
            elif defect=='risk':args['risk_chains_by_decision']['2026-03-18'][sid]='wrong'
            elif defect=='latest':args['schedule'][0]['decision_date']='2026-09-17'
            elif defect=='missing':args['inputs']['prices']['nominal_open']['data'].pop(150)
            elif defect=='null':args['inputs']['prices']['nominal_close']['data'][150][0]=None
            else:args['inputs']['prices']['submitted_full_split_events']['NFLX'].append({'session':'2026-04-01'})
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.assemble_account_arguments(**args)

    def test_control_definition_and_boolean_target_rejected(self):
        args=fixture();args['inputs']['incumbent_original_securities'][0]['extra']=True
        with self.assertRaises(ValueError):m.assemble_account_arguments(**args)
        args=fixture();sid=next(iter(args['schedule'][0]['targets']));args['schedule'][0]['targets'][sid]['target_weight']=True
        with self.assertRaises(ValueError):m.assemble_account_arguments(**args)
        args=fixture();sid=next(iter(args['schedule'][0]['targets']));args['schedule'][0]['targets'][sid]['target_weight']=0.
        with self.assertRaises(ValueError):m.assemble_account_arguments(**args)
        args=fixture();r=next(r for r in args['inputs']['candidate_coordinate_and_risk_rows'] if r['ticker']=='LRCX');r['cusip']='512807108'
        with self.assertRaises(ValueError):m.assemble_account_arguments(**args)


if __name__=='__main__':unittest.main()
