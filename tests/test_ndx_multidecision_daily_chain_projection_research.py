from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_multidecision_daily_chain_projection_research as m
from backtest.ndx_saved_chain_weight_aggregation_research import aggregate_saved_weights


def fixture():
    references={r:dict(path=r,sha256='a'*64)for r in ('supplement','diagnostics')}
    cal=[(date(2026,1,1)+timedelta(days=n)).isoformat()for n in range(120)]
    input_refs={r:dict(path=r,sha256='b'*64)for r in ('candidate_inputs','candidate_execution')}
    raw_bundles={};diag=[];blocked=[]
    for role in ('candidate','control'):
        raw_bundles[role]=[]
        for index in range(16):
            coordinate=[m.MODES[index//8],m.LANES[(index%8)//2],m.TRACKS[index%2]]
            if role=='candidate'and index<8:
                raw_bundles[role].append(None);blocked.append([role,index,*coordinate,'[]','source']);continue
            daily=[];diagnostic_rows=[]
            ref=dict(path=f'{role}-{index}',sha256='c'*64)
            for n,session in enumerate(cal):
                empty=n<(22 if role=='candidate'and index%2 else 1)
                weights={}if empty else {'SID':1.0}
                risk={'actual_weights':weights}
                if index%2:
                    day=dict(session=session,shares={}if empty else {'SID':1},risk=risk,risk_chains={}if empty else {'SID':'CHAIN'},risk_chain_observation_dates={}if empty else {'SID':cal[0]})
                else:
                    if not empty:risk['risk_chain_weights']={'CHAIN':1.0}
                    day=dict(session=session,holdings={}if empty else {'SID':dict(shares=1.0)},risk=risk)
                    if role=='candidate':diagnostic_rows.append(dict(daily_index=n,diagnostic=dict(session=session,metrics=None if empty else {},chain_weights={}if empty else {'CHAIN':dict(numerator='1',denominator='1')})))
                daily.append(day)
            raw_bundles[role].append(dict(reference=ref,document=dict(returned=True,error=None,result=dict(daily=daily))))
            if role=='candidate'and index%2==0:diag.append(dict(track_index=index,coordinate=coordinate,raw_reference=ref,projection=dict(rows=diagnostic_rows)))
    s=dict(schema='MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1',supplement=dict(schema='MULTIDECISION_SAVED_HOLDINGS_SUPPLEMENT_V1',point_in_time_verified=False,promotion_allowed=False,calendar=cal,references=input_refs,original_raw_bundles_preserved=raw_bundles,tables=[{}]*5+[dict(name='未执行阻断轨道',headers=['角色','轨道序号','FX','lane','账户轨','原阻断JSON','原执行槽来源'],rows=blocked)]))
    d=dict(schema='CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1',point_in_time_verified=False,promotion_allowed=False,paths=diag,blocked_track_indices=list(range(8)),input_references=dict(inputs=input_refs['candidate_inputs'],execution=input_refs['candidate_execution']))
    return dict(supplement_document=s,diagnostics_document=d,references=references)


class Tests(unittest.TestCase):
    def test_all_positions_and_all_three_bases(self):
        args=fixture();before=deepcopy(args);calls=[]
        def aggregate(**kw):calls.append(kw);return aggregate_saved_weights(**kw)
        result=m.build_chain_projection(**args,aggregate_saved_weights=aggregate)
        self.assertEqual(args,before);self.assertEqual(len(calls),1344)
        self.assertEqual([len(t['rows'])for t in result['tables']],[2880,2880,2880,8])
        self.assertEqual(sum(r['chain_weights']is None for p in result['paths']if p['rows']is not None for r in p['rows']),108)
        self.assertEqual(len(result['paths']),32)

    def test_missing_held_weights_future_dates_and_reordered_inputs(self):
        changes=[lambda x:x['supplement_document']['supplement']['original_raw_bundles_preserved']['candidate'][9]['document']['result']['daily'][22]['risk'].pop('actual_weights'),lambda x:x['diagnostics_document']['paths'].reverse(),lambda x:x['diagnostics_document']['paths'][0].update(raw_reference=dict(path='wrong',sha256='c'*64)),lambda x:x['supplement_document']['supplement']['original_raw_bundles_preserved']['control'][1]['document']['result']['daily'][1]['risk_chain_observation_dates'].update(SID='2027-01-01')]
        for change in changes:
            args=fixture();change(args)
            with self.assertRaises((KeyError,ValueError)):m.build_chain_projection(**args,aggregate_saved_weights=aggregate_saved_weights)
        args=fixture();args['supplement_document']['supplement']['original_raw_bundles_preserved']['control'][1]['document']['result']['daily'][1]['shares']['SID']=0
        with self.assertRaisesRegex(ValueError,'positive-holding'):m.build_chain_projection(**args,aggregate_saved_weights=aggregate_saved_weights)


if __name__=='__main__':unittest.main()
