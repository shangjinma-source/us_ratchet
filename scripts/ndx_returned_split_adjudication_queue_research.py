"""Classify returned events and capture a bounded primary-source first step."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_component_evidence_research as transport
BASE=ROOT/'data/cache/research'
INDEX=BASE/'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json'
INDEX_SHA='5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117'
COVERAGE=BASE/'provider_gap_batch12_capture_20260912_v1/coverage_addendum.json'
COVERAGE_SHA='6fc0d5ee29cecb12ae70433fece84cd43e64ae90030aa92fe00f95880a3b1b22'
OUTPUT=BASE/'provider_returned_event_adjudication_queue_20260912_v1'
PRIMARY={
 'AMZN':'https://ir.aboutamazon.com/faqs/default.aspx/1000/',
 'EXC':'https://www.exeloncorp.com/newsroom/exelon-completes-separation-of-constellation',
 'AZN':'https://www.astrazeneca.com/media-centre/press-releases/2026/astrazeneca-to-complete-direct-listing-on-NYSE.html',
 'SIRI':'https://investor.siriusxm.com/news-events/press-releases/detail/2105/siriusxm-kicks-off-new-phase-as-an-independent-public',
 'ILMN':'https://www.illumina.com/company/news-center/press-releases/press-release-details.html?newsid=7881',
 'TSLA':'https://ir.tesla.com/press-release/tesla-announces-three-one-stock-split',
 'PANW':'https://investors.paloaltonetworks.com/static-files/2655de46-df5a-4a15-ac9b-fde81baae9f0',
 'DXCM':'https://investors.dexcom.com/news/news-details/2022/Dexcom-Announces-Four-for-One-Forward-Stock-Split/default.aspx',
 'CMCSA':'https://www.sec.gov/Archives/edgar/data/1166691/000095010326000079/dp239108_ex9901.htm',
 'HON':'https://www.honeywell.com/us/en/press/2026/06/honeywell-board-of-directors-sets-record-date-and-announces-expected-timing-for-spin-off-of-honeywell-aerospace-and-honeywell-reverse-stock-split',
}
COMPLEX={
 ('EXC','2022-02-02'):'SPINOFF_CONSTELLATION_NOT_1_402_NEW_EXELON_SHARES',
 ('CMCSA','2026-01-05'):'SPINOFF_VERSANT_NOT_1_067_NEW_COMCAST_SHARES',
 ('HON','2025-10-30'):'SPINOFF_SOLSTICE_NOT_1_061_NEW_HONEYWELL_SHARES',
 ('HON','2026-06-29'):'HONA_SPINOFF_AND_HON_REVERSE_SPLIT_COMBINED_NOT_PURE_1907_2000',
 ('ILMN','2024-06-25'):'GRAIL_SPINOFF_NOT_1_028_NEW_ILLUMINA_SHARES',
 ('AZN','2026-02-02'):'NASDAQ_ADS_TO_NYSE_ORDINARY_SHARE_AND_VENUE_TRANSITION',
 ('SIRI','2024-09-10'):'LIBERTY_SPLITOFF_AND_NEW_SIRIUS_MERGER_SECURITY_EXCHANGE',
}
EXISTING={'GOOG','GOOGL','FTNT','AVGO','NVDA'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if sha(INDEX)!=INDEX_SHA or sha(COVERAGE)!=COVERAGE_SHA:raise ValueError('Hard source SHA differs')
    index=json.loads(INDEX.read_bytes());coverage=json.loads(COVERAGE.read_bytes())
    sources=dict(index['source_hashes']);sources[str(INDEX)]=INDEX_SHA;sources[str(COVERAGE)]=COVERAGE_SHA
    for path,digest in sources.items():
        if sha(path)!=digest:raise ValueError('Event source closure differs')
    events={};ticker_events=defaultdict(list)
    by_ticker={row['ticker']:row for row in coverage['candidate_rows']}
    for ticker,variants in index['provider_channels'].items():
        for variant in variants:
            for event in variant['returned_events']['splits']:
                value=event['provider_fields'];key=(ticker,event['session'])
                pair=(value['numerator'],value['denominator'],value['splitRatio'])
                if key in events and events[key]['provider_ratio_fields']!=pair:raise ValueError('Conflicting provider event ratios')
                if key not in events:
                    periods=[]
                    for period in by_ticker[ticker]['periods']:
                        calendar=coverage['calendar_requirements'][period['selection_date']]['return_dates']
                        periods.append(dict(selection_date=period['selection_date'],training_first=calendar[0],training_last=calendar[-1],
                                            event_in_training_returns=event['session'] in calendar,
                                            event_after_training=event['session']>calendar[-1],
                                            event_before_training=event['session']<calendar[0]))
                    events[key]=dict(ticker=ticker,session=event['session'],provider_ratio_fields=pair,raw_sources=[],applicable_original_periods=periods,
                                     semantic_classification=COMPLEX.get(key,'PREVIOUSLY_EVIDENCED_STANDARD_SPLIT' if ticker in EXISTING else 'STANDARD_OR_REVERSE_SPLIT_CANDIDATE_REQUIRES_OFFICIAL_CONFIRMATION'),
                                     pure_share_multiplier_admitted=False,
                                     after_window_adjustment_note='Later events can affect currently served historical nominal quote scale; cannot use a distribution-price adjustment as a share-count multiplier.')
                events[key]['raw_sources'].append(dict(path=variant['path'],sha256=variant['sha256'],event=event))
    if len(events)!=32:raise ValueError('Returned split denominator differs')
    for key,event in events.items():ticker_events[key[0]].append(event)
    queue=[]
    for ticker,rows in ticker_events.items():
        if ticker in EXISTING:continue
        complex_event=any((ticker,row['session']) in COMPLEX for row in rows)
        historical=any(any(p['event_in_training_returns'] for p in row['applicable_original_periods']) for row in rows)
        queue.append(dict(ticker=ticker,priority=0 if complex_event and historical else 1 if historical else 2 if complex_event else 3,
                          event_sessions=[row['session'] for row in rows],primary_url=PRIMARY.get(ticker),
                          official_lookup_query=(ticker+' official investor relations stock split '+','.join(row['session'] for row in rows)),
                          required_fields=['dated_official_publication','distribution_or_effective_date','first_adjusted_trading_session','share_class_and_issuer_identity','new_shares_per_old_share_or_distribution_entitlement','non_cash_or_cash_in_lieu_treatment'],
                          first_safe_action='Adjudicate corporate-action semantics separately from provider numeric ratio; preserve publication time versus receipt time.',
                          historical_price_basis_ready=False))
    queue.sort(key=lambda row:(row['priority'],row['ticker']))
    OUTPUT.mkdir(parents=True,exist_ok=False);transport.OUTPUT=OUTPUT
    # Only this first bounded set is requested. Other listed URLs remain a plan.
    initial=['AMZN','EXC','AZN','SIRI','ILMN','TSLA']
    with ThreadPoolExecutor(max_workers=2) as executor:
        captures=list(executor.map(transport.capture,[(ticker.lower()+'_official_event',PRIMARY[ticker]) for ticker in initial]))
    for row in captures:
        if row.get('raw_path'):sources[row['raw_path']]=row['raw_sha256']
    for path in (Path(__file__).resolve(),Path(transport.__file__).resolve()):sources[str(path)]=sha(path)
    report=dict(schema='RETURNED_PROVIDER_EVENTS_OFFICIAL_ADJUDICATION_QUEUE',source_hashes=sources,returned_event_count=32,
                returned_events=[events[key] for key in sorted(events)],official_evidence_first_capture=captures,remaining_official_adjudication_queue=queue,
                existing_standard_evidence_tickers=sorted(EXISTING),complex_action_keys=[dict(ticker=ticker,session=day,interpretation=value) for (ticker,day),value in COMPLEX.items()],
                no_event_response_does_not_certify_no_corporate_actions=True,
                ticker_events_not_exhaustive=['META FB-to-META identity event has no share-ratio split','WBD predecessor class conversion requires mapping','EA acquisition and halt; five failed channels remain unresolved'],
                full_ndx_historical_official_baseline_verified=False,provider_return_semantics_globally_verified=False,
                official_capture_does_not_itself_adjudicate_share_multiplier=True,point_in_time_verified=False,promotion_allowed=False,
                new_quote_requests=False,training_returns_generated=False)
    for path,digest in sources.items():
        if sha(path)!=digest:raise ValueError('Source drift before final save')
    path=OUTPUT/'report.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=sha(path),events=32,queue=len(queue),captures=[(x['name'],x.get('http_status')) for x in captures])))


if __name__=='__main__':main()
