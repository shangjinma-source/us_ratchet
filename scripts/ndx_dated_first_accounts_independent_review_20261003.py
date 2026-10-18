"""First dated candidate/control accounting; independent Fraction, no engine imports.

Bounded to the newly saved single-decision, action-free pair. This verifies the
saved basket and its actual execution, not the optimizer's global search.
"""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/dated_account_execution_20261003_v1'
TASK='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
POSTS={'candidate':('candidates/'+TASK,'2ff8d2dcb8a31de960c6ff285c5da71e4d63c91b0458b8813a20e9096fc46e9e'),'incumbent':('incumbent','6d5974d0d257b772963f8d81c95246a80072dd9381d8c5d3175e7d67ab07b8b4')}
RUNNER='33752035971557f2ae1d273bd9424f293c9d4530938bee4bae44581cfab496cd'
INPUT='ac0201e24925dff189d25e4fb5f0a8c741d567c31060f2aa48e3e2232fd90409'
INPUTPUB='c1f4ed8910725b5451c3cfa63f9545ded929f36d9abdba9586b3fe086386ff60'
INPUTAUDIT='396b45c1eec5a3fa0f2441744d409c0642eb21d2f6719da33725360707e114a3'
SEEN={}
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def eq(a,b):assert enc(a)==enc(b)
def read(ref):
 p=ref['path'];h=ref['sha256'];assert p not in SEEN or SEEN[p]==h
 b=Path(p).read_bytes();assert sha(b)==h;SEEN[p]=h;return json.loads(b)
def n(v):
 assert type(v) in (str,int,float);return F(str(v))
def near(actual,expected):assert abs(n(actual)-expected)<=F(1,10**7),(actual,str(expected))
def ratio(v):return {'numerator':str(v.numerator),'denominator':str(v.denominator)}
def positive_lots(v):
 assert type(v) is dict and all(type(q) is int and q>0 for q in v.values());return v

def risks(saved,shares,marks,chains,params,control):
 if not shares:
  eq(saved,dict(checks={'ALL_CASH':False},all_passed=False));return {'ALL_CASH':False}
 values={s:q*marks[s] for s,q in positive_lots(shares).items()};total=sum(values.values());weights={s:v/total for s,v in values.items()};ordered=sorted(weights.values(),reverse=True);groups={}
 for s,w in weights.items():groups[chains[s]]=groups.get(chains[s],F(0))+w
 neff=1/sum(w*w for w in weights.values());tol=F(1,10**9)
 checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=n(params['max_single_weight'])+tol,MIN_SINGLE_WEIGHT=ordered[-1]>=n(params['min_single_weight'])-tol,SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=n(params['top_weight_cap'])+tol,MINIMUM_EFFECTIVE_N=neff>=n(params['minimum_effective_n_ratio'])*len(weights)-tol,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=n(params['risk_chain_top1_cap'])+tol)
 eq(saved['checks'],checks);assert saved['all_passed'] is all(checks.values())
 assert set(saved['actual_weights'])==set(weights)
 for s,v in weights.items():near(saved['actual_weights'][s],v)
 for k,v in dict(top1_weight=ordered[0],minimum_single_weight=ordered[-1],top3_weight=sum(ordered[:3]),effective_n=neff,risk_chain_top1_weight=max(groups.values())).items():near(saved[k],v)
 if control:
  assert saved['risk_is_order_gate'] is False
  eq(saved['financial_allocation_checks'],{'NONNEGATIVE_WHOLE_SHARES':True})
  eq(saved['positive_holding_count'],len(shares));eq(saved['target_slot_count'],len(shares));eq(saved['zero_share_security_ids'],[])
 return checks

