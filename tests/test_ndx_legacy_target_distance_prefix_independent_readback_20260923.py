from copy import deepcopy
import unittest
from scripts import ndx_legacy_target_distance_prefix_independent_readback_20260923 as m
from test_ndx_drawdown_prefix_independent_implementation_review import fixture as old_fixture


def step(index=2,count=4):
    args=old_fixture(2)
    args['index']=index
    selected=args['selected']
    for i in range(4,count):
        selected['S'+str(i)]=dict(ticker='T'+str(i),issuer_id='I'+str(i),risk_chain='R'+str(i))
    previous=None if index==0 else args['previous']
    args['previous']=previous
    args['previous_reference']=None if index==0 else args['previous_reference']
    previous_selected={sid:dict(ticker=sid,issuer_id='old-'+sid,risk_chain='old-'+sid) for sid in previous or {}}
    previous_selected.update(selected)
    binding=m.lane_binding(index=index,previous=previous,previous_selected=previous_selected,selected=selected,
        universe=previous_selected,context_reference={},input_binding={},candidate_provenance={})
    args['binding']=binding;spec=m.SPECS[index];args['weight_spec']=spec
    fitted=args['raw']['fitted'];numerical=previous or {}
    mass=sum(numerical.get(sid,0.) for sid in sorted(selected))
    fitted.update(weight_spec=spec,previous_target_weights=numerical,surviving_anchor_mass=mass,
        projection_reconstruction_audit=dict(attempt_count=0,attempts=[]),
        anchor_by_security={sid:numerical.get(sid,0.)/mass if mass else 0. for sid in selected},
        effective_anchor_strength=.25 if mass and spec.endswith('turnover_anchor') else 0,
        targets={sid:dict(ticker=row['ticker'],issuer_id=row['issuer_id'],target_weight=1./count) for sid,row in selected.items()},
        risk_chains_by_security={sid:row['risk_chain'] for sid,row in selected.items()})
    counts=m.mode_counts(index)
    for key in ('started','raw','final'):
        document=args[key]
        document['schema']=document['schema'].replace('DRAWDOWN','LEGACY_TARGET_DISTANCE')
        document.update(plan_reference=m.PLAN,execution_date=m.DATES[index])
    for key in ('started','raw'):
        args[key].update(previous_target_weights=previous,previous_target_reference=args['previous_reference'],numerical_and_lane_binding=binding)
    started=args['started'];started.pop('new_fit_attempt')
    started.update(cutoff=m.CUTOFFS[index],selected=selected,weight_spec=spec,
        materialization_mode=counts['materialization_mode'],optimizer_called_by_equal_branch=counts['optimizer_called_by_equal_branch'],
        planned_operation_counts={key:value for key,value in counts.items() if key not in ('materialization_mode','optimizer_called_by_equal_branch')})
    args['raw'].pop('new_fit_attempt_count');args['raw'].pop('first_fit_imported_without_refit')
    args['raw'].update(counts);args['final'].update(counts)
    return args


class ReaderTests(unittest.TestCase):
    def test_three_equal_modes_and_six_security_construction(self):
        for index,count in ((0,4),(4,6),(5,4)):
            args=step(index,count);result=m.validate_step(**args)
            self.assertFalse(result['imported_original_fit'])
            self.assertEqual(result['effective_anchor_strength'],0)
            self.assertEqual(args['raw']['numerical_fit_request_count'],0)
        bad=step(4,6);targets=bad['raw']['fitted']['targets']
        targets['S0']['target_weight']+=.001;targets['S1']['target_weight']-=.001
        with self.assertRaisesRegex(ValueError,'exact frozen 1/k'):m.validate_step(**bad)

    def test_unanchored_preserves_nonzero_mass_and_full_exit_prior(self):
        args=step(2);result=m.validate_step(**args)
        self.assertEqual(args['raw']['fitted']['surviving_anchor_mass'],.75)
        self.assertEqual(result['effective_anchor_strength'],0)
        for change in ('prior','mass','strength'):
            bad=deepcopy(args);f=bad['raw']['fitted']
            if change=='prior':f['previous_target_weights']={}
            elif change=='mass':f['surviving_anchor_mass']=0
            else:f['effective_anchor_strength']=.25
            with self.subTest(change=change),self.assertRaises(ValueError):m.validate_step(**bad)

    def test_request_counts_distinguish_equal_and_numerical_and_reject_bool(self):
        for index in range(6):m.validate_step(**step(index,6 if index==4 else 4))
        for container,key,value in (('raw','wrapper_call_attempt_count',True),('final','import_count',1),
            ('raw','numerical_fit_request_count',0),('started','optimizer_called_by_equal_branch',False)):
            bad=step(2);bad[container][key]=value
            with self.subTest(container=container,key=key),self.assertRaises(ValueError):m.validate_step(**bad)
        bad=step(4,6);bad['started']['planned_operation_counts']['wrapper_call_attempt_count']=True
        with self.assertRaises(ValueError):m.validate_step(**bad)

    def test_issuer_shared_class_does_not_enter_surviving_anchor(self):
        args=step(3)
        # The exited class and new class share an issuer, but only SID overlap counts.
        args['selected']['S3']['issuer_id']='ALPHABET'
        args['raw']['fitted']['targets']['S3']['issuer_id']='ALPHABET'
        args['selected']['S3']['ticker']='GOOG'
        args['raw']['fitted']['targets']['S3']['ticker']='GOOG'
        m.validate_step(**args)
        bad=deepcopy(args);bad['raw']['fitted']['anchor_by_security']['S3']=1/3
        with self.assertRaises(ValueError):m.validate_step(**bad)

    def test_prefix_complete_and_no_skipped_equal_step(self):
        refs=[dict(path=str(m.FOLDER/day/'finalization.json'),sha256='a'*64) for day in m.DATES]
        self.assertEqual(m.prefix_references(refs),refs)
        with self.assertRaises(ValueError):m.prefix_references(refs[:3]+refs[4:])


if __name__=='__main__':unittest.main()
