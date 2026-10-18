"""Five bounded SEC web observations. No HTTP, interval certification, or admission."""
import argparse
import copy
import gzip
import hashlib
import json
import os
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = BASE / 'legacy_five_dated_facts_20260923_v1/facts.json'
FLAGS = ('full_tool_response_preserved', 'local_full_http_body_available',
         'local_http_original_bytes_available', 'historical_identity_interval_verified',
         'provider_binding_verified', 'point_in_time_verified', 'promotion_allowed',
         'trading_allowed', 'order_submission_allowed')
BOUND = {
 'note': ('DYNAMIC_LEGACY_FIVE_DATED_CUSIP_FACTS_20260923.md', 'e4434727f6d3b99442fab212e11769a3b363aec4dfbab1317044609ca5b0b0bd'),
 'adi_readback': ('data/cache/research/three_cusip_web_transcription_20260919_v1/readback.json', 'd6eb603467df281896f51fc6d5315845d4f9ea43e7d0373effff4f0cf4b52da4'),
 'adi_transcription': ('data/cache/research/three_cusip_web_transcription_20260919_v1/transcription.json', '718284f9e2e71872a789ae8acd5e525dc31772bcc6626d60bd6a06f6b0c616f5'),
 'QCOM_submissions': ('data/cache/research/current_92_sec_submissions_capture_20260919_v1/0000804328.response.bin', '8e8f0d483992eb3de5f30050e87aa2491a2440aff665276bea66aecc6473ee4e'),
 'TXN_submissions': ('data/cache/research/current_92_sec_submissions_capture_20260919_v1/0000097476.response.bin', 'ab07ead1162f12f250c82620048c1efc4b5012ea8cf8221440c9b0058c4e5340'),
}
COVERS = {
 'QCOM': ('0000804328','747525103','issuer_0000804328/000172894921000076/qcom-20210926.htm','384b5d8b249c01e07a7200ea9d93f19815d3c59b0a7ddb76d1d8d78f0b3976da'),
 'DDOG': ('0001561550','23804L103','issuer_0001561550/000156155022000009/ddog-20211231.htm','3f372783583a82bb507b0be0897d3236a277997849dec30a0a873cacea93f639'),
 'ADI': ('0000006281','032654105','issuer_0000006281/000000628121000294/adi-20211030.htm','255342488f21389d46960ed589b984d58cd60e0e1618909272a972e3a015a6ea'),
 'TXN': ('0000097476','882508104','issuer_0000097476/000009747622000009/txn-20211231.htm','87b7f5bc148aaf3d01eda87e8b7f97603c5beb588366cf852ec6cfb3c93604e5'),
 'TEAM': ('0001650372','049468101','issuer_0001650372/000165037222000078/team-20220930.htm','4f7983d953281eb213a4a322bb18efc8d7336106a0246515599733025116825d'),
}
for ticker, (_, _, relative, digest) in COVERS.items():
    BOUND[ticker + '_cover'] = ('data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/' + relative, digest)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(sources):
    if sha(SOURCE.read_bytes()) != LOADED_SHA:
        raise ValueError('Loaded source drift')
    for path, digest in sources.items():
        if sha(Path(path).read_bytes()) != digest:
            raise ValueError('Source bytes drift: ' + path)


def submission_link(value, ticker, accession, date, document):
    if str(value['cik']).zfill(10) != COVERS[ticker][0]:
        raise ValueError('Subject CIK mismatch')
    recent = value['filings']['recent']
    if recent['accessionNumber'].count(accession) != 1:
        raise ValueError('Unique accession required')
    i = recent['accessionNumber'].index(accession)
    if (recent['filingDate'][i], recent['primaryDocument'][i], recent['form'][i]) != (date, document, 'SC 13G/A'):
        raise ValueError('Accession coordinates mismatch')
    return recent['acceptanceDateTime'][i]


def excerpt(line, text):
    return {'tool_line': line, 'verbatim_value': text}


class CoverParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.values = {}

    def handle_starttag(self, tag, attrs):
        name = dict(attrs).get('name', '').lower()
        self.stack.append([tag, name, []])

    def handle_endtag(self, tag):
        positions = [i for i, item in enumerate(self.stack) if item[0] == tag]
        if not positions:
            return
        position = positions[-1]
        for _, name, text in self.stack[position:]:
            if name.startswith('dei:'):
                self.values.setdefault(name, set()).add(' '.join(''.join(text).split()))
        del self.stack[position:]

    def handle_data(self, data):
        for item in self.stack:
            item[2].append(data)


def cover_context(raw, ticker):
    parser = CoverParser()
    parser.feed(raw.decode('utf-8'))
    def field(name):
        values = parser.values.get('dei:' + name.lower(), set())
        if len(values) != 1:
            raise ValueError('Unique cover field required: ' + name)
        return next(iter(values))
    value = dict(subject_cik=field('EntityCentralIndexKey'), ticker=field('TradingSymbol'),
                 issuer_name=field('EntityRegistrantName'), security_class=field('Security12bTitle'),
                 period_end_original_text=field('DocumentPeriodEndDate'))
    if value['subject_cik'] != COVERS[ticker][0] or value['ticker'] != ticker:
        raise ValueError('Local cover coordinates differ')
    if ticker in ('DDOG', 'TEAM') and 'Class A' not in value['security_class']:
        raise ValueError('Local class A context differs')
    value['cusip_directly_verified_from_cover'] = False
    return value


