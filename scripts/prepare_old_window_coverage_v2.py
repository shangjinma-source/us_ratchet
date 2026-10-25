"""Isolated local coverage and pure recompilation; no optimizer or book."""
import json,csv,hashlib,sys
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window
OUT=ROOT/'tmp/old_window_source_reuse_20261026'

def main():
 pins={}
 def load(path):
  b=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(b).hexdigest();return json.loads(b)
 inv=load('tmp/old_window_source_reuse_20261026/inventory.json')
 timeline=load('tmp/old_window_membership_timeline_20261026/timeline.json')
 calendar=load('tmp/old_window_official_calendar_20261026/review.json')
 eligibility=load('tmp/old_window_regular_way_20261026/review.json')
 old=load('tmp/next12_training_prepare_20261014_v1/prepared.json')
 load('tmp/anss_terminal_bridge_20261026/review.json');load('tmp/ea_splk_lifecycle_20261026/review.json')
 for path,expected in old['source_hashes'].items():
  if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise ValueError('OLD_SOURCE_CHANGED:'+path)
  pins[path]=expected
 candidate='tmp/anss_terminal_bridge_20261026/ANSS_price_candidate.csv'
 b=(ROOT/candidate).read_bytes();pins[candidate]=hashlib.sha256(b).hexdigest()
 anss=list(csv.DictReader(b.decode('utf-8-sig').splitlines()));anss_days={r.get('date',r.get('Date')) for r in anss}
 ea_path='tmp/next12_ea_alternate_source_20261014_v1/web_observation.json';ea=load(ea_path);ea_days={r['date'] for r in ea['rows']}
 rows=deepcopy(inv['monthly_matrix']);short=[r for r in eligibility['rows'] if r['status']=='EXCLUDED_SHORT_REGULAR_HISTORY']
 short_keys={(r.get('decision_date',r.get('decision_cutoff')),r['ticker']):r for r in short}
 for r in rows:
  r['post_termination_no_quote_required']=[]
  if r['ticker']=='ANSS':
   r['missing_training']=[d for d in r['missing_training'] if d not in anss_days]
   r['missing_execution_ohlc']=[d for d in r['missing_execution_ohlc'] if d not in anss_days]
   r['additional_source']=candidate
  if r['ticker']=='EA':
   r['missing_execution_ohlc']=[d for d in r['missing_execution_ohlc'] if d not in ea_days];r['additional_execution_segment']=ea_path
  terminal={'SPLK':'2024-03-15','ANSS':'2025-07-16'}.get(r['ticker'])
  if terminal:
   r['post_termination_no_quote_required']=[d for d in r['missing_execution_ohlc'] if d>terminal]
   r['missing_execution_ohlc']=[d for d in r['missing_execution_ohlc'] if d<=terminal]
   r['held_cash_or_stock_entitlement_must_be_modeled']=True
  key=(r['decision_date'],r['ticker'])
  if key in short_keys:
   r['training_eligibility']=short_keys[key];r['training_status']='EXCLUDED_SHORT_REGULAR_HISTORY'
  else:r['training_status']='DATES_COMPLETE_NOT_ADMITTED' if not r['missing_training'] else 'MISSING_REQUIRED_PRICE'
  r['identity_coordinate_action_status']='REQUIRES_ROUTE_SPECIFIC_REVIEW'
 windows=[];old_by_day={w['decision_cutoff']:w for w in old['windows']};routes={}
 for m in timeline['monthly_candidates']:
  day=m['decision_date'];w=old_by_day.get(day);result=dict(decision_date=day,full_members=m['members'],uncertain_members=m.get('uncertain_members',[]),membership_limitations=m.get('unresolved',[]),compiled_search_arguments=None)
  if w:
   if set(c['ticker'] for c in w['candidates'])!=set(m['members']):raise ValueError('OLD_DOMAIN_NOT_EQUAL:'+day)
   window=dict(decision_cutoff=day,training_dates=w['training_dates'],candidates=w['candidates'])
   args=compile_monthly_training_window(window=window,source_hashes=old['source_hashes'],admission=w['admission'])
   if args!=w['search_arguments']:raise ValueError('RECOMPILED_ARGUMENTS_DIFFER:'+day)
   result.update(status='RECOMPILED_CONDITIONAL_KNOWN_MEMBER_DOMAIN',compiled_search_arguments=args,
     source_hashes=old['source_hashes'],uncertain_member_training_exclusions=[r for r in short if r.get('decision_date',r.get('decision_cutoff'))==day and r['ticker'] in m.get('uncertain_members',[])],
     blockers=['COMPLETE_MEMBERSHIP_CERTIFICATION_AND_CONTINUOUS_EXECUTION_ACTION_ADMISSION_PENDING'])
   for c in w['candidates']:
    routes.setdefault(c['ticker'],dict(training_source=c['training_source'],source_sha256=old['source_hashes'][c['training_source']],identity=dict(security_id=c['security_id'],issuer_id=c['issuer_id']),source_references=c['source_references'],scope='OLD_LATER_12_WINDOWS_ONLY',coordinate_basis=c.get('training_basis'),frozen_costs={} ))['frozen_costs'][day]=c['decision_cost']
  else:
   result.update(status='ROUTE_IDENTITY_COORDINATE_BINDING_REQUIRED',blockers=['COMPLETE_TRUE_MEMBER_WINDOW_NOT_PREVIOUSLY_COMPILED','PER_SOURCE_IDENTITY_AND_NOMINAL_COORDINATE_BINDING_NOT_YET_ASSEMBLED'],data_rows=[r for r in rows if r['decision_date']==day])
  windows.append(result)
 result=dict(status='COVERAGE_V2_AND_BOUNDED_PURE_RECOMPILATION',source_hashes=pins,official_calendar_count=calendar['official_count'],rows=rows,short_history_exclusions=short,windows=windows,route_manifest=routes,
    pure_compiled_windows=sum(w['compiled_search_arguments'] is not None for w in windows),window_count=len(windows),search_calls=0,economic_runs=0,execution_authorized=False,
    limitations=['Coverage is conditional on frozen timeline, including uncertain members.','Short-history securities excluded from new stock selection still require rights valuation if distributed to a held parent.','Twelve recompiled known-member windows retain original reviewed units; this is not all 31-window execution admission.','Early19 metadata/cost fields are not invented from a later source label.'])
 (OUT/'coverage_v2.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ('window_count','pure_compiled_windows','search_calls','economic_runs')}))

if __name__=='__main__':main()
