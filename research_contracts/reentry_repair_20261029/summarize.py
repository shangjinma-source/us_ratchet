"""Read-only result table; refuses candidate without full independent review."""
import json
from pathlib import Path
from fractions import Fraction as F
from datetime import date
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
rows=[];pins={}
for window,start,end in [('2021_2023','2020-12-31','2023-12-29'),('2024_2026','2023-12-29','2026-07-30')]:
 for arm in ['baseline','candidate']:
  folder=HERE/(arm+'_'+window);path=folder/'book.json';book=json.loads(path.read_bytes());assert book['status']=='COMPLETE'
  pins[path.relative_to(ROOT).as_posix()]=sha256(path.read_bytes()).hexdigest()
  if arm=='candidate':
   rpath=folder/'independent_result_review.json';r=json.loads(rpath.read_bytes());assert r['status']=='COMPLETE_DECLARED_INTERVAL_REVIEW_PASS';assert r['source_hashes'][path.relative_to(ROOT).as_posix()]==pins[path.relative_to(ROOT).as_posix()]
   pins[rpath.relative_to(ROOT).as_posix()]=sha256(rpath.read_bytes()).hexdigest()
  equity=[(start,F(20000))]+[(v['date'],F(v['equity'])) for v in book['daily_ledger']]
  high=equity[0][1];highday=start;dd=F(0);peak=start;trough=start
  for day,value in equity:
   if value>high:high=value;highday=day
   if 1-value/high>dd:dd=1-value/high;peak=highday;trough=day
  total=equity[-1][1]/20000-1;assert total==F(book['total_return']);assert dd==F(book['drawdown']['maximum_close_drawdown'])
  years=(date.fromisoformat(end)-date.fromisoformat(start)).days/365.25
  audits=book.get('reentry_audit',[])
  rows.append(dict(window=window,arm=arm,ending_equity=float(equity[-1][1]),total_return=float(total),cagr=(1+float(total))**(1/years)-1,maximum_close_drawdown=float(dd),drawdown_peak=peak,drawdown_trough=trough,assumed_fills=sum(x.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for x in book['order_log']),filtered_buy_orders=sum(len(a['original']['orders'])-len(a['adjusted']['orders']) for a in audits),recovery_releases=sum(x['recovered_at'] is not None for a in audits for x in a['interval_reviews']),remaining_locks=len(book.get('reentry_locks',{}))))
result=dict(status='FULL_TWO_WINDOW_INDEPENDENTLY_REVIEWED_COMPARISON',rows=rows,source_hashes=pins,limitations=['Research next-open fills; not actual execution','Conditional nominal history not certified point-in-time','Historical evidence does not guarantee future performance','No parameter scan or combined staging'])
(HERE/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf8')
lines=['|窗口|方案|年化|最大收盘回撤|假设成交数|禁买订单数|最大回撤区间|','|---|---|---:|---:|---:|---:|---|']
for r in rows:lines.append(f"|{r['window']}|{r['arm']}|{r['cagr']:.2%}|{r['maximum_close_drawdown']:.2%}|{r['assumed_fills']}|{r['filtered_buy_orders']}|{r['drawdown_peak']} → {r['drawdown_trough']}|")
(HERE/'comparison.md').write_text('\n'.join(lines)+'\n\n研究假设成交；未部署。两窗完整独立核验，仅一个预先固定机制，非前瞻或未来收益保证。\n',encoding='utf8')
print(json.dumps(rows))
