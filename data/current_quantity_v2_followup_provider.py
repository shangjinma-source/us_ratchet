"""Server-owned immutable follow-up bundles. Construction/read perform no writes."""
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import re
from data.current_quantity_v2_followup_review import review_reference_followup

STORAGE='data/quantity_v2_followup'
MAX_FILES=4096
MAX_TOTAL=128*1024*1024


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def safe_path(root,name):
    if (type(name)is not str or not name or '\\' in name or ':' in name
        or PurePosixPath(name).is_absolute() or any(p in ('','.','..') for p in name.split('/'))):raise ValueError('UNSAFE_BUNDLE_PATH')
    target=root/name
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):raise ValueError('BUNDLE_PATH_ESCAPE')
    return target


def read_bytes(path,limit):
    with path.open('rb') as stream:raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('BUNDLE_BYTE_LIMIT')
    return raw


def parse(raw):
    def unique(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('DUPLICATE_BUNDLE_KEY')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_BUNDLE_JSON')))


class FollowupBundleProvider:
    def __init__(self,*,repository_root,clock=lambda:datetime.now(timezone.utc)):
        self.repository_root=Path(repository_root).resolve()
        self.root=self.repository_root/STORAGE
        self.clock=clock

    def review(self,*,event_raw,binding,now):
        """Production entry: no caller-supplied filesystem path."""
        try:
            if type(event_raw)is not bytes or len(event_raw)>1024*1024:raise ValueError('EVENT_BYTE_LIMIT')
            event=parse(event_raw);identifier=event['event_id']
            if re.fullmatch('[a-f0-9]{32}',identifier)is None:raise ValueError('EVENT_ID')
            started=datetime.fromisoformat(event['request_started_at'])
            observed=datetime.fromisoformat(event['observed_at'])
            if (started.tzinfo is None or observed.tzinfo is None or not isinstance(now,datetime)
                or now.tzinfo is None or not started<=observed<=now):raise ValueError('EVENT_TIME')
            day=started.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            return self.read(binding=binding,event_path=f'events/{day}/{identifier}.json',event_bytes=event_raw,now=now)
        except (ValueError,TypeError,KeyError,AttributeError):
            return dict(status='BLOCKED_BUNDLE_VALIDATION',binding=dict(binding),reason='FOLLOWUP_SOURCE_OR_BINDING_INVALID',actual_fill_inferred=False,performance_computed=False)

    def read(self,*,binding,event_path,event_bytes,now=None):
        """Arguments come from the server's selected journal event, never URL paths."""
        try:
            if not self.root.resolve().is_relative_to(self.repository_root):raise ValueError('STORAGE_ROOT_ESCAPE')
            if (set(binding)!={'decision_id','research_version','available_cash_exact'}
                or re.fullmatch('[a-f0-9]{64}',binding['decision_id'])is None
                or binding['research_version']!='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
                or not isinstance(binding['available_cash_exact'],str)
                or re.fullmatch(r'[0-9]{1,20}(?:\.[0-9]{1,10})?(?:/[1-9][0-9]{0,20})?',binding['available_cash_exact'])is None):
                raise ValueError('EXACT_BINDING_REQUIRED')
            safe_path(self.root,event_path)
            if type(event_bytes)is not bytes or len(event_bytes)>1024*1024:raise ValueError('EVENT_BYTE_LIMIT')
            event=parse(event_bytes);context=event['research_context']
            if (event.get('schema')!='V2_GENERATED_PREVIEW_OBSERVATION_V1'
                or event.get('generated_not_confirmed_displayed')is not True
                or event.get('actual_fill_inferred')is not False):raise ValueError('EVENT_SEMANTICS')
            if (event['decision_id']!=binding['decision_id'] or context['research_id']!=binding['decision_id'][:24]
                or any(context[k]!=binding[k] for k in ('research_version','available_cash_exact'))):raise ValueError('EVENT_BINDING_MISMATCH')
            event_hash=sha256(event_bytes).hexdigest();binding_hash=sha256(canonical(binding)).hexdigest()
            index_path=safe_path(self.root,f'index/{binding_hash}/{event_hash}.json')
            if not index_path.exists():
                return dict(status='PENDING_SOURCE_CAPTURE',binding=dict(binding),event_sha256=event_hash,
                    horizons=[dict(sessions_after_reference=n,status='PENDING_SOURCE_CAPTURE',price_change_vs_reference=None) for n in (1,5,20)],
                    event_binding_checked=True,source_evidence_checked=False,actual_fill_inferred=False,performance_computed=False)
            pointer=parse(read_bytes(index_path,4096))
            if set(pointer)!={'manifest_sha256'} or re.fullmatch('[a-f0-9]{64}',pointer['manifest_sha256'])is None:raise ValueError('INVALID_BUNDLE_INDEX')
            directory=safe_path(self.root,'bundles/'+pointer['manifest_sha256'])
            raw=read_bytes(safe_path(directory,'manifest.json'),4*1024*1024)
            if sha256(raw).hexdigest()!=pointer['manifest_sha256']:raise ValueError('BUNDLE_MANIFEST_CHANGED')
            manifest=parse(raw)
            if (set(manifest)-{'trusted_chain_sources'}!={'schema','binding','event_path','event_sha256','source_hashes','daily_observations','action_evidence'}
                or manifest['schema']!='V2_FOLLOWUP_BUNDLE_V1' or manifest['binding']!=binding
                or manifest['event_path']!=event_path or manifest['event_sha256']!=event_hash):raise ValueError('BUNDLE_IDENTITY_MISMATCH')
            pins=manifest['source_hashes']
            if type(pins)is not dict or not 1<=len(pins)<=MAX_FILES or pins.get(event_path)!=event_hash:raise ValueError('BUNDLE_CLOSURE_INVALID')
            sources=safe_path(directory,'sources');files={};total=0
            for name,digest in pins.items():
                if type(digest)is not str or re.fullmatch('[a-f0-9]{64}',digest)is None:raise ValueError('INVALID_SOURCE_HASH')
                content=read_bytes(safe_path(sources,name),min(32*1024*1024,MAX_TOTAL-total))
                total+=len(content)
                if total>MAX_TOTAL or sha256(content).hexdigest()!=digest:raise ValueError('BUNDLE_SOURCE_CHANGED')
                files[name]=content
            if files[event_path]!=event_bytes:raise ValueError('BUNDLE_EVENT_CHANGED')
            chain_sources=manifest.get('trusted_chain_sources',{})
            if type(chain_sources)is not dict or len(chain_sources)>1000:raise ValueError('INVALID_CHAIN_SOURCES')
            for record,entry in chain_sources.items():
                if (re.fullmatch('[a-f0-9]{64}',record)is None or type(entry)is not dict or set(entry)!={'path','sha256'}
                    or pins.get(entry['path'])!=entry['sha256'] or entry['path'] not in files):raise ValueError('INVALID_CHAIN_CLOSURE')
            result=review_reference_followup(root=sources,binding=binding,event_path=event_path,files=files,source_hashes=pins,
                trusted_chain_sources=chain_sources,daily_observations=manifest['daily_observations'],action_evidence=manifest['action_evidence'],now=now if now is not None else self.clock())
            if any(pins.get(path)!=digest for path,digest in result['source_hashes'].items()):raise ValueError('UNDECLARED_REVIEW_SOURCE')
            result.update(bundle_sha256=pointer['manifest_sha256'],event_sha256=event_hash,bundle_bytes=total)
            return result
        except (OSError,ValueError,KeyError,TypeError,AttributeError,OverflowError):
            return dict(status='BLOCKED_BUNDLE_VALIDATION',binding=dict(binding),reason='FOLLOWUP_SOURCE_OR_BINDING_INVALID',
                actual_fill_inferred=False,performance_computed=False)