def inspect(track):
 relative,h=POSTS[track];folder=BASE/relative
 assert {p.name for p in folder.iterdir()}=={'started.json','raw.json','postcheck.json'}
 post=read(dict(path=str(folder/'postcheck.json'),sha256=h))
 assert post['schema']=='DATED_ACCOUNT_POSTCHECK_V1' and post['status']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING' and post['error'] is None
 assert post['track']==track and post['numerical_task_id']==TASK
 started=read(post['started_reference']);raw=read(post['raw_reference']);state=started['state']
 assert started['schema']=='DATED_ACCOUNT_STARTED_V1' and raw['schema']=='DATED_ACCOUNT_RAW_V1'
 eq(raw['started_reference'],post['started_reference']);eq(raw['source_hashes'],state['source_hashes']);eq(raw['runtime'],state['runtime'])
 assert raw['status']=='ACCOUNT_RETURNED' and raw['error'] is None
 eq(raw['engine_call_attempt_count'],1);eq(raw['returned_account_count'],1);eq(started['planned_engine_call_count'],1)
 assert state['track']==track and state['numerical_task_id']==TASK and state['blocked_nonpositive'] is False
 assert state['source_hashes'][str(ROOT/'scripts/ndx_dated_account_execution_20261003.py')]==RUNNER
 for path,digest in state['source_hashes'].items():
  assert path not in SEEN or SEEN[path]==digest;assert sha(Path(path).read_bytes())==digest;SEEN[path]=digest
 assert state['inputs_reference']['sha256']==INPUT and state['publication_reference']['sha256']==INPUTPUB and state['input_readback_reference']['sha256']==INPUTAUDIT
 doc=read(state['inputs_reference']);publication=read(state['publication_reference']);audit=read(state['input_readback_reference'])
 eq(publication['inputs_reference'],state['inputs_reference']);eq(audit['inputs_reference'],state['inputs_reference']);eq(audit['publication_reference'],state['publication_reference']);assert audit['status']=='PASS'
 inputs=doc['inputs'];t=inputs[track];eq(t,state['account']);eq(inputs['original_task'],state['original_task']);eq(inputs['calendar'],state['calendar']);eq(doc['task_reference'],state['task_reference'])
 eq(state['engine_security_keys'],inputs['engine_security_keys']);eq(state['candidate_normalization_evidence'],inputs['candidate_engine_normalization_evidence'])
 shared=dict(account={k:inputs['incumbent'][k] for k in ('matrices','schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date','external_cashflows','initial_holdings','risk_parameters')},original_control=inputs['original_incumbent_definition'],calendar=inputs['calendar'])
 eq(state['common_incumbent_definition'],shared);assert sha(enc(shared))==state['common_incumbent_identity']==post['common_incumbent_identity']
 eq(post['display_original_ticker_by_security'],t['original_ticker_by_security'])
 account=raw['account'];control=track=='incumbent';calendar=inputs['calendar'];assert len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[1]=='2026-03-23' and calendar[-1]=='2026-09-21'
 assert account['schema']==('ndx_dynamic_frozen_incumbent_control_v1' if control else 'ndx_dynamic_frozen_execution_research_v2')
 for field in ('corporate_actions','identity_events'):eq(account[field],[]);eq(t[field],[])
 eq(t['external_cashflows'],[]);eq(t['initial_holdings'],{})
 for k in ('point_in_time_verified','promotion_allowed','source_authenticity_verified','dividend_modelled','auto_replan_enabled','corporate_action_coverage_verified'):assert account[k] is False
 for path,digest in account['source_hashes'].items():assert state['source_hashes'][path]==digest
 assert account['execution_policy']=='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET'
 if control:
  assert account['risk_is_order_gate'] is False and account['original_target_weights_modified'] is False
 schedule=deepcopy(t['schedule']);assert len(schedule)==1
 targets=schedule[0]['targets'];total=sum(float(v['target_weight']) for v in targets.values())
 if not control:
  for v in targets.values():v['target_weight']=float(v['target_weight'])/total
  eq({s:v['target_weight'] for s,v in targets.items()},state['candidate_normalization_evidence']['effective_weights'])
 else:eq({r['security_id']:r['target_weight'] for r in inputs['original_incumbent_definition']},{s:r['target_weight'] for s,r in targets.items()})
 sids=list(targets);aliases=t['engine_ticker_by_security'];params=t['risk_parameters'];chains=t['risk_chains_by_decision'][calendar[0]]
 assert len({v['issuer_id'] for v in targets.values()})==len(sids)
 marks={day:{} for day in calendar};cells=0
 for sid in sids:
  rows=t['exact_quote_conversion_evidence'][sid];assert [r['session'] for r in rows]==calendar
  for i,row in enumerate(rows):
   marks[calendar[i]][sid]={}
   for field in ('open','close'):
    e=row[field];value=F(e['exact']);assert float(value)==e['value'] and float(value).hex()==e['float_hex']
    mat=t['matrices'][field];eq(mat['index'],calendar);j=mat['columns'].index(aliases[sid]);assert mat['data'][i][j]==e['value'];cells+=1;marks[calendar[i]][sid][field]=value
 assert [r['session'] for r in account['daily']]==calendar and len(account['decisions'])==len(account['executions'])==1
 decision=account['decisions'][0];fill=account['executions'][0]
 for key in ('decision_date','execution_date','targets'):eq(decision[key],schedule[0][key])
 assert decision['status']=='FROZEN' and decision['projection'] is None and decision['shares_before']=={}
 desired=positive_lots(decision['desired_shares']);assert set(desired)==set(sids);eq(decision['delta'],desired);eq(decision['target_k'],len(sids));near(decision['cash_before_usd'],F(25000))
 eq(decision['risk_chains'],chains);eq(decision['risk_chain_observation_dates'],dict.fromkeys(sids,calendar[0]))
 closemarks={s:marks[calendar[0]][s]['close'] for s in sids};openmarks={s:marks[calendar[1]][s]['open'] for s in sids}
 # This actual pair had no repair projection. Check its original floor independently.
 floor={s:int(F(24900)*n(targets[s]['target_weight'])/closemarks[s]) for s in sids};eq(desired,floor)
 rate=F(1,1000);closegross=sum(desired[s]*closemarks[s] for s in sids);open_gross=sum(desired[s]*openmarks[s] for s in sids)
 for s in sids:near(decision['prices'][s],closemarks[s]);near(fill['prices'][s],openmarks[s])
 near(decision['projected_fees_usd'],closegross*rate);near(decision['projected_cash_usd'],F(25000)-closegross*(1+rate))
 decision_checks=risks(decision['decision_risk'],desired,closemarks,chains,params,control)
 assert control or all(decision_checks.values())
 open_checks=risks(fill['risk'],desired,openmarks,chains,params,control)
 projected=F(25000)-open_gross*(1+rate);reasons=[] if control else [k for k,v in open_checks.items() if not v]
 if projected<F(100)-F(1,10**8):reasons.append('CASH_BUFFER')
 eq(fill['failure_reasons'],reasons);assert fill['status']==('REJECTED' if reasons else 'FILLED')
 eq(fill['shares_before'],{});eq(fill['desired_shares'],desired);eq(fill['frozen_delta'],desired);assert fill['session']==calendar[1] and fill['decision_date']==calendar[0]
 near(fill['cash_before_usd'],F(25000));near(fill['projected_cash_usd'],projected);near(fill['projected_fees_usd'],open_gross*rate)
 shares={} if reasons else desired;cash=F(25000) if reasons else projected;fees=F(0) if reasons else open_gross*rate
 eq(fill['shares_after'],shares);near(fill['cash_after_usd'],cash)
 if not reasons:near(fill['accounting_error_usd'],F(0))
 trades=account['trades'];assert len(trades)==len(shares)
 for saved,sid in zip(trades,sorted(shares)):
  eq(saved['share_delta'],shares[sid]);assert saved['session']==calendar[1] and saved['security_id']==sid and saved['ticker']==aliases[sid]
  near(saved['price_usd'],openmarks[sid]);near(saved['transaction_cost_usd'],shares[sid]*openmarks[sid]*rate)
 values=[];risk_false=0
 for i,row in enumerate(account['daily']):
  holding={} if i==0 else shares;cashday=F(25000) if i==0 else cash
  eq(row['shares'],holding);eq(row['tickers'],{s:aliases[s] for s in holding});eq(row['risk_chains'],{s:chains[s] for s in holding});eq(row['risk_chain_observation_dates'],dict.fromkeys(holding,calendar[0]));assert set(row['prices'])==set(holding)
  cm={s:marks[calendar[i]][s]['close'] for s in holding}
  for s,v in cm.items():near(row['prices'][s],v)
  checks=risks(row['risk'],holding,cm,chains,params,control);risk_false+=not all(checks.values())
  value=cashday+sum(holding[s]*cm[s] for s in holding);near(row['cash_usd'],cashday);near(row['total_value_usd'],value);values.append(value)
 ret=values[-1]/25000-1;dd=max(F(0),max(1-values[j]/values[i] for i in range(127) for j in range(i,127)));summary=account['summary']
 near(summary['terminal_value_usd'],values[-1]);near(summary['path_return_net'],ret);near(summary['path_max_drawdown'],dd);eq(summary['session_count'],127);eq(summary['k_path'],[len(sids)]);eq(summary['all_cash_session_count'],127 if not shares else 1)
 for obj in (post,raw,started,state):
  for k in ('fit_performed','winner_selected','economic_comparison_performed','independent_accounting_readback_performed','promotion_allowed','point_in_time_verified','execution_authorized','future_independent_oos','untouched_holdout','retry_allowed'):assert obj[k] is False
 return dict(track=track,status='PASS',postcheck_reference=dict(path=str(folder/'postcheck.json'),sha256=h),raw_reference=post['raw_reference'],input_reference=state['inputs_reference'],days=127,quote_conversion_cells=cells,decision_count=1,execution_status=fill['status'],failure_reasons=reasons,trade_count=len(trades),cash_usd_exact=ratio(cash),fees_usd_exact=ratio(fees),terminal_value_usd_exact=ratio(values[-1]),return_exact=ratio(ret),maximum_drawdown_exact=ratio(dd),return_display=float(ret),maximum_drawdown_display=float(dd),terminal_shares=shares,daily_risk_false_count=risk_false,original_floor_matches=True,integer_search_reexecuted=False,common_incumbent_identity=state['common_incumbent_identity'])

