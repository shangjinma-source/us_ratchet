"""Serialized local paper wake with durable diagnostics, never a broker adapter."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path,PurePosixPath
from uuid import uuid4

from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import reject_links
from data.strategy_paper_application_descriptor_v2 import require
from scripts.run_prospective_paper_v2 import run_scheduled

SOURCE='scripts/run_prospective_paper_diagnosed_v2.py'


@contextmanager
def exclusive_wake(path):
    """Kernel-owned lock: file presence is not ownership; process death releases it."""
    path=Path(path);reject_links(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as stream:
        require(path.stat().st_nlink==1,'PAPER_WAKE_LOCK_LINK')
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0);locked=False
        try:
            if os.name=='nt':
                import msvcrt
                try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);locked=True
                except OSError as error:
                    if error.errno not in (13,11):raise
            else:
                import fcntl
                try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
                except BlockingIOError:pass
            yield locked
        finally:
            if locked:
                stream.seek(0)
                if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def run(*,root,configuration_path,expected_sha256):
    root=Path(root).absolute();reject_links(root)
    def read(name,digest):
        require(type(name) is str and '\\' not in name and ':' not in name and
            not PurePosixPath(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')),
            'PAPER_WAKE_PATH')
        path=root/name;reject_links(path)
        require(path.is_file() and path.stat().st_nlink==1,
            'PAPER_WAKE_SOURCE_FILE')
        size=path.stat().st_size
        require(size<=32*1024*1024,'PAPER_WAKE_SOURCE_FILE')
        with path.open('rb') as stream:raw=stream.read(size+1)
        require(sha256(raw).hexdigest()==digest,'PAPER_WAKE_SOURCE_CHANGED')
        return raw
    config=json.loads(read(configuration_path,expected_sha256))
    descriptor=json.loads(read(config['descriptor']['path'],config['descriptor']['sha256']))
    require(descriptor['code_sha256'].get(SOURCE)==sha256(Path(__file__).read_bytes()).hexdigest(),
        'PAPER_WAKE_CODE_NOT_REGISTERED')
    # Account namespace is shared even if two configuration files name it.
    account_key=sha256(descriptor['account_id'].encode()).hexdigest()
    directory=root/'data/local_scheduler/prospective_paper_v2'/account_key
    reject_links(directory)
    with exclusive_wake(directory/'wake.lock') as owned:
        if not owned:return dict(status='WAIT_OTHER_PAPER_WAKE',account_writes=False)
        started=datetime.now(timezone.utc).isoformat()
        try:
            result=run_scheduled(root=root,configuration_path=configuration_path,expected_sha256=expected_sha256)
        except Exception as error:
            reason=str(error)
            result=dict(status='BLOCKED',reason=reason if isinstance(error,ValueError) and
                reason.replace('_','').isalnum() else 'PAPER_WAKE_RUNTIME_ERROR',error_type=type(error).__name__)
        receipt=dict(schema='PROSPECTIVE_PAPER_WAKE_DIAGNOSTIC_V2',started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),configuration_sha256=expected_sha256,result=result)
        with (directory/(uuid4().hex+'.json')).open('xb') as stream:
            stream.write(canonical(receipt));stream.flush();os.fsync(stream.fileno())
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--configuration-path',required=True)
    parser.add_argument('--expected-sha256',required=True)
    result=run(**vars(parser.parse_args()))
    print(json.dumps(result,ensure_ascii=False))
    return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
