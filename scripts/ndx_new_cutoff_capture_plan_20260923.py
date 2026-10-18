"""Prepare-only new-asof channel request plan; this module has no HTTP client."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.ndx_corrected_frontier_single_refit_archive_research import publish
BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'new_cutoff_raw_capture_20260923_v1'
ANCHORS={
 'observation':('current_quote_list_observation_20260923_v1/observation.json','a6d8899fb2bc22f755ecd721271ed173f24a0b959b6ff8da9c96985f940fa990'),
 'audit':('current_quote_list_observation_20260923_v1/independent_observation_audit.json','a8c9f94fb0ad3c43e9aded9a3ce43ea81291a3f938278100cf2d2fccab22cd89'),
 'old_manifest':('latest_all_ndx_conditional_manifest_20260919_v1/manifest.json','be842f56db29f989af87885079c8807334089b36334c4c8c743d9ab2c33007e2'),
 'old22':('current_22_price_capture_20260919_v1/completion_index_22.json','7a41e3f47ecb4ea9fc6757a9e0393993be99ffeaceab8d2b21ea38c83797890d'),
 'old79':('current79_new_asof_capture_20260919_v1/completion_index_79.json','280fd0aecb9c02afe0cfa99fadc3b08a483eff283602f9c341e990d171b1f310'),
 'old_tsm':('current_tsm_raw_capture_20260919_v1/index.json','a8746baefec9de164f288f441b7d7a456a073b0787d0563edce57a29d229a9bc'),
 'old_inputs':('latest_twenty_historical_inputs_20260919_v1/inputs.json','49551a1f9cc0069935646d696b27621b748681b5769bfecbe1c8e8fa87d80939')}
FALSE=('http_performed','fit_performed','prices_reconstructed','cutoff_coverage_verified',
       'point_in_time_membership_verified','latest_security_identity_verified','complete_corporate_actions_verified',
       'liquidity_admitted','legal_training_input_admitted','promotion_allowed','old_files_modified',
       'prior_reports_transitive_source_closure_reverified','executable_runner_verified')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,allow_nan=False,separators=(',',':'))
LOADED={str(p):sha(p) for p in (Path(__file__).resolve(),Path(publish.__code__.co_filename).resolve())}

def verify_sources(sources):
    for p,h in sources.items():
        if sha(p)!=h:raise ValueError('Source differs: '+p)

def read(path,h,sources):
    path=str(Path(path).resolve())
    if path in sources and sources[path]!=h:raise ValueError('Conflicting source')
    if sha(path)!=h:raise ValueError('Source SHA differs')
    sources[path]=h
    return json.loads(Path(path).read_bytes())

def validate_start(now):
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset().total_seconds()!=0:
        raise ValueError('Actual aware UTC clock required')
    if now < datetime(2026,9,23,4,tzinfo=timezone.utc) or now.astimezone(ZoneInfo('America/New_York')).date().isoformat()!='2026-09-23':
        raise ValueError('Dedicated new-asof window is New York 2026-09-23, after midnight')

def prior_url(receipt,ticker):
    parsed=urlparse(receipt['request_url']);q=parse_qs(parsed.query,keep_blank_values=True)
    if parsed.scheme!='https' or parsed.netloc!='query1.finance.yahoo.com' or parsed.path!='/v8/finance/chart/'+ticker or set(q)!={'period1','period2','interval','events'}:
        raise ValueError('Original chart request differs')
    if q['period1']!=['1640995200'] or q['interval']!=['1d'] or q['events']!=['div,splits'] or len(q['period2'])!=1 or not q['period2'][0].isdigit():
        raise ValueError('Original request parameters ambiguous')
    if receipt['ticker']!=ticker or type(receipt['attempt_count']) is not int or receipt['attempt_count']!=1:
        raise ValueError('Original receipt identity differs')
    return int(q['period2'][0])

def build():
    sources=dict(LOADED);verify_sources(sources)
    docs={k:read(BASE/p,h,sources) for k,(p,h) in ANCHORS.items()}
    obs=docs['observation'];audit=docs['audit'];symbols=obs['observed_symbols']
    if len(symbols)!=101 or len(set(symbols))!=101 or audit['added_symbols'] or audit['removed_symbols'] or audit['retained_count']!=101:
        raise ValueError('Hard observed denominator differs')
    ref=dict(path=str(BASE/ANCHORS['observation'][0]),sha256=ANCHORS['observation'][1])
    if audit['details'][1]['observation_reference']!=ref or audit['raw_observation_reconstruction_exact'] is not True:
        raise ValueError('Observation independent audit differs')
    old={r['ticker']:r for r in docs['old_manifest']['rows']}
    if set(old)!=set(symbols) or len(docs['old_manifest']['rows'])!=101:raise ValueError('Old reference denominator differs')
    controls=[r['ticker'] for r in docs['old_inputs']['incumbent_original_securities']]
    if len(controls)!=8 or len(set(controls))!=8 or set(controls)-set(symbols)!={'TSM'}:
        raise ValueError('Original control union changed')
    previous={}
    entries=docs['old22']['entries']+docs['old79']['entries']+[docs['old_tsm']['entry']]
    for e in entries:
        t=e['ticker']
        if t in previous:raise ValueError('Duplicate historical receipt channel')
        r=read(e['receipt_path'],e['receipt_sha256'],sources)
        previous[t]=dict(receipt_reference=dict(path=e['receipt_path'],sha256=e['receipt_sha256']),
                         request_url=r['request_url'],period2=prior_url(r,t),received_at_utc=r['received_at_utc'])
    if set(previous)!=set(symbols)|{'TSM'}:raise ValueError('Exact 22+79+TSM prior receipt denominator required')
    queue=[]
    for t in symbols+['TSM','QQQ','SPY']:
        row=old.get(t)
        queue.append(dict(ticker=t,role='OBSERVED_MEMBER_PROVIDER_CHANNEL' if row else 'ORIGINAL_INCUMBENT_ONLY' if t=='TSM' else 'OBSERVED_SESSION_REFERENCE_ONLY',
            original_incumbent_channel=t in controls,prior_receipt=previous.get(t),
            historical_identity_reference=None if row is None else dict(manifest_reference=dict(path=str(BASE/ANCHORS['old_manifest'][0]),sha256=ANCHORS['old_manifest'][1]),
                ticker=t,conditional_issuer_id=row['conditional_issuer_id'],security_id=row['security_id'],share_class=row['share_class'],
                share_class_evidence_status=row['share_class_evidence_status'],unresolved_qualification=row['unresolved_qualification'],
                usage='DATED_PRIOR_REFERENCE_NOT_NEW_IDENTITY_ATTESTATION'),
            request_url_template='https://query1.finance.yahoo.com/v8/finance/chart/'+t+'?period1=1640995200&period2={actual_request_start_utc_epoch}&interval=1d&events=div,splits',
            maximum_attempts=1,request_fields='QUOTE_OPEN_HIGH_LOW_CLOSE_VOLUME_ADJCLOSE_AND_ALL_RETURNED_DIVIDENDS_SPLITS',
            returned_split_is_not_automatically_ordinary_share_split=True,
            prior_url_inventory_complete=False if t in ('QQQ','SPY') else True))
    verify_sources(sources)
    return dict(schema='NEW_CUTOFF_RAW_CHANNEL_CAPTURE_PREPARATION_V1',queue=queue,observed_member_channels=101,
        original_incumbent_tickers=controls,additional_nonmember_channels=['TSM','QQQ','SPY'],maximum_chart_requests=104,
        maximum_requests_per_batch=8,earliest_request_utc='2026-09-23T04:00:00+00:00',
        request_new_york_day='2026-09-23',target_cutoff_to_verify='2026-09-22',period1_utc_epoch=1640995200,
        output_directory=str(OUTPUT),partial_bar_policy='RECEIPT_NEW_YORK_DATE_AND_LATER_EXCLUDED',
        request_policy='ACTUAL_START_PERIOD2_STRICTLY_AFTER_EACH_KNOWN_PRIOR_PERIOD2_NO_DUPLICATE_URL_NO_RETRY',
        persistence_policy='DURABLE_EXCLUSIVE_STARTED_BEFORE_HTTP_RAW_AND_RECEIPT_BEFORE_DECODE_EXTERNAL_INDEX_ONLY_ORPHANS_BLOCK',
        benchmark_nav=dict(code='012922',status='NEW_DATED_NAV_SOURCE_PLAN_REQUIRED_SEPARATELY',network_budget=0,
                           old_input_reference=dict(path=str(BASE/ANCHORS['old_inputs'][0]),sha256=ANCHORS['old_inputs'][1]),
                           publication_time_verified=False,fx_alignment_verified=False),
        unresolved_execution_preconditions=['SOURCE_BOUND_NEW_RUNNER_REVIEW_REQUIRED','QQQ_SPY_PRIOR_REQUEST_INVENTORY_REQUIRED',
            'ACTUAL_CLOCK_GATE_BEFORE_ATTEMPT','FINAL_URL_GUARD_AND_NO_REDIRECT_OPENER','RAW_READBACK_BEFORE_PRICE_OR_ACTION_CLASSIFICATION'],
        source_hashes=sources,scope='CAPTURE_PREPARATION_ONLY_NOT_HTTP_EXECUTION_AUTHORIZATION_OR_MEMBERSHIP_CERTIFICATE',
        **dict.fromkeys(FALSE,False))

def publish_verified(path,value):
    if canonical(value)!=canonical(build()):raise ValueError('Full preparation rebuild differs')
    result=publish(path,value);verify_sources(value['source_hashes']);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(publish_verified(a.output,build())))
