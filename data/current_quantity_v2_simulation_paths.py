"""Read-only validation of isolated cap storage and the existing entry policy."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import sqlite3

from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources


def validate_cap_configuration(*, simulation_database, cap_database, policy):
    simulation=Path(simulation_database).resolve();caps=Path(cap_database).resolve()
    require(simulation!=caps and not (simulation.exists() and caps.exists() and simulation.samefile(caps)),
            'SIMULATION_AND_CAP_DATABASE_MUST_DIFFER')
    require(not Path(cap_database).is_symlink() and not any(p.is_symlink() for p in Path(cap_database).parents),
            'INVALID_CAP_DATABASE_PATH')
    # This existing constructor validates all policy keys/ranges without opening
    # storage or fetching data. The dummy capability is never invoked.
    CurrentQuantityV2CurrentCashSources(root=caps.parent,snapshot_service=None,server_account_id='policy-validation',
        pullback_policy=policy,pullback_cap_store=SimpleNamespace(candidate=lambda **_:None))
    if caps.exists():
        require(caps.is_file(),'INVALID_CAP_DATABASE_PATH')
        with closing(sqlite3.connect(caps.as_uri()+'?mode=ro',uri=True)) as connection:
            names={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view','trigger') AND name NOT LIKE 'sqlite_%'")}
            require(names=={'pullback_caps'},'WRONG_CAP_DATABASE_SCHEMA')
            columns=[row[1] for row in connection.execute('PRAGMA table_info(pullback_caps)')]
            require(columns==['binding','ordinal','raw','parameters','result','previous_hash','record_hash'], 'WRONG_CAP_DATABASE_SCHEMA')
    return dict(database_path=str(caps),policy=policy)
