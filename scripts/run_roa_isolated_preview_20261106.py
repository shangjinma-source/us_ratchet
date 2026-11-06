"""Local preview with SQLite backup and independent lifecycle. Never uses source DB for writes."""
import argparse,json,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.strategy_account import StrategyAccountService,create_router as account_router
from api.roa_strategy import create_router
from data.roa_current_signal import load_current_signal,CONTRACT_PATHS
from data.roa_daily_signal import RoaDailySignalProvider
from data.roa_session_reader import RoaSessionReader
from data.roa_execution_lifecycle import RoaExecutionLifecycle,digest
from data.roa_strategy_service import RoaStrategyService
from core.strategy_account_store import StrategyAccountStore
ROOT=Path(__file__).resolve().parents[1]

def build(*,source_database,directory):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'tmp'):raise ValueError('PREVIEW_TMP_REQUIRED')
    directory.mkdir(parents=True,exist_ok=False);destination=directory/'account.sqlite3'
    with sqlite3.connect(Path(source_database).resolve().as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(destination) as target:source.backup(target)
    current=StrategyAccountStore(destination).read();account_id=current['account_id']
    contracts={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CONTRACT_PATHS}
    frozen=load_current_signal(as_of_date='2026-11-06',expected_contract_hashes=contracts)
    names={r['ticker']:r for r in frozen['securities']}
    for event in current['events']:
        identity=event['payload'].get('identity_evidence')
        if identity:names[identity['ticker']]=identity
    clock=lambda:datetime.now(timezone.utc)
    service_account=StrategyAccountService(database_path=destination,account_id=account_id,resolver=lambda ticker:names[ticker],clock=clock)
    epoch=frozen['strategy_epoch'];contract=digest(contracts)
    life=RoaExecutionLifecycle(path=directory/'lifecycle.json',account_id=account_id,strategy_epoch=epoch,contract_sha256=contract)
    daily=RoaDailySignalProvider(root=ROOT,path=directory/'daily_signal.json',expected_contract_hashes=contracts,clock=clock)
    def disabled_quotes(*args):raise ValueError('EXECUTION_ADMISSION_REQUIRED')
    service=RoaStrategyService(account_service=service_account,lifecycle=life,signal_provider=daily,
        session_provider=RoaSessionReader(ROOT),quote_provider=disabled_quotes,clock=clock,execution_admission=None)
    app=FastAPI();app.include_router(account_router(database_path=destination,account_id=account_id,resolver=lambda ticker:names[ticker],clock=clock));app.include_router(create_router(coordinator=service))
    app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
    app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='web')
    (directory/'preview.json').write_text(json.dumps(dict(isolated=True,account_id=account_id,strategy_epoch=epoch,source_database=str(Path(source_database).resolve()),cloned_database=str(destination),execution_admission=None)),encoding='utf8')
    return app
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-database',required=True);parser.add_argument('--directory',required=True);parser.add_argument('--port',type=int,default=8011);a=parser.parse_args()
    import uvicorn
    uvicorn.run(build(source_database=a.source_database,directory=a.directory),host='127.0.0.1',port=a.port)
