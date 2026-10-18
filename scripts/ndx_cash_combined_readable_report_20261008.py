"""Create-only literal projection of independently audited forty-case comparisons."""
import argparse,hashlib,json,os
from collections import Counter,defaultdict
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/cash_neighbor_combined_path_comparison_20261008_v1'
AUDIT_ROOT=ROOT/'data/cache/research/cash_neighbor_combined_path_comparison_independent_readback_20261008_v1'
OUTPUT=ROOT/'data/cache/research/cash_combined_readable_report_20261008_v1'
BOUND={'index':(PARENT/'index.json','d36303c57eb4643c841d019fca5dbf0caa95e964961b327fa4aa49bdaa4d7fb9'),'publication':(PARENT/'publication.json','2477e5eeea1014dcee9886e34cc1dedd69e269b9b6cf63a92ea4d73e26b4f0d0'),'audit':(AUDIT_ROOT/'independent_readback.json','11aa3998d8f710c54a5c584a2b4f3de0d2307c094f6ca49bf5540c8f7e9426b6'),'reader':(ROOT/'scripts/ndx_cash_neighbor_combined_path_comparison_independent_readback_20261008.py','f56c3f3ba06c7548595b9f84d2992320577ce3372180fad32654e47ace0a3bd7')}
LANES={'RETURN':'收益','BAD_TAIL':'坏尾部','DRAWDOWN':'回撤','LEGACY_TARGET_DISTANCE':'目标距离'}
ROLES={'candidate':'候选账户','same_flow_zero_trade_control':'同现金流零交易控制','same_flow_incumbent':'同现金流原组合','fund_012922_cny_nav_reference':'012922 人民币净值参考'}
FALSE=('financial_recomputation_performed','account_executed','selection_reexecuted','cross_window_ranking_performed','formal_dual_benchmark_admission','currency_fx_equivalence_verified','point_in_time_verified','promotion_allowed','fresh_oos_claimed')
LIMITS='仅投影已审历史诊断；不跨短窗口或不等窗口平均、排行。012922为人民币净值参考，不是同现金流可执行账户；汇率等价、净值发布时间和候选决策时可执行性未验证。候选使用执行日开盘条件搜索后持有，原组合使用前收盘冻结并后续月调，信息集不对称。人读TWR/DD、原年化Decimal与差值仅用Decimal ROUND_HALF_EVEN格式化到百分比4位；sidecar保留原分数/原Decimal及字段指针，不转浮点、不重新计算收益或风险。差值单位为百分点（pp）；DD差为正表示候选回撤更深。非零数值舍入到零时显示带符号的小量提示，只有精确零显示0.0000。年化仅为短窗口诊断，不能作为长期证据或晋级结论。'
def require(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def file_sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def merge(sources,path,digest):
 require(type(digest) is str and len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'Pending source anchor')
 path=str(path);require(path not in sources or sources[path]==digest,'Source conflict');sources[path]=digest

def guard(sources):
 require(file_sha(SOURCE)==LOADED,'Report source drift')
 for path,digest in sources.items():
  require(file_sha(path)==digest,'Source SHA '+path);require(not (Path(path).parent/'failure.json').exists(),'Failed source namespace')
def fraction(value):
 require(type(value) is dict and set(value)=={'numerator','denominator'},'Original fraction required')
 for key in value:require(type(value[key]) is str and value[key].lstrip('-').isdigit(),'Original integer text')
 require(int(value['denominator'])>0,'Positive denominator');return value['numerator']+'/'+value['denominator']
def percentage(value,*,difference=False):
 unit=' pp' if difference else '%'
 if type(value) is dict:
  fraction(value);n=value['numerator'];d=value['denominator']
  with localcontext() as ctx:
   ctx.prec=len(n)+len(d)+40;ctx.rounding=ROUND_HALF_EVEN;scaled=Decimal(n)*100/Decimal(d);rounded=scaled.quantize(Decimal('0.0001'))
 else:
  require(type(value) is str,'Original Decimal string');original=Decimal(value);require(original.is_finite(),'Finite original Decimal')
  with localcontext() as ctx:
   ctx.prec=max(len(original.as_tuple().digits),original.adjusted()+1,0)+40;ctx.rounding=ROUND_HALF_EVEN;scaled=original*100;rounded=scaled.quantize(Decimal('0.0001'))
 if scaled==0:return '0.0000'+unit
 if rounded==0:return ('负且绝对值 < ' if scaled<0 else '正且 < ')+'0.0001'+unit
 return format(rounded,'f')+unit
def cell(value):return str(value).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','&#124;').replace('\n','<br>')
def project(row,descriptor):
 i=descriptor['scenario_index'];require(type(i) is int and row['scenario_index']==i and row['scenario_id']==descriptor['scenario_id'],'Original row identity')
 case=row['original_case_evidence'];original=case['input_row'];event=original['cash_event'];lane=original['lane'];require(lane in LANES,'Original lane')
 require(row['candidate_status'] in ('AVAILABLE_NEW','AVAILABLE_REUSED'),'Audited available path required')
 require(all(row[k] is False for k in ('account_executed','point_in_time_verified','formal_dual_benchmark_admission','cross_window_ranking_performed','currency_fx_equivalence_verified','nav_dataset_currency_binding_certified','nav_publication_time_verified','candidate_decision_time_executability_verified')) and row['short_and_unequal_windows_not_aggregated'] is True,'Original diagnostic limitations')
 candidate=case['candidate'];execution=event['execution_date'];days=[(j,v) for j,v in enumerate(candidate['account']['rows']) if v['session']==execution];sessions=[(j,v) for j,v in enumerate(candidate['accounting_inputs']['sessions']) if v['session']==execution]
 require(len(days)==len(sessions)==1,'Unique execution date');j,day=days[0];k,session=sessions[0];require(day['buy_shares']==session['buy_shares'],'Original buy cross reference')
 buys=[]
 for sid,q in day['buy_shares'].items():
  require(type(q) is int and q>=0,'Exact nonnegative buy shares')
  if q==0:continue
  identity=original['securities'][sid];require(type(identity['ticker']) is str and bool(identity['ticker']) and type(identity['issuer_id']) is str,'Saved true identity')
  buys.append(dict(security_id=sid,ticker=identity['ticker'],issuer_id=identity['issuer_id'],buy_shares=q,quantity_pointer=f'/original_case_evidence/candidate/account/rows/{j}/buy_shares/'+sid,identity_pointer='/original_case_evidence/input_row/securities/'+sid,request_quantity_pointer=f'/original_case_evidence/candidate/accounting_inputs/sessions/{k}/buy_shares/'+sid))
 metrics=[];differences=[]
 for role in ROLES:
  m=row['metrics'][role];require(m is not None,'Saved metrics required')
  metrics.append(dict(role=role,cumulative_return=m['cumulative_return'],maximum_drawdown=m['maximum_drawdown'],annualized_return_diagnostic_decimal=m['annualized_return_diagnostic_decimal'],source_pointer='/metrics/'+role,source_pointers={key:'/metrics/'+role+'/'+key for key in ('cumulative_return','maximum_drawdown','annualized_return_diagnostic_decimal')}))
  fraction(m['cumulative_return']);fraction(m['maximum_drawdown'])
  if role!='candidate':
   d=row['candidate_minus_references'][role];fraction(d['cumulative_return']);fraction(d['maximum_drawdown']);differences.append(dict(role=role,cumulative_return=d['cumulative_return'],maximum_drawdown=d['maximum_drawdown'],annualized_return_diagnostic_decimal=d['annualized_return_diagnostic_decimal'],source_pointer='/candidate_minus_references/'+role,source_pointers={key:'/candidate_minus_references/'+role+'/'+key for key in ('cumulative_return','maximum_drawdown','annualized_return_diagnostic_decimal')}))
 return dict(scenario_index=i,scenario_id=row['scenario_id'],lane=lane,decision_date=event['decision_date'],execution_date=execution,cash_amount_usd=event['amount_usd'],candidate_status=row['candidate_status'],buys=buys,metrics=metrics,differences=differences,jsonl_descriptor=descriptor,coordinate_pointer='/original_case_evidence/input_row',original_limitations={k:row[k] for k in ('policy_asymmetry','nav_currency','nav_is_same_flow_executable_account','currency_fx_equivalence_verified','nav_dataset_currency_binding_certified','nav_publication_time_verified','candidate_decision_time_executability_verified','short_and_unequal_windows_not_aggregated')})
def render(rows):
 text=['# 现金邻域：40 场景已审结果投影','',LIMITS,'','按原40行顺序展示；10个日期×现金金额坐标各4种目标，不重新排序。年化按原Decimal格式化显示，原字符串在JSON sidecar保留。','']
 for r in rows:
  text += [f"## {r['scenario_index']+1:02d} · {LANES[r['lane']]} · 决策 {r['decision_date']} / 执行 {r['execution_date']} · 注资 {r['cash_amount_usd']} USD",'', '状态：'+cell(r['candidate_status'])+'；场景：'+cell(r['scenario_id']),'','| 股票 | 证券SID | 买入股数 |','|---|---|---:|']
  text += ['| '+cell(b['ticker'])+' | '+cell(b['security_id'])+' | '+str(b['buy_shares'])+' |' for b in r['buys']] or ['| 无买入（原零数量） | — | — |']
  text += ['','| 原存角色 | 累计TWR | 最大回撤 | 年化（短窗口诊断） |','|---|---|---|---|']
  text += ['| '+ROLES[m['role']]+' | '+percentage(m['cumulative_return'])+' | '+percentage(m['maximum_drawdown'])+' | '+percentage(m['annualized_return_diagnostic_decimal'])+' |' for m in r['metrics']]
  text += ['','| 候选减参考 | 累计TWR差（pp） | 回撤差（正值更深，pp） | 年化诊断差（pp） |','|---|---|---|---|']
  text += ['| '+ROLES[m['role']]+' | '+percentage(m['cumulative_return'],difference=True)+' | '+percentage(m['maximum_drawdown'],difference=True)+' | '+percentage(m['annualized_return_diagnostic_decimal'],difference=True)+' |' for m in r['differences']]
  text += ['']
 return '\n'.join(text)+'\n'
def save(path,raw):
 with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(path.read_bytes()==raw,'Saved bytes');return dict(path=str(path),sha256=sha(raw))
def run():
 require(not OUTPUT.exists(),'Create-only report namespace');sources={str(SOURCE):LOADED};refs={}
 for role,(path,digest) in BOUND.items():merge(sources,path,digest);refs[role]=dict(path=str(path),sha256=digest)
 guard(sources);docs={k:json.loads(Path(r['path']).read_bytes()) for k,r in refs.items() if k!='reader'};index=docs['index'];pub=docs['publication'];audit=docs['audit']
 require(audit['schema']=='CASH_NEIGHBOR_PATH_COMPARISON_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['scenario_count']==40,'Actual independent audit PASS required')
 require(audit['index_reference']==pub['index_reference']==refs['index'] and audit['publication_reference']==refs['publication'] and audit['reader_sha256']==refs['reader']['sha256'],'Independent output links')
 require(all(audit['source_hashes'].get(refs[k]['path'])==refs[k]['sha256'] for k in ('index','publication','reader')),'Audited input source identities')
 require(index['source_hashes']==pub['source_hashes'] and index['consumed_candidate_sources']==audit['consumed_candidate_sources'],'Matching audited source closure')
 require(index['schema']=='SOURCE_BOUND_CASH_NEIGHBOR_PATH_COMPARISON_V1' and pub['schema']=='CASH_NEIGHBOR_PATH_COMPARISON_PUBLICATION_V1' and pub['status']=='PUBLISHED_PENDING_INDEPENDENT_READBACK','Comparison contract')
 for d in (index,pub,audit):
  for k in ('account_executed','point_in_time_verified','formal_dual_benchmark_admission','fresh_oos_claimed'):require(d[k] is False,'Source authority')
  for path,digest in d['source_hashes'].items():merge(sources,path,digest)
 for path,digest in audit['consumed_candidate_sources'].items():merge(sources,path,digest)
 jr=index['case_jsonl_reference'];require(jr['path']==str(PARENT/'cases.jsonl') and jr['record_count']==40,'Original JSONL');merge(sources,jr['path'],jr['sha256']);guard(sources)
 require({p.name for p in PARENT.iterdir()}=={'started.json','cases.jsonl','index.json','publication.json'} and {p.name for p in AUDIT_ROOT.iterdir()}=={'started.json','independent_readback.json'},'Exact successful input inventories')
 rows=[];offset=0;groups=defaultdict(list);counts=Counter();h=hashlib.sha256()
 require(len(index['cases'])==len(audit['cases'])==40,'Complete forty rows')
 with Path(jr['path']).open('rb') as f:
  for i,d in enumerate(index['cases']):
   raw=f.readline(32*1024*1024+1);require(raw.endswith(b'\n') and len(raw)<=32*1024*1024 and d['scenario_index']==i and d['byte_start']==offset and d['byte_stop']==offset+len(raw) and sha(raw)==d['row_sha256'],'Exact original row bytes')
   row=json.loads(raw);r=project(row,d);rows.append(r);groups[(r['decision_date'],r['execution_date'],r['cash_amount_usd'])].append(r['lane']);counts[r['candidate_status']]+=1;offset+=len(raw);h.update(raw)
  require(f.read(1)==b'' and offset==jr['byte_count'] and h.hexdigest()==jr['sha256'],'Full JSONL EOF')
 require(len(groups)==10 and all(sorted(v)==sorted(LANES) for v in groups.values()) and dict(counts)==index['candidate_status_counts']==audit['candidate_status_counts'],'Exact original domain and status')
 projection=dict(schema='CASH_COMBINED_LITERAL_REPORT_PROJECTION_V1',input_references=refs,jsonl_reference=jr,rows=rows,limitations=LIMITS,source_hashes=sources,**dict.fromkeys(FALSE,False));markdown=render(rows).encode('utf-8');guard(sources);OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  save(OUTPUT/'started.json',enc(dict(input_references=refs,source_hashes=sources)))
  pr=save(OUTPUT/'projection.json',enc(projection));mr=save(OUTPUT/'report.md',markdown);guard(sources)
  receipt=save(OUTPUT/'publication.json',enc(dict(schema='CASH_COMBINED_LITERAL_REPORT_PUBLICATION_V1',projection_reference=pr,report_reference=mr,input_references=refs,source_hashes=sources,**dict.fromkeys(FALSE,False))))
  guard(sources);require({p.name for p in OUTPUT.iterdir()}=={'started.json','projection.json','report.md','publication.json'},'Exact report inventory');return receipt
 except BaseException as e:
  save(OUTPUT/'failure.json',enc(dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False)));raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();require(args.execute,'Explicit report publication');print(json.dumps(run()))
