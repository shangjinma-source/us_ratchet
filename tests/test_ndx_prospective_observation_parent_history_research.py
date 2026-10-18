from copy import deepcopy
import hashlib
from datetime import date,timedelta
import unittest
from backtest import ndx_prospective_observation_parent_history_research as m

def ref(p): return dict(path=p,sha256=hashlib.sha256(p.encode()).hexdigest())
def envelope(doc,name,genesis=False):
    r,pr,ar,rr=map(ref,(name,name+'pub',name+'audit',name+'reader'))
    key='policy_reference' if genesis else 'history_reference'
    flags=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'),False)
    pub=dict(schema='GAP_MONTHLY_POLICY_PUBLICATION_V1' if genesis else 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2',status='PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL' if genesis else 'PUBLISHED_OBSERVATION_HISTORY_NO_SEAL',source_hashes=deepcopy(doc['source_hashes']),**{key:r},**flags)
    audit=dict(schema=m.GENESIS_READBACK_SCHEMA if genesis else m.HISTORY_READBACK_SCHEMA,status='PASS',publication_reference=pr,reader_sha256=rr['sha256'],source_hashes={**doc['source_hashes'],**{v['path']:v['sha256'] for v in (r,pr,rr)}},**{key:r},**flags)
    return dict(document=doc,publication=pub,readback=audit,reference=r,publication_reference=pr,readback_reference=ar,reader_reference=rr)
def genesis():
    # V1 reader really authenticates exactly 60 observed + 5 gaps, not a toy prefix.
    dates=[];d=date(2026,7,1)
    while len(dates)<65:
      if d.weekday()<5:dates.append(d.isoformat())
      d+=timedelta(days=1)
    rows=[dict(sequence=i+1,session=day,kind='SEALED_PARENT_OBSERVED_SESSION' if i<60 else 'MISSED_OBSERVATION',seal_status=('FAILED' if i==0 else 'UNKNOWN') if i<60 else 'NOT_ATTEMPTED',evidence_reference=dict(ref('old'+str(i)),json_pointer='/rows/0')) for i,day in enumerate(dates)]
    g=envelope(dict(schema='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1',policy_id=m.POLICY,new_observation_count=0,projection_inputs=dict(known_rows=rows,new_prospective_observations=[]),source_hashes={},**m.FLAGS),'genesis',True)
    g['baseline_references']={t:ref('base'+t) for t in ('QQQ','SPY')};g['readback']['baseline_references']=deepcopy(g['baseline_references']);g['readback']['source_hashes'].update({r['path']:r['sha256'] for r in g['baseline_references'].values()});return g

def observation(g,parent=None,session='2026-10-02',late=False):
    known=g['document']['projection_inputs']['known_rows'] if parent is None else parent['document']['known_typed_rows']
    inventory=[] if parent is None else parent['document']['parent_attempt_inventory']
    pbase=g if parent is None else parent;baseline=g['baseline_references'] if parent is None else parent['document']['baseline_references']
    refs={k:ref(session+k) for k in ('payload_reference','receipt_reference','audit_reference','reader_reference')}
    identity=dict(parent_reference=pbase['reference'],capture_reference=ref(session+'capture'),session=session);ident=hashlib.sha256(m.encoded(identity)).hexdigest()
    first=next((r['session'] for r in known if r['session'][:7]==session[:7] and r['kind']!='MISSED_OBSERVATION'),session)
    flags=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed'),False)
    p=dict(schema='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1',known_typed_rows_preserved=deepcopy(known),parent_attempt_inventory_preserved=deepcopy(inventory),parent_readback_reference=pbase['readback_reference'],observation_identity=identity,observation_id=ident,sequence=len(known)+1,session=session,kind='PROSPECTIVE_OBSERVED_SESSION',initial_seal_status='NOT_ATTEMPTED',month_first_actual_observation=first==session,first_actual_observed_session_of_month=first,timing_classification='LATE_OBSERVATION' if late else 'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW',full_original_sources_preserved={t:dict(sources=dict(reference=ref(session+t)),baseline_sources=dict(reference=baseline[t])) for t in baseline},**flags)
    receipt=dict(schema='PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',status='PERSISTED_RESEARCH_OBSERVATION_NOT_CANDIDATE_AUTHORITY',observation_id=ident,payload_reference=refs['payload_reference'],month_first_actual_observation=p['month_first_actual_observation'],timing_classification=p['timing_classification'],**flags)
    audit=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1' if parent is None else m.OBSERVATION_READBACK_V2,parent_history_reference=pbase['reference'],counts=dict(parent_observed_count=sum(r['kind']!='MISSED_OBSERVATION' for r in known),parent_gap_count=sum(r['kind']=='MISSED_OBSERVATION' for r in known),new_observation_count=1,month_first_actual_observation=p['month_first_actual_observation'],timing_classification=p['timing_classification']),status='PASS',payload_reference=refs['payload_reference'],receipt_reference=refs['receipt_reference'],reader_sha256=refs['reader_reference']['sha256'],source_hashes={v['path']:v['sha256'] for v in refs.values()},writer_called=False,old_audit_repeated=False,**flags)
    claims={identity['capture_reference']['path']:identity['capture_reference']['sha256']}
    for t in baseline:
      for role in ('sources','baseline_sources'):
        r=p['full_original_sources_preserved'][t][role]['reference'];claims[r['path']]=r['sha256']
    p['source_hashes']=deepcopy(claims);receipt['source_hashes']=deepcopy(claims);audit['source_hashes'].update(claims)
    return dict(payload=p,receipt=receipt,audit=audit,**refs)

class Tests(unittest.TestCase):
 def test_append_two_late_and_failed_unknown_preserved(self):
    g=genesis();o=observation(g,late=True);before=deepcopy((g,o));h=m.append_observation_history(genesis=g,previous_history=None,observation=o)
    self.assertEqual((g,o),before);self.assertEqual(h['known_typed_rows'][:65],g['document']['projection_inputs']['known_rows']);self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02');self.assertTrue(all(h[k] is False for k in m.FLAGS))
    parent=envelope(h,'history1');second=observation(g,parent,'2026-10-05');out=m.append_observation_history(genesis=g,previous_history=parent,observation=second)
    self.assertEqual(out['known_typed_rows'][:-1],h['known_typed_rows']);self.assertFalse(second['payload']['month_first_actual_observation']);self.assertEqual(out['observation_count'],2);self.assertEqual(out['baseline_references'],m.captured_baselines(second['payload']))
 def test_parent_receipt_and_audit_cannot_be_just_claimed_refs(self):
    for mutate in (lambda g:g['readback'].update(status='FAILED'),lambda g:g['publication'].update(policy_reference=ref('wrong')),lambda g:g['readback'].update(source_hashes={}),lambda g:g['document'].update(candidate_seal_allowed=0)):
      g=genesis();o=observation(g);mutate(g)
      with self.assertRaises((ValueError,KeyError)):m.append_observation_history(genesis=g,previous_history=None,observation=o)
 def test_partial_duplicate_and_altered_baseline_rejected(self):
    g=genesis()
    for mutate in (lambda o:o['receipt'].update(status='FAILED'),lambda o:o['audit'].update(status='UNKNOWN'),lambda o:o['payload'].update(sequence=True),lambda o:o['payload']['full_original_sources_preserved']['QQQ']['baseline_sources'].update(reference=ref('changed')),lambda o:o['payload'].update(parent_attempt_inventory_preserved=[{}]),lambda o:o['receipt'].update(month_first_actual_observation=1)):
      o=observation(g);mutate(o)
      with self.assertRaises((ValueError,KeyError)):m.append_observation_history(genesis=g,previous_history=None,observation=o)
 def test_prior_inventory_omission_and_month_replacement_rejected(self):
    g=genesis();h=m.append_observation_history(genesis=g,previous_history=None,observation=observation(g));parent=envelope(h,'history1')
    for mode in ('inventory','month','old'):
      p=deepcopy(parent);o=observation(g,p,'2026-10-05')
      if mode=='inventory':p['document']['parent_attempt_inventory']=[]
      if mode=='month':o['payload']['month_first_actual_observation']=True
      if mode=='old':p['document']['known_typed_rows'][0]['seal_status']='SEALED'
      with self.assertRaises(ValueError):m.append_observation_history(genesis=g,previous_history=p,observation=o)
 def test_complete_source_union_and_conflicts(self):
    g=genesis();o=observation(g);o['payload']['source_hashes']['extra']='f'*64;o['receipt']['source_hashes']['extra']='f'*64;o['audit']['source_hashes']['extra']='f'*64
    h=m.append_observation_history(genesis=g,previous_history=None,observation=o)
    for p,d in o['audit']['source_hashes'].items():self.assertEqual(h['source_hashes'][p],d)
    for kind in ('receipt','conflict','raw','audit'):
      bad=deepcopy(o)
      if kind=='receipt':bad['receipt']['source_hashes']['extra']='e'*64
      if kind=='conflict':
        for role in ('payload','receipt','audit'):bad[role]['source_hashes'][g['reference']['path']]='e'*64
      if kind=='raw':bad['payload']['full_original_sources_preserved']['QQQ']['sources']['reference']=ref('unbound')
      if kind=='audit':del bad['audit']['source_hashes']['extra']
      with self.assertRaises(ValueError):m.append_observation_history(genesis=g,previous_history=None,observation=bad)
 def test_parent_derived_month_and_last_day_must_match(self):
    g=genesis();h=m.append_observation_history(genesis=g,previous_history=None,observation=observation(g))
    for key,value in [('last_accounted_session','2026-10-01'),('first_actual_observed_session_by_month',{'2026-10':'2026-10-05'})]:
      parent=envelope(deepcopy(h),'history1');parent['document'][key]=value;o=observation(g,parent,'2026-10-05')
      with self.assertRaises(ValueError):m.append_observation_history(genesis=g,previous_history=parent,observation=o)
 def test_genesis_baseline_roles_and_bytes_bound(self):
    for mode in ('swap','missing'):
      g=genesis();o=observation(g)
      if mode=='swap':g['baseline_references']={k:g['baseline_references']['SPY' if k=='QQQ' else 'QQQ'] for k in ('QQQ','SPY')}
      else:del g['readback']['source_hashes'][g['baseline_references']['QQQ']['path']]
      with self.assertRaises(ValueError):m.append_observation_history(genesis=g,previous_history=None,observation=o)
 def test_real_v1_count_boundary_and_boolean_counts(self):
    for mode in ('short','bool','count'):
      g=genesis()
      if mode=='short':g['document']['projection_inputs']['known_rows']=g['document']['projection_inputs']['known_rows'][:3]
      o=observation(g)
      if mode=='bool':o['audit']['counts']['parent_gap_count']=True
      if mode=='count':o['audit']['counts']['parent_observed_count']=59
      with self.assertRaises(ValueError):m.append_observation_history(genesis=g,previous_history=None,observation=o)
 def test_compact_two_append_never_embeds_full_raw_payload(self):
    g=genesis();o=observation(g,late=True)
    for t in ('QQQ','SPY'):
      for role in ('sources','baseline_sources'):
        o['payload']['full_original_sources_preserved'][t][role].update(original_csv_bytes_base64='SYNTHETIC_RAW_SENTINEL'*1000,rows=[{'unconsumed_raw_marker':'SYNTHETIC_ROW_SENTINEL'}])
    h=m.append_observation_history(genesis=g,previous_history=None,observation=o);parent=envelope(h,'history1');o2=observation(g,parent,'2026-10-05');h2=m.append_observation_history(genesis=g,previous_history=parent,observation=o2)
    self.assertEqual(h2['observations'][0],h['observations'][0]);self.assertEqual(h2['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
    text=m.encoded(h2).decode();self.assertNotIn('SYNTHETIC_RAW_SENTINEL',text);self.assertNotIn('SYNTHETIC_ROW_SENTINEL',text);self.assertNotIn('full_original_sources_preserved',text)
    for item in h2['observations']:
      self.assertEqual(set(item),m.COMPACT_KEYS);self.assertIs(item['original_payload_embedded'],False)
    self.assertEqual(h2['observations'][0]['payload_reference'],o['payload_reference']);self.assertEqual(h2['observations'][0]['original_source_hash_claims']['audit'],o['audit']['source_hashes'])
if __name__=='__main__':unittest.main()
