"""Same-accession annual raw financial diagnostics; no ranking or economics."""
import json,hashlib
from pathlib import Path
from datetime import date,datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[2]
ROSTER='tmp/cross_sectional_momentum_static_20261105/result.json'
INVENTORY='tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json'
COVERAGE='tmp/annual_quality_coverage_20261106/result.json'
REQUIRED=('NetIncomeLoss','NetCashProvidedByUsedInOperatingActivities','Assets')
CONCEPTS=('GrossProfit',)+REQUIRED

def cik_matches(expected,actual):
 a,b=str(expected),str(actual)
 return a.isdigit() and b.isdigit() and int(a)==int(b)

def acceptance_class(value,cutoff):
 if not value:return 'FILED_DATE_ONLY',None
 try:
  parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
  if parsed.tzinfo is None:return 'FILED_ONLY_ACCEPTANCE_TIMEZONE_UNSPECIFIED',None
  local=parsed.astimezone(ZoneInfo('America/New_York'))
  return ('EXACT_ACCEPTANCE_PRIOR_DATE' if local.date()<date.fromisoformat(cutoff) else 'ACCEPTANCE_NOT_PRIOR_DATE'),local.isoformat()
 except ValueError:return 'FILED_ONLY_ACCEPTANCE_UNPARSEABLE',None

def select(facts,accepted,cutoff):
 groups={};excluded={}
 for concept in CONCEPTS:
  for item in facts.get(concept,{}).get('units',{}).get('USD',[]):
   acc=item.get('accn');end=item.get('end');reason=None
   if item.get('form')!='10-K':reason='NOT_10K'
   elif not item.get('filed') or item['filed']>=cutoff:reason='FILED_NOT_BEFORE_CUTOFF'
   elif not end or end>=cutoff:reason='PERIOD_NOT_BEFORE_CUTOFF'
   elif (date.fromisoformat(cutoff)-date.fromisoformat(end)).days>550:reason='STALE_OVER_550_DAYS'
   elif concept!='Assets' and not(item.get('start') and 330<=(date.fromisoformat(end)-date.fromisoformat(item['start'])).days<=380):reason='NOT_ANNUAL_330_380_DAYS'
   if reason:
    k=(acc,end,reason);excluded[k]=excluded.get(k,0)+1;continue
   groups.setdefault((acc,end),{}).setdefault(concept,[]).append(item)
 choices=[];rejected=[]
 for (acc,end),fields in groups.items():
  reason=None
  if not all(k in fields for k in REQUIRED):reason='MISSING_SAME_ACCESSION_FIELDS'
  elif len({f.get('start') for k in REQUIRED[:2] for f in fields[k]})!=1:reason='ANNUAL_START_MISMATCH'
  elif any(len({F(str(f['val'])) for f in values})!=1 for values in fields.values()):reason='CONFLICTING_VALUES_SAME_VERSION'
  elif F(str(fields['Assets'][0]['val']))<=0:reason='NONPOSITIVE_ASSETS'
  ac,local=acceptance_class(accepted.get(acc),cutoff)
  if ac=='ACCEPTANCE_NOT_PRIOR_DATE':reason='ACCEPTANCE_NOT_PRIOR_DATE'
  if reason:rejected.append(dict(accession=acc,period_end=end,reason=reason,available_concepts=sorted(fields)));continue
  filed=min(f['filed'] for f in fields['Assets']);choices.append((end,filed,acc,fields,ac,local))
 rejected.extend(dict(accession=a,period_end=e,reason=r,observations=n) for (a,e,r),n in sorted(excluded.items(),key=lambda x:str(x[0])))
 if not choices:return dict(status='NO_COMPATIBLE_ANNUAL_SAME_ACCESSION',rejected_versions=rejected)
 chosen=max(choices,key=lambda r:(r[0],r[1],r[2]));end,filed,acc,fields,ac,local=chosen
 rejected.extend(dict(accession=c[2],period_end=c[0],reason='ELIGIBLE_OLDER_SELECTION_KEY') for c in choices if c is not chosen)
 values={k:F(str(fields[k][0]['val'])) for k in REQUIRED};assets=values['Assets'];ni=values['NetIncomeLoss'];ocf=values['NetCashProvidedByUsedInOperatingActivities']
 detail={k:dict(concept=k,unit='USD',value_exact=str(F(str(v[0]['val']))),start=v[0].get('start'),end=end,accession=acc,filed_dates=sorted({f['filed'] for f in v}),raw_observations=v) for k,v in fields.items()}
 return dict(status='DESCRIPTIVE_RAW_SAME_VERSION',accession=acc,period_end=end,selection_filed=filed,acceptance=accepted.get(acc),acceptance_new_york=local,availability_layer=ac,fields=detail,ratios={'net_income_over_ending_assets':str(ni/assets),'operating_cash_flow_over_ending_assets':str(ocf/assets),'ni_minus_ocf_over_ending_assets':str((ni-ocf)/assets)},rejected_versions=rejected,revision_chain_verified=False,original_values_verified=False)