def run():
 rows=[inspect(t) for t in ('candidate','incumbent')]
 assert rows[0]['common_incumbent_identity']==rows[1]['common_incumbent_identity']
 for p,h in SEEN.items():assert sha(Path(p).read_bytes())==h
 return dict(schema='DATED_FIRST_ACCOUNTS_INDEPENDENT_ACCOUNTING_READBACK_V1',status='PASS',reader_sha256=sha(Path(__file__).read_bytes()),rows=rows,source_hashes=SEEN,unique_source_count=len(SEEN),daily_rows=254,account_reexecution_performed=False,old_audit_repeated=False,original_raw_price_decode_performed=False,monetary_float_comparison_tolerance_usd='0.0000001',exact_fraction_accounting=True,corporate_actions_in_actual_pair=0,future_split_accounts_not_covered_by_this_reader=True,point_in_time_verified=False,promotion_allowed=False,formal_cohort_verified=False)

if __name__=='__main__':
 result=run();stem=ROOT/'DYNAMIC_DATED_FIRST_ACCOUNTS_INDEPENDENT_READBACK_20261003'
 with stem.with_suffix('.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
 a,b=result['rows'];md=f'''# 首个 dated 候选及共享原八账户独立会计读回

结论：PASS。独立 Fraction 核验 2×127 日、全部现金/整股/费用/风险/成交与拒单、原目标及候选单次 float 归一。直接来源去重 {result['unique_source_count']} 项，脚本 SHA `{result['reader_sha256']}`。

候选：3/20 冻结篮子五风险通过；3/23 Open 原冻结量的预计剩余现金低于100美元，整篮因 CASH_BUFFER 拒单。实际成交0、费用0，127日现金25000美元，收益/回撤均0。不得把拟交易费用当实际扣费。

原八控制：同一初始本金/日历，实际8笔成交；保留原始目标而未归一，风险仅观察。终值 {float(F(int(b['terminal_value_usd_exact']['numerator']),int(b['terminal_value_usd_exact']['denominator']))):.10f} 美元，收益 {b['return_display']:.12%}，最大回撤 {b['maximum_drawdown_display']:.12%}。MIN_SINGLE_WEIGHT 等观察失败没有伪造成控制拒单。

核验首点25000、Close冻结/次Open原量执行、全部254日保存价与原exact→float证据、实际0企业行为、来源及post/raw/started/input独读链。货币保存float与精确值容差1e-7美元；风险门使用原1e-9，现金缓冲使用原1e-8。没有调用生产引擎、重拟合或父raw审计；只验证本次无拆股的实际双账户，不声称验证未来含拆股账户或优化搜索最优。当前池/身份仍条件性，评价区间已消费，非未来OOS、非正式准入。
'''
 with stem.with_suffix('.md').open('x',encoding='utf-8') as f:f.write(md)
 print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'},ensure_ascii=False))
