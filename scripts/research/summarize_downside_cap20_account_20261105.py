"""Only fully audited separate cap20 windows; QQQ gross receivable benchmark."""
import argparse,json
from fractions import Fraction as F
from pathlib import Path
from hashlib import sha256
from backtest.research_exact_fraction_json import loads
from scripts.research.summarize_downside_max10_20261105 import verify_qqq
from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
from scripts.research.summarize_ema20_market_20261105 import experience
ROOT=Path(__file__).resolve().parents[2]
def read(p):return loads(Path(p).read_bytes())
def read_metadata(p):return json.loads(Path(p).read_bytes())
def require(x,why):
 if not x:raise ValueError(why)
def check(pins):
 for p,h in pins.items():require(sha256((ROOT/p).read_bytes()).hexdigest()==h,'PIN:'+p)
def summarize(output):
 folder=ROOT/output;contract=read(folder/'contract.json');summary=read(folder/'summary.json');book=read(folder/'book.json');audit=read_metadata(folder/'independent_review.json');late=contract['window']=='2024_2026';n=646 if late else 753
 require(audit['status'] in ('INDEPENDENT_CAP20_ACCOUNT_PASS','INDEPENDENT_CAP20_CONDITIONAL_ACCOUNT_ARITHMETIC_PASS','INDEPENDENT_CAP20_ZERO_RECOVERY_CASH_PATH_PASS') and summary['status']==book['status']=='COMPLETE' and audit['sessions']==summary['completed_sessions']==summary['required_sessions']==len(book['daily_ledger'])==n,'FULL_AUDITED_WINDOW_ONLY');check(audit['source_hashes']);check(contract['source_hashes']);require(audit['book_sha256']==sha256((folder/'book.json').read_bytes()).hexdigest(),'CURRENT_BOOK')
 require(audit['window']==contract['window'] and audit['months_checked']==(31 if late else 36) and audit['trades_checked']==sum(r['event']=='ASSUMED_NEXT_OPEN_FILLED' for r in book['order_log']),'AUDIT_WINDOW_MONTH_TRADE_COUNTS')
 zero_recovery=bool(contract.get('azn_zero_recovery_assumption'));require(zero_recovery==(audit['status']=='INDEPENDENT_CAP20_ZERO_RECOVERY_CASH_PATH_PASS'),'ZERO_RECOVERY_STATUS_BINDING');conditional=bool(contract.get('conditional_assumption_dependency'));require(conditional==(audit['status']=='INDEPENDENT_CAP20_CONDITIONAL_ACCOUNT_ARITHMETIC_PASS'),'CONDITIONAL_STATUS_BINDING');require(audit.get('production_eligible') is False,'NO_AUTOMATIC_PRODUCTION_CLAIM')
 dates=read(folder/'execution_inputs.json')['document']['assembled']['session_dates'];name='old_continuous_baseline_20261026_v9' if late else 'recent_continuous_baseline_20261026_v7';qdir=ROOT/'tmp/qqq_fair_hold_20261105';qqq=read_metadata(qdir/(name+'.json'));manifest=read_metadata(qdir/'summary.json');qaudit=next(a for a in read_metadata(qdir/'independent_audit.json') if a['window']==name);verify_qqq(qqq,manifest,qaudit,dates)
 result=dict(status='COMPLETE_CAP20_ZERO_RECOVERY_CASH_PATH_COMPARISON' if zero_recovery else 'COMPLETE_CONDITIONAL_CAP20_RESEARCH_COMPARISON' if conditional else 'COMPLETE_AUDITED_CAP20_SEPARATE_WINDOW_COMPARISON',conditional_assumptions=audit['conditional_assumptions'],assumption_exposure=audit['assumption_exposure'],production_eligible=False,azn_zero_recovery_assumption=audit.get('azn_zero_recovery_assumption'),unvalued_fractional_rights=audit.get('unvalued_fractional_rights',[]),full_account_equity_certified=False,window=contract['window'],start=dates[0],end=dates[-1],limitations=['Two independent 20000 USD accounts, not stitched.', 'Retrospective conditional corporate-action evidence; not PIT or OOS certification.', 'QQQ integer buy-and-hold, gross dividends accrue without reinvestment.', 'Issuer payment calendar is not verified HSBC receipt.','2026 ends July 30; no terminal forced liquidation.'])
 if zero_recovery:result['limitations'].append('AZN half-share cash right remains unpaid and unvalued; zero recovery is an explicit assumption, and disposal costs are not modeled.')
 for label,current,rows in [('candidate',book,book['daily_ledger']),('qqq',qqq,qqq['ledger'])]:
  require([r['date'] for r in rows]==dates[1:],'COMPLETE_DATE_GRID');fills=[] if label=='qqq' else [o for o in current['order_log'] if o['event']=='ASSUMED_NEXT_OPEN_FILLED'];result[label]=metrics(rows,dates[0],1 if label=='qqq' else len(fills));result[label]['experience']=experience(rows,dates[0]);result[label]['years']={};prior=F(20000);previous=dates[0]
  for year in sorted({r['date'][:4] for r in rows}):
   ys=[r for r in rows if r['date'].startswith(year)];normalized=[dict(date=r['date'],equity=F(r['equity'])*20000/prior) for r in ys];period=metrics(normalized,previous,int(year==dates[1][:4]) if label=='qqq' else sum(f['date'].startswith(year) for f in fills));period.update(return_pct=float(F(ys[-1]['equity'])/prior-1)*100,start_equity=float(prior),end_equity=float(F(ys[-1]['equity'])),partial=year=='2026',experience=experience(normalized,previous));result[label]['years'][year]=period;prior=F(ys[-1]['equity']);previous=ys[-1]['date']
  counts=[sum(q>0 for q in row['shares'].values()) if isinstance(row['shares'],dict) else int(row['shares']>0) for row in rows];result[label]['maximum_actual_positions']=max(counts);result[label]['cash_only_sessions']=counts.count(0)
 paths=[folder/n for n in ('contract.json','summary.json','book.json','execution_inputs.json','independent_review.json')]+[qdir/n for n in (name+'.json','summary.json','independent_audit.json')]+[Path(__file__),ROOT/'scripts/research/summarize_downside_max10_20261105.py',ROOT/'scripts/research/summarize_cross_month_held_peak_20261105.py',ROOT/'scripts/research/summarize_ema20_market_20261105.py'];result['source_hashes']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths};check(result['source_hashes']);(folder/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf8');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();r=summarize(a.output);print(json.dumps(dict(status=r['status'],window=r['window'])))
