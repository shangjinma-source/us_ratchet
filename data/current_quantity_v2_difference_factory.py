"""File-backed, explicit strategy-account difference service; no default instance.

The caller supplies a server-owned descriptor hash. Immutable evidence is hashed
on every read. Mutable account files require explicit state, never broker defaults.
This validates local integrity, not authenticity of external review assertions.
"""
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

from data.current_quantity_v2_difference_service import (
    CurrentQuantityV2DifferenceService, document, require)


SCHEMA = 'V2_DIFFERENCE_FILE_DESCRIPTOR_V1'
ACCOUNT_SCHEMA = 'EXPLICIT_STRATEGY_ACCOUNT_STATE_V1'


def create_service(*, root, descriptor_path, descriptor_sha256,
                   clock=lambda: datetime.now(timezone.utc)):
    root = Path(root).resolve()

    def safe_path(name):
        require(type(name) is str and bool(name) and '\\' not in name and ':' not in name
                and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
                'INVALID_SERVER_SOURCE_PATH')
        path = (root / name).resolve()
        require(path.is_relative_to(root), 'SOURCE_OUTSIDE_ROOT')
        return path

    def read(name, maximum):
        path = safe_path(name)
        require(path.stat().st_size <= maximum, 'SOURCE_TOO_LARGE')
        with path.open('rb') as stream:
            raw = stream.read(maximum + 1)
        require(len(raw) <= maximum, 'SOURCE_TOO_LARGE')
        return raw

    require(type(descriptor_sha256) is str and re.fullmatch('[a-f0-9]{64}',descriptor_sha256),
            'INVALID_DESCRIPTOR_HASH')

    def descriptor():
        raw = read(descriptor_path, 1024*1024)
        require(sha256(raw).hexdigest()==descriptor_sha256, 'DESCRIPTOR_CHANGED')
        result = document(raw)
        require(type(result) is dict and set(result)=={'schema','decisions','accounts'}
                and result['schema']==SCHEMA and type(result['decisions']) is dict
                and type(result['accounts']) is dict, 'INVALID_DESCRIPTOR_SCHEMA')
        for account_id,path in result['accounts'].items():
            require(type(account_id) is str and bool(account_id.strip()), 'INVALID_ACCOUNT_ID')
            safe_path(path)
        for identifier,entry in result['decisions'].items():
            require(re.fullmatch('[a-f0-9]{64}',identifier) and type(entry) is dict
                    and set(entry)=={'account_id','documents','source_hashes'}
                    and entry['account_id'] in result['accounts'], 'INVALID_DECISION_REGISTRATION')
            pins=entry['source_hashes'];paths=entry['documents']
            required_documents={'capital_decision','target_mandate','identities','unit_continuity','quote_receipts'}
            require(type(pins) is dict and 0<len(pins)<=2000 and type(paths) is dict
                    and set(paths) in (required_documents,required_documents|{'genesis_declaration'})
                    and type(paths['quote_receipts']) is dict, 'INVALID_SOURCE_REGISTRATION')
            for name,digest in pins.items():
                safe_path(name)
                require(type(digest) is str and re.fullmatch('[a-f0-9]{64}',digest), 'INVALID_SOURCE_HASH')
            names=[paths[k] for k in paths if k!='quote_receipts']+list(paths['quote_receipts'].values())
            require(all(type(name) is str and name in pins for name in names), 'DOCUMENT_NOT_PINNED')
        return result

    def resolve(identifier):
        registration=descriptor()['decisions']
        require(identifier in registration, 'DECISION_NOT_REGISTERED')
        entry=registration[identifier];files={};total=0
        for name,digest in entry['source_hashes'].items():
            raw=read(name,min(32*1024*1024,128*1024*1024-total))
            total+=len(raw)
            require(sha256(raw).hexdigest()==digest, 'SOURCE_HASH_MISMATCH')
            files[name]=raw
        mandate=document(files[entry['documents']['target_mandate']])
        require(mandate['account_id']==entry['account_id'], 'REGISTERED_ACCOUNT_MISMATCH')
        return dict(files=files,source_hashes=entry['source_hashes'],documents=entry['documents'])

    def account_reader(account_id):
        accounts=descriptor()['accounts']
        require(account_id in accounts,'ACCOUNT_NOT_REGISTERED')
        saved=document(read(accounts[account_id],1024*1024))
        require(type(saved) is dict and set(saved)=={'schema','state'}
                and saved['schema']==ACCOUNT_SCHEMA, 'EXPLICIT_ACCOUNT_SCHEMA_REQUIRED')
        state=saved['state']
        require(type(state) is dict and set(state)=={'account_id','revision','cash','shares','observed_at',
            'open_orders','reserved_cash','reserved_shares','pending_rights'}, 'COMPLETE_ACCOUNT_STATE_REQUIRED')
        require(state['account_id']==account_id and type(state['revision']) is str and bool(state['revision']),
                'ACCOUNT_BINDING_INVALID')
        for key in ('cash','reserved_cash'):
            require(type(state[key]) in (str,int) and Fraction(state[key])>=0,'INVALID_ACCOUNT_CASH')
        for key in ('shares','reserved_shares'):
            require(type(state[key]) is dict and all(type(sid) is str and type(q) is int and q>=0
                    for sid,q in state[key].items()), 'INVALID_ACCOUNT_SHARES')
        require(type(state['open_orders']) is list and type(state['pending_rights']) is list,
                'EXPLICIT_ORDER_RIGHTS_STATE_REQUIRED')
        require(type(state['observed_at']) is str and datetime.fromisoformat(state['observed_at']).tzinfo is not None,
                'AWARE_ACCOUNT_TIME_REQUIRED')
        return state

    descriptor()  # Configuration validation only, never writes or calculates.
    return CurrentQuantityV2DifferenceService(resolver=resolve, account_reader=account_reader, clock=clock)
