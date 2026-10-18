"""Read existing raw only; four post-action proposals and two unresolved channels."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from bs4 import BeautifulSoup
from backtest import ndx_post_action_interval_research as core
BASE = ROOT/'data/cache/research'
PLAN = BASE/'current101_conditional_prices_20260919_v1/plan.json'
PLAN_SHA = '5e3fc9d87dd180d458265bf256e55c04b51da3b9c74be2a58a187beb6e99daf0'
FACTS = BASE/'remaining_standard_split_evidence_20260912_v1/all_32_event_status.json'
FACTS_SHA = '99119e5c3664b272d65eec498fb18714feb4fa7aa43e0ceff9682c79df8cafae'
EVIDENCE = {
 'EXC': ('provider_returned_event_adjudication_queue_20260912_v1/exc_official_event.response.bin',
   '17b31d310538f940b3fbfba0fefdb1535c5656f457404326bdad96a0da3f984e',
   ['February 02, 2022', 'completed the separation of Constellation Energy Corp.', 'trade on Nasdaq under the ticker symbol "EXC."', 'shareholders will retain their current shares of Exelon stock.']),
 'HON': ('ndx_current_component_evidence_20260912_v1/hona_completed_spinoff.response.bin',
   'cebe78ef0f90b6ee211ab2bae6bb827b4b59f9c806ebbdcdae2c0a6ac6673e59',
   ['June 29, 2026', 'has completed the previously announced reverse stock split', 'ratio of 1-for-2',
    'split-adjusted basis effective at the market opening today', 'new CUSIP number (438516205)']),
 'LRCX': ('remaining_standard_split_evidence_20260912_v1/lrcx.response.bin',
   'bb6602b62f62d214a12b8439c99cec343105658593a92ba36173e20fb27d55b9',
   ['common stock will begin trading on a post-split basis at the market open on Thursday, October 3, 2024', 'existing trading symbol "LRCX."']),
 'WDC': ('current_listing_segments_20260919_v1/sndk_when_issued.response.bin',
   '6372e4413c69bd25bb9b28d6bafd598051c22dde6373a7d4af39eff3d3be65dc',
   ['Pending contingencies have been satisfied', 'Parent Company/Issue: Western Digital Corporation Common Stock CUSIP: 958102105 Symbol: WDC',
    'EX Date: February 24, 2025', 'Symbol: WDCVV CUSIP: 958102121']),
}
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(), Path(core.__file__).resolve())}


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result: raise ValueError('Duplicate JSON field')
        result[k] = v
    return result


def verify(sources):
    if any(sources.get(p) != h for p,h in LOADED.items()): raise ValueError('Loaded source omitted')
    for p,h in sources.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h: raise ValueError('Source drift')


def build():
    sources = dict(LOADED)
    def raw(path, sha):
        path = str(Path(path).resolve()); value = Path(path).read_bytes()
        if hashlib.sha256(value).hexdigest() != sha: raise ValueError('Hard captured bytes changed')
        if path in sources and sources[path] != sha: raise ValueError('Source collision')
        sources[path] = sha; return value
    plan = json.loads(raw(PLAN, PLAN_SHA), object_pairs_hook=unique)
    facts = json.loads(raw(FACTS, FACTS_SHA), object_pairs_hook=unique)
    lrcx, = [r for r in facts['specific_new_events'] if r['ticker']=='LRCX']
    if (lrcx['first_adjusted_trading_date'] != '2024-10-03' or lrcx['cusip'] != '512807306'
            or lrcx['identity_transition_requires_explicit_mapping'] is not True): raise ValueError('Hard post-action LRCX fact differs')
    raw(lrcx['identity_evidence']['raw_path'], lrcx['identity_evidence']['raw_sha256'])
    blocked = [t for t in plan['tasks'] if t['mode']=='BLOCKED_COMPLEX_OR_IDENTITY']
    if {t['ticker'] for t in blocked} != {'CMCSA','EXC','HON','LRCX','TRI','WDC'}: raise ValueError('Exact six blocked task set required')
    output=[]
    for task in blocked:
        ticker=task['ticker']; wire=raw(task['raw_path'],task['raw_sha256'])
        decoded=gzip.decompress(wire) if wire[:2]==b'\x1f\x8b' else wire
        body=json.loads(decoded,object_pairs_hook=unique)['chart']['result'][0]
        if body['meta']['symbol']!=ticker or body['meta']['currency']!='USD':raise ValueError('Exact channel/USD required')
        def date_from_timestamp(t):
            if type(t) is not int:raise ValueError('Integer timestamp required')
            return datetime.fromtimestamp(t,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        days=[date_from_timestamp(t) for t in body['timestamp']]
        if days!=sorted(set(days)):raise ValueError('Unique original provider dates required')
        events=[dict(provider_event_key=k,session=date_from_timestamp(e['date']),provider_fields=e) for k,e in body.get('events',{}).get('splits',{}).items()]
        common=dict(ticker=ticker,raw_path=task['raw_path'],raw_sha256=task['raw_sha256'],decoded_sha256=hashlib.sha256(decoded).hexdigest(),
            original_task=task,all_returned_events=events,full_provider_row_count=len(days))
        if ticker not in EVIDENCE:
            output.append(dict(common,status='BLOCKED_NO_LOCAL_PRIMARY_BOUNDARY',proposed_interval=None,
                reason='Provider action date alone does not establish post-action regular security boundary'))
            continue
        relative,sha,fragments=EVIDENCE[ticker]; path=BASE/relative
        text=' '.join(BeautifulSoup(raw(path,sha).decode('utf8'),'html.parser').get_text(' ',strip=True).split())
        if any(fragment not in text for fragment in fragments):raise ValueError('Official exact boundary text not reproduced: '+ticker)
        floor,cusip,role=core.SUPPORTED[ticker]
        calendar=[d for d in days if floor<=d<task['exclude_on_or_after']]
        proposal=core.propose_interval(ticker=ticker,calendar=calendar,returned_events=events,
            official_boundary=dict(ticker=ticker,first_post_action_session=floor,post_action_cusip=cusip,role=role),completed_before=task['exclude_on_or_after'])
        output.append(dict(common,status='CONDITIONAL_POST_ACTION_INTERVAL_PROPOSED_NOT_RECONSTRUCTED',proposed_interval=proposal,
            primary_boundary_evidence=dict(path=str(path),sha256=sha,exact_text_fragments=fragments),
            excluded_pre_boundary_provider_dates=[d for d in days if d<floor],
            receipt_or_later_dates_excluded=[d for d in days if d>=task['exclude_on_or_after']]))
    verify(sources)
    return dict(schema='SIX_BLOCKED_CHANNEL_POST_ACTION_INTERVAL_PLAN_V1',rows=output,source_hashes=sources,
        original_blocked_count=6,conditional_interval_proposals=4,still_blocked_count=2,
        original_whole_channel_guard_unchanged=True,source_scope='HARD_ORIGINAL_PLAN_AND_REFERENCED_RAW_BOUNDARY_FACTS_NOT_TRANSITIVE_HISTORICAL_CLOSURE',
        full_historical_source_closure_verified=False,quote_reconstruction_performed=False,network_requests=0,
        returns_generated=False,training_performed=False,price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    report=build(); folder=BASE/'post_action_interval_plan_20260919_v1';folder.mkdir(exist_ok=False)
    path=folder/'plan.json'
    with path.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    verify(report['source_hashes'])
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
