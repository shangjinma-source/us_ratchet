from copy import deepcopy
import unittest
from backtest import ndx_multidecision_h_workbook_display_v2_research as m
from backtest.ndx_multidecision_daily_chain_projection_research import build_chain_projection
from backtest.ndx_saved_chain_weight_aggregation_research import aggregate_saved_weights
from test_ndx_multidecision_daily_chain_projection_research import fixture as chain_fixture


def fixture():
    args=chain_fixture();s=args['supplement_document'];d=args['diagnostics_document'];calendar=s['supplement']['calendar']
    ratio=dict(numerator='1',denominator='1')
    for path in d['paths']:
        for row in path['projection']['rows']:
            diag=row['diagnostic'];empty=diag['metrics']is None
            diag.update(status='EMPTY_HOLDINGS_UNDEFINED'if empty else'DERIVED_SAVED_DECIMAL_DIAGNOSTIC',security_weights={}if empty else{'SID':deepcopy(ratio)},label_observations={}if empty else{'SID':dict(label='CHAIN',observation_session=calendar[0])})
            if not empty:diag['metrics']={key:deepcopy(ratio)for key in ('hhi','effective_n','top1_weight','top3_weight','minimum_single_weight','risk_chain_top1_weight')}
            row['source_locator_tokens']={}if empty else{'SID':dict(price_tokens=['closes',row['daily_index']])}
    chain=build_chain_projection(**args,aggregate_saved_weights=aggregate_saved_weights)
    hold=[]
    for role in ('candidate','control'):
        for index,bundle in enumerate(s['supplement']['original_raw_bundles_preserved'][role]):
            if bundle is None:continue
            for day in bundle['document']['result']['daily']:
                if not(day.get('shares')or day.get('holdings')):continue
                hold.append([role,index,'FX','lane','track',day['session'],'SID','真实股票','发行人','内部别名','1','identity','raw'])
    saved_names=['原身份与内部列分离','控制原目标','完整每日原记录','每日SID原持仓','每日原风险与缺口']
    for i,name in enumerate(saved_names):s['supplement']['tables'][i]=dict(name=name,headers=['原值'],rows=[['完整合成行']])
    s['supplement']['tables'][3]=dict(name='每日SID原持仓',headers=['角色','轨道序号','FX','lane','账户轨','日期','SID','真实ticker','issuer','内部列名','原数量文本','身份来源','RAW来源'],rows=hold)
    metrics=[];curves=[];modes=['严格同日汇率','向前取最近有效汇率'];lanes=['收益','尾部','回撤','目标包络'];tracks=['连续权重','整股']
    for index in range(16):
        labels=[index,modes[index//8],lanes[(index%8)//2],tracks[index%2]]
        for role in ('候选','原八只控制'):
            blocked=role=='候选'and index<8
            metrics.append(labels+[role,'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'if blocked else'SAVED_PATH_DIAGNOSTIC',None if blocked else'1/10',None if blocked else'0.1234567890123456789',None if blocked else'1/20'])
            if not blocked:curves.extend(labels+[role,session,f'{100+n}/100']for n,session in enumerate(calendar))
    for mode in modes:curves.extend([None,mode,None,None,'012922参考',session,f'{100+n}/100']for n,session in enumerate(calendar))
    names=['轨道与阻断','已存路径指标','到NAV的逐项距离','两种NAV参考','48个决策位置','已存归一轨迹','来源索引','范围与未晋级','候选原目标证券','已保存决策风险','决策逐SID原暴露']
    tables=[dict(name=name,headers=['原值'],rows=[['完整合成行']])for name in names]
    tables[1]=dict(name=names[1],headers=['轨道序号','汇率模式','目标lane','账户轨','角色','状态','累计收益精确分数','年化收益原Decimal文本','最大回撤精确分数'],rows=metrics)
    tables[5]=dict(name=names[5],headers=['轨道序号','汇率模式','目标lane','账户轨','角色','日期','归一净值精确分数'],rows=curves)
    presentation=dict(schema='MULTIDECISION_PATH_PRESENTATION_DOCUMENT_V1',input_references={'candidate_inputs':s['supplement']['references']['candidate_inputs']},presentation=dict(tables=tables,point_in_time_verified=False,promotion_allowed=False))
    return dict(presentation_document=presentation,supplement_document=s,diagnostics_document=d,chain_document=dict(schema='MULTIDECISION_DAILY_CHAIN_DOCUMENT_V1',projection=chain),references={**args['references'],'presentation':dict(path='presentation',sha256='d'*64),'chain':dict(path='chain',sha256='e'*64)})


class Tests(unittest.TestCase):
    def test_readable_views_all_original_rows_and_actual_curves(self):
        args=fixture();before=deepcopy(args);display=m.build_display(**args)
        self.assertEqual(args,before);self.assertEqual(len(display['tables']),25);self.assertEqual(len(display['charts']),16)
        self.assertEqual(sum(len(c['headers'])-1 for c in display['charts']),40)
        self.assertIsNone(display['tables'][0]['rows'][0][6]);self.assertEqual(display['tables'][0]['rows'][16][6],1)
        self.assertEqual(display['tables'][0]['rows'][16][7],'真实股票：100.00%')
        self.assertEqual(display['tables'][0]['rows'][16][8],'10.00%')
        self.assertEqual(display['tables'][2:13],args['presentation_document']['presentation']['tables'])
        self.assertEqual(display['tables'][13:19],args['supplement_document']['supplement']['tables'])
        self.assertEqual(display['charts'][0]['headers'],['日期','原八只控制（近似）','012922参考（近似）'])

    def test_missing_curve_tail_and_wrong_parent_rejected(self):
        args=fixture();args['presentation_document']['presentation']['tables'][5]['rows'].pop()
        with self.assertRaises(ValueError):m.build_display(**args)
        args=fixture();args['chain_document']['projection']['references']['supplement']['sha256']='f'*64
        with self.assertRaises(ValueError):m.build_display(**args)


if __name__=='__main__':unittest.main()
