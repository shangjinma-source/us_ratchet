from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_original_eight_scoring_inputs_research as m

def fixture():
    days=[];d=date(2023,1,2)
    while d<=date(2026,9,21):
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    ss=[dict(ticker=t,security_id='s'+t,issuer_id='i'+t,risk_chain='R',target_weight=1.) for t in m.ORDER];ss[4].update(security_id='security:incumbent_overlay:TSM',issuer_id='issuer:0001046179')
    definition=dict(securities=deepcopy(ss));control=dict(securities=ss,complete_original_definition=definition,complete_original_manifest=dict(definition=deepcopy(definition)),new_execution_contract_frozen=False)
    bindings=[]
    for i,s in enumerate(ss):
        ds=[]
        for cutoff in m.CUTOFFS:
            end=days.index(cutoff);ds.append(dict(cutoff=cutoff,price_index_start=end-504,required_price_dates=days[end-504:end+1]))
        rows=[dict(previous_session=a,session=b,split_only_return_exact=str((i+1)/100),split_only_return_float=(i+1)/100) for a,b in zip(days,days[1:])]
        ch=dict(schema='ORIGINAL_EIGHT_TSM_SCORING_HISTORY_CHANNEL_V1' if i==4 else 'MULTIDECISION_SCORING_HISTORY_CHANNEL_V1',ticker=s['ticker'],calendar=days,decisions=ds,return_rows=rows,**dict.fromkeys(('fit_performed','score_computed','point_in_time_verified','source_bytes_authenticated','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed'),False))
        if i==4:ch.update(role=m.__dict__.get('ROLE','CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE'),ndx_candidate_admitted=False,original_control_contract=dict(securities=deepcopy(ss)))
        ch['content_sha256']=m.digest(ch)
        bindings.append(dict(coordinate=deepcopy(s),channel=ch,channel_reference=dict(path='channel'+str(i),sha256='a'*64),independent_readback_reference=dict(path='audit'+str(i),sha256='b'*64)))
    return dict(original_control=control,control_reference=dict(path='control',sha256='c'*64),channel_bindings=bindings)

class Tests(unittest.TestCase):
    def test_fixed_daily_weights_full78_and_original_unchanged(self):
        a=fixture();before=deepcopy(a);r=m.prepare_original_eight_scoring_inputs(**a);self.assertEqual(a,before)
        self.assertEqual(r['normalized_scoring_weights'],dict.fromkeys(m.ORDER,.125));self.assertEqual(r['original_float_weight_sum'],8.)
        for d in r['decisions']:
            self.assertEqual(len(d['return_rows']),504);self.assertEqual(len(d['windows']),13)
            for row in d['return_rows']:self.assertAlmostEqual(row['return_float'],.045,places=15)
        self.assertFalse(r['entry_fee_applied']);self.assertFalse(r['score_computed']);self.assertFalse(r['source_bytes_authenticated'])
    def test_zero_weight_missing_still_blocks_and_not_daily_skipna(self):
        a=fixture();ss=a['original_control']['securities'];ss[0]['target_weight']=0
        a['original_control']['complete_original_definition']['securities']=deepcopy(ss);a['original_control']['complete_original_manifest']['definition']=deepcopy(a['original_control']['complete_original_definition'])
        for b,s in zip(a['channel_bindings'],ss):b['coordinate']=deepcopy(s)
        a['channel_bindings'][4]['channel']['original_control_contract']['securities']=deepcopy(ss)
        ch=a['channel_bindings'][0]['channel'];j=ch['decisions'][0]['price_index_start'];ch['return_rows'][j].update(split_only_return_exact=None,split_only_return_float=None)
        for b in a['channel_bindings']:
            c=b['channel'];c['content_sha256']=m.digest({k:v for k,v in c.items() if k!='content_sha256'})
        r=m.prepare_original_eight_scoring_inputs(**a);self.assertIsNone(r['decisions'][0]['return_rows'][0]['return_float']);self.assertEqual(r['decisions'][0]['windows'][0]['status'],'BLOCKED_WINDOW')
    def test_source_role_original_weight_and_order_conflicts(self):
        for change in [lambda a:a['channel_bindings'].reverse(),lambda a:a['channel_bindings'][4]['channel'].update(role='CANDIDATE'),lambda a:a['original_control']['securities'][0].update(target_weight=True),lambda a:a['channel_bindings'][0]['channel_reference'].update(path='control',sha256='d'*64)]:
            a=fixture();change(a)
            with self.assertRaises(ValueError):m.prepare_original_eight_scoring_inputs(**a)

    def test_resigned_exact_float_and_calendar_contradictions(self):
        for kind in ('exact_none','exact_wrong','negative_index','calendar_duplicate'):
            a=fixture();ch=a['channel_bindings'][0]['channel'];i=ch['decisions'][0]['price_index_start']
            if kind=='exact_none':ch['return_rows'][i]['split_only_return_exact']=None
            elif kind=='exact_wrong':ch['return_rows'][i]['split_only_return_exact']='999'
            elif kind=='negative_index':ch['decisions'][0]['price_index_start']=-505
            else:ch['calendar'][1]=ch['calendar'][0]
            ch['content_sha256']=m.digest({k:v for k,v in ch.items() if k!='content_sha256'})
            with self.assertRaises(ValueError):m.prepare_original_eight_scoring_inputs(**a)
