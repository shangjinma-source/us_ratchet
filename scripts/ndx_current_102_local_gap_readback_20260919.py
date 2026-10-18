"""Local-only refresh of evidence for the September 11 quote-list observation."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import sys
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_102_local_gap_research as original
PRIOR=ROOT/'data/cache/research/current_102_local_gap_20260912_v1/local_gap_plan.json'
PRIOR_SHA='f3cb3fc49ee187e3a591199f83b884ade5e3b999be385b34e730882d8f7f7926'
OUTPUT=ROOT/'data/cache/research/current_102_local_gap_20260919_v1'

def build():
    raw=PRIOR.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PRIOR_SHA:raise ValueError('Prior sealed report differs')
    prior=json.loads(raw);old_status=[]
    for path,expected in prior['source_hashes'].items():
        actual=hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None
        old_status.append(dict(path=path,expected=expected,actual=actual,unchanged=expected==actual))
    if any(not x['unchanged'] and Path(x['path']).name not in ('APP.csv','AXON.csv','STX.csv') for x in old_status):raise ValueError('Unexpected immutable source drift; review before continuing')
    current=original.build();sources=dict(current['source_hashes'])
    def bind(path,expected=None):
        path=Path(path).resolve();data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if expected is not None and digest!=expected:raise ValueError('Bound evidence differs')
        if str(path) in sources and sources[str(path)]!=digest:raise ValueError('Source changed during audit')
        sources[str(path)]=digest;return data
    for row in current['rows']:
        facts=[]
        for path in row['existing_issuer_filing_paths']:
            metadata_path=Path(str(path)+'.manifest.json')
            metadata=json.loads(bind(metadata_path)) if metadata_path.exists() else None
            data=bind(path,metadata['content_sha256'] if metadata else None)
            soup=BeautifulSoup(data,'html.parser')
            fields={}
            for name in ('EntityCentralIndexKey','TradingSymbol','Security12bTitle','DocumentPeriodEndDate'):
                found=soup.find_all(attrs={'name':lambda x:x is not None and str(x).lower()=='dei:'+name.lower()})
                fields[name]=sorted(set(' '.join(t.get_text(' ',strip=True).split()) for t in found))
            facts.append(dict(path=path,sha256=sources[str(Path(path).resolve())],sidecar=metadata,
              inline_xbrl_cover_facts=fields,document_identity_is_not_full_interval_provider_binding=True))
        row['bound_existing_filing_cover_facts']=facts
        row['same_ticker_history_join_allowed']=False
    bind(PRIOR,PRIOR_SHA);bind(Path(__file__).resolve())
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source drift at completion')
    return dict(schema='LOCAL_EVIDENCE_READBACK_20260919_FOR_20260911_QUOTE_OBSERVATION',
      audited_at_utc=datetime.now(timezone.utc).isoformat(),membership_observation_date='2026-09-11',
      latest_as_of_20260919_membership_verified=False,prior_report_path=str(PRIOR),prior_report_sha256=PRIOR_SHA,
      prior_source_count=len(old_status),prior_unchanged_source_count=sum(x['unchanged'] for x in old_status),
      prior_source_status=old_status,source_hashes=sources,quote_observation_count=102,old_channel_overlap=80,
      missing_old_channel_count=22,existing_normalized_sina_csv_count=13,existing_root_cache_count=current['root_cache_count'],
      rows=current['rows'],additional_yndx_named_paths=current['additional_yndx_named_paths'],
      price_http_capture_found_for_22_in_bounded_local_search=False,
      price_gap='13 normalized Sina CSVs end 2026-07-13; 16 mutable root caches are not raw HTTP; current source receipt/events/price basis are not established.',
      time_gap='September 11 quote observation and July 10 crosswalk receipt are separate; neither authenticates September 19 membership or historical availability.',
      identity_gap='22 current CIK lookup candidates; resolve share classes and dated corporate actions separately, especially SPCX/SNDK/NBIS/HONA/FER/ARM/WDC.',
      next_work=['Refresh official membership observation separately before claiming current membership.',
        'For the fixed old-observation 22-channel research queue, obtain original quote responses only after confirming no newer local capture exists.',
        'Keep original request, receipt, raw and decoded SHA, event horizon, and unfinalized-bar status; do not stitch old aliases.',
        'Determine actual required fit/evaluation calendar after latest completed-session cutoff is independently fixed.'],
      old_evidence_resealed=False,network_requests=False,live_files_modified=False,training_performed=False,point_in_time_verified=False,promotion_allowed=False)

if __name__=='__main__':
    report=build();OUTPUT.mkdir(parents=True,exist_ok=False);path=OUTPUT/'readback.json'
    with path.open('xb') as stream:stream.write((json.dumps(report,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),source_count=len(report['source_hashes']),unchanged=report['prior_unchanged_source_count'],prior_count=report['prior_source_count'])))
