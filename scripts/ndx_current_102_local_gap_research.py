"""Bounded local audit of 22 current quote-list channels absent from the old proxy captures."""
import csv,hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NAMES='ALAB ALNY APP ARM AXON CRWV FER HONA LITE MPWR MSTR NBIS PLTR RKLB SHOP SNDK SPCX STX TER TRI WDC WMT'.split()
THIRTEEN='ALNY APP ARM AXON FER MPWR MSTR PLTR SHOP STX TRI WDC WMT'.split()
OUTPUT=ROOT/'data/cache/research/current_102_local_gap_20260912_v1'

def build():
    sources={}
    def bind(path,expected=None):
        path=Path(path).resolve();raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and digest!=expected:raise ValueError('Source differs: '+str(path))
        if str(path) in sources and sources[str(path)]!=digest:raise ValueError('Source drift')
        sources[str(path)]=digest;return raw
    def rows(path):
        return list(csv.DictReader(bind(path).decode('utf-8-sig').splitlines()))
    observation_path=ROOT/'data/cache/research/ndx_current_quote_list_capture_20260912_v1/observation.json'
    observation=json.loads(bind(observation_path,'950a76544cc63d11ed492b8feb37f2d7eebe4212f42b1761e9ac9a65938a5e38'))
    index=json.loads(bind(ROOT/'data/cache/research/provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json','5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117'))
    if len(observation['observed_symbols'])!=102 or sorted(set(observation['observed_symbols'])-set(index['provider_channels']))!=NAMES:raise ValueError('Current 102 minus old 107 exact 22 differs')
    crosswalk_path=ROOT/'data/cache/candidate_pools/ndx_history/sec_company_tickers_exchange.json'
    crosswalk_manifest=json.loads(bind(str(crosswalk_path)+'.manifest.json'))
    crosswalk=json.loads(bind(crosswalk_path,crosswalk_manifest['content_sha256']))
    current=[dict(zip(crosswalk['fields'],row)) for row in crosswalk['data'] if row[2] in NAMES]
    if len(current)!=22 or len({x['ticker'] for x in current})!=22:raise ValueError('Unique current crosswalk candidate per symbol required')
    identities=rows(ROOT/'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv')
    source_rows=rows(ROOT/'data/cache/research/ndx_v11_current_price_basis_v2/sources.csv')
    price_basis=bind(ROOT/'data/ndx_price_basis.py').decode();cn_source=bind(ROOT/'data/cn_source.py').decode('utf-8-sig')
    for clause in ('cn_source.fetch_sina_daily(symbol)','normalize_unadjusted_bars(source_frame','output.to_csv(index=True)'):
        if clause not in price_basis:raise ValueError('Observed price normalization pipeline changed')
    for clause in ('content.find("(")','float(r.get("o") or c)','c_raw in (None, "", "0", "0.000")'):
        if clause not in cn_source:raise ValueError('Sina parser evidence differs')
    listing=subprocess.run(['rg','--files','--no-ignore','data/cache'],cwd=ROOT,check=True,capture_output=True,encoding='utf-8').stdout.splitlines()
    scan_names=set(NAMES+['YNDX'])
    matcher=re.compile(r'(?:^|[/\\_])('+'|'.join(scan_names)+r')(?=[._/\\-]|$)',re.I)
    named=[ROOT/path for path in listing if matcher.search(path)]
    output=[]
    for ticker in NAMES:
        matches=[p for p in named if re.search(r'(?:^|[/\\_])'+ticker+r'(?=[._/\\-]|$)',str(p),re.I)]
        row=dict(ticker=ticker,current_sec_crosswalk=next(x for x in current if x['ticker']==ticker),
          current_crosswalk_received_at_metadata=crosswalk_manifest['fetched_at'],historical_membership_or_price_identity_verified=False,
          local_identity_candidates=[x for x in identities if x['ticker']==ticker],named_local_paths=[str(p) for p in matches],
          named_http_raw_candidates=[str(p) for p in matches if p.suffix in ('.bin','.pdf')])
        root_csv=ROOT/'data/cache'/f'{ticker}.csv'
        if root_csv.exists():
            data=rows(root_csv);row['root_cache']=dict(path=str(root_csv),sha256=sources[str(root_csv)],rows=len(data),first=data[0]['Date'],last=data[-1]['Date'],
              manifest_present=Path(str(root_csv)+'.manifest.json').exists(),role='LEGACY_NORMALIZED_RETURN_CACHE_NOT_HTTP_CAPTURE')
        if ticker in THIRTEEN:
            path=ROOT/'data/cache/research/ndx_v11_current_price_basis_v1/raw'/f'{ticker}.csv'
            manifest=json.loads(bind(str(path)+'.manifest.json'));data=rows(path)
            source,=[x for x in source_rows if x['ticker']==ticker]
            if sources[str(path)]!=manifest['content_sha256'] or source['content_sha256']!=manifest['content_sha256'] or len(data)!=274:raise ValueError('Current valuation CSV binding differs')
            if data[0]['Date']!='2025-06-09' or data[-1]['Date']!='2026-07-13' or manifest['valuation_use_only'] is not True:raise ValueError('Original valuation range or use differs')
            row['valuation_csv']=dict(path=str(path),sha256=sources[str(path)],rows=len(data),first=data[0]['Date'],last=data[-1]['Date'],manifest=manifest,
              source_table_row=source,original_http_bytes_preserved_here=False,role='NORMALIZED_FILTERED_SINA_CSV_VALUATION_ONLY')
        cik=f"{row['current_sec_crosswalk']['cik']:010d}"
        row['existing_issuer_filing_paths']=[str(ROOT/p) for p in listing if ('issuer_'+cik+'/') in p.replace('\\','/') and p.endswith('.htm')]
        row['next_required_evidence']=['CAPTURE_ORIGINAL_PRICE_HTTP_RESPONSE_WITH_REQUEST_RECEIPT_AND_FULL_EVENT_HORIZON',
          'ASSESS_LATEST_COMPLETED_SESSION_AND_ACTUAL_FIT_WINDOW_NOT_OLD_274_ROW_CUTOFF',
          'BIND_SHARE_CLASS_AND_CORPORATE_ACTIONS_SEPARATELY_FROM_CURRENT_TICKER']
        row['special_identity_constraint']={
          'SPCX':'SPACEX_CURRENT_CIK1181412_IS_NOT_OLD_SPCX_ETF_NO_ALIAS_HISTORY_JOIN',
          'SNDK':'NEW_LISTING_CURRENT_CIK2023554_DO_NOT_JOIN_OLD_SANDISK_SECURITY',
          'NBIS':'NEBIUS_CURRENT_CIK1513845_YNDX_REORGANIZATION_REQUIRES_EXPLICIT_SECURITY_EVENT_CHAIN',
          'HONA':'HONEYWELL_AEROSPACE_CIK2089271_SPINOFF_SEPARATE_FROM_HON',
          'FER':'TAXONOMY_CONTAINS_RESOLVED_AND_MISSING_CUSIP_RECORDS_KEEP_BOTH',
          'ARM':'ADS_SHARE_CLASS_AND_ORDINARY_SHARE_RATIO_REQUIRE_EXPLICIT_IDENTITY',
          'WDC':'SANDISK_SPINOFF_MUST_NOT_BE_TREATED_AS_PURE_SHARE_SPLIT',
        }.get(ticker,'NO_CURRENT_TICKER_TO_HISTORICAL_IDENTITY_INFERENCE')
        output.append(row)
    for p in (Path(__file__).resolve(),):bind(p)
    for p,h in sources.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Source drift during local audit')
    return dict(schema='CURRENT_102_QUOTE_LIST_LOCAL_22_CHANNEL_GAP_PLAN',source_hashes=sources,
      current_quote_security_count=102,old_provider_channel_overlap=80,missing_old_raw_channel_count=22,
      valuation_normalized_csv_count=13,root_cache_count=sum('root_cache' in x for x in output),rows=output,
      bounded_search='RG_FILES_NO_IGNORE_DATA_CACHE_PLUS_CIK_DIRECTORIES_AND_EXPLICIT_SOURCE_PIPELINE',
      additional_yndx_named_paths=[str(p) for p in named if re.search(r'[/\\_]YNDX[._/\\-]',str(p),re.I)],
      sina_raw_response_label_does_not_mean_http_bytes_saved=True,
      sina_transformations=['JSONP_WRAPPER_REMOVED','NUMERIC_FLOAT_CONVERSION','MISSING_OR_ZERO_CLOSE_ROWS_SKIPPED','MISSING_OPEN_HIGH_LOW_FALLBACK_TO_CLOSE','DATE_RANGE_FILTER','STANDARDIZED_CSV_SERIALIZATION'],
      same_level_original_http_price_evidence_found_in_named_local_candidates=False,
      current_sec_crosswalk_is_not_historical_identity_or_pit=True,official_current_quote_date_is_not_historical_membership_effective_date=True,
      new_requests=False,old_cache_modified=False,training_performed=False,point_in_time_verified=False,promotion_allowed=False)

if __name__=='__main__':
    report=build();OUTPUT.mkdir(parents=True,exist_ok=False);path=OUTPUT/'local_gap_plan.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),missing=22,valuation_csv=13,root_cache_count=report['root_cache_count'])))
