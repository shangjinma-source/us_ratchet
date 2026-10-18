import copy,unittest
import pandas as pd
from backtest import ndx_latest_conditional_panel_research as m

def fixture():
    calendar=[d.date().isoformat() for d in pd.bdate_range(end='2026-09-17',periods=127)]
    observed=[dict(ticker='T'+str(i),issuer_id='issuer:'+str(max(i,1)).zfill(10)) for i in range(101)]
    channels={};audits={};coordinates={};risks={};ref=[dict(path='synthetic-evidence',sha256='a'*64)]
    for row in observed[:3]:
        ticker=row['ticker'];i=int(ticker[1:]);cusip=str(i).zfill(9);sid='security:'+row['issuer_id'][7:]+':'+cusip
        value=dict(schema='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1',ticker=ticker,cutoff=calendar[-1],calendar=calendar,
            price_rows=[dict(session=d,nominal_close=100.) for d in calendar],
            price_returns=[dict(session=b,previous_session=a,declared_share_ratio='1',price_return=0.) for a,b in zip(calendar,calendar[1:])],
            liquidity=dict(status='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE',rows=[dict(session=d,raw_volume=1000000,dollar_volume='100000000') for d in calendar[-63:]],median_dollar_volume_usd='100000000',numerical_threshold_passed=True),minimum_median_dollar_volume_usd=50000000,**dict.fromkeys(m.CHANNEL_FALSE,False))
        channels[ticker]=value;audits[ticker]=dict(channel_sha256=m.canonical_sha(value),passed=True,source_references=ref)
        facts=dict(ticker=ticker,issuer_id=row['issuer_id'],security_id=sid,cusip=cusip,security_class='Class A' if i!=1 else 'Class B')
        coordinates[ticker]=dict(facts,dated_fact=dict(facts,dated_as_of='2026-01-01',source_references=ref),scope=m.SCOPE,assumed_window={'first':calendar[0],'last':calendar[-1]},latest_interval_verified=False,provider_binding_verified=False)
        risks[ticker]=dict(scope=m.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,historical_labels=['semiconductor_equipment'],risk_chain='semiconductor_equipment',source_references=ref,source_kind='LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION')
    return dict(observed_rows=observed,calendar=calendar,cutoff=calendar[-1],channels=channels,channel_audits=audits,coordinate_assumptions=coordinates,risk_assumptions=risks)

class PanelTests(unittest.TestCase):
    def test_dynamic_panel_and_issuer_unique_subsets(self):
        args=fixture();panel=m.assemble_conditional_panel(**args)
        self.assertEqual(panel['returns'].shape,(126,3));self.assertTrue(all(str(v)=='float64' for v in panel['returns'].dtypes))
        self.assertIsInstance(panel['returns'].index,pd.DatetimeIndex)
        self.assertEqual(len(panel['observed_provenance_and_missing']),101)
        ids=panel['universe']['security_id'].tolist()
        self.assertEqual(len(m.selected_mapping(panel,[ids[0]])),1)
        self.assertEqual(len(m.selected_mapping(panel,[ids[0],ids[2]])),2)
        with self.assertRaises(ValueError):m.selected_mapping(panel,ids[:2])
        del args['risk_assumptions']['T2'];self.assertEqual(m.assemble_conditional_panel(**args)['conditional_security_count'],2)
    def test_wrong_class_issuer_duplicate_and_privilege_rejected(self):
        for field,value in [('security_class','Class C'),('issuer_id','issuer:9999999999'),('latest_interval_verified',True)]:
            args=fixture();args['coordinate_assumptions']['T0'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.assemble_conditional_panel(**args)
        args=fixture();c=args['coordinate_assumptions'];c['T1']['security_id']=c['T0']['security_id'];c['T1']['cusip']=c['T0']['cusip'];c['T1']['dated_fact'].update(security_id=c['T0']['security_id'],cusip=c['T0']['cusip'])
        with self.assertRaises(ValueError):m.assemble_conditional_panel(**args)
    def test_missing_predecessor_and_false_certification_rejected(self):
        for change in ('date','privilege','nan'):
            args=fixture();v=args['channels']['T0']
            if change=='date':v['price_returns'][0]['previous_session']=args['calendar'][1]
            elif change=='privilege':v['security_identity_verified']=True
            else:v['price_returns'][0]['price_return']=float('nan')
            if change!='nan':args['channel_audits']['T0']['channel_sha256']=m.canonical_sha(v)
            with self.subTest(change=change),self.assertRaises(ValueError):m.assemble_conditional_panel(**args)
    def test_volume_block_and_conflicting_risk_retained(self):
        args=fixture();v=args['channels']['T0'];v['liquidity']=dict(status='BLOCKED_VOLUME_UNIT_UNKNOWN',rows=None,median_dollar_volume_usd=None,numerical_threshold_passed=None)
        args['channel_audits']['T0']['channel_sha256']=m.canonical_sha(v)
        args['risk_assumptions']['T1']['historical_labels']=['software','hardware']
        panel=m.assemble_conditional_panel(**args)
        self.assertEqual(panel['conditional_security_count'],1)
        self.assertIn('BLOCKED_VOLUME_UNIT_UNKNOWN',panel['observed_provenance_and_missing'][0]['blocking_reasons'])
        self.assertIn('UNKNOWN_OR_CONFLICTING_RISK_CHAIN',panel['observed_provenance_and_missing'][1]['blocking_reasons'])
        self.assertFalse(panel['source_assertions_authenticated']);self.assertFalse(panel['historical_six_input_training_ready'])

if __name__=='__main__':unittest.main()
