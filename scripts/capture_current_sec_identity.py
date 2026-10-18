"""Bounded official SEC identity capture; no strategy/account/runtime mutation."""
import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 8 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def save(path, value):
    raw = json.dumps(value, indent=2, ensure_ascii=False).encode()
    with path.open('xb') as stream:
        stream.write(raw)
    return digest(raw)


def company_name(value):
    """Spelling/punctuation equivalence only; never edit-distance/name inference."""
    words = re.findall(r'[A-Z0-9]+', value.upper())
    aliases = {'INCORPORATED':'INC', 'CORPORATION':'CORP', 'LIMITED':'LTD',
               'HOLDINGS':'HLDGS', 'COMPANY':'CO'}
    return ' '.join(aliases.get(word, word) for word in words)


def subject_fields(raw):
    require(type(raw) is bytes and 0 < len(raw) <= LIMIT, 'RAW_SIZE')
    lines = [re.sub(r'\s+', ' ', line).strip() for line in
             BeautifulSoup(raw, 'html.parser').get_text('\n', strip=True).splitlines()]
    fields = {}; positions = []
    for key, label in [('issuer','(Name of Issuer)'), ('security_class','(Title of Class of Securities)'),
                       ('cusip','(CUSIP Number)'), ('event_date','(Date of Event Which Requires Filing of this Statement)')]:
        indexes = [i for i, line in enumerate(lines) if line.lower() == label.lower()]
        require(len(indexes) == 1 and indexes[0] > 0, 'SUBJECT_LABEL_NOT_UNIQUE:' + key)
        positions.append(indexes[0])
        fields[key] = lines[indexes[0]-1]
    require(positions == sorted(positions) and positions[-1]-positions[0] <= 16,
            'SUBJECT_FIELDS_NOT_ONE_COVER_SEGMENT')
    require(re.fullmatch('[A-Z0-9]{9}', fields['cusip']) is not None, 'SUBJECT_CUSIP_FORMAT')
    require(bool(fields['security_class'].strip()), 'SUBJECT_CLASS_REQUIRED')
    fields['event_date'] = datetime.strptime(fields['event_date'], '%m/%d/%Y').date().isoformat()
    return fields


def check_subject(member, submissions, fields, filing_date, today):
    cik = member['issuer_id'].split(':')[1]
    require(str(submissions['cik']).zfill(10) == cik and member['ticker'] in submissions['tickers'],
            'CURRENT_SUBMISSIONS_IDENTITY_MISMATCH')
    require(member['security_id'].startswith('security:' + cik + ':'), 'INPUT_ISSUER_MISMATCH')
    require(date.fromisoformat(filing_date).isoformat() == filing_date
            and f'{today[:4]}-01-01' <= filing_date <= today, 'NOT_CURRENT_YEAR_FILING')
    require(fields['event_date'] <= filing_date, 'FUTURE_EVENT_DATE')
    if company_name(fields['issuer']) != company_name(submissions['name']):
        return 'SUBJECT_NAME_MISMATCH_NOT_ACCEPTED'
    require(fields['cusip'] == member['security_id'].split(':')[-1], 'CURRENT_SUBJECT_CUSIP_CONFLICT')
    return 'MATCHED_EXACT_CURRENT_IDENTIFIER'


