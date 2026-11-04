"""Five preselected issuers only: local annual+YTD bridge locators and value checks."""
from pathlib import Path
from datetime import date,timedelta,datetime
from fractions import Fraction as F
from hashlib import sha256
from zoneinfo import ZoneInfo
import json,re,subprocess
ROOT=Path(__file__).resolve().parents[2]
NAMES={'0001091667':'CHTR','0000882095':'GILD','0000865752':'MNST','0000872589':'REGN','0001713683':'ZS'}


def main():
 pins={}
 def load(p):
  path=ROOT/p;pins[path.relative_to(ROOT).as_posix()]=sha256(path.read_bytes()).hexdigest();return json.loads(path.read_bytes())
 originals=load('tmp/early_compounder_inventory_20261105/five_originals_review.json')
 paths=subprocess.run(['rg','--files','data/cache','tmp'],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",check=True).stdout.splitlines()
 rows=[]
 for original in originals:
  cik=original['cik'];assert cik in NAMES
  for field,digest_field in [('path','sha256'),('header_path','header_sha256')]:
   original_path=ROOT/original[field];assert sha256(original_path.read_bytes()).hexdigest()==original[digest_field];pins[original_path.relative_to(ROOT).as_posix()]=original[digest_field]
  facts=load(f'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts/CIK{cik}.json')['facts']['us-gaap']
  submission_path=f'data/cache/research/current_92_sec_submissions_capture_20260919_v1/{cik}.response.bin'
  submission=load(submission_path).get('filings',{}).get('recent',{}) if (ROOT/submission_path).exists() else {}
  submission_acceptance=dict(zip(submission.get('accessionNumber',[]),submission.get('acceptanceDateTime',[])))
  relevant=[r for r in original['records'] if r['concept'].split(':')[-1] in ('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','GrossProfit','NetCashProvidedByUsedInOperatingActivities') and r['exact_match']]
  for concept in sorted({r['concept'] for r in relevant}):
   candidates=[r for r in relevant if r['concept']==concept]
   last=max(r['end'] for r in candidates)
   current=max((r for r in candidates if r['end']==last),key=lambda r:r['duration_days'])
   prior=[r for r in candidates if r['end'][:4]==str(int(last[:4])-1) and abs(r['duration_days']-current['duration_days'])<=7]
   if len(prior)!=1:
    rows.append(dict(ticker=NAMES[cik],concept=concept,status='PRIOR_YTD_CONTEXT_NOT_UNIQUE'));continue
   prior=prior[0];annual_end=(date.fromisoformat(current['start'])-timedelta(days=1)).isoformat()
   records=facts[concept.split(':')[-1]]['units']['USD']
   annuals=[r for r in records if r.get('start')==prior['start'] and r['end']==annual_end and r.get('filed','9999')<=original['acceptance_eastern'][:10] and r.get('form')=='10-K']
   prior_filings=[r for r in records if r.get('start')==prior['start'] and r['end']==prior['end'] and r.get('filed','9999')<original['acceptance_eastern'][:10] and r.get('form')=='10-Q']
   def describe(records):
    if not records:return None
    first=min(records,key=lambda r:(r['filed'],r['accn']));acc=first['accn'];same=[r for r in records if r['accn']==acc];values=sorted({str(F(str(r['val']))) for r in same})
    header=ROOT/f'data/cache/candidate_pools/ndx_fundamentals/sic_history_v1/raw_headers/{int(cik)}/{acc}.header.txt'
    acceptance=None;acceptance_source=None
    if header.exists():
     text=header.read_text();m=re.search(r'<ACCEPTANCE-DATETIME>(\d{14})',text)
     if m:acceptance=datetime.strptime(m[1],'%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
     pins[header.relative_to(ROOT).as_posix()]=sha256(header.read_bytes()).hexdigest()
    if acceptance:acceptance_source=header.relative_to(ROOT).as_posix()
    if not acceptance and acc in submission_acceptance:
     acceptance=datetime.fromisoformat(submission_acceptance[acc].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).isoformat();acceptance_source=submission_path
    matches=[p for p in paths if (acc in p or acc.replace('-','') in p) and Path(p).suffix.lower() in ('.htm','.html','.xml','.response')]
    return dict(accession=acc,filed=first['filed'],acceptance_eastern=acceptance,acceptance_source=acceptance_source,header_path=header.relative_to(ROOT).as_posix(),start=first['start'],end=first['end'],companyfacts_values=values,original_path_candidates=matches,original_context_verified=False)
   annual=describe(annuals);old=describe(prior_filings)
   comparable=bool(old and old['companyfacts_values']==[str(F(prior['original_value']))])
   arithmetic=None
   if annual and len(annual['companyfacts_values'])==1 and annual['acceptance_eastern'] and annual['acceptance_eastern']<=original['acceptance_eastern']:
    arithmetic=str(F(annual['companyfacts_values'][0])+F(current['original_value'])-F(prior['original_value']))
   rows.append(dict(ticker=NAMES[cik],concept=concept,current_filing=dict(accession=original['accession'],acceptance=original['acceptance_eastern'],path=original['path'],sha256=original['sha256']),current_ytd=current,prior_ytd_in_current_filing=prior,required_annual=dict(start=prior['start'],end=annual_end),annual_candidate=annual,prior_ytd_original_filing=old,prior_ytd_numeric_consistency=comparable,prior_ytd_consistency_reason='SAME_VALUE_AS_PRIOR_ACCESSION_COMPANYFACTS' if comparable else 'PRIOR_CONCEPT_ACCESSION_MISSING' if old is None else 'VALUE_DIFFERENCE_REQUIRES_RECAST_BRIDGE',conditional_exact_ttm=arithmetic,ttm_start=(date.fromisoformat(prior['end'])+timedelta(days=1)).isoformat(),ttm_end=last,status='COMPONENT_ARITHMETIC_NOT_ORIGINAL_ANNUAL_OR_REVISION_CHAIN_VERIFIED',pit_ttm_certified=False))
 out=ROOT/'tmp/five_ttm_bridges_20261105';out.mkdir(exist_ok=True)
 pins[Path(__file__).relative_to(ROOT).as_posix()]=sha256(Path(__file__).read_bytes()).hexdigest()
 result=dict(rows=rows,source_hashes=pins,downloads=0,economic_runs=0,lookup_scope='Path-only accession lookup in data/cache and tmp; no assertion of global file absence',limitations=['Annual original context and complete intervening amendment/restatement chain not verified.','Conditional arithmetic is not admitted TTM, rank or economic result.'])
 (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 for r in rows:print(r['ticker'],r['concept'].split(':')[-1],r['annual_candidate']['accession'] if r.get('annual_candidate') else None,len((r.get('annual_candidate') or {}).get('original_path_candidates',[])),r.get('prior_ytd_numeric_consistency'),r.get('conditional_exact_ttm'))

if __name__=='__main__':main()
