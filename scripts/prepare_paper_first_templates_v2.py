"""Prepare isolated first-window templates; never register or execute an account."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from core.strategy_account_ledger import canonical, require
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_daily_session_capture import pinned, reject_links
from data.strategy_paper_first_window_core_v2 import SOURCES
from data.strategy_verified_context_monthly_normalizer_v1 import NORMALIZATION_CODE_PATHS


def prepare(*, root, training_reference, identity_reference, calendar_reference, output):
    root = Path(root).absolute()
    directory = root / output
    reject_links(root)
    reject_links(directory)
    require(directory.resolve().is_relative_to(root.resolve()) and directory.resolve()!=root.resolve()
            and not directory.exists(), 'PAPER_TEMPLATE_OUTPUT_MUST_BE_NEW')
    training_raw = pinned(root, training_reference)
    training = json.loads(training_raw)
    members = training['admission']['members']
    require(members and len(set(members))==len(members), 'PAPER_TEMPLATE_MEMBER_DOMAIN')
    epoch = training['admission']['decision_date']
    identity_raw = pinned(root, identity_reference)
    identity = PinnedStrategyIdentity(root, identity_reference['path'], identity_reference['sha256'])
    calendar_raw = pinned(root, calendar_reference)
    calendar = json.loads(calendar_raw)
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ',
            'PAPER_TEMPLATE_CALENDAR')
    dates = [row['date'] for row in calendar['sessions']]
    require(dates==sorted(set(dates)) and epoch in dates, 'PAPER_TEMPLATE_CALENDAR_RANGE')
    files = {}
    def include(name, raw):
        # pinned validates each logical path before inclusion; generated paths
        # below consist only of a fixed prefix and a digest.
        require(name not in files or files[name]==raw, 'PAPER_TEMPLATE_SOURCE_COLLISION')
        files[name] = raw
    for ref, raw in ((training_reference,training_raw),(identity_reference,identity_raw),
                     (calendar_reference,calendar_raw)):
        include(ref['path'], raw)
    securities = {}
    for ticker in members:
        resolved = identity(ticker)
        sid = resolved['security_id']
        require(sid not in securities, 'PAPER_TEMPLATE_DUPLICATE_SECURITY')
        securities[sid] = dict(ticker=ticker)
        for name, digest in resolved['source_hashes'].items():
            include(name, pinned(root,dict(path=name,sha256=digest)))
    source_pins = []
    for name in sorted(SOURCES | NORMALIZATION_CODE_PATHS):
        raw = (Path(__file__).resolve().parents[1]/name).read_bytes()
        include(name, raw)
        source_pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
    templates = {}
    for sid in sorted(securities):
        key = sha256(sid.encode()).hexdigest()
        raw = canonical(dict(schema='PAPER_FIRST_DAILY_WINDOW_V2', security_id=sid,
            identity=identity_reference, calendar=calendar_reference, source_pins=source_pins,
            monthly_decision_date=epoch, output_root='paper-first-captures/'+key))
        name = 'paper-first-templates/'+key+'.json'
        include(name,raw)
        templates[sid] = dict(configuration=dict(path=name,sha256=sha256(raw).hexdigest()))
    require(len(files)<=20000 and sum(map(len,files.values()))<=256*1024*1024,
            'PAPER_TEMPLATE_SOURCE_BUDGET')
    result = dict(status='PAPER_FIRST_TEMPLATES_PREPARED_NOT_REGISTERED',
        training_reference=training_reference, identity_reference=identity_reference,
        calendar_reference=calendar_reference, daily_sources=templates, securities=securities,
        candidate_count=len(templates), source_sha256={p:sha256(b).hexdigest() for p,b in files.items()},
        epoch_semantics='TEMPLATE_ONLY_RUNTIME_USES_VERIFIED_SELECTION_DATE',
        account_mutated=False, scheduler_changed=False, daily_evidence_approved=False)
    directory.mkdir(parents=True,exist_ok=False)
    try:
        for name, raw in files.items():
            path = directory/name
            reject_links(path)
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)
            require(path.read_bytes()==raw,'PAPER_TEMPLATE_READBACK')
        # Re-resolve every copied identity from the isolated root.
        copied = PinnedStrategyIdentity(directory,identity_reference['path'],identity_reference['sha256'])
        for sid, security in securities.items():
            require(copied(security['ticker'])['security_id']==sid,'PAPER_TEMPLATE_COPIED_IDENTITY')
        with (directory/'preparation.json').open('xb') as stream:
            stream.write(canonical(result))
        return result
    except BaseException:
        with (directory/'failed.json').open('xb') as stream:
            stream.write(canonical(dict(status='FAILED_PRESERVED_NOT_REGISTERED')))
        raise


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--output',required=True)
    for name in ('training','identity','calendar'):
        parser.add_argument('--'+name,required=True)
        parser.add_argument('--'+name+'-sha256',required=True)
    args = parser.parse_args()
    refs = {name+'_reference':dict(path=getattr(args,name),sha256=getattr(args,name+'_sha256'))
            for name in ('training','identity','calendar')}
    result = prepare(root=args.root,output=args.output,**refs)
    print(json.dumps(dict(status=result['status'],candidate_count=result['candidate_count'],
                         source_files=len(result['source_sha256'])),ensure_ascii=False))
