"""Independent v6 audit with scoped provider absence, no synthetic dividends."""
import argparse,gzip,inspect,json
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from scripts.research import review_downside_account_20261105_v5 as prior
chain=prior.chain;base=prior.base;ROOT=prior.ROOT;require=prior.require
FREEZE='research_contracts/downside_max10_resume_v6_20261105/freeze.json'
INSM_PATH='tmp/insm_absence_evidence_20261105/supplement.json'
INSM_SHA='c5b13cea85933011860fe582d7543528bba3fa44544417f583920073f5744aac'

def validate_insm_absence(artifact,original_events,inventory):
    require(artifact['schema']=='BOUNDED_PROVIDER_ABSENCE_V1' and artifact['status']=='REVIEWED_CONDITIONAL_PROVIDER_ABSENCE','INSM_SCHEMA')
    require('dividend_events' not in artifact and len(artifact['review_rows'])==1,'INSM_NO_FINANCIAL_EVENTS')
    sid='security:0001104506:457669307';source='tmp/next12_missing_quote_capture_20261014_v1/INSM.response.bin'
    row=artifact['review_rows'][0]
    require(row['status']=='REVIEWED_NO_ACTION_FOR_PERIOD' and row['security_id']==artifact['security_id']==sid,'INSM_SID')
    require((row['start_exclusive'],row['end_inclusive'])==('2023-12-29','2026-07-30') and row['selected_price_sources']==[source],'INSM_EXACT_SCOPE')
    require(not any(e['ticker']=='INSM' for e in inventory),'INSM_NO_KNOWN_PROVIDER_EVENT')
    require(not any(e['security_id']==sid for e in original_events),'INSM_NO_KNOWN_FINANCIAL_EVENT')
    receipt=base.read(ROOT/source.replace('.response.bin','.receipt.json'));started=base.read(ROOT/source.replace('.response.bin','.started.json'))
    raw=(ROOT/source).read_bytes();require(raw[:2]==b'\x1f\x8b','INSM_GZIP')
    decoded=gzip.decompress(raw)
    require(sha256(raw).hexdigest()==receipt['raw_sha256']==artifact['source_hashes'][source] and len(raw)==receipt['raw_bytes'] and sha256(decoded).hexdigest()==receipt['decoded_sha256'],'INSM_RAW_COMPLETE')
    require(receipt['http_status']==200 and receipt['request_url']==receipt['final_url']==started['request_url'] and receipt['started_at_utc']==started['started_at_utc'],'INSM_RECEIPT')
    url=urlparse(receipt['request_url']);q=parse_qs(url.query)
    require(url.scheme=='https' and url.hostname=='query1.finance.yahoo.com' and url.path=='/v8/finance/chart/INSM' and q['events']==['div,splits'] and q['interval']==['1d'],'INSM_EXPLICIT_REQUEST')
    chart=json.loads(decoded)['chart'];require(chart['error'] is None and len(chart['result'])==1,'INSM_CHART_SUCCESS');r=chart['result'][0]
    require(r['meta']['symbol']=='INSM' and r['meta']['instrumentType']=='EQUITY' and 'events' not in r and receipt['returned_events']=={},'INSM_PROVIDER_ABSENCE')
    days=[datetime.fromtimestamp(t,timezone.utc).date().isoformat() for t in r['timestamp']]
    document=base.read(ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json');sessions=document['assembled']['session_dates']
    require(document['prepared_input_candidate']['metadata'][sid]==dict(ticker='INSM',issuer_id='issuer:0001104506'),'INSM_FROZEN_IDENTITY')
    require(len(sessions)==647 and sessions[0]==row['start_exclusive'] and sessions[-1]==row['end_inclusive'] and days==sorted(set(days)) and len(days)==receipt['rows'] and set(sessions)<=set(days),'INSM_FULL_CALENDAR')
    begin=datetime.fromtimestamp(int(q['period1'][0]),timezone.utc).date().isoformat();end=datetime.fromtimestamp(int(q['period2'][0]),timezone.utc).date().isoformat()
    require(begin<=sessions[0] and end>sessions[-1],'INSM_REQUEST_INTERVAL')
    for key in ('open','high','low','close'):
        values=r['indicators']['quote'][0][key]
        require(len(values)==len(days) and all(values[days.index(d)] is not None and values[days.index(d)]>0 for d in sessions),'INSM_OHLC_COVERAGE')
    require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'INSM_REFERENCE_PINS')
    return []

