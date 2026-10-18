"""Exact 1..100 issuer table extraction from dated public mirrors, not security membership."""
import gzip,hashlib,json,re
from pathlib import Path
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/cache/research/adobe_historical_peer_mirror_20260919_v1'
MANIFEST=FOLDER/'manifest.json'
MANIFEST_SHA='6037713f1b675f496495bf2298e776b9cad1c0ea8a81d51fa9665e48c85f75a2'
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def extract(raw,year):
    soup=BeautifulSoup(raw,'html.parser');text=' '.join(soup.get_text(' ',strip=True).split())
    marker=f'There were 100 Index Companies in the NASDAQ-100 Index as of January 1, {year}'
    if text.count(marker)!=1:raise ValueError('Unique contemporary issuer denominator/date statement required')
    tables=[]
    for table in soup.find_all('table'):
        tables.append([[' '.join(c.get_text(' ',strip=True).split()) for c in tr.find_all(['td','th'],recursive=False)] for tr in table.find_all('tr',recursive=False) or table.select('tbody > tr')])
    matches=[i for i,rows in enumerate(tables) if ['', 'Ticker','Company'] in rows]
    if len(matches)!=(2 if year==2023 else 1) or (len(matches)==2 and matches[1]!=matches[0]+1):raise ValueError('Exact contiguous ticker/company table headers required')
    start=matches[0];rows=[]
    for block in tables[start:start+2]:
        for cells in block:
            if not any(cells) or cells==['','Ticker','Company']:continue
            if len(cells)!=3 or not cells[0].isdigit() or not re.fullmatch(r'[A-Z][A-Z0-9.\-]*',cells[1]) or not cells[2]:raise ValueError('Unexpected issuer table row')
            rows.append(dict(ordinal=int(cells[0]),ticker=cells[1],company=cells[2]))
    if [r['ordinal'] for r in rows]!=list(range(1,101)) or len({r['ticker'] for r in rows})!=100:raise ValueError('Complete distinct 1..100 issuer rows required')
    if 'GOOGL' not in {r['ticker'] for r in rows} or 'GOOG' in {r['ticker'] for r in rows}:raise ValueError('Observed Alphabet single-company coordinate changed')
    return dict(stated_as_of=f'{year}-01-01',issuer_row_count=100,rows=rows,alphabet_class_c_GOOG_in_table=False,security_class_denominator_verified=False,
        normalized_text_sha256=digest(text.encode()),denominator_statement_offset=text.index(marker))
def build():
    if digest(MANIFEST.read_bytes())!=MANIFEST_SHA:raise ValueError('Hard mirror manifest changed')
    manifest=json.loads(MANIFEST.read_bytes());sources=dict(manifest['source_hashes']);sources.update({str(SOURCE):LOADED,str(MANIFEST):MANIFEST_SHA});results=[]
    if [r['year'] for r in manifest['captures']]!=[2023,2024]:raise ValueError('Exact two dated captures required')
    for capture in manifest['captures']:
        path=Path(capture['raw_path']);raw=path.read_bytes()
        if capture['http_status']!=200 or digest(raw)!=capture['raw_sha256']:raise ValueError('Mirror response bytes/status differ')
        sources[str(path)]=capture['raw_sha256'];decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        if digest(decoded)!=capture['decoded_sha256']:raise ValueError('Decoded response differs')
        for suffix in ('started','receipt'):
            auxiliary=FOLDER/f"{capture['year']}.{suffix}.json";sources[str(auxiliary)]=digest(auxiliary.read_bytes())
        if json.loads((FOLDER/f"{capture['year']}.receipt.json").read_bytes())!=capture:raise ValueError('Persisted receipt differs')
        results.append(dict(extract(decoded,capture['year']),request_url=capture['request_url'],final_url=capture['final_url'],received_at_utc=capture['received_at_utc'],raw_path=str(path),raw_sha256=capture['raw_sha256']))
    before={r['ticker'] for r in results[0]['rows']};after={r['ticker'] for r in results[1]['rows']}
    report=dict(schema='ADOBE_DATED_MIRROR_ISSUER_TABLE_FACTS_V1',tables=results,source_hashes=sources,company_ticker_added_2024=sorted(after-before),company_ticker_absent_2024=sorted(before-after),
        mirror_not_sec_origin_http=True,original_sec_requests_failed_and_preserved=True,statement_date_is_receipt_date=False,
        issuer_table_not_all_security_classes=True,index_provider_membership_baseline_verified=False,point_in_time_verified=False,promotion_allowed=False)
    for path,sha in sources.items():
        if digest(Path(path).read_bytes())!=sha:raise ValueError('Source changed')
    return report
if __name__=='__main__':
    report=build();path=FOLDER/'issuer_table_facts.json'
    with path.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(path),sha256=digest(path.read_bytes()),counts=[t['issuer_row_count'] for t in report['tables']],added=report['company_ticker_added_2024'],absent=report['company_ticker_absent_2024'])))
