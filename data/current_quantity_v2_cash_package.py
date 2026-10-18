"""Pure assembly of a declared new cash strategy pool; no IO/search/registration.

Pins verify supplied bytes. Identity and unit-review assertions remain caller
responsibility; no missing corporate-action review is manufactured here.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import PurePosixPath
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_quantity_v2_difference_service import document, require
from data.current_quantity_v2_difference_plan import stamp


def assemble_cash_package(*,account_id,capital_decision,original_source_files,
                          genesis_at,active_date,execution_package):
    require(type(account_id)is str and 0<len(account_id.strip())<=200,'FIXED_ACCOUNT_ID_REQUIRED')
    require(type(genesis_at)is str,'GENESIS_ISO_TIME_REQUIRED');genesis=stamp(genesis_at)
    require(type(active_date)is str and date.fromisoformat(active_date).isoformat()==active_date,'CANONICAL_ACTIVE_DATE_REQUIRED')
    decision=deepcopy(capital_decision);b=decision['binding']
    view=project_capital_decision_v2(decision)
    require(view['status'] in ('AVAILABLE','ALL_CASH'),'COMPLETE_DECISION_REQUIRED')
    cash=Fraction(b['available_cash'])
    require(b['shares']=={} and b['valuation_quotes'] is not None and cash>0
            and cash==Fraction(b['investable_equity'])==Fraction(b['search_arguments']['entered_cash']), 'CASH_ONLY_DECISION_REQUIRED')
    require(b['decision_date']<=active_date,'ACTIVE_BEFORE_DECISION')
    original_pins=b['source_hashes'];files={};pins={}

    def merge(source_files,source_pins):
        require(type(source_files)is dict and type(source_pins)is dict and set(source_files)==set(source_pins), 'SOURCE_CLOSURE_REQUIRED')
        for name,raw in source_files.items():
            require(type(name)is str and name and '\\' not in name and ':' not in name
                    and name not in ('.','..') and PurePosixPath(name).as_posix()==name
                    and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,'UNSAFE_SOURCE_NAME')
            require(type(raw)is bytes and len(raw)<=32*1024*1024,'SOURCE_BYTES_REQUIRED')
            digest=sha256(raw).hexdigest();require(source_pins[name]==digest,'SOURCE_HASH_MISMATCH')
            require(name not in files or (files[name]==raw and pins[name]==digest),'SOURCE_NAME_CONFLICT')
            files[name]=raw;pins[name]=digest
        require(len(files)<=2000 and sum(map(len,files.values()))<=128*1024*1024,'SOURCE_CLOSURE_TOO_LARGE')

    merge(original_source_files,original_pins)
    execution=deepcopy(execution_package)
    require(set(execution)=={'files','source_hashes','securities','unit_continuity','quote_receipts','identity_source_references'},'EXECUTION_PACKAGE_SCHEMA')
    merge(execution['files'],execution['source_hashes'])
    needed={sid for sid,q in decision['target_quantities'].items() if q>0}
    require(set(execution['securities'])==set(execution['unit_continuity'])==set(execution['quote_receipts'])==needed,'SELECTED_POSITIVE_DOMAIN_REQUIRED')
    identity_refs=execution['identity_source_references']
    require(type(identity_refs)is list and identity_refs and all(p in pins for p in identity_refs),'IDENTITY_SOURCE_REQUIRED')
    for sid in needed:
        security=execution['securities'][sid];unit=execution['unit_continuity'][sid]
        require(security==b['search_arguments']['metadata'][sid],'SECURITY_BINDING_MISMATCH')
        path=execution['quote_receipts'][sid];require(path in pins,'RECEIPT_NOT_PINNED')
        receipt=document(files[path]);rawpath=receipt['raw_path']
        require(receipt['security_id']==sid and receipt['ticker']==security['ticker'] and rawpath in pins
                and receipt['raw_sha256']==pins[rawpath],'QUOTE_RECEIPT_BINDING_MISMATCH')
        captured=stamp(receipt['captured_at'])
        require(genesis<=captured,'GENESIS_AFTER_CAPTURE')
        require(unit['security_id']==sid and unit['ticker']==security['ticker']
                and unit['capital_decision_id']==decision['decision_id']
                and unit['status']=='NO_UNPROCESSED_ACTIONS'
                and unit['price_basis']=='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS'
                and unit['reference_source_hashes']=={path:pins[path],rawpath:pins[rawpath]}
                and type(unit['source_references'])is list and unit['source_references'] and all(p in pins for p in unit['source_references'])
                and type(unit['covered_from_date'])is str and date.fromisoformat(unit['covered_from_date']).isoformat()==unit['covered_from_date']
                and unit['covered_from_date']<=b['decision_date']
                and captured<=stamp(unit['covered_through'])<=stamp(unit['reviewed_at']), 'EXPLICIT_UNIT_REVIEW_REQUIRED')
        if sid in b['valuation_quotes']:
            refs=b['valuation_quotes'][sid]['source_references']
            require(refs and all(p in pins for p in refs) and unit.get('valuation_source_references')==refs,'VALUATION_UNIT_BRIDGE_REQUIRED')

    prefix='generated/v2_cash/'+sha256((account_id+'\0'+decision['decision_id']).encode()).hexdigest()+'/'
    def add(name,value):
        name=prefix+name+'.json';require(name not in files,'GENERATED_DOCUMENT_NAME_CONFLICT')
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        require(len(raw)<=32*1024*1024,'GENERATED_DOCUMENT_TOO_LARGE')
        files[name]=raw;pins[name]=sha256(raw).hexdigest();return name
    provenance=add('provenance',dict(kind='SERVER_EXPLICIT_PAPER_GENESIS_NOT_EXTERNAL_ACCOUNT_PROOF',
        account_id=account_id,decision_id=decision['decision_id'],research_id=decision['research_id'],
        initial_cash_exact=str(cash),declared_at=genesis_at,active_date=active_date,
        original_source_hashes=deepcopy(original_pins),execution_source_hashes=deepcopy(execution['source_hashes'])))
    account=dict(account_id=account_id,revision=b['state_revision'],cash=str(cash),shares={},observed_at=genesis_at,
        open_orders=[],reserved_cash='0',reserved_shares={},pending_rights=[])
    mandate=dict(account_id=account_id,capital_decision_id=decision['decision_id'],target_month=active_date[:7],
        active_date=active_date,source_references=[provenance])
    declaration=dict(purpose='PAPER_INITIALIZATION_NOT_BROKER_BALANCE',account_id=account_id,
        research_id=decision['research_id'],decision_id=decision['decision_id'],capital_origin_revision=b['state_revision'],
        initial_cash_exact=str(cash),target_month=active_date[:7],declared_at=genesis_at,source_references=[provenance])
    paths=dict(capital_decision=add('capital_decision',decision),target_mandate=add('target_mandate',mandate),
        genesis_declaration=add('genesis_declaration',declaration),
        identities=add('identities',dict(securities=execution['securities'],source_references=identity_refs)),
        unit_continuity=add('unit_continuity',execution['unit_continuity']),quote_receipts=execution['quote_receipts'])
    require(len(files)<=2000 and sum(map(len,files.values()))<=128*1024*1024,'SOURCE_CLOSURE_TOO_LARGE')
    return dict(decision_id=decision['decision_id'],package=dict(files=files,source_hashes=pins,documents=paths),
        account_document=dict(schema='EXPLICIT_STRATEGY_ACCOUNT_STATE_V1',state=account),
        research_only=True,real_account=False,registered=False,source_authenticated=False,
        limits=['No global capital-pool uniqueness: server must map this same intended pool to one stable account_id.',
                'Explicit identity/unit reviews are supplied, not independently authenticated; raw freshness is checked by difference service.'])
