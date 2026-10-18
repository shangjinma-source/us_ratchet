"""Create-only public-page evidence capture, never a membership certification."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/official_ndx_public_access_20261003_v1'
PAGES = (
 ('companies', 'https://www.nasdaq.com/products/global-indexes/nasdaq-100/companies'),
 ('giw_weighting', 'https://indexes.nasdaqomx.com/Index/Weighting/NDX'),
)
LIMIT = 8 * 1024 * 1024
FLAGS = dict.fromkeys(('membership_complete', 'membership_effective_date_verified',
 'publication_time_verified', 'point_in_time_verified', 'candidate_seal_allowed',
 'cohort_registration_allowed', 'live_cache_modified', 'credentials_sent',
 'parsed_membership_generated', 'prior_mapping_used'), False)

def require(ok, message):
 if not ok: raise ValueError(message)
def now(): return datetime.now(timezone.utc).isoformat()
def encoded(v): return (json.dumps(v, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
def write(path, raw):
 with path.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
 return {'path': str(path), 'sha256': sha256(raw).hexdigest(), 'byte_count': len(raw)}
def save(path, obj): return write(path, encoded(obj))
def guard(): require(sha256(SOURCE.read_bytes()).hexdigest()==LOADED_SHA, 'Loaded capture source drift')
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def fetch(url):
 # Fresh opener, no cookie jar, no authentication, no redirect follow-through.
 req=Request(url, headers={'User-Agent':'Mozilla/5.0', 'Accept':'text/html'}, method='GET')
 try: response=build_opener(NoRedirect()).open(req, timeout=30)
 except HTTPError as error: response=error
 with response:
  raw=response.read(LIMIT+1)
  return raw, {'http_status':response.code, 'response_url':response.geturl(),
    'headers':{k:response.headers.get(k) for k in ('Content-Type','Content-Encoding','Date','Last-Modified','Location')}}

def run(*, execute=False):
 require(execute is True, 'Explicit execution required')
 guard();require(not OUTPUT.exists(), 'Create-only capture: no retry')
 OUTPUT.mkdir(parents=True)
 refs=[];receipts=[];current=None
 try:
  refs.append(save(OUTPUT/'started.json',dict(schema='OFFICIAL_NDX_PUBLIC_PAGE_CAPTURE_STARTED_V1',
   started_at_utc=now(), pages=[dict(name=n,url=u) for n,u in PAGES],
   source_reference=dict(path=str(SOURCE),sha256=LOADED_SHA), **FLAGS)))
  for name,url in PAGES:
   current=name;start=now();rawref=None;error=None;metadata=None
   try:
    raw,metadata=fetch(url)
    # Persist returned bytes before response/size/HTTP interpretation.
    rawref=write(OUTPUT/(name+'.response.bin'),raw);refs.append(rawref)
    require(len(raw)<=LIMIT, 'Response resource limit; saved prefix is not complete response')
   except Exception as exc:
    error=dict(type=type(exc).__name__,message=str(exc))
   receipt=dict(schema='OFFICIAL_NDX_PUBLIC_PAGE_RECEIPT_V1',name=name,
    request=dict(method='GET',url=url),started_at_utc=start,completed_at_utc=now(),
    response_reference=rawref,transport_metadata=metadata,error=error,
    body_complete=rawref is not None and rawref['byte_count']<=LIMIT,
    status='PUBLIC_RESPONSE_SAVED_NOT_MEMBERSHIP_AUTHORITY' if error is None else 'CAPTURE_FAILURE_RECORDED',
    http_date_is_not_publication_time=True, response_not_parsed=True, **FLAGS)
   rr=save(OUTPUT/(name+'.receipt.json'),receipt);refs.append(rr);receipts.append(rr);guard()
  manifest=dict(schema='OFFICIAL_NDX_PUBLIC_ACCESS_EVIDENCE_V1',
   status='PUBLIC_ACCESS_EVIDENCE_ONLY_NO_MEMBER_LIST',receipts=receipts,
   outputs=refs,source_reference=dict(path=str(SOURCE),sha256=LOADED_SHA),
   observed_response_does_not_prove_all_public_endpoints_unavailable=True,
   unavailable_member_list_is_not_empty_universe=True, **FLAGS)
  mr=save(OUTPUT/'manifest.json',manifest);refs.append(mr);guard()
  require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in refs},'Exact capture namespace')
  for r in refs:require(sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'],'Saved evidence drift')
  return mr
 except BaseException as exc:
  save(OUTPUT/'failure.json',dict(schema='OFFICIAL_NDX_PUBLIC_CAPTURE_FAILURE_V1',
   status='FAILED_NO_RETRY',current_page=current,retained_references=refs,
   error=dict(type=type(exc).__name__,message=str(exc)),**FLAGS))
  raise

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
 print(json.dumps(run(execute=p.parse_args().execute),sort_keys=True))
