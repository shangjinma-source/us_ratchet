"""Pure supplemental identity gate for a future runtime adapter.

Caller must separately use SimulationStore.read for schema/revision/replay checks.
This matches account identity; it does not authenticate the origin or database.
No IO, mutations, bootstrap, or strategy execution.
"""


def validate_account_binding(*, bootstrap, simulation):
    def identifier(document, key):
        if not isinstance(document, dict):
            raise ValueError('ACCOUNT_BINDING_DOCUMENT_REQUIRED')
        value = document.get(key)
        if type(value) is not str or not value.strip():
            raise ValueError('ACCOUNT_BINDING_IDENTIFIER_REQUIRED')
        return value

    expected_account = identifier(bootstrap, 'account_id')
    expected_simulation = identifier(bootstrap, 'simulation_id')
    actual_simulation = identifier(simulation, 'simulation_id')
    if actual_simulation != expected_simulation:
        raise ValueError('ACCOUNT_BINDING_SIMULATION_MISMATCH')
    origin = simulation.get('origin')
    chain = simulation.get('chain')
    if not isinstance(origin, dict) or not isinstance(chain, dict):
        raise ValueError('ACCOUNT_BINDING_CHAIN_REQUIRED')
    origin_account = identifier(origin.get('ledger'), 'account_id')
    current_account = identifier(chain.get('ledger'), 'account_id')
    if origin_account != expected_account:
        raise ValueError('ACCOUNT_BINDING_ORIGIN_MISMATCH')
    if current_account != origin_account:
        raise ValueError('ACCOUNT_BINDING_CURRENT_MISMATCH')
    return dict(status='ACCOUNT_IDENTITY_MATCHED_NOT_ORIGIN_AUTHENTICATED',
        account_id=expected_account, simulation_id=expected_simulation,
        origin_account_id=origin_account, current_account_id=current_account,
        requires_store_replay_validation=True, origin_authenticity_certified=False,
        account_writes=False, deployed=False)
