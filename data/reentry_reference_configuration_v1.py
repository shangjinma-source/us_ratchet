"""Bounded same-unit reference config construction from authenticated local archives.

No capture, identity-disjoint inference, action approval, or account mutation.
The server supplies the archive references and real DecisionBoundaryArchive.
"""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from core.strategy_account_ledger import canonical, require
from data.strategy_daily_rolling_parent_v3 import pinned
from data.reentry_reference_evidence_v1 import review_reference_interval
from core.reentry_buy_scope_v1 import valid_hash


def hashed(raw):
    return sha256(raw).hexdigest()


def build_reference_sources(*, root, output_directory, reference_state, reader_archive,
                            source_configuration_reference, exit_boundary_archive,
                            exit_boundary_references, decision_session, as_of):
    root = Path(root).resolve()
    output = Path(output_directory).resolve()
    require(output.is_relative_to(root) and output != root, 'REFERENCE_CONFIG_OUTPUT_SCOPE')
    require(not output.is_symlink() and all(not p.is_symlink() for p in output.parents),
            'REFERENCE_CONFIG_OUTPUT_SYMLINK')
    source_raw = pinned(root, source_configuration_reference, maximum=8*1024*1024)
    source = json.loads(source_raw)
    # The real reader archive is content addressed; validate the entire closure.
    receipt_path = Path(reader_archive['receipt_path'])
    require(receipt_path.resolve().is_relative_to(root), 'REFERENCE_ARCHIVE_SCOPE')
    raw = receipt_path.read_bytes()
    require(hashed(raw) == reader_archive['receipt_sha256'], 'REFERENCE_ARCHIVE_RECEIPT_CHANGED')
    receipt = json.loads(raw)
    require(receipt['schema'] == 'SERVER_REVIEWED_DAILY_EVIDENCE_V1' and
            receipt['account_id'] == reference_state['account_id'], 'REFERENCE_ARCHIVE_ACCOUNT')
    folder = receipt_path.parent
    manifest_raw = (folder/'manifest.json').read_bytes()
    manifest, complete = json.loads(manifest_raw), json.loads((folder/'complete.json').read_bytes())
    require(hashed(manifest_raw) == reader_archive['manifest_sha256'] == complete['manifest_sha256'] and
            complete['receipt_sha256'] == manifest['receipt_sha256'] == reader_archive['receipt_sha256'] and
            manifest['source_sha256'] == receipt['source_sha256'], 'REFERENCE_ARCHIVE_CLOSURE')
    files = {}
    require(0 < len(receipt['source_sha256']) <= 2000, 'REFERENCE_CONFIG_SOURCE_COUNT')
    for name, digest in receipt['source_sha256'].items():
        require(valid_hash(digest), 'REFERENCE_ARCHIVE_DIGEST')
        body = (folder/'sources'/(digest+'.bin')).read_bytes()
        require(hashed(body) == digest, 'REFERENCE_ARCHIVE_SOURCE_CHANGED')
        files[name] = body
    require(sum(map(len,files.values())) <= 32*1024*1024, 'REFERENCE_CONFIG_SOURCE_BYTES')
    capture = json.loads(files['frontier/capture.json'])
    inputs = json.loads(files['frontier/source-review.json'])['inputs']
    require(files['frontier/calendar.json']==pinned(root,source['calendar'],maximum=8*1024*1024),
            'REFERENCE_ARCHIVE_CALENDAR_CHANGED')
    output.mkdir(parents=True, exist_ok=True)

    def materialize(raw):
        path=output/(hashed(raw)+'.json')
        try:
            with path.open('xb') as stream: stream.write(raw)
        except FileExistsError:
            require(path.read_bytes()==raw, 'REFERENCE_CONFIG_EXISTING_CHANGED')
        return dict(path=path.relative_to(root).as_posix(),sha256=hashed(raw))

    def receipt_projection(receipt_raw, body):
        old=json.loads(receipt_raw)
        require(old['raw_sha256']==hashed(body), 'REFERENCE_CONFIG_RAW_CHANGED')
        new=dict(old,stored_bytes=len(body))
        return materialize(canonical(new)), dict(original_receipt=materialize(receipt_raw),
            projected_receipt_sha256=hashed(canonical(new)), rule='stored_bytes from authenticated raw only')

    results={}
    for origin, lock in reference_state['locks'].items():
        try:
            require(lock.get('current_security_id',origin)==origin and
                    lock.get('current_unit_id',lock['unit_id'])==lock['unit_id'], 'WAIT_REFERENCE_ONLY_IDENTITY_CAPTURE')
            verified=exit_boundary_archive.read_verified(exit_boundary_references.get(origin))
            require(verified['status']=='SERVER_ARCHIVED_BOUNDARY_VERIFIED', 'WAIT_ORIGINAL_EXIT_BOUNDARY')
            boundary=json.loads(verified['decision_evidence']); observation=verified['observation']
            require(boundary['account_id']==reference_state['account_id'] and
                    boundary['session_date']==lock['exit_session'] and
                    observation['unit_ids'][origin]==lock['unit_id'] and
                    Fraction(observation['closes'][origin])==Fraction(lock['reference_price']), 'REFERENCE_EXIT_ANCHOR_CHANGED')
            history=inputs['histories'][origin]
            require(history['units']['basis_id']==lock['unit_id'], 'WAIT_REFERENCE_UNIT_CHANGED')
            receipt_raw=files[capture['documents']['action_receipts'][origin]]
            daily=json.loads(receipt_raw); body=files[daily['raw_path']]
            series=json.loads(body)['chart']['result'][0]
            require(not any(series.get('events',{}).values()), 'WAIT_REFERENCE_APPROVED_ACTION_FACTS_REQUIRED')
            projected, provenance=receipt_projection(receipt_raw,body)
            rss_body=files[capture['documents']['rss_raw']]
            rss_receipt, rss_provenance=receipt_projection(files[capture['documents']['rss_receipt']],rss_body)
            config=dict(schema='SERVER_REFERENCE_INTERVAL_V1',
                reviewer_sha256=hashed((root/'data/reentry_reference_evidence_v1.py').read_bytes()),
                origin_security_id=origin, origin_unit_id=lock['unit_id'],exit_session=lock['exit_session'],
                decision_session=decision_session,calendar=source['calendar'],
                approved_actions=materialize(canonical(dict(schema='SERVER_APPROVED_REFERENCE_ACTIONS_V1',facts=[]))),
                notice_scope_reviewer=dict(path='data/saved_frontier_first_window_v1.py',
                    sha256=hashed((root/'data/saved_frontier_first_window_v1.py').read_bytes())),
                segments=[dict(identity=source['identity'],ticker=daily['ticker'],security_id=origin,
                    exchange=series['meta']['exchangeName'],unit_id=lock['unit_id'],
                    start_session=lock['exit_session'],end_session=decision_session,
                    price_basis='ARCHIVED_SAME_UNIT_RAW_CLOSE',raw=materialize(body),receipt=projected)],
                official_rss=dict(raw=materialize(rss_body),receipt=rss_receipt),
                construction=dict(source_configuration=source_configuration_reference,
                    reader_archive_sha256=reader_archive['receipt_sha256'],exit_boundary_sha256=verified['archive_sha256'],
                    receipt_projection=provenance,rss_receipt_projection=rss_provenance))
            reference=materialize(canonical(config))
            reviewed=review_reference_interval(root=root,configuration_reference=reference,lock=lock,
                                               decision_session=decision_session,as_of=as_of)
            require(reviewed['status']=='REFERENCE_SOURCE_REVIEWED_CONDITIONAL',reviewed.get('reason','WAIT_REFERENCE_INTERVAL'))
            results[origin]=dict(status='REFERENCE_CONFIGURATION_READY_CONDITIONAL',configuration_reference=reference,review=reviewed)
        except (ValueError,KeyError,TypeError,OSError,IndexError) as error:
            results[origin]=dict(status='WAIT_REFERENCE_CONFIGURATION',reason=str(error),
                                next_step='Reference-only capture or separately reviewed action/identity evidence required')
    return dict(status='REFERENCE_CONFIGURATION_CONSTRUCTION_COMPLETE',locks=results,
                network_requests=0,account_mutated=False,disjoint_identity_certified=False)