def validate_resume(directory,freeze_path=FREEZE,schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V6',parent_rows=502,parent_budget=None,additional=(),absence_origin=None):
    freeze=base.read(ROOT/freeze_path);chain.v2.check_pins(freeze['source_hashes'])
    require(freeze['schema']==schema,'RESUME_FREEZE')
    extra=[(prior.prior.AZN_PATH,prior.prior.AZN_SHA,prior.prior.validate_azn_pairs),(prior.prior.CTSH_PATH,prior.prior.CTSH_SHA,prior.prior.validate_ctsh_pairs),(prior.LRCX_PATH,prior.LRCX_SHA,prior.validate_lrcx_pairs),(INSM_PATH,INSM_SHA,validate_insm_absence)]
    extra.extend(additional)
    require(freeze['additional_execution_artifacts']==[chain.v2.META_PATH,chain.CEG_PATH,*[x[0] for x in extra]],'V6_ARTIFACT_ORDER')
    require(all(freeze['source_hashes'][p]==h for p,h,_ in extra),'APPROVED_ARTIFACT_HASHES')
    result=chain.validate_resume(directory,parent_rows=parent_rows,parent_budget=parent_budget or dict(new=25,reused=0,replayed=21),additional=extra)
    require(result[0]['parent_output']==freeze['parent_output'] and result[0]['inherited_seconds']==freeze['inherited_seconds'],'V6_FREEZE_PARENT')
    # Original blocked gate must have exactly the one source-scoped INSM absence.
    origin=absence_origin or freeze['parent_output']
    require((ROOT/origin/'contract.json').relative_to(ROOT).as_posix() in result[1]['hashes'],'ABSENCE_ORIGIN_ANCESTOR')
    old=base.read(ROOT/origin/'2025-12-31.exposure.json',True)
    require(not old['unmapped_events'] and len(old['missing_action_streams'])==1,'INSM_ORIGINAL_GATE')
    missing=old['missing_action_streams'][0];row=base.read(ROOT/INSM_PATH)['review_rows'][0]
    require(missing['security_id']==row['security_id'] and missing['source'] in row['selected_price_sources'] and all(s['source_path'] in row['selected_price_sources'] for s in missing['selected_source_segments']),'INSM_OLD_SOURCE_SCOPE')
    new=base.read(directory/'2025-12-31.exposure.json',True)
    require(new['admitted'] and not new['missing_action_streams'] and not new['unmapped_events'],'INSM_NEW_GATE')
    require(any(e['review']==row and e['missing_stream']==missing for e in new['accepted_period_reviews']),'INSM_SCOPED_REVIEW_APPLIED')
    return result

def run(output):
    namespace=dict(chain.__dict__);namespace.update(validate_resume=validate_resume,__file__=__file__)
    exec(compile(inspect.getsource(chain.run),'<independent-downside-v6-audit>','exec'),namespace);namespace['run'](output)
    path=ROOT/output/'independent_review.json';report=base.read(path)
    report['resume_review'].update(parent_rows_checked=502,azn_events_checked=3,ctsh_events_checked=10,lrcx_new_events_checked=2,lrcx_existing_events_checked=2,insm_absence_sessions_checked=647,insm_financial_events_added=0)
    report['insm_limitations']=base.read(ROOT/INSM_PATH)['limitations']
    for p in [Path(chain.__file__),Path(prior.__file__),Path(prior.prior.__file__),ROOT/FREEZE,ROOT/prior.prior.AZN_PATH,ROOT/prior.prior.CTSH_PATH,ROOT/prior.LRCX_PATH,ROOT/INSM_PATH]:
        report['source_hashes'][p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
