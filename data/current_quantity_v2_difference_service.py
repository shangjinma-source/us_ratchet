"""Read-only source bridge for explicitly identified strategy accounts.

No default resolver, broker import, network, search or account writes. Resolver
pins are server-owned trust anchors, not independently authenticated evidence.
Corporate-action/identity review remains an explicit pinned human/server record.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from collections import OrderedDict
from threading import RLock

from data.current_quantity_v2_difference_plan import build_account_difference_plan
from data.current_research_intraday_execution import decode_intraday_reference


def require(ok, reason):
    if not ok: raise ValueError(reason)


def document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_SOURCE_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def decode_execution_package(package, *, needed, now, sell_only=frozenset()):
    """Shared raw-byte validation for initial and continuation server sources."""
    require(set(sell_only)<=needed,'INVALID_SELL_ONLY_DOMAIN')
    files,pins,paths=package['files'],package['source_hashes'],package['documents']
    identities=document(files[paths['identities']]);units=document(files[paths['unit_continuity']])
    require(identities['source_references'] and all(p in pins for p in identities['source_references']),'IDENTITY_EVIDENCE_REQUIRED')
    securities=identities['securities']
    require(set(paths['quote_receipts'])==needed,'COMPLETE_QUOTE_DOMAIN_REQUIRED')
    references = {}
    pullback_policy=None
    if 'pullback_policy' in paths or 'pullback_proofs' in paths:
        require('pullback_policy' in paths and 'pullback_proofs' in paths,'COMPLETE_PULLBACK_POLICY_REQUIRED')
        pullback_policy=document(files[paths['pullback_policy']])
        require(set(pullback_policy)=={'schema','status','rebound_fraction','minimum_discount','maximum_age_seconds'}
                and pullback_policy['schema']=='V2_PULLBACK_EXECUTION_POLICY_V1'
                and pullback_policy['status']=='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED'
                and needed-set(sell_only)<=set(paths['pullback_proofs'])<=needed,'INVALID_PULLBACK_POLICY')
    require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
    for sid,path in paths['quote_receipts'].items():
        receipt=document(files[path]); ticker=securities[sid]['ticker']
        require(receipt['security_id']==sid and receipt['ticker']==ticker,'RECEIPT_IDENTITY_MISMATCH')
        rawpath=receipt['raw_path'];raw=files[rawpath]
        require(receipt['raw_sha256']==pins[rawpath], 'RAW_RECEIPT_MISMATCH')
        captured=datetime.fromisoformat(receipt['captured_at'])
        parsed=document(raw)['chart']['result'][0]
        require(parsed['meta'].get('instrumentType')=='EQUITY','EQUITY_QUOTE_REQUIRED')
        require(not any(events for kind,events in parsed.get('events',{}).items() if kind!='dividends'),
                'UNPROCESSED_QUOTE_UNIT_EVENT')
        decoded=decode_intraday_reference(raw,ticker=ticker,now=now,captured_at=captured)
        references[sid]=dict(decoded,security_id=sid,ticker=ticker,currency='USD',
            price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
            captured_at=captured.isoformat(),checked_at=now.isoformat(),valid_until=decoded['refresh_by'],
            source_hashes={path:pins[path],rawpath:pins[rawpath]})
        if pullback_policy is not None and sid in paths['pullback_proofs']:
            from data.current_quantity_v2_pullback_proof import replay_frozen_pullback
            proof_path=paths['pullback_proofs'][sid]
            proof=document(files[proof_path])
            require(sha256(files[proof_path]).hexdigest()==pins[proof_path]
                    and sha256(files[paths['pullback_policy']]).hexdigest()==pins[paths['pullback_policy']],
                    'PULLBACK_PROOF_SOURCE_CHANGED')
            replay=replay_frozen_pullback(raw,proof,now.isoformat());parameters=proof['parameters']
            require(parameters['security_id']==sid and parameters['ticker']==ticker
                    and parameters['session']==decoded['session']
                    and datetime.fromisoformat(parameters['captured_at'])==captured
                    and parameters['expected_sha256']==pins[rawpath]
                    and all(parameters[key]==pullback_policy[key] for key in
                            ('rebound_fraction','minimum_discount','maximum_age_seconds')),
                    'PULLBACK_REFERENCE_POLICY_MISMATCH')
            references[sid]['pullback']=dict(deepcopy(replay['candidate']),
                prior_cap=deepcopy(proof['prior_cap']),execution_policy=deepcopy(pullback_policy),
                cap_record_hash=proof['record_hash'])
            references[sid]['valid_until']=min(datetime.fromisoformat(decoded['refresh_by']),
                datetime.fromisoformat(replay['candidate']['reference_valid_until'])).isoformat()
    return dict(securities=securities,execution_references=references,unit_continuity=units,source_hashes=pins)


class CurrentQuantityV2DifferenceService:
    """resolver(decision_id)->{files:bytes map,source_hashes,documents}.

    documents names capital_decision, target_mandate, identities, unit_continuity,
    plus quote_receipts {sid:path}. Receipt binds raw_path/raw_sha256,
    security_id/ticker/captured_at. All documents and referenced evidence are in
    files. account_reader(account_id) must return explicit strategy state,
    including open orders/reservations/rights; absent broker fields are NOT zero.
    Both readers are called again before publishing. They must be read-only.
    """
    def __init__(self, *, resolver, account_reader, clock):
        self.resolver = resolver
        self.account_reader = account_reader
        self.clock = clock
        self._proposal_lock = RLock()
        self._proposals = OrderedDict()

    @staticmethod
    def _package_identity(package):
        files,pins=package['files'],package['source_hashes']
        require(type(files)is dict and 0<len(files)<=2000 and set(files)==set(pins),'SOURCE_CLOSURE_REQUIRED')
        require(all(type(raw)is bytes and len(raw)<=32*1024*1024 for raw in files.values())
                and sum(map(len,files.values()))<=128*1024*1024,'SOURCE_BYTES_LIMIT')
        hashes={name:sha256(raw).hexdigest() for name,raw in files.items()}
        require(hashes==pins,'SOURCE_HASH_MISMATCH')
        return dict(documents=deepcopy(package['documents']),source_hashes=deepcopy(pins),raw_hashes=hashes)

    def _build(self, decision_id):
        """Server-private pure proposal; raises on invalid evidence, never searches."""
        require(type(decision_id) is str and re.fullmatch('[a-f0-9]{64}',decision_id), 'INVALID_DECISION_ID')
        package = deepcopy(self.resolver(decision_id))
        package_identity=self._package_identity(package)
        files, pins, paths = package['files'], package['source_hashes'], package['documents']
        decision = document(files[paths['capital_decision']])
        require(decision['decision_id']==decision_id, 'DECISION_BINDING_MISMATCH')
        mandate = document(files[paths['target_mandate']])
        identities = document(files[paths['identities']])
        units = document(files[paths['unit_continuity']])
        require(identities['source_references'] and all(p in pins for p in identities['source_references']), 'IDENTITY_EVIDENCE_REQUIRED')
        securities = identities['securities']
        account = deepcopy(self.account_reader(mandate['account_id']))
        require(account['account_id']==mandate['account_id'], 'ACCOUNT_ID_MISMATCH')
        needed={sid for m in (account['shares'],decision['target_quantities']) for sid,q in m.items() if q}
        require(set(paths['quote_receipts'])==needed, 'COMPLETE_QUOTE_DOMAIN_REQUIRED')
        execution=decode_execution_package(package,needed=needed,now=self.clock())
        references=execution['execution_references']
        # Source documents, not client prices, determine the entire plan.
        args=dict(capital_decision=decision,account_state=account,securities=securities,
            execution_references=references,unit_continuity=units,source_hashes=pins,
            target_scope='ACCOUNT_EQUITY_TARGET',target_mandate=mandate)
        if 'genesis_declaration' in paths:
            args.update(target_scope='NEW_CASH_STRATEGY_INITIAL_TARGET',
                        genesis_declaration=document(files[paths['genesis_declaration']]))
        require(self.account_reader(mandate['account_id'])==account, 'ACCOUNT_CHANGED_DURING_PREVIEW')
        require(self.resolver(decision_id)==package, 'DECISION_SOURCES_CHANGED_DURING_PREVIEW')
        # Final time check also covers slow source/account rereads.
        result=build_account_difference_plan(**args,now=self.clock().isoformat())
        if result['status']!='READY': raise ValueError(result['reason'])
        return result,package_identity

    def _proposal(self,decision_id):
        """Uncached internal construction; public preview records adoption identity."""
        return self._build(decision_id)[0]

    def initial_resolver(self,account_id,proposal_id,now):
        """Store callback: revalidate sources but return the original immutable proposal."""
        with self._proposal_lock:
            require(proposal_id in self._proposals,'PROPOSAL_UNKNOWN_OR_EVICTED')
            cached=deepcopy(self._proposals[proposal_id]);proposal=cached['proposal']
            require(proposal['account_id']==account_id,'PROPOSAL_ACCOUNT_MISMATCH')
            decision_id=proposal['causal_inputs']['capital_decision']['decision_id']
            require(self._package_identity(self.resolver(decision_id))==cached['package_identity'],'PROPOSAL_SOURCE_CHANGED')
            account=deepcopy(self.account_reader(account_id))
            require(account==proposal['causal_inputs']['account_state'],'ACCOUNT_CHANGED')
            require(self._package_identity(self.resolver(decision_id))==cached['package_identity'],'PROPOSAL_SOURCE_CHANGED')
            require(self.account_reader(account_id)==account,'ACCOUNT_CHANGED')
            require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
            require(datetime.fromisoformat(proposal['causal_inputs']['now'])<=now,'ACCEPTANCE_BEFORE_PROPOSAL')
            current=build_account_difference_plan(**dict(proposal['causal_inputs'],now=now.isoformat()))
            require(current['status']=='READY' and current['orders']==proposal['orders'],'REFERENCE_NOT_ACCEPTABLE')
            return dict(proposal=proposal,account_state=account)

    def preview(self, decision_id):
        base = dict(decision_id=decision_id, research_only=True, execution_blocked=True,
                    orders_created=False, account_mutated=False,
                    source_authenticated=False, corporate_actions_complete=False)
        try:
            with self._proposal_lock:
                pure,package_identity=self._build(decision_id)
                identifier=pure['proposal_id']
                self._proposals[identifier]=dict(proposal=deepcopy(pure),package_identity=package_identity)
                self._proposals.move_to_end(identifier)
                while len(self._proposals)>32:self._proposals.popitem(last=False)
                result=deepcopy(pure)
            pins=result['causal_inputs']['source_hashes']
            target_scope=result['causal_inputs']['target_scope']
            research_id=result['causal_inputs']['capital_decision']['research_id']
            result.pop('causal_inputs')  # Full raw/source package is never returned over HTTP.
            result.update(base, source_bytes_verified=True, target_scope=target_scope, research_id=research_id,
                evidence_hashes=deepcopy(pins),
                source_scope='SERVER_PINNED_DECLARATIONS_AND_REPLAYED_INTRADAY_RAW',
                integration_status='READ_ONLY_SOURCE_BRIDGE_NOT_PRODUCTION_ADMISSION')
            result['limitations'].append('Explicit strategy account only; old broker holdings are never automatically imported. Initial CASH_ONLY research remains independent.')
            return result
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OSError,ArithmeticError) as error:
            return dict(base,status='UNAVAILABLE',reason=str(error),orders=[],proposal_id=None,
                        source_bytes_verified=False)
