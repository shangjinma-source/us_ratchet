"""Same captured provider, only DLTR fixed staged-holding interval extended."""
from types import FunctionType
from docs.candidates import pullback_absence_20261105 as prior
from copy import deepcopy
def append_review(document,review):
 namespace=dict(prior.append_review.__globals__);namespace['SCOPES']=[('security:0000935703:256746108','DLTR','2024-03-01','2024-03-13')]
 function=FunctionType(prior.append_review.__code__,namespace,prior.append_review.__name__,prior.append_review.__defaults__)
 isolated=dict(rows=[],source_hashes={});proof=function(document,isolated)
 matches=[r for r in review['rows'] if r.get('security_id')=='security:0000935703:256746108' and r['status']=='REVIEWED_NO_ACTION_FOR_PERIOD']
 prior.need(len(matches)==1 and matches[0]['start_exclusive']=='2024-03-01' and matches[0]['end_inclusive']=='2024-03-08','EXACT_PARENT_DLRT_REVIEW')
 review['rows'].remove(matches[0]);review['rows'].extend(deepcopy(proof['rows']));review['source_hashes'].update(proof['source_hashes']);return proof