class Capture:
    def __init__(self, directory, user_agent):
        self.directory = directory
        self.user_agent = user_agent
        self.calls = 0
        self.last_request = 0.0
        # The access stop survives process restarts, including receipts written
        # before this guard existed. No new request may bypass a cached denial.
        require(not any(json.loads(p.read_bytes()).get('status') in (403,429)
                        for p in directory.glob('*.json')), 'SEC_ACCESS_LIMIT_STOP_NO_RETRY')

    def get(self, url):
        parsed = urlparse(url)
        require(parsed.scheme == 'https' and parsed.netloc in ('www.sec.gov','data.sec.gov')
                and not parsed.query and not parsed.fragment, 'OFFICIAL_SEC_URL_REQUIRED')
        key = digest(url.encode())
        rawpath = self.directory / (key + '.bin')
        receiptpath = self.directory / (key + '.json')
        if receiptpath.exists():
            receipt = json.loads(receiptpath.read_bytes())
            require(receipt['url'] == url and rawpath.stat().st_size <= LIMIT, 'CACHE_BINDING')
            raw = rawpath.read_bytes()
            require(digest(raw) == receipt['sha256'], 'CACHE_CHANGED')
        else:
            require(not rawpath.exists(), 'INCOMPLETE_CACHE_NO_IMPLICIT_RETRY')
            time.sleep(max(0, 1.0 - (time.monotonic()-self.last_request)))
            self.last_request = time.monotonic()
            started = datetime.now(timezone.utc).isoformat()
            self.calls += 1
            try:
                request = urllib.request.Request(url, headers={'User-Agent':self.user_agent})
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read(LIMIT+1); status = response.status; final_url = response.geturl()
            except urllib.error.HTTPError as error:
                raw = error.read(LIMIT+1); status = error.code; final_url = error.geturl()
            except OSError:
                raw = b''; status = 'TRANSPORT_UNAVAILABLE'; final_url = None
            require(len(raw) <= LIMIT, 'RAW_TOO_LARGE')
            with rawpath.open('xb') as stream:
                stream.write(raw)
            receipt = dict(url=url, status=status, started_at=started,
                           captured_at=datetime.now(timezone.utc).isoformat(), sha256=digest(raw), bytes=len(raw),final_url=final_url)
            save(receiptpath, receipt)
        require(receipt['status'] not in (403,429), 'SEC_ACCESS_LIMIT_STOP_NO_RETRY')
        require(receipt['status'] == 200, 'SOURCE_HTTP_UNAVAILABLE')
        final = urlparse(receipt.get('final_url') or '')
        require(final.scheme == 'https' and final.netloc in ('www.sec.gov','data.sec.gov'),
                'FINAL_OFFICIAL_SEC_URL_UNVERIFIED')
        return raw, receipt, [rawpath, receiptpath]


def review_member(member, capture, today):
    cik = member['issuer_id'].split(':')[1]
    raw, receipt, sourcepaths = capture.get('https://data.sec.gov/submissions/CIK'+cik+'.json')
    submissions = json.loads(raw)
    require(str(submissions['cik']).zfill(10) == cik and member['ticker'] in submissions['tickers'],
            'CURRENT_SUBMISSIONS_IDENTITY_MISMATCH')
    recent = submissions['filings']['recent']; considered = []
    indexes = [i for i, form in enumerate(recent['form']) if form in ('SCHEDULE 13G','SCHEDULE 13G/A')
               and f'{today[:4]}-01-01' <= recent['filingDate'][i] <= today]
    indexes.sort(key=lambda i: (recent['filingDate'][i], recent['accessionNumber'][i]), reverse=True)
    require(indexes, 'NO_CURRENT_YEAR_SUBJECT_FILING')
    for i in indexes[:6]:
        accession = recent['accessionNumber'][i]; primary = recent['primaryDocument'][i]
        require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) is not None
                and re.fullmatch(r'[A-Za-z0-9_./-]+', primary) is not None
                and '..' not in primary and not primary.startswith('/'), 'FILING_LOCATOR_INVALID')
        url = 'https://www.sec.gov/Archives/edgar/data/'+str(int(cik))+'/'+accession.replace('-','')+'/'+primary
        filing_raw, filing_receipt, filingpaths = capture.get(url)
        # Malformed/ambiguous current evidence cannot be made clean by falling
        # back to an older filing. Only a fully decoded other subject may skip.
        fields = subject_fields(filing_raw)
        status = check_subject(member, submissions, fields, recent['filingDate'][i], today)
        if status != 'MATCHED_EXACT_CURRENT_IDENTIFIER':
            considered.append(dict(accession=accession, reason=status, subject=fields)); continue
        paths = sourcepaths + filingpaths
        references = [path.relative_to(ROOT).as_posix() for path in paths]
        return dict(**{key:member[key] for key in ('ticker','security_id','issuer_id')},
            security_class=fields['security_class'], cusip=fields['cusip'], subject_issuer_name=fields['issuer'],
            status='READY_CONDITIONAL_IDENTITY', identity_reviewed=True,
            no_unresolved_identifier_conflict=True, unresolved=[], source_references=references,
            source_hashes={path.relative_to(ROOT).as_posix():digest(path.read_bytes()) for path in paths},
            accession=accession, filing_date=recent['filingDate'][i], event_date=fields['event_date'],
            reviewed_at=filing_receipt['captured_at'], considered_not_used=considered,
            conflict_flag_scope='Only current identifiers explicitly matched in retained subject filing and issuer submissions.',
            current_continuity_verified=False, point_in_time_verified=False, corporate_actions_complete=False,
            execution_admitted=False, independent_review_pending=True,
            limitations=['No all-period continuity or exhaustive action certification. Existing execution quote/unit gates still apply.'])
    raise ValueError('NO_EXACT_SUBJECT_WITHIN_SIX_CURRENT_FILINGS')