def main():
 pins={};expected=json.loads((ROOT/COVERAGE).read_bytes())['source_hashes']
 def load(name):
  raw=(ROOT/name).read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if name in expected and digest!=expected[name]:raise ValueError('PRIOR_CAPTURE_HASH_CHANGED:'+name)
  pins[name]=digest;return json.loads(raw,parse_float=Decimal)
 rosters=load(ROSTER)['rows'];inventory=load(INVENTORY);load(COVERAGE);mapping={};cache={};results=[]
 for w in inventory['windows']:
  for r in w['rows']:
   if r.get('cik'):
    for t in r['tickers']:mapping.setdefault(t,set()).add(r['cik'])
 for roster in rosters:
  cutoff=roster['decision_date']
  if cutoff[5:7] not in ('03','06','09','12'):continue
  rows=[]
  for stock in roster['ranked']:
   ticker=stock['ticker'];ciks=sorted(mapping.get(ticker,[]));row=dict(security_id=stock['security_id'],issuer_id=stock['issuer_id'],ticker=ticker,ciks=ciks,status='IDENTITY_LEAD_MISSING_OR_AMBIGUOUS');rows.append(row)
   if len(ciks)!=1:continue
   cik=ciks[0];path='data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts/CIK'+cik+'.json'
   if cik not in cache:
    if not(ROOT/path).exists():cache[cik]=None
    else:
     document=load(path);facts=document.get('facts',{}).get('us-gaap',{});accepted={e['accession']:e['acceptance'] for e in inventory['issuers'].get(cik,{}).get('events',[]) if e.get('acceptance')};sub='data/cache/research/current_92_sec_submissions_capture_20260919_v1/'+cik+'.response.bin';sources=[path,INVENTORY]
     if (ROOT/sub).exists():
      rec=load(sub).get('filings',{}).get('recent',{});accepted.update(dict(zip(rec.get('accessionNumber',[]),rec.get('acceptanceDateTime',[]))));sources.append(sub)
     cache[cik]=(facts,accepted,sources,document.get('cik'))
   if cache[cik] is None:row['status']='FACTS_MISSING';continue
   facts,accepted,sources,fact_cik=cache[cik];row.update(cik=cik,companyfacts_cik=fact_cik,source_hashes={s:pins[s] for s in sources})
   if not cik_matches(cik,fact_cik):row['status']='COMPANYFACTS_CIK_IDENTITY_MISMATCH';continue
   row.update(select(facts,accepted,cutoff))
  count=sum(r['status']=='DESCRIPTIVE_RAW_SAME_VERSION' for r in rows);layers={}
  for r in rows:layers[r.get('availability_layer',r['status'])]=layers.get(r.get('availability_layer',r['status']),0)+1
  results.append(dict(cutoff=cutoff,domain=len(rows),descriptive_available=count,layers=layers,rows=rows))
 script=Path(__file__).relative_to(ROOT).as_posix();pins[script]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();out=dict(status='LOCAL_DESCRIPTIVE_NOT_QMJ_NOT_PIT_CERTIFIED',results=results,source_hashes=pins,downloads=0,rankings=0,economic_runs=0,availability_rule='Filed strictly prior cutoff date. Explicit timezone acceptance converted to New York and must be prior calendar date; no decision-day acceptance admitted.',limitations=['Ending assets, not average assets','No revision-chain certification; currently captured companyfacts can contain later corrections','Historical identity/domain conditional','Missing values not zero; all ranked original domain rows retained','No complete QMJ growth safety payout or gross profitability construction','Original inline contexts/units not independently re-certified'])
 target=ROOT/'tmp/annual_quality_local_diagnostic_20261106';target.mkdir(exist_ok=True);(target/'result.json').write_text(json.dumps(out,default=str,indent=2),encoding='utf8')
 panel=[]
 for section in results:
  compact=[]
  for index,row in enumerate(section['rows']):
   item={k:v for k,v in row.items() if k not in ('rejected_versions','fields')}
   item['fields']={k:{key:value for key,value in field.items() if key!='raw_observations'} for k,field in row.get('fields',{}).items()}
   item['full_record_pointer']='results/'+str(len(panel))+'/rows/'+str(index)
   item['rejected_version_record_count']=len(row.get('rejected_versions',[]));compact.append(item)
  panel.append(dict(cutoff=section['cutoff'],domain=section['domain'],descriptive_available=section['descriptive_available'],layers=section['layers'],rows=compact))
 summary=dict(status=out['status'],sections=len(results),domain_rows=sum(r['domain'] for r in results),available_rows=sum(r['descriptive_available'] for r in results),sections_summary=[{k:v for k,v in r.items() if k!='rows'} for r in results],full_result_sha256=hashlib.sha256((target/'result.json').read_bytes()).hexdigest(),source_hashes=pins,limitations=out['limitations'])
 (target/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
 (target/'descriptive_panel.json').write_text(json.dumps(dict(status=out['status'],results=panel,source_hashes=pins,full_result_sha256=summary['full_result_sha256'],limitations=out['limitations']),default=str,indent=2),encoding='utf8')
 print(json.dumps({k:v for k,v in summary.items() if k not in ('source_hashes','sections_summary')},indent=2))
if __name__=='__main__':main()
