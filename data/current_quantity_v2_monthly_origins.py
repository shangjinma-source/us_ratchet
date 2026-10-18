"""Read only accepted held-position origins; no discovery, fetch or writes.

The configured root is the monthly archive's blobs directory, not a repo root.
Known hashes come only from a replay-verified accepted proposal. Hash binding is
local integrity, not independent authentication of provider prices or identities.
"""
import base64
from hashlib import sha256
from pathlib import Path
import re
from data.current_quantity_v2_difference_plan import require
from data.current_quantity_v2_difference_service import document
from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources

MAX_SOURCE_BYTES=32*1024*1024
MAX_TOTAL_BYTES=128*1024*1024
MAX_FILES=2000


class MonthlyOriginReader:
    def __init__(self,*,monthly_blob_root=None):
        self.monthly_blob_root=Path(monthly_blob_root) if monthly_blob_root is not None else None

    def __call__(self,snapshot):
        require(type(snapshot)is dict and 'state' in snapshot,'MONTHLY_ORIGIN_STATE_REQUIRED')
        state=review_chain(snapshot['state']);ledger=state['ledger'];proposal=active_proposal(ledger)
        causal=proposal['causal_inputs'];cash=proposal.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION'
        frozen=causal.get('frozen_execution_package',{}) if cash else {}
        securities=proposal['securities'] if cash else causal['securities']
        rows={row['security_id']:row for row in proposal['rows']} if cash else causal['execution_references']
        accepted_pins=frozen['source_hashes'] if cash else causal['source_hashes']
        needed={sid:rows[sid] for sid,q in ledger['shares'].items() if q>0}
        files={};pins={};total=0
        for sid,row in needed.items():
            security=securities[sid];references=row['source_hashes']
            require(type(references)is dict and references,'MONTHLY_ORIGIN_REFERENCES_REQUIRED')
            for name,h in references.items():
                CurrentQuantityV2CurrentCashSources._path(name)
                require(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) is not None
                    and accepted_pins.get(name)==h,'MONTHLY_ORIGIN_PIN_MISMATCH')
                if name in files:
                    require(pins[name]==h,'MONTHLY_ORIGIN_PIN_MISMATCH');continue
                require(len(files)<MAX_FILES,'MONTHLY_ORIGIN_SIZE_LIMIT')
                encoded=frozen.get('files_base64',{}).get(name)
                if encoded is not None:
                    require(type(encoded)is str and len(encoded)<=4*((MAX_SOURCE_BYTES+2)//3),'MONTHLY_ORIGIN_SIZE_LIMIT')
                    raw=base64.b64decode(encoded,validate=True)
                else:
                    root=self.monthly_blob_root
                    require(root is not None and root.is_dir() and not root.is_symlink(),'MONTHLY_ORIGIN_ARCHIVE_REQUIRED')
                    root=root.resolve();path=root/h
                    require(not path.is_symlink() and path.resolve().is_relative_to(root),'MONTHLY_ORIGIN_PATH_ESCAPE')
                    require(path.is_file(),'MONTHLY_ORIGIN_BYTES_MISSING')
                    size=path.stat().st_size
                    require(size<=MAX_SOURCE_BYTES and total+size<=MAX_TOTAL_BYTES,'MONTHLY_ORIGIN_SIZE_LIMIT')
                    with path.open('rb') as stream:raw=stream.read(MAX_SOURCE_BYTES+1)
                total+=len(raw)
                require(len(raw)<=MAX_SOURCE_BYTES and total<=MAX_TOTAL_BYTES,'MONTHLY_ORIGIN_SIZE_LIMIT')
                require(sha256(raw).hexdigest()==h,'MONTHLY_ORIGIN_BYTES_CHANGED')
                files[name]=raw;pins[name]=h
            # Original receipts, not new training bars, bind the old raw identity.
            receipts=[]
            for name in references:
                parsed=document(files[name])
                if type(parsed)is dict and {'security_id','ticker','raw_path','raw_sha256','captured_at'}<=set(parsed):
                    receipts.append(parsed)
            require(len(receipts)==1,'MONTHLY_ORIGIN_RECEIPT_REQUIRED')
            receipt=receipts[0];rawpath=receipt['raw_path']
            require(receipt['security_id']==sid and receipt['ticker']==security['ticker']
                and rawpath in references and receipt['raw_sha256']==references[rawpath]
                and receipt['captured_at']==row['captured_at'],'MONTHLY_ORIGIN_IDENTITY_MISMATCH')
            raw=document(files[rawpath]);results=raw['chart']['result']
            require(type(results)is list and len(results)==1 and results[0]['meta']['symbol']==security['ticker'],
                'MONTHLY_ORIGIN_IDENTITY_MISMATCH')
        return dict(files=files,source_hashes=pins)
