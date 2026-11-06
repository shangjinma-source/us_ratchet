"""Bounded single-factor residual ranking feasibility, never performance."""
from pathlib import Path
import json,gzip,statistics,math,hashlib
from datetime import datetime,timezone
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[2];pins={}
def read(name):
 raw=(ROOT/name).read_bytes();pins[name]=hashlib.sha256(raw).hexdigest();return json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)
def main():
 original=read('tmp/cross_sectional_momentum_static_20261105/result.json');byday={r['decision_date']:r for r in original['rows']};rows=[];missing=[];degenerate=[]
 specs=[('2021_2023','tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json','tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin'),('2024_2026','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin')]
 for label,training,market in specs:
  chart=read(market)['chart']['result'][0];q={datetime.fromtimestamp(t,timezone.utc).date().isoformat():c for t,c in zip(chart['timestamp'],chart['indicators']['quote'][0]['close']) if c is not None};data=read(training)
  for outer in data['windows']:
   w=outer.get('window',outer);dates=w['training_dates'];day=w.get('decision_cutoff',w.get('decision_date'));assert len(dates)==253 and dates==sorted(set(dates)) and dates[-1]==day
   absent=[d for d in dates if d not in q]
   if absent:missing.append(dict(window=label,date=day,dates=absent));continue
   assert dates[189]<dates[190]<=day
   market_returns=[q[b]/q[a]-1 for a,b in zip(dates,dates[1:])];x=market_returns[:189];xm=statistics.mean(x);den=sum((v-xm)**2 for v in x);assert den>0
   candidates={c['security_id']:c for c in w['candidates'] if c.get('security_id')};metadata=byday[day]['ranked'];ranked=[]
   for meta in metadata:
    sid=meta['security_id'];p=[float(F(v)) for v in candidates[sid]['training_close']];assert len(p)==253 and all(math.isfinite(v) and v>0 for v in p)
    y=[b/a-1 for a,b in zip(p,p[1:])];ym=statistics.mean(y[:189]);beta=sum((a-xm)*(b-ym) for a,b in zip(x,y[:189]))/den;alpha=ym-beta*xm
    residual=[a-alpha-beta*b for a,b in zip(y[189:],market_returns[189:])];sd=statistics.stdev(residual)
    if sd==0:degenerate.append(dict(day=day,sid=sid));continue
    ranked.append(dict(security_id=sid,issuer_id=meta['issuer_id'],ticker=meta['ticker'],alpha=alpha,beta=beta,score=statistics.mean(residual)/sd))
   ranked.sort(key=lambda r:(-r['score'],r['security_id']));selected=[];issuers=set()
   for item in ranked:
    if item['issuer_id'] in issuers:continue
    selected.append(item);issuers.add(item['issuer_id'])
    if len(selected)==10:break
   assert len(selected)==10 and not degenerate
   old={r['security_id'] for r in byday[day]['selected']};new={r['security_id'] for r in selected};rows.append(dict(window=label,date=day,aligned_prices=253,regression_returns=189,score_returns=63,fit_end=dates[189],score_start=dates[190],information_cutoff=day,legal_count=len(metadata),risk_on=byday[day]['gate']['risk_on'],overlap=len(old&new),new_sids=sorted(new-old),selected=selected))
 summary={}
 for label,_,_ in specs:
  group=[r for r in rows if r['window']==label];on=[r for r in group if r['risk_on']];summary[label]=dict(months=len(group),aligned_security_months=sum(r['legal_count'] for r in group),mean_top10_overlap=statistics.mean(r['overlap'] for r in group),changed_months=sum(r['overlap']<10 for r in group),risk_on_months=len(on),new_selected_sid_months_on=sum(len(r['new_sids']) for r in on),risk_on_months_needing_new_exposure_audit=sum(bool(r['new_sids']) for r in on),unique_new_sids_on=len({s for r in on for s in r['new_sids']}))
 out=dict(status='DATA_AND_INFORMATION_INCREMENT_ONLY',fixed_proxy='QQQ_SINGLE_FACTOR_189_FIT_63_FORWARD_RESIDUAL_MEAN_OVER_SD',rows=rows,summary=summary,missing_dates=missing,degenerate=degenerate,source_hashes=pins,limitations=['No future outcome or return measurement','Not original multifactor residual momentum paper','Historical price-only coordinates conditional, not total return factors','Causal timing not causal economic identification','New SID/month counts are exposure-review upper bound, not count of missing actions','Issuer dedup top10; no positive-score or parameter search'])
 target=ROOT/'tmp/residual_momentum_feasibility_20261106.json';target.write_text(json.dumps(out,indent=2));print(json.dumps(dict(summary=summary,missing=missing,degenerate=degenerate),indent=2))
if __name__=='__main__':main()
