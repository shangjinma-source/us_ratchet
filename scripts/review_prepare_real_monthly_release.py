"""Prepare and review a real-account monthly candidate; never activate it."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import os

from core.strategy_account_ledger import canonical, replay, require
from data.strategy_account_runtime import ScopedAccountStore
from data.strategy_account_monthly_review import StrategyAccountMonthlyReview
from scripts.prepare_real_monthly_release import prepare, _safe, _read


def run(*, root, registry_path, registry_sha256, archive_path, archive_sha256,
        new_entry, output_directory, clock=None, market_capture=None, action_capture=None):
    root=Path(root).absolute()
    output=_safe(root,output_directory)
    require(output.parent.is_dir() and not output.exists(),'REVIEW_PREPARE_OUTPUT_CONFLICT')
    clock=clock or (lambda:datetime.now(timezone.utc))
    now=clock();require(isinstance(now,datetime) and now.utcoffset() is not None,'AWARE_SERVER_CLOCK_REQUIRED')
    accounts=ScopedAccountStore(root/'data/strategy_account/real_strategy.sqlite3',clock=clock)
    state=accounts.read();require(state is not None,'ACCOUNT_NOT_INITIALIZED')
    require(replay(state['account_id'],[event['payload'] for event in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
    output.mkdir(exist_ok=False)
    def save(name,value):
        with (output/name).open('xb') as stream:
            stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    def unchanged():
        current=accounts.read()
        require(current is not None and current['revision']==state['revision'],'ACCOUNT_CHANGED_DURING_MONTHLY_PREPARATION')
    save('started.json',dict(account_id=state['account_id'],account_revision=state['revision'],started_at=now.isoformat()))
    try:
        candidate=(Path(output_directory)/'candidate').as_posix()
        prepared=prepare(root=root,registry_path=registry_path,registry_sha256=registry_sha256,
            archive_path=archive_path,archive_sha256=archive_sha256,new_entry=deepcopy(new_entry),
            output_directory=candidate,account_state=state,clock=clock)
        unchanged()
        configuration=_read(root,candidate+'/runtime.json',prepared['files']['runtime.json'])
        reviewed=StrategyAccountMonthlyReview(root=root,configuration=configuration,
            output_directory=(Path(output_directory)/'review').as_posix(),clock=clock,
            market_capture=market_capture,action_capture=action_capture).review(expected_revision=state['revision'])
        require(reviewed['account_revision']==state['revision'],'REVIEW_ACCOUNT_BINDING_MISMATCH')
        unchanged()
        def binding(path):
            with _safe(root,path).open('rb') as stream:
                raw=stream.read(32*1024*1024+1)
            require(len(raw)<=32*1024*1024,'REVIEW_PREPARE_RECEIPT_TOO_LARGE')
            return dict(path=path,sha256=sha256(raw).hexdigest())
        candidates={name:binding(candidate+'/'+name) for name in ('registry.json','archive.json','runtime.json')}
        require(all(value['sha256']==prepared['files'][name] for name,value in candidates.items()),'PREPARED_PACKAGE_CHANGED')
        review_binding=binding(reviewed['review_path'])
        require(review_binding['sha256']==reviewed['review_sha256'],'MONTHLY_REVIEW_CHANGED')
        receipt=dict(status='READY_FOR_ACTIVATION_NOT_ACTIVATED',target_month=configuration['target_month'],
            account_id=state['account_id'],account_revision=state['revision'],
            finished_at=clock().isoformat(),files={**{name.removesuffix('.json'):value for name,value in candidates.items()},
                'unit_review':review_binding,'complete':binding(reviewed['complete_path'])},
            reviewed_at=reviewed['reviewed_at'],account_writes=False,service_activated=False,
            search_calls=0,orders_created=False,limitations=reviewed['limitations']+[
                'Candidate only; activation must recheck account revision and all source pins.',
                'Failed attempts require a new explicitly reviewed output directory; no automatic retry.'])
        unchanged();save('ready.json',receipt);return receipt
    except Exception as error:
        import re
        reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'MONTHLY_PREPARATION_FAILED'
        save('failed.json',dict(status='BLOCKED',reason=reason,account_revision=state['revision'],
            account_writes=False,service_activated=False,automatic_retry=False))
        raise


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','registry-path','registry-sha256','archive-path','archive-sha256',
                 'new-entry-path','new-entry-sha256','output-directory'):
        parser.add_argument('--'+name,required=True)
    args=vars(parser.parse_args(argv))
    root=Path(args['root']).absolute()
    try:
        args['new_entry']=_read(root,args.pop('new_entry_path'),args.pop('new_entry_sha256'))
        result=run(**args)
    except Exception:
        print(json.dumps(dict(status='BLOCKED',reason='MONTHLY_PREPARATION_REJECTED',
            account_writes=False,service_activated=False,automatic_retry=False)))
        return 2
    print(json.dumps(result,ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