def assemble(blobs):
    rows = []
    readback = json.loads(blobs['adi_readback'])
    transcript = json.loads(blobs['adi_transcription'])
    prior = [r for r in readback['rows'] if r['ticker'] == 'ADI']
    observed = [r for r in transcript['rows'] if r['ticker'] == 'ADI']
    if len(prior) != 1 or len(observed) != 1:
        raise ValueError('ADI exact saved fact required')
    adi = copy.deepcopy(prior[0])
    if (adi['cusip'], adi['subject_cik'], adi['accession']) != ('032654105','0000006281','0001104659-23-015306'):
        raise ValueError('ADI saved coordinate differs')
    adi.update(excerpts=observed[0]['excerpts'], tool_references=['SAVED_TRANSCRIPTION_AND_READBACK'],
               tool_call_started_utc=observed[0]['tool_call_started_utc'],
               tool_call_completed_utc=observed[0]['tool_call_completed_utc'],
               accepted_original_text='unknown', reporter_cik='unknown',
               evidence_mode='REUSE_SAVED_READBACK_NO_REAUDIT')
    rows.append(adi)
    for ticker, accession, date, event, document, issuer, event_text, signature, ref, sigline in (
        ('QCOM','0001104659-23-016796','2023-02-09','2022-12-30','tv01740-qualcomminc.htm','QUALCOMM Inc.','December 30, 2022','February 9, 2023','turn21view0',172),
        ('TXN','0001104659-22-018703','2022-02-10','2021-12-31','tv02027-texasinstrumentsinc.htm','Texas Instruments Inc.','December 31, 2021','February 9, 2022','turn14view0',174)):
        raw = blobs[ticker + '_submissions']
        submission = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        accepted = submission_link(submission, ticker, accession, date, document)
        directory = f'https://www.sec.gov/Archives/edgar/data/{int(COVERS[ticker][0])}/{accession.replace("-", "")}/'
        rows.append(dict(ticker=ticker, subject_cik=COVERS[ticker][0], cusip=COVERS[ticker][1], security_class='Common Stock',
            accession=accession, filing_date=date, event_date=event, source_url=directory+document,
            index_url=directory+accession+'-index.html', index_web_read_success=False,
            filing_date_evidence='LOCAL_ORIGINAL_SUBMISSIONS_SAME_ACCESSION', accepted_original_text=accepted,
            reporter_name='The Vanguard Group', reporter_cik='unknown',
            subject_cik_evidence='SAME_ACCESSION_IN_ORIGINAL_SEC_SUBMISSIONS',
            excerpts=[excerpt(10,issuer),excerpt(12,'Common Stock'),excerpt(14,COVERS[ticker][1]),excerpt(16,event_text),excerpt(sigline,signature)],
            tool_references=[ref], tool_call_started_utc='unknown', tool_call_completed_utc='unknown',
            evidence_mode='WEB_TOOL_FACTUAL_EXCERPT_NOT_FULL_RESPONSE'))
    directory = 'https://www.sec.gov/Archives/edgar/data/1357550/000135755023000062/'
    for ticker, issuer, title, line in [('DDOG','DATADOG INC','CL A COM',165),('TEAM','ATLASSIAN CORPORATION','CL A',69)]:
        rows.append(dict(ticker=ticker, subject_cik=COVERS[ticker][0], cusip=COVERS[ticker][1], security_class=title,
            accession='0001357550-23-000062', filing_date='2023-02-14', event_date=None,
            report_period='2022-12-31', accepted_original_text='2023-02-14 09:35:13', accepted_timezone='unknown',
            source_url=directory+'xslForm13F_X02/wam13fh4q2022.xml',
            index_url=directory+'0001357550-23-000062-index.html', index_web_read_success=True,
            filing_date_evidence='OFFICIAL_INDEX_LINKS_EXACT_INFORMATION_TABLE',
            reporter_name='Weiss Asset Management LP', reporter_cik='0001357550',
            subject_cik_evidence='SEPARATE_LOCAL_COVER_NAME_CLASS_CONTEXT_NOT_IN_13F_TABLE',
            subject_cik_directly_in_cusip_document=False,
            excerpts=[{'tool_line':line, 'extraction':'SELECTED_TABLE_COLUMNS_NOT_CONTIGUOUS_QUOTE',
                       'column_values':{'issuer':issuer,'class':title,'cusip':COVERS[ticker][1]}}],
            index_excerpts=[excerpt(11,'0001357550-23-000062'),excerpt(15,'2023-02-14'),excerpt(19,'2023-02-14 09:35:13'),excerpt(27,'2022-12-31'),excerpt(45,'Weiss Asset Management LP (Filer)')],
            tool_references=['turn30view0','turn31view0'], tool_call_started_utc='unknown',tool_call_completed_utc='unknown',
            old_issuer_or_class_conversion_verified=False, evidence_mode='WEB_TOOL_FACTUAL_EXCERPT_NOT_FULL_RESPONSE'))
    for row in rows:
        row.update({flag: False for flag in FLAGS})
        row['local_cover_context'] = cover_context(blobs[row['ticker']+'_cover'], row['ticker'])
        row['local_cover_reference'] = {'path':str(ROOT / BOUND[row['ticker']+'_cover'][0]), 'sha256':BOUND[row['ticker']+'_cover'][1]}
        row['continuous_identity_interval'] = None
    return {'schema':'LEGACY_FIVE_DATED_WEB_FACTS_V1', 'rows':rows, 'security_count':5,
            'scope':'DATED_FACTS_ONLY_NOT_TWELVE_SECURITY_IDENTITY_ASSEMBLY',
            'old_readback_nested_sources_reaudited':False, **{flag:False for flag in FLAGS}}


def build():
    sources = {str(SOURCE):LOADED_SHA}
    blobs = {}
    for key, (relative, digest) in BOUND.items():
        path = ROOT / relative
        raw = path.read_bytes()
        if sha(raw) != digest:
            raise ValueError('Hard anchor mismatch: ' + key)
        sources[str(path)] = digest
        blobs[key] = raw
    verify(sources)
    value = assemble(blobs)
    value['source_hashes'] = sources
    value['source_references'] = {key: {'path':str(ROOT / path), 'sha256':digest} for key,(path,digest) in BOUND.items()}
    verify(sources)
    return value


def publish(value):
    verify(value['source_hashes'])
    # Public publisher accepts only the exact hard-bound fact assembly.
    if value != build():
        raise ValueError('Publication differs from hard-bound assembly')
    payload = (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    verify(value['source_hashes'])
    if OUTPUT.read_bytes() != payload:
        raise ValueError('Published bytes mismatch')
    return {'path':str(OUTPUT),'sha256':sha(payload)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish',action='store_true')
    args = parser.parse_args()
    if not args.publish:
        parser.error('Explicit --publish required; no implicit writes')
    print(json.dumps(publish(build())))

