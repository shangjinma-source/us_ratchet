"""Mount user-confirmed transfer facts beside, never inside, the account journal."""
from pathlib import Path
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from api.broker_internal_transfers import create_router
from core.broker_transfer_store import TransferStore


def attach_transfers(*, prepared, root, validate_sources, clock=None):
    validate_sources()
    root = Path(root).resolve()
    account = prepared['roa_service'].account_service
    account_path = Path(account.store.path).absolute()
    path = account_path.with_name(account_path.name + '.internal-transfers.sqlite3')
    if not path.resolve().is_relative_to(root / 'data/strategy_account'):
        raise ValueError('TRANSFER_STORE_PATH_INVALID')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('TRANSFER_STORE_PATH_INVALID')
    if any(getattr(route, 'path', '') == '/api/strategy-account/internal-transfers'
           for route in prepared['router'].routes):
        raise ValueError('TRANSFER_ROUTE_ALREADY_MOUNTED')

    class GuardedStore(TransferStore):
        def read(self):
            validate_sources()
            return super().read()

        def append(self, event, *, expected_revision):
            validate_sources()
            return super().append(event, expected_revision=expected_revision)

    store = GuardedStore(path, account.account_id, clock=clock)
    router = create_router(store=store)

    @router.get('/static/broker_internal_transfers.js')
    async def asset():
        await run_in_threadpool(validate_sources)
        return FileResponse(root / 'web/broker_internal_transfers.js',
                            media_type='application/javascript', headers={'Cache-Control': 'no-store'})

    prepared['router'].include_router(router)
    return dict(prepared, internal_transfer_store=store)
