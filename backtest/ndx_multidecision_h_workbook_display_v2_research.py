"""Readable workbook projection; only chart-display conversion is approximate."""
from copy import deepcopy
from fractions import Fraction
import json,math

SCHEMA='MULTIDECISION_H_WORKBOOK_DISPLAY_V2'
NOT_PROMOTED='尚未晋级：缺独立cohort P50/P10/P90、正式逐项非劣比较及新前瞻OOS/PIT证据。'
ROLES={'候选':'candidate','原八只控制':'control'}


def require(value,message):
    if not value:raise ValueError(message)


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def exact(a,b):require(encode(a)==encode(b),'Exact saved evidence')


def literal(value):
    if value is None:return None
    if type(value)is dict and set(value)=={'numerator','denominator'}:return value['numerator']+'/'+value['denominator']
    if type(value)is str:return value
    return encode(value)


def table(name,headers,rows):return dict(name=name,headers=headers,rows=rows)


def approximate(value,percent=False):
    if value is None:return None
    number=float(Fraction(literal(value)));require(math.isfinite(number),'Finite display approximation')
    return format(number*100 if percent else number,'.2f')+('%'if percent else '')


def build_display(*,presentation_document,supplement_document,diagnostics_document,chain_document,references):
    require(set(references)=={'presentation','supplement','diagnostics','chain'},'Four exact documents')
    for doc,schema in [(presentation_document,'MULTIDECISION_PATH_PRESENTATION_DOCUMENT_V1'),(supplement_document,'MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1'),(diagnostics_document,'CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1'),(chain_document,'MULTIDECISION_DAILY_CHAIN_DOCUMENT_V1')]:require(doc['schema']==schema,'Source document role')
    presentation=presentation_document['presentation'];supplement=supplement_document['supplement'];chain=chain_document['projection']
    for source in (presentation,supplement,diagnostics_document,chain):require(source['point_in_time_verified']is False and source['promotion_allowed']is False,'Conditional saved scope')
    exact(chain['references'],{key:references[key]for key in ('supplement','diagnostics')})
    exact(diagnostics_document['input_references']['inputs'],supplement['references']['candidate_inputs'])
    exact(presentation_document['input_references']['candidate_inputs'],supplement['references']['candidate_inputs'])
    calendar=supplement['calendar'];require(len(calendar)==120 and calendar==sorted(set(calendar)),'Full 120 sessions')
    exact(chain['calendar'],calendar)
    original=presentation['tables'];saved=supplement['tables'];require(len(original)==11 and len(saved)==6 and len(chain['tables'])==4,'All saved tables')
    metrics=original[1];curves=original[5];holdings=saved[3]
    require(metrics['name']=='已存路径指标'and curves['name']=='已存归一轨迹'and holdings['name']=='每日SID原持仓','Original table roles')
    require(len(metrics['rows'])==32 and len(curves['rows'])==3120,'Complete metrics and curves')
    exact([(row[0],row[4])for row in metrics['rows']],[(i,role)for i in range(16)for role in ROLES])
    exact([(p['role'],p['track_index'])for p in chain['paths']],[(role,i)for role in ('candidate','control')for i in range(16)])
    diagnostics={p['track_index']:p for p in diagnostics_document['paths']};exact(list(diagnostics),[8,10,12,14])
    last_holdings={}
    for row in holdings['rows']:
        if row[5]==calendar[-1]and row[6]is not None:
            key=(row[0],row[1],row[6]);require(key not in last_holdings,'Unique last-day SID');last_holdings[key]=row
    overview=[];positions=[]
    for metric in metrics['rows']:
        index,mode,lane,track,label,status,cumulative,annual,drawdown=metric;role=ROLES[label]
        bundle=supplement['original_raw_bundles_preserved'][role][index]
        chain_path=chain['paths'][(0 if role=='candidate'else 16)+index]
        if bundle is None:
            require(role=='candidate'and index<8 and status=='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'and chain_path['rows']is None,'Blocked has no invented account')
            ticker_weights='未执行：来源阻断';effective=None;chain_weights=None;basis='来源阻断，未执行账户';date_value=None;actual_k=None
        else:
            require(status=='SAVED_PATH_DIAGNOSTIC','Original returned metric status')
            day=bundle['document']['result']['daily'][-1];exact(day['session'],calendar[-1]);date_value=day['session']
            quantities=list(day['shares'].values())if index%2 else[item['shares']for item in day['holdings'].values()]
            require(all(type(q)in (int,float)and math.isfinite(q)and q>=0 for q in quantities),'Original finite nonnegative quantities')
            actual_k=sum(q>0 for q in quantities)
            chain_day=chain_path['rows'][-1];exact(chain_day['session'],date_value)
            basis=chain_day['basis'];chain_weights=None if chain_day['chain_weights']is None else '; '.join(f'{key}：{approximate(value,True)}'for key,value in chain_day['chain_weights'].items())
            if role=='candidate'and index%2==0:
                diagnostic=diagnostics[index]['projection']['rows'][-1]['diagnostic'];exact(diagnostic['session'],date_value)
                weights=diagnostic['security_weights'];effective=None if diagnostic['metrics']is None else literal(diagnostic['metrics']['effective_n'])
            else:
                risk=day['risk'];weights=risk.get('actual_weights',{});effective=literal(risk.get('effective_n'))
            entries=[]
            for (holding_role,holding_index,sid),h in last_holdings.items():
                if (holding_role,holding_index)!=(role,index):continue
                weight=literal(weights.get(sid));entries.append(f'{h[7]}：{approximate(weight,True) if weight is not None else "原值未提供"}')
                positions.append([mode,lane,track,label,date_value,sid,h[7],h[8],h[10],weight,basis,h[11],h[12]])
            ticker_weights='; '.join(entries)if entries else '空仓：股票权重与风险undefined'
        basis_label={'DERIVED_SUM_OF_SAVED_WHOLE_SID_WEIGHTS_NO_RENORMALIZATION':'原整股权重逐链相加，未重新归一','ORIGINAL_SAVED_CONTROL_CONTINUOUS_CHAIN_WEIGHTS':'原存控制连续链权重','PREVIOUSLY_AUDITED_CANDIDATE_CONTINUOUS_DERIVED_CHAIN_WEIGHTS':'已审候选连续派生链权重'}.get(basis,basis)
        overview.append([mode,lane,track,label,status,date_value,actual_k,ticker_weights,approximate(cumulative,True),approximate(annual,True),approximate(drawdown,True),approximate(effective),chain_weights,basis_label,NOT_PROMOTED])
    new_tables=[table('组合主视图',['汇率模式','目标类型','账户轨','角色','原状态','期末日期','期末实际持仓数k','期末真实股票及权重（展示近似）','累计收益（展示近似）','年化收益（展示近似）','最大回撤（展示近似）','期末有效N（展示近似）','期末逐链权重（展示近似）','链权重数值口径','未晋级原因'],overview),table('期末真实股票比例',['汇率模式','目标类型','账户轨','角色','日期','SID','真实ticker','issuer','原持仓数量文本','股票权重精确原文','权重数值口径','身份来源','RAW来源'],positions)]
    new_tables.extend(deepcopy(original+saved))
    for t in deepcopy(chain['tables']):
        if t['name']=='未执行阻断轨道':t['name']='链投影原阻断轨道'
        new_tables.append(t)
    daily_diagnostics=[];security_weights=[]
    metric_keys=['hhi','effective_n','top1_weight','top3_weight','minimum_single_weight','risk_chain_top1_weight']
    for path in diagnostics_document['paths']:
        for row in path['projection']['rows']:
            d=row['diagnostic'];prefix=[path['track_index'],*path['coordinate'],d['session'],d['status']]
            daily_diagnostics.append(prefix+[None if d['metrics']is None else literal(d['metrics'][key])for key in metric_keys]+[encode(d['chain_weights']),encode(row['source_locator_tokens'])])
            if not d['security_weights']:security_weights.append(prefix+[None,None,None,None,encode(row['source_locator_tokens'])])
            for sid,weight in d['security_weights'].items():
                observation=d['label_observations'][sid]
                security_weights.append(prefix+[sid,literal(weight),observation['label'],observation['observation_session'],encode(row['source_locator_tokens'][sid])])
    prefix=['轨道序号','FX','lane','账户轨','日期','原诊断状态']
    new_tables.extend([table('候选连续派生每日风险',prefix+['HHI精确分数','有效N精确分数','最大单股精确分数','前三股精确分数','最小单股精确分数','最大链精确分数','链权重原值JSON','来源'],daily_diagnostics),table('候选连续派生SID权重',prefix+['SID','权重精确分数','风险链','标签观察日','来源'],security_weights)])
    series={}
    for row in curves['rows']:
        key=tuple(row[:5]);series.setdefault(key,[]).append((row[5],row[6]))
    require(len(series)==26,'All 26 original numerical series')
    for values in series.values():exact([v[0]for v in values],calendar)
    charts=[]
    for index in range(16):
        base=metrics['rows'][2*index];mode,lane,track=base[1:4]
        keys=[(index,mode,lane,track,label)for label in ROLES if (index,mode,lane,track,label)in series]+[(None,mode,None,None,'012922参考')]
        require(len(keys)==(2 if index<8 else 3),'Blocked candidate has no zero curve')
        values=[[session]+[float(Fraction(series[key][n][1]))for key in keys]for n,session in enumerate(calendar)]
        require(all(math.isfinite(v)for row in values for v in row[1:]),'Finite approximate chart values')
        charts.append(dict(name=f'曲线{index+1:02d}_{lane}_{track}',track_index=index,
            title=f'{mode} · {lane} · {track}（近似图示）',note='原已审归一净值精确分数转binary64，仅用于图示；不重算收益。'+('候选来源阻断，未绘制候选曲线。'if index<8 else ''),
            headers=['日期']+[key[4]+'（近似）'for key in keys],rows=values,source_series_keys=[list(key)for key in keys]))
    return dict(schema=SCHEMA,tables=new_tables,charts=charts,references=deepcopy(references),original_curve_row_count=3120,original_curve_series_count=26,
        chart_conversion='BINARY64_APPROXIMATION_OF_SAVED_EXACT_FRACTIONS_FOR_DISPLAY_ONLY',main_view_rounding='TWO_DECIMAL_DISPLAY_ONLY_ORIGINAL_VALUES_PRESERVED_IN_EXACT_TABLES',financial_recomputation_performed=False,account_executed=False,point_in_time_verified=False,promotion_allowed=False,full_h_delivery_complete=False)
