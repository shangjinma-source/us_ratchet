"""Read-only local replay of a server-owned frozen research candidate.

The cap store checked prior history when creating this proof. This helper checks
only a local closed loop, not authorization or authentication of prior history.
Never accept an HTTP client's proof as trusted server evidence. A coherent rewrite
of proof and history cannot be detected without an external trusted anchor.
"""
from hashlib import sha256

from data.current_quantity_v2_pullback_entry import VERSION, digest, require, stamp
from data.current_quantity_v2_pullback_sources import ADAPTER_VERSION, candidate_from_yahoo_bytes


def replay_frozen_pullback(raw, proof, now):
    require(type(proof) is dict and proof.get('schema') == 'V2_FROZEN_PULLBACK_PROOF_V1',
            'INVALID_PULLBACK_PROOF')
    require(proof.get('proof_digest') == digest({key: value for key, value in proof.items()
                                               if key != 'proof_digest'}),
            'PROOF_DIGEST_MISMATCH')
    require(proof.get('kernel_version') == VERSION
            and proof.get('adapter_version') == ADAPTER_VERSION, 'PROOF_VERSION_MISMATCH')
    require(type(raw) is bytes and sha256(raw).hexdigest() == proof.get('raw_sha256'),
            'PROOF_RAW_HASH_MISMATCH')
    parameters = proof.get('parameters')
    require(type(parameters) is dict
            and parameters.get('expected_sha256') == proof['raw_sha256'],
            'PROOF_PARAMETERS_INVALID')
    ordinal = proof.get('ordinal')
    parent = proof.get('prior_record_hash')
    prior_cap = proof.get('prior_cap')
    require(type(ordinal) is int and ordinal >= 0, 'PROOF_ORDINAL_INVALID')
    require((ordinal == 0 and parent == '' and prior_cap is None)
            or (ordinal > 0 and type(prior_cap) is dict and type(parent) is str
                and len(parent) == 64 and all(c in '0123456789abcdef' for c in parent)),
            'PROOF_PRIOR_INVALID')
    replay = candidate_from_yahoo_bytes(raw=raw, previous_cap=prior_cap, **parameters)
    require(replay == proof.get('result'), 'PROOF_RESULT_MISMATCH')
    require(replay['candidate']['policy'] == proof.get('policy')
            and digest(replay['candidate']) == proof.get('candidate_digest'),
            'PROOF_CANDIDATE_MISMATCH')
    expected_hash = digest(dict(ordinal=ordinal, parameters=parameters, result=replay,
                               previous_hash=parent))
    require(expected_hash == proof.get('record_hash'), 'PROOF_RECORD_HASH_MISMATCH')
    current, checked, original = map(stamp, (now, proof['commit_checked_at'], parameters['now']))
    require(original <= checked <= current, 'PROOF_TIME_REVERSED')
    require(current < stamp(replay['candidate']['reference_valid_until']), 'PROOF_EXPIRED')
    return dict(replay, replay_receipt=dict(research_only=True, production_enabled=False,
        orders_created=False, prior_history_authenticated=False, local_replay_verified=True,
        record_hash=expected_hash, checked_at=current.isoformat()))
