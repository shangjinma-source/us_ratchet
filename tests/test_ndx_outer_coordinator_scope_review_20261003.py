"""Independent full-domain orchestration checks using synthetic callbacks only."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1]/'scripts/ndx_outer_lane_refit_coordinator_20261003.py'
spec = importlib.util.spec_from_file_location('outer_scope_review', path)
coordinator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinator)


class ScopeReview(unittest.TestCase):
    def run_scenario(self, first_outcome='REFIT_RISK_FAILED', dispatch_error=False):
        documents = {}; dispatched = []; rows = []
        reader = dict(path=str(path.resolve()), sha256='a'*64)
        def persist(name, value):
            documents[name] = deepcopy(value)
            return dict(path=str((path.parent/name).resolve()), sha256=coordinator.sha(coordinator.enc(value)), name=name)
        def read(reference): return deepcopy(documents[reference['name']])
        for index in range(48):
            coordinate = [f'period{index//8}', f'fx{index%8//4}', f'lane{index%4}']
            request = None
            if index in (4, 5):
                request = dict(coordinate=coordinate, numerical_task_id=str(index)*64, location_id=str(index)*64)
            rows.append(dict(cutoff=coordinate[0], fx_mode=coordinate[1], lane=coordinate[2],
                decision_index=index//8, outer_request=request, status='SOURCE_BLOCKED' if request is None else 'INITIAL_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED',
                missing_latest_return_slots=[]))
        state = dict(schema='MULTIDECISION_SELECTED_LATEST126_REFIT_INPUTS_V2', rows=rows,
                     status_counts=dict(SOURCE_BLOCKED=46, INITIAL_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED=2))
        def dispatch(index, prior, origin):
            dispatched.append(index)
            if dispatch_error: raise RuntimeError('No saved call fact exists')
            request = rows[index]['outer_request']
            return persist(f'post{index}', dict(numerical_task_id=request['numerical_task_id'], location_id=request['location_id'],
                outcome=first_outcome if index==4 else 'REFIT_PASSED_PENDING_INDEPENDENT_READBACK',
                current_location_call_invoked=True, request_reference=persist(f'request{index}', request),
                raw_result_reference=persist(f'raw{index}', {'synthetic':True})))
        def inspect(reference):
            post = read(reference); success = post['outcome']=='REFIT_PASSED_PENDING_INDEPENDENT_READBACK'
            return persist('audit'+reference['name'], dict(postcheck_reference=reference,reader_sha256=reader['sha256'],
                status='PASS' if success else 'PASS_SAVED_RISK_FAILURE',prior_eligible=success))
        result_ref = coordinator.execute_full48(prepared=state, expected_coordinates=[[r['cutoff'],r['fx_mode'],r['lane']] for r in rows],
            reader_reference=reader, resolve_state=lambda prior:deepcopy(state), dispatch=dispatch,
            inspect_saved=inspect, read_saved=read, guard_sources=lambda:None,
            resource_check=lambda:10*1024**3,persist=persist)
        return read(result_ref), dispatched, documents

    def test_economic_failure_does_not_remove_independent_lane(self):
        result, dispatched, documents = self.run_scenario()
        self.assertEqual(dispatched,[4,5])
        self.assertEqual(len(result['rows']),48)
        self.assertEqual(result['rows'][5]['outcome'],'AUDITED_DIRECT_SUCCESS')
        self.assertEqual(result['summary']['unprocessed_coordinate_count'],0)
        self.assertEqual(len(documents['prepared48.json']['prepared']['rows']),48)

    def test_unknown_dispatch_never_invents_actual_fit(self):
        result, dispatched, _ = self.run_scenario(dispatch_error=True)
        self.assertEqual(dispatched,[4])
        self.assertEqual(result['status'],'STOPPED_NO_RETRY')
        self.assertEqual(len(result['rows']),48)
        self.assertEqual(result['rows'][4]['outcome'],'UNRESOLVED_DISPATCH')
        self.assertIsNone(result['rows'][4]['fit_call_invoked'])
        self.assertGreater(result['summary']['unprocessed_coordinate_count'],0)


if __name__ == '__main__': unittest.main()
