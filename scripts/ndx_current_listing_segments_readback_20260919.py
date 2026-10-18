"""Official listing segments and provider-date diagnostics, no price identity grant."""
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'
FOLDER=BASE/'current_listing_segments_20260919_v1'
LOADED=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def extract_when_issued(raw, symbol, cusip, first, regular, settlement):
    soup=BeautifulSoup(raw.decode('utf8'),'html.parser')
    matches=[]
    for table in soup.find_all('table'):
        if table.find('table') is not None:
            continue
        cells={}
        for row in table.find_all('tr'):
            values=[' '.join(cell.stripped_strings) for cell in row.find_all(['td','th'],recursive=False)]
            if len(values)==2:
                if values[0] in cells:
                    raise ValueError('Duplicate event table label')
                cells[values[0]]=values[1]
        if cells.get('Symbol:')==symbol:
            matches.append(cells)
    expected={'Symbol:':symbol,'CUSIP:':cusip,'First Trade Date:':first,
              'Regular Way Trading Begins:':regular,'Settlement Date:':settlement}
    if matches != [expected]:
        raise ValueError('Exact unique when-issued event table differs')
    text=' '.join(soup.stripped_strings)
    return expected,text


def build():
    sources={}
    def bound(path,expected):
        path=Path(path);raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError('Source differs: '+str(path))
        if str(path) in sources and sources[str(path)]!=expected:
            raise ValueError('Source conflict')
        sources[str(path)]=expected
        return raw
    def load(path,expected):return json.loads(bound(path,expected))
    manifest=load(FOLDER/'manifest.json','772ae0a7b1d9632e16bcdf93b030c69021b167b828e6fd86644cbdc90babc12b')
    coverage=load(BASE/'current_22_price_capture_20260919_v1/coverage_readback.json','85b7c60865be7a7bfb6f86ee6d6c93b9faa5a5c662a43016911835cebe99556e')
    for artifact in (manifest,coverage):
        for path,expected in artifact['source_hashes'].items():bound(path,expected)
    captures={row['name']:row for row in manifest['captures']}
    documents={}
    for name,row in captures.items():
        if row['http_status']!=200:raise ValueError('Official source unavailable')
        raw=bound(row['raw_path'],row['raw_sha256'])
        decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        if hashlib.sha256(decoded).hexdigest()!=row['decoded_sha256']:raise ValueError('Decoded source differs')
        documents[name]=decoded
    hona,text=extract_when_issued(documents['hona_when_issued'],'HONAV','43849R105','June 15, 2026','June 29, 2026','June 30, 2026')
    if 'The symbol will change to HONA effective June 29, 2026.' not in text:raise ValueError('HONA conversion differs')
    sndk,text=extract_when_issued(documents['sndk_when_issued'],'SNDKV','80004C200','February 13, 2025','February 24, 2025','February 25, 2025')
    if 'The symbol will change to SNDK on February 24, 2025.' not in text:raise ValueError('SNDK conversion differs')
    fer=' '.join(BeautifulSoup(documents['fer_us_listing'].decode('utf8'),'html.parser').stripped_strings)
    if not all(phrase in fer for phrase in ('May 9, 2024', 'at the opening of the U.S. market today under the ticker symbol "FER"', 'Ferrovial', 'Nasdaq Global Select Market')):
        raise ValueError('FER first US listing evidence differs')
    specs=[('HONA','HONAV','43849R105','2026-06-15','2026-06-29','hona_when_issued',hona),
           ('SNDK','SNDKV','80004C200','2025-02-13','2025-02-24','sndk_when_issued',sndk),
           ('FER',None,None,None,'2024-05-09','fer_us_listing',None)]
    rows=[]
    for ticker,when_symbol,cusip,first,regular,name,table in specs:
        row=next(r for r in coverage['rows'] if r['ticker']==ticker)
        raw=bound(row['raw_path'],row['raw_sha256'])
        chart,=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result']
        dates=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in chart['timestamp']]
        completed=[d for d in dates if d<row['exclude_dates_on_or_after']]
        when=[d for d in completed if first is not None and first<=d<regular]
        unsupported=[d for d in completed if d<(first or regular)]
        regular_dates=[d for d in completed if d>=regular]
        rows.append(dict(ticker=ticker,official_when_issued_symbol=when_symbol,official_cusip=cusip,
            official_first_when_issued_date=first,official_regular_way_start=regular,extracted_event_table=table,
            provider_completed_slots=len(completed),regular_way_date_candidate_count=len(regular_dates),
            regular_way_date_candidate_first_last=[regular_dates[0],regular_dates[-1]],
            when_issued_date_candidates=when,unsupported_pre_us_listing_dates=unsupported,
            raw_path=row['raw_path'],raw_sha256=row['raw_sha256'],
            official_response_path=captures[name]['raw_path'],official_response_sha256=captures[name]['raw_sha256'],
            official_received_at_utc=captures[name]['received_at_utc'],
            proposed_regular_us_filter='session >= '+regular,
            historical_ticker_projection_for_when_issued=when_symbol,
            projection_status='OFFICIAL_EVENT_FACTS_NOT_PROVIDER_PRICE_SECURITY_BINDING',
            provider_prelisting_exchange_currency_identity_verified=False,
            when_issued_auto_inclusion_allowed=False,price_reconstruction_performed=False,
            historical_alpha_information_availability_verified=False))
    bound(Path(__file__).resolve(),LOADED)
    for path,expected in list(sources.items()):bound(path,expected)
    return dict(schema='OFFICIAL_REGULAR_VS_WHEN_ISSUED_SEGMENT_FACTS_AND_PROVIDER_DATE_DIAGNOSTIC',rows=rows,
        proposed_policy='Regular US research requires documented regular-way floor; when-issued segments separate and opt-in, not relabeled regular ticker.',
        fer_prelisting_policy='Exclude from regular US coordinates; no inference whether foreign, OTC, synthetic, or another venue.',
        source_page_initial_date_is_not_capture_time=True,updated_page_contents_not_proven_available_on_initial_date=True,
        old_provider_bodies_unchanged=True,alias_stitching_performed=False,provider_identity_binding_verified=False,
        point_in_time_verified=False,promotion_allowed=False,source_hashes=dict(sorted(sources.items())))


if __name__=='__main__':
    report=build();path=FOLDER/'listing_segment_facts.json'
    raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as handle:handle.write(raw)
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),counts=[(r['ticker'],r['regular_way_date_candidate_count'],len(r['when_issued_date_candidates']),len(r['unsupported_pre_us_listing_dates'])) for r in report['rows']])))
