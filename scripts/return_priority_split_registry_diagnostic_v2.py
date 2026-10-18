"""Extend v1 with NVDA original evidence and bounded saved-provider event inventory."""
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
from datetime import datetime, timezone
from fractions import Fraction
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/historical_split_registry_diagnostic_20261014_v2'
V1='tmp/historical_split_registry_diagnostic_20261014_v1/result.json'
OVERLAY='tmp/historical_official_event_overlay_20261014_v1/coverage.json'
NVDA='data/cache/research/incumbent_price_source_probe_20260912_v1/nvda_official_manifest_20260912.json'


def main():
    assert not OUT.exists(), 'Create-only v2'
    hashes={}
    def read(path,expected=None):
        path=Path(path)
        if not path.is_absolute():path=ROOT/path
        raw=path.read_bytes();actual=hashlib.sha256(raw).hexdigest()
        assert expected is None or actual==expected, str(path)
        hashes[path.relative_to(ROOT).as_posix()]=actual
        return raw
    def decoded(raw):return gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    def original_text(raw):
        raw=decoded(raw)
        text=(' '.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
              if raw.startswith(b'%PDF') else html.unescape(re.sub('<[^>]+>',' ',raw.decode('utf-8'))))
        return re.sub(r'\s*-\s*','-',re.sub(r'\s+',' ',text))
    v1=json.loads(read(V1,'51285d7060dad21bbb0f99f977a4a63ff3f4ba70d9a55b0f7d8746fa37d014c9'))
    for path,expected in v1['source_hashes'].items():read(path,expected)
    overlay=json.loads(read(OVERLAY))
    members=sorted({row['ticker'] for block in overlay['dates'] for row in block['corrected_members']})
    manifest=json.loads(read(NVDA));proof=[]
    for row in manifest['probes']:
        text=original_text(read(row['response_path'],row['response_sha256']))
        assert 'ten-for-one' in text.lower() and 'June 10, 2024' in text and 'June 7, 2024' in text
        snippets=[]
        for needle in ('ten-for-one','June 10, 2024','June 7, 2024'):
            index=text.lower().index(needle.lower());snippets.append(text[max(0,index-80):index+len(needle)+220])
        proof.append(dict(path=row['response_path'],sha256=row['response_sha256'],url=row['final_url'],
                          received_at=row['received_at_utc'],original_text_checks=snippets))
    nvda=dict(ticker='NVDA',event_date='2024-06-10',new_shares=10,old_shares=1,factor='10',
              status='SPECIFIC_ISSUER_FAQ_AND_FILED_EVENT_SUPPORTED',legal_effective_after_close='2024-06-07',
              evidence=proof,conditional_unit_conversion_event=True,
              inferred_csv_omission_context='Old nominal CSV collection ends2024-06-03, before this event')
    explicit=v1['explicit_conditional_event_table']+[nvda]
    ftnt_path='data/cache/research/legacy_pool_additional_split_probe_20260912_v1/sec_ftnt_split_8k.response.bin'
    ftnt=original_text(read(ftnt_path, v1['source_hashes'][ftnt_path]))
    ftnt_dates=[ftnt[max(0,m.start()-70):m.end()+110] for m in re.finditer(r'(?i)June\s+\d+',ftnt)]
    assert not re.search(r'(?i)June\s*23|2022[-/]06[-/]23|6/23/2022',ftnt)
    research=ROOT/'data/cache/research'
    directories=sorted(research.glob('provider_gap_*_capture_20260912_v1'))
    directories += [research/name for name in ('legacy_pool_additional_split_probe_20260912_v1',
        'incumbent_price_source_probe_20260912_v1','root_return_semantics_probe_20260912_v1',
        'preference_price_action_source_probe_20260912_v1','preference_price_action_supplement_20260912_v1')]
    def records(value):
        if isinstance(value,dict):
            yield value
            for child in value.values():yield from records(child)
        elif isinstance(value,list):
            for child in value:yield from records(child)
    references={}
    for directory in directories:
        if not directory.exists():continue
        candidates=set(directory.glob('*manifest*.json'))|set(directory.glob('*.metadata.json'))
        for path in sorted(candidates):
            document=json.loads(read(path))
            for row in records(document):
                rawpath=row.get('response_path',row.get('raw_path'))
                expected=row.get('response_sha256',row.get('raw_sha256'))
                if not rawpath or not expected:continue
                name=Path(rawpath).name.lower()
                ticker=row.get('ticker')
                if ticker not in members:
                    matches=[ticker for ticker in members if name==ticker.lower()+'.response.bin'
                             or name.startswith('yahoo_'+ticker.lower()+'_') or name=='yahoo_'+ticker.lower()+'.response.bin']
                    ticker=matches[0] if len(matches)==1 else None
                if ticker in members:
                    if rawpath in references:assert references[rawpath]['sha256']==expected
                    references[rawpath]=dict(ticker=ticker,sha256=expected,metadata_path=str(path.relative_to(ROOT)))
    observed={};coverage={ticker:[] for ticker in members}
    for path,ref in sorted(references.items()):
        raw=read(path,ref['sha256'])
        try:
            document=json.loads(decoded(raw));channels=document.get('chart',{}).get('result')
        except (ValueError,UnicodeError):channels=None
        record=dict(raw_path=path,raw_sha256=ref['sha256'],metadata_path=ref['metadata_path'])
        if not channels:
            record['status']='NO_PARSEABLE_SUCCESS_CHART';coverage[ref['ticker']].append(record);continue
        channel=channels[0]
        symbol=channel.get('meta',{}).get('symbol')
        if symbol!=ref['ticker']:
            record.update(status='PROVIDER_SYMBOL_MISMATCH',provider_symbol=symbol);coverage[ref['ticker']].append(record);continue
        inrange=[]
        for event in channel.get('events',{}).get('splits',{}).values():
            day=datetime.fromtimestamp(event['date'],timezone.utc).date().isoformat()
            if not '2022-03-01'<=day<='2024-07-31':continue
            ratio=str(Fraction(str(event['numerator']))/Fraction(str(event['denominator'])))
            key=(ref['ticker'],day,ratio)
            observed.setdefault(key,dict(ticker=ref['ticker'],event_date=day,factor=ratio,provider_sources=[]))['provider_sources'].append(record.copy())
            inrange.append(dict(event_date=day,factor=ratio))
        record.update(status='SAVED_CHART_EVENT_INVENTORY_ONLY',in_range_events=inrange,
                      absence_certifies_no_event=False)
        coverage[ref['ticker']].append(record)
    official={(row['ticker'],row['event_date'],row['factor']):row for row in explicit}
    comparison=[]
    for key,row in sorted(observed.items()):
        row['registry_status']='MATCHES_EXPLICIT_ORIGINAL_EVENT' if key in official else 'MISSING_OFFICIALLY_DATED_REGISTRY_EVENT'
        row['provider_event_is_official_authority']=False
        comparison.append(row)
    result=dict(status='COMPLETE_BOUNDED_MEMBER_PROVIDER_EVENT_INVENTORY_V2',parent_v1_sha256=hashes[V1],
        scope_start='2022-03-01',scope_end='2024-07-31',member_union=members,member_union_count=len(members),
        explicit_conditional_event_table=explicit,added_official_events=[nvda],
        provider_event_comparison=comparison,
        missing_official_registry_events=[row for row in comparison if row['registry_status'].startswith('MISSING')],
        per_ticker_saved_provider_coverage=[dict(ticker=ticker,sources=sources,
            status='NO_SAVED_CHART_IN_BOUNDED_SOURCE_SET' if not sources else 'INVENTORIED_NOT_ABSENCE_CERTIFICATION') for ticker,sources in coverage.items()],
        scanned_directories=[str(path.relative_to(ROOT)) for path in directories],
        raw_files_verified=len(references),source_hashes=hashes,
        ftnt_full_original_recheck=dict(june_date_contexts=ftnt_dates,june23_literal_found=False,
            ratio5_supported=True,official_first_adjusted_trading_date_still_unverified=True),
        all_corporate_actions_complete=False,no_event_absence_certification=True,
        official_registry_missing_events_auto_promoted=False,conversion_applied=False,
        formal_pit_verified=False,provider_quote_basis_certified=False,
        original_csv_or_panel_modified=False,network_calls=0,strategy_runs=0,book_calls=0)
    for path,expected in hashes.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected
    OUT.mkdir()
    for name,value in [('result.json',result),('explicit_conditional_events.json',explicit)]:
        raw=json.dumps(value,ensure_ascii=False,indent=2).encode('utf8')
        with (OUT/name).open('xb') as stream:stream.write(raw)
        print(name,hashlib.sha256(raw).hexdigest())
    print('members',len(members),'raws',len(references),'gaps',[(row['ticker'],row['event_date'],row['factor']) for row in result['missing_official_registry_events']])


if __name__=='__main__':main()