def run(*, descriptor_path, descriptor_sha256, coverage_path, output, capture=False,
        user_agent='us_ratchet bounded-identity-research/1.0'):
    from data.current_quantity_v2_service_factory import create_service
    service = create_service(root=ROOT, descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256)
    descriptor, data, _, _ = service._load()
    coverage = json.loads((ROOT/coverage_path).read_bytes())
    members = [dict(ticker=meta['ticker'], security_id=sid, issuer_id=meta['issuer_id'])
               for sid,meta in data['search_arguments']['metadata'].items()]
    blocked = {row['security_id'] for row in coverage['identity_results'] if row['status']=='BLOCKED'}
    require(blocked <= {m['security_id'] for m in members}, 'COVERAGE_DOMAIN_MISMATCH')
    selected = [m for m in members if m['security_id'] in blocked]
    plan = dict(descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256,
                coverage_path=coverage_path, coverage_sha256=digest((ROOT/coverage_path).read_bytes()),
                members=selected, request_interval_seconds=1, maximum_filings_per_issuer=6,
                input_sha256=descriptor['source_hashes'][descriptor['input_path']], production_changed=False)
    if not capture:
        return dict(status='OFFLINE_PLAN_ONLY', count=len(selected), network_calls=0, plan=plan)
    output = (ROOT/output).resolve(); require(output.is_relative_to(ROOT/'tmp'), 'ISOLATED_TMP_OUTPUT_REQUIRED')
    output.mkdir(parents=True, exist_ok=True)
    if (output/'plan.json').exists():
        require(json.loads((output/'plan.json').read_bytes()) == plan, 'EXISTING_PLAN_MISMATCH')
    else:
        save(output/'plan.json', plan)
    cachedir=output/'raw'; cachedir.mkdir(exist_ok=True)
    transport=Capture(cachedir,user_agent); today=datetime.now(timezone.utc).date().isoformat(); rows=[]; halted=False
    for member in selected:
        path=output/(member['ticker']+'.json')
        if path.exists():
            row=json.loads(path.read_bytes())
            require(all(row[k]==member[k] for k in ('ticker','security_id','issuer_id')), 'ROW_BINDING_CHANGED')
            for name,h in row.get('source_hashes',{}).items():
                require(digest((ROOT/name).read_bytes())==h,'ROW_SOURCE_CHANGED')
                if name.endswith('.json'):
                    evidence=json.loads((ROOT/name).read_bytes())
                    if 'url' in evidence and 'status' in evidence:
                        final=urlparse(evidence.get('final_url') or '')
                        require(evidence['status']==200 and final.scheme=='https'
                                and final.netloc in ('www.sec.gov','data.sec.gov'),
                                'CACHED_ROW_FINAL_URL_UNVERIFIED')
        else:
            try:
                row=review_member(member,transport,today)
            except (ValueError,KeyError,TypeError) as error:
                reason=str(error) if isinstance(error,ValueError) else type(error).__name__
                row=dict(**member,status='BLOCKED',reason=reason,execution_admitted=False)
                halted=reason=='SEC_ACCESS_LIMIT_STOP_NO_RETRY'
            save(path,row)
        rows.append(row)
        progress=dict(processed=len(rows), total=len(selected), ready=sum(r['status']=='READY_CONDITIONAL_IDENTITY' for r in rows),
                      blocked=sum(r['status']=='BLOCKED' for r in rows), last_ticker=member['ticker'], network_calls=transport.calls,halted=halted)
        (output/'progress.json').write_text(json.dumps(progress,indent=2))
        print(json.dumps(progress),flush=True)
        if halted:break
    result=dict(status='HALTED_ACCESS_LIMIT' if halted else 'COMPLETE_IDENTITY_REVIEW_PENDING_INDEPENDENT',
                rows=rows,requested_count=len(selected),source_hashes={p:h for r in rows for p,h in r.get('source_hashes',{}).items()},
                network_calls=transport.calls,production_changed=False,search_calls=0)
    save(output/'result.json',result)
    return dict(status=result['status'],processed=len(rows),network_calls=transport.calls)


def main():
    parser=argparse.ArgumentParser()
    for name in ('descriptor-path','descriptor-sha256','coverage-path','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--capture',action='store_true');args=parser.parse_args()
    print(json.dumps(run(**vars(args)),indent=2))


if __name__=='__main__':main()
