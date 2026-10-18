from copy import deepcopy
import unittest
from backtest import ndx_outer_refit_result_inspection_research as inspector
import test_ndx_outer_lane_refit_evidence_research as source


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepared, contract = source.fixture()
        resolved = source.m.resolve_adjacent_refit_priors(prepared=prepared, prior_evidence=[], receipt_contract=contract)
        cls.request = resolved['rows'][4]['outer_request']
        cls.fitter = prepared['fitter_contract_preserved']
        cls.body = source.evidence(cls.request, cls.fitter, contract)['raw_result']['result']

    def inspect(self, request=None, body=None):
        return inspector.inspect_saved_outer_result(request=request or self.request,
            result=body or self.body, fitter_contract=self.fitter)

    def test_original_equal_result_and_no_permission(self):
        result = self.inspect()
        self.assertTrue(result['declared_risks_passed'])
        self.assertTrue(result['next_prior_simplex_eligible'])
        self.assertFalse(result['fit_performed'])
        self.assertFalse(result['source_bytes_authenticated'])

    def test_false_zero_matrix_and_missing_sources_rejected(self):
        for attack in ('boolean', 'matrix', 'source', 'weight'):
            request, body = deepcopy(self.request), deepcopy(self.body)
            if attack == 'boolean': body['declared_constraints_passed'] = 1
            if attack == 'matrix': request['fit_matrix']['returns'][0][0] += .01
            if attack == 'source': body['source_hashes'].pop(next(iter(body['source_hashes'])))
            if attack == 'weight': body['targets'][next(iter(body['targets']))]['target_weight'] = True
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                self.inspect(request, body)

    def test_honest_risk_failure_retained_not_laundered(self):
        request, body = deepcopy(self.request), deepcopy(self.body)
        for selected in request['numerical_identity']['selected'].values(): selected['risk_chain'] = 'ONE_CHAIN'
        request['numerical_task_id'] = inspector.hashlib.sha256(inspector.encoded(request['numerical_identity'])).hexdigest()
        body['risk_chains_by_security'] = {s:'ONE_CHAIN' for s in body['targets']}
        body['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT'] = False
        body['declared_constraints_passed'] = False
        result = self.inspect(request, body)
        self.assertFalse(result['declared_risks_passed'])
        body['declared_constraint_checks']['RISK_CHAIN_TOP1_WEIGHT'] = True
        with self.assertRaises(ValueError): self.inspect(request, body)

    def test_equal_weight_cannot_be_arbitrary_risk_passing_weights(self):
        request, body = deepcopy(self.request), deepcopy(self.body)
        request['numerical_identity']['weight_spec'] = body['weight_spec'] = 'equal_weight'
        request['numerical_task_id'] = inspector.hashlib.sha256(inspector.encoded(request['numerical_identity'])).hexdigest()
        self.inspect(request, body)
        securities = sorted(body['targets'])
        body['targets'][securities[0]]['target_weight'] += .01
        body['targets'][securities[1]]['target_weight'] -= .01
        with self.assertRaises(ValueError): self.inspect(request, body)


if __name__ == '__main__': unittest.main()
