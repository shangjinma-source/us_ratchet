"""Local dynamic-domain source entry point. Real clock; dry run by default."""
import argparse
from hashlib import sha256
import json
import sqlite3
from pathlib import Path

from core.strategy_account_ledger import require
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_daily_dynamic_factory_v1 import FACTORY_SOURCES,run_dynamic_sources
from data.strategy_daily_rolling_parent_v3 import bounded_read,pinned
from data.strategy_daily_session_capture import reject_links

CLI_SOURCES=FACTORY_SOURCES|{
    'scripts/run_daily_dynamic_source_v1.py',
    'core/strategy_account_store.py','core/strategy_monthly_target_store.py',
}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--config-path',required=True)
    parser.add_argument('--config-sha256',required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    try:
        reject_links(args.root);root=Path(args.root).resolve()
        config_path=Path(args.config_path)
        if not config_path.is_absolute():config_path=root/config_path
        reject_links(config_path)
        require(config_path.resolve().is_relative_to(root),'DYNAMIC_CLI_CONFIGURATION_OUTSIDE_ROOT')
        raw=bounded_read(config_path)
        require(sha256(raw).hexdigest()==args.config_sha256,'DYNAMIC_CLI_CONFIGURATION_HASH')
        config=json.loads(raw)
        require(config['schema']=='SERVER_DYNAMIC_DAILY_SOURCE_V1'
                and CLI_SOURCES<={ref['path'] for ref in config['source_pins']},'DYNAMIC_CLI_SOURCE_SCOPE')
        for ref in config['source_pins']:
            body=pinned(root,ref,maximum=32*1024*1024)
            if ref['path'] in CLI_SOURCES:
                require(body==(Path(__file__).resolve().parents[1]/ref['path']).read_bytes(),
                        'DYNAMIC_CLI_EXECUTING_SOURCE_CHANGED')
        def database_path(key):
            relative=Path(config[key])
            require(not relative.is_absolute() and '..' not in relative.parts,'DYNAMIC_CLI_DATABASE_PATH')
            path=root/relative;reject_links(path)
            require(path.resolve().is_relative_to(root) and path.is_file(),'DYNAMIC_CLI_DATABASE_REQUIRED')
            return path
        accounts=StrategyAccountStore(database_path('account_database'))
        targets=StrategyMonthlyTargetStore(database_path('target_database'))
        def read_account():
            state=accounts.read()
            require(state is not None and state['account_id']==config['account_id'],'DYNAMIC_CLI_ACCOUNT_BINDING')
            return state
        def read_target():
            target=targets.current()
            require(target is None or target['payload']['account_id']==config['account_id'],
                    'DYNAMIC_CLI_TARGET_BINDING')
            return target
        # Validate the real stores even when the calendar means waiting. These
        # methods use SQLite mode=ro; no initialize/append method is called.
        read_account();read_target()
        result=run_dynamic_sources(root=root,configuration_bytes=raw,configuration_sha256=args.config_sha256,
            account_reader=read_account,target_reader=read_target,execute=args.execute)
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as error:
        result=dict(status='NEEDS_RECOVERY',reason=str(error),http_calls=None)
        print(json.dumps(result,ensure_ascii=False))
        return 2
    print(json.dumps(result,ensure_ascii=False))
    return 2 if result.get('status')=='NEEDS_RECOVERY' else 0


if __name__=='__main__':raise SystemExit(main())
