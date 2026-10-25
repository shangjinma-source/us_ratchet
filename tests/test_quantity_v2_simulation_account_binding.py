from copy import deepcopy
import unittest

from data.quantity_v2_simulation_account_binding import validate_account_binding


class AccountBindingTests(unittest.TestCase):
    def test_actual_bootstrap_store_read_matches_and_foreign_expectation_fails(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from test_bootstrap_current_quantity_v2_simulation import fixture, fetch, NOW
        from scripts.bootstrap_current_quantity_v2_simulation import run
        from backtest.current_quantity_v2_simulation_store import SimulationStore
        with TemporaryDirectory() as directory:
            config, arguments = fixture(Path(directory))
            run(**arguments, execute=True, clock=lambda: NOW, fetch=fetch)
            store = SimulationStore(config['database_path'])
            before = store.read(config['simulation_id'])
            result = validate_account_binding(bootstrap=config, simulation=before['simulation'])
            self.assertEqual(result['account_id'], config['account_id'])
            foreign = dict(config, account_id='other-registered-account')
            with self.assertRaisesRegex(ValueError, 'ACCOUNT_BINDING_ORIGIN_MISMATCH'):
                validate_account_binding(bootstrap=foreign, simulation=before['simulation'])
            self.assertEqual(store.read(config['simulation_id']), before)

    def fixture(self):
        return ({'account_id':'approved-account','simulation_id':'one-simulation'},
            {'simulation_id':'one-simulation',
             'origin':{'ledger':{'account_id':'approved-account','revision':'initial'}},
             'chain':{'ledger':{'account_id':'approved-account','revision':'current'}}})

    def test_matching_and_monthly_retarget_preserve_identity_without_mutation(self):
        bootstrap, simulation = self.fixture()
        simulation['chain']['ledger']['active_monthly_acceptance']={'proposal':{'month':'2026-11'}}
        simulation['chain']['ledger']['shares']={'NEW':10}
        saved=deepcopy((bootstrap,simulation))
        result=validate_account_binding(bootstrap=bootstrap,simulation=simulation)
        self.assertEqual(result['account_id'],'approved-account')
        self.assertFalse(result['origin_authenticity_certified'])
        self.assertEqual((bootstrap,simulation),saved)

    def test_same_simulation_id_foreign_self_consistent_account_rejected(self):
        bootstrap,simulation=self.fixture()
        for field in ('origin','chain'):simulation[field]['ledger']['account_id']='foreign-account'
        with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_ORIGIN_MISMATCH'):
            validate_account_binding(bootstrap=bootstrap,simulation=simulation)

    def test_current_chain_mixed_account_rejected(self):
        bootstrap,simulation=self.fixture();simulation['chain']['ledger']['account_id']='foreign'
        with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_CURRENT_MISMATCH'):
            validate_account_binding(bootstrap=bootstrap,simulation=simulation)

    def test_simulation_id_mismatch_rejected(self):
        bootstrap,simulation=self.fixture();simulation['simulation_id']='other'
        with self.assertRaisesRegex(ValueError,'ACCOUNT_BINDING_SIMULATION_MISMATCH'):
            validate_account_binding(bootstrap=bootstrap,simulation=simulation)

    def test_missing_or_invalid_identifiers_and_chains_rejected(self):
        for field in ('bootstrap_account','bootstrap_simulation','simulation','origin','chain',
                      'origin_ledger','chain_ledger','origin_account','chain_account'):
            for invalid in (None,'',True,42,'   '):
                with self.subTest(field=field,invalid=invalid):
                    bootstrap,simulation=self.fixture()
                    if field=='bootstrap_account':bootstrap['account_id']=invalid
                    elif field=='bootstrap_simulation':bootstrap['simulation_id']=invalid
                    elif field=='simulation':simulation['simulation_id']=invalid
                    elif field in ('origin','chain'):simulation[field]=invalid
                    elif field.endswith('_ledger'):simulation[field.split('_')[0]]['ledger']=invalid
                    else:simulation[field.split('_')[0]]['ledger']['account_id']=invalid
                    with self.assertRaises(ValueError):
                        validate_account_binding(bootstrap=bootstrap,simulation=simulation)
        bootstrap,simulation=self.fixture();del simulation['origin']['ledger']['account_id']
        with self.assertRaises(ValueError):validate_account_binding(bootstrap=bootstrap,simulation=simulation)


if __name__=='__main__':unittest.main()
