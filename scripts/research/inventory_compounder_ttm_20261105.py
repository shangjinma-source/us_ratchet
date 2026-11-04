"""Local fixed-domain TTM/version feasibility, not a ranker or trading backtest."""
from pathlib import Path
from datetime import date,datetime,timedelta
from fractions import Fraction as F
from collections import Counter,defaultdict
from hashlib import sha256
import json,re,sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from data.ndx_fundamental_normalization import _Fact,_annual_plus_ytd_candidates,_direct_quarter_candidates,NormalizationPolicy
ROOT=Path(__file__).resolve().parents[2]
FIELDS={'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet'],'gross_profit':['GrossProfit'],'operating_cash_flow':['NetCashProvidedByUsedInOperatingActivities']}

def main():
 pins={}
 def load(path):
  p=ROOT/path;pins[p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest();return json.loads(p.read_bytes())
 inventory=load('tmp/early_compounder_inventory_20261105/result.json')
 events=load('tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json')
 originals=load('tmp/early_compounder_inventory_20261105/five_originals_review.json')
 original_by_acc={r['accession']:r for r in originals}
 for r in originals:
  for path,key in [(r['path'],'sha256'),(r['header_path'],'header_sha256')]:
   p=ROOT/path;assert sha256(p.read_bytes()).hexdigest()==r[key];pins[p.relative_to(ROOT).as_posix()]=r[key]
 cache={};results=[]
 for section in inventory['results']:
  cutoff=section['cutoff'];rows=[]
  for item in section['rows']:
   row=dict(ticker=item['ticker'],cik_candidates=item['cik_candidates'],historical_identity_certified=False,fields={})
   if len(item['cik_candidates'])!=1 or not item['fields']:
    row['reason']=item.get('reason','COMPANYFACTS_UNAVAILABLE');rows.append(row);continue
   cik=item['cik_candidates'][0]
   if cik not in cache:cache[cik]=load(f'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts/CIK{cik}.json')
   raw=cache[cik]['facts'].get('us-gaap',{})
   acceptance={e['accession']:e['acceptance'] for e in events['issuers'].get(cik,{}).get('events',[]) if e.get('acceptance')}
   def accepted(acc):
    header=ROOT/f'data/cache/candidate_pools/ndx_fundamentals/sic_history_v1/raw_headers/{int(cik)}/{acc}.header.txt'
    if header.exists():
     body=header.read_text();m=re.search(r'<ACCEPTANCE-DATETIME>(\d{14})',body)
     if m:
      pins[header.relative_to(ROOT).as_posix()]=sha256(header.read_bytes()).hexdigest()
      return datetime.strptime(m[1],'%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
    return acceptance.get(acc)
   for metric,concepts in FIELDS.items():
    eligible=[];unmatched=set();exact={};conflicts=set();accepted_map={}
    for priority,concept in enumerate(concepts):
     for unit,values in raw.get(concept,{}).get('units',{}).items():
      if unit!='USD':continue
      for x in values:
       if not x.get('start') or x.get('filed','9999')>cutoff or x['end']>cutoff or x.get('form') not in ('10-K','10-Q'):continue
       acc=x['accn'];when=accepted_map.setdefault(acc,accepted(acc))
       if not when or when[:10]>cutoff:
        unmatched.add(acc);continue
       start,end=date.fromisoformat(x['start']),date.fromisoformat(x['end']);duration=(end-start).days+1
       key=(acc,concept,unit,x['start'],x['end']);value=F(str(x['val']))
       if key in exact and exact[key]!=value:conflicts.add(key)
       exact[key]=value
       fact=_Fact(int(cik),metric,'us-gaap',concept,priority,unit,float(value),x['form'],date.fromisoformat(when[:10]),start,end,duration,acc,x.get('frame',''))
       if fact not in eligible:eligible.append(fact)
    def key(f):return (f.accession_number,f.concept,f.unit,f.period_start.isoformat(),f.period_end.isoformat())
    eligible=[f for f in eligible if key(f) not in conflicts]
    latest=max((f.period_end for f in eligible),default=None)
    grouped=defaultdict(list)
    for f in eligible:grouped[(f.accession_number,f.concept,f.unit)].append(f)
    candidates=[]
    for group in grouped.values():
     for c in _annual_plus_ytd_candidates(metric,group,NormalizationPolicy())+_direct_quarter_candidates(metric,group,NormalizationPolicy()):
      if c.method=='direct_four_quarters' and any((b[2].period_start-a[2].period_end).days!=1 for a,b in zip(c.components,c.components[1:])):continue
      if c.method=='annual_plus_ytd':
       a,cur,prior=[v[2] for v in c.components]
       if cur.period_start!=a.period_end+timedelta(days=1) or prior.period_start!=a.period_start:continue
      components=[];total=F(0);verified=True
      for role,coefficient,f in c.components:
       value=exact[key(f)];total+=F(str(coefficient))*value;original=original_by_acc.get(f.accession_number)
       contexts=[] if original is None else [r['context_id'] for r in original['records'] if r['concept']=='us-gaap:'+f.concept and r['unit']==f.unit and r.get('start')==f.period_start.isoformat() and r['end']==f.period_end.isoformat() and r['exact_match'] and F(r['original_value'])==value]
       verified=verified and bool(contexts)
       components.append(dict(role=role,coefficient=str(coefficient),accession=f.accession_number,acceptance=accepted_map[f.accession_number],concept=f.concept,unit=f.unit,start=f.period_start.isoformat(),end=f.period_end.isoformat(),duration_days=f.duration_days,value=str(value),original_context_ids=contexts))
      candidates.append(dict(method=c.method,period_start=((c.components[2][2].period_end+timedelta(days=1)).isoformat() if c.method=='annual_plus_ytd' else c.period_start.isoformat()),period_end=c.period_end.isoformat(),value=str(total),accession=c.components[0][2].accession_number,concept=c.components[0][2].concept,components=components,original_context_verified=verified))
    current=[c for c in candidates if latest and c['period_end']==latest.isoformat()]
    current.sort(key=lambda c:(c['components'][0]['acceptance'],c['accession'],c['concept'],c['method']),reverse=True)
    chosen=current[0] if current else None
    prior=[] if not chosen else [c for c in candidates if c['accession']==chosen['accession'] and c['concept']==chosen['concept'] and 350<=(date.fromisoformat(chosen['period_end'])-date.fromisoformat(c['period_end'])).days<=380]
    prior.sort(key=lambda c:c['period_end'],reverse=True);old=prior[0] if prior else None
    yoy=None if not old or F(old['value'])<=0 else str(F(chosen['value'])/F(old['value'])-1)
    latest_acc=max((f.accession_number for f in eligible),key=lambda a:accepted_map[a],default=None)
    available_components=[]
    for f in eligible:
     if f.accession_number!=latest_acc:continue
     original=original_by_acc.get(latest_acc);value=exact[key(f)]
     contexts=[] if not original else [x['context_id'] for x in original['records'] if x['concept']=='us-gaap:'+f.concept and x['unit']==f.unit and x.get('start')==f.period_start.isoformat() and x['end']==f.period_end.isoformat() and x['exact_match'] and F(x['original_value'])==value]
     available_components.append(dict(accession=latest_acc,acceptance=accepted_map[latest_acc],concept=f.concept,unit=f.unit,start=f.period_start.isoformat(),end=f.period_end.isoformat(),duration_days=f.duration_days,value=str(value),original_context_ids=contexts))
    row['fields'][metric]=dict(latest_accepted_accession_components=available_components,latest_accepted_period_end=latest.isoformat() if latest else None,same_accession_latest_ttm_candidate=chosen,same_accession_yoy=yoy,prior_ttm=old,original_ttm_verified=bool(chosen and chosen['original_context_verified']),original_yoy_verified=bool(yoy is not None and chosen['original_context_verified'] and old['original_context_verified']),older_annual_or_ttm_only_count=len(candidates)-len(current),unmatched_acceptance_accessions=sorted(unmatched),conflicting_fact_keys=[list(k) for k in conflicts],reason='SAME_ACCESSION_COMPANYFACTS_CANDIDATE_NOT_FULL_PIT' if chosen else 'LATEST_PERIOD_REQUIRES_CROSS_FILING_VERSION_BRIDGE_OR_MISSING_ANNUAL' if eligible else 'NO_ACCEPTED_DURATION_FACT',yoy_reason='SAME_VERSION_POSITIVE_PRIOR_TTM_AVAILABLE' if yoy is not None else 'SAME_ACCESSION_PRIOR_TTM_MISSING_OR_NONPOSITIVE',latest_filing_chain_certified=False)
   rows.append(row)
  coverage={}
  for metric in FIELDS:
   fs=[r['fields'].get(metric,{}) for r in rows]
   coverage[metric]=dict(same_accession_ttm_candidates=sum(bool(x.get('same_accession_latest_ttm_candidate')) for x in fs),same_accession_yoy_candidates=sum(x.get('same_accession_yoy') is not None for x in fs),original_ttm_verified=sum(x.get('original_ttm_verified',False) for x in fs),original_yoy_verified=sum(x.get('original_yoy_verified',False) for x in fs),reasons=dict(Counter(x.get('reason',r.get('reason','MISSING')) for x,r in zip(fs,rows))))
  results.append(dict(cutoff=cutoff,denominator=len(rows),coverage=coverage,rows=rows))
 pins['scripts/research/inventory_compounder_ttm_20261105.py']=sha256(Path(__file__).read_bytes()).hexdigest()
 pins['data/ndx_fundamental_normalization.py']=sha256((ROOT/'data/ndx_fundamental_normalization.py').read_bytes()).hexdigest()
 out=ROOT/'tmp/early_compounder_ttm_20261105';out.mkdir(exist_ok=True)
 (out/'result.json').write_text(json.dumps(dict(results=results,source_hashes=pins,downloads=0,economic_runs=0,scope='Same-accession exact arithmetic only; no cross-filing revision bridge inferred; latest complete filings not certified'),indent=2),encoding='utf-8')
 print(json.dumps([{k:v for k,v in r.items() if k!='rows'} for r in results],indent=2))

if __name__=='__main__':main()
