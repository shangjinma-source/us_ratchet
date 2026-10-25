/** Immutable overlay planning only: no IO, workbook authoring, export or acceptance. */
import assert from 'node:assert/strict';
import path from 'node:path';
import {createHash} from 'node:crypto';
const P=path.win32;
const clone=structuredClone;
const hash=x=>assert.match(x,/^[a-f0-9]{64}$/);
const integer=x=>assert(Number.isSafeInteger(x)&&x>=0);
const reference=x=>{assert(x&&typeof x==='object');assert.equal(typeof x.path,'string');assert(P.isAbsolute(x.path));hash(x.sha256);};
const same=(a,b)=>assert.deepEqual(a,b);
const flags=Object.freeze({source_bytes_authenticated:false,economics_recomputed:false,risk_recomputed:false,fit_performed:false,account_executed:false,point_in_time_verified:false,formal_comparison_passed:false,future_independent_oos:false,promotion_allowed:false,independent_export_readback_passed:false,visual_acceptance_passed:false,native_excel_open_verified:false,workbook_delivered:false});
const digest=x=>createHash('sha256').update(JSON.stringify(x,(_k,v)=>typeof v==='bigint'?['bigint',v.toString()]:v)).digest('hex');
const descendant=(file,dir)=>{assert(P.isAbsolute(file));const r=P.relative(dir,file);assert(r&&!P.isAbsolute(r)&&r!=='..'&&!r.startsWith('..\\'),'Bounded namespace');return r.replaceAll('\\','/');};
const parentFlags=['formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','fit_performed','account_executed','independent_export_readback_passed','visual_acceptance_passed','workbook_delivered'];
export const REPAIR_SHA='f5ef70fbc034a17a1254723b07b4cf21278d1ee11967a6a1c11489bb008fdc00';

export function planSingletonOverlay({parentManifest,parentPublication,parentReference,parentPublicationReference,dataIndex,outputRoot,repairReference}){
 for(const r of [parentReference,parentPublicationReference,repairReference])reference(r);assert.equal(repairReference.sha256,REPAIR_SHA);
 assert(P.isAbsolute(outputRoot));const parentRoot=P.dirname(parentReference.path);assert.notEqual(P.resolve(parentRoot).toLowerCase(),P.resolve(outputRoot).toLowerCase());assert.equal(P.dirname(parentPublicationReference.path),parentRoot);
 assert.equal(parentManifest.schema,'DATED_H_WORKBOOK_EXTENSION_EXPORT_V1');assert.equal(parentManifest.status,'EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE');
 assert.equal(parentPublication.schema,'DATED_H_WORKBOOK_EXTENSION_PUBLICATION_V1');assert.equal(parentPublication.status,'PUBLISHED_EXPORT_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE');same(parentPublication.manifest_reference,parentReference);same(parentManifest.source_hashes,parentPublication.source_hashes);
 for(const key of parentFlags){assert.equal(parentManifest[key],false);assert.equal(parentPublication[key],false);}
 for(const [k,v] of Object.entries({planned_task_count:1632,packaged_task_count:1632,unprocessed_task_count:0,classification_count:101,shared_series_count:4,shared_risk_track_count:2}))assert.equal(parentManifest[k],v);
 for(const k of ['source_eof_verified','original_order_preserved','actual_package_bytes_within_50_mib'])assert.equal(parentManifest[k],true);
 assert.equal(dataIndex.schema,'SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1');assert.equal(dataIndex.planned_task_count,1632);assert.equal(dataIndex.task_index.length,1632);
 const ids=dataIndex.task_index.map((r,i)=>{assert.equal(r.task_ordinal,i);hash(r.numerical_task_id);return r.numerical_task_id;});assert.equal(new Set(ids).size,1632);assert.equal(parentManifest.default_task_id,ids[0]);
 const inventory=new Map(parentManifest.output_inventory.map(x=>[x.path,x]));assert.equal(inventory.size,parentManifest.output_inventory.length);
 const artifact=r=>{reference(r);const rel=descendant(r.path,parentRoot);const v=inventory.get(rel);assert(v,'Parent attachment must be in sealed inventory');assert.equal(v.sha256,r.sha256);integer(v.byte_count);return v;};
 artifact(parentManifest.machine_index_reference);for(const r of [parentManifest.navigation.workbook_reference,parentManifest.navigation.expected_cells_reference,parentManifest.navigation.native_links_reference,...parentManifest.navigation.previews])artifact(r);
 let ordinal=0;const packages=[];const replacements=[];const names=new Set();
 for(const [i,p] of parentManifest.packages.entries()){
  assert.equal(p.package_index,i);assert.match(p.filename,/^package-\d{4}\.xlsx$/);assert(!names.has(p.filename));names.add(p.filename);assert.equal(p.start_task_ordinal,ordinal);integer(p.stop_task_ordinal);assert(p.stop_task_ordinal>ordinal);assert.equal(p.tasks.length,p.stop_task_ordinal-ordinal);
  const observed=[];for(const [local,t] of p.tasks.entries()){assert.equal(t.task_ordinal,ordinal);assert.equal(t.numerical_task_id,ids[ordinal]);assert.equal(t.local_task_number,local+1);assert.equal(t.navigation_row,local+2);assert.equal(t.comparison_status,dataIndex.task_index[ordinal].status);observed.push(t.numerical_task_id);ordinal++;}
  if(p.task_ids!==undefined)same(p.task_ids,observed);
  const wb=artifact(p.workbook_reference);integer(p.byte_count);assert.equal(p.byte_count,wb.byte_count);assert.equal(p.sha256,p.workbook_reference.sha256);assert(wb.byte_count<=50*1024**2);assert.equal(P.basename(p.workbook_reference.path),p.filename);
  for(const r of [p.expected_cells_reference,p.chart_source_index_reference,...p.previews])artifact(r);
  const needs=p.tasks.length===1&&p.tasks[0].comparison_status!=='COMPARISON_NOT_SUPPLIED';
  const row={package_index:i,filename:p.filename,start_task_ordinal:p.start_task_ordinal,stop_task_ordinal:p.stop_task_ordinal,task_ids:observed,action:needs?'REBUILD_SINGLETON_B5_ONLY':'REUSE_PARENT_EXACT_REFERENCES',parent_package:clone(p),destination_workbook_path:needs?P.join(outputRoot,p.filename):p.workbook_reference.path,source_records:p.tasks.map(t=>({numerical_task_id:t.numerical_task_id,task_ordinal:t.task_ordinal,jsonl_record:clone(dataIndex.task_index[t.task_ordinal].jsonl_record)}))};
  if(needs)replacements.push({package_index:i,task_id:observed[0],original_workbook_reference:clone(p.workbook_reference),replacement_path:row.destination_workbook_path,allowed_formula_delta:{worksheet:'路径查看',cell:'B5',repair_reference:clone(repairReference)},source_records:clone(row.source_records)});
  packages.push(row);
 }
 assert.equal(ordinal,1632);assert.equal(parentManifest.packages.length,packages.length);
 const native_links=[];
 for(const p of packages){const target=P.relative(outputRoot,p.destination_workbook_path).replaceAll('\\','/');assert(target&&!P.isAbsolute(target));for(const t of p.parent_package.tasks)native_links.push({worksheet:'全部任务',cell:`H${t.task_ordinal+2}`,target,location:`'任务索引'!A${t.navigation_row}`,numerical_task_id:t.numerical_task_id,package_index:p.package_index,expected_workbook_reference:p.action==='REUSE_PARENT_EXACT_REFERENCES'?clone(p.parent_package.workbook_reference):null});}
 const out={schema:'DATED_H_SINGLETON_REPAIR_OVERLAY_PLAN_V1',status:'PLANNED_NOT_EXPORTED',parent_manifest_reference:clone(parentReference),parent_publication_reference:clone(parentPublicationReference),parent_root:parentRoot,output_root:outputRoot,repair_reference:clone(repairReference),original_task_ids:ids,planned_task_count:1632,package_count:packages.length,replacement_package_count:replacements.length,reused_package_count:packages.length-replacements.length,packages,replacements,native_links,machine_index_reference:clone(parentManifest.machine_index_reference),parent_navigation_preserved:clone(parentManifest.navigation),parent_input_references_preserved:clone(parentManifest.input_references),parent_output_inventory_preserved:clone(parentManifest.output_inventory),parent_source_hashes_preserved:clone(parentManifest.source_hashes),original_parent_manifest_preserved:clone(parentManifest),only_structure_determines_replacement:true,actual_export_size_limit_verified:false,...flags};
 out.content_sha256=digest(out);return out;
}

export function composeSingletonOverlayManifest({plan,replacementPackages,navigation,newSourceReferences}){
 const unsigned={...plan};delete unsigned.content_sha256;assert.equal(digest(unsigned),plan.content_sha256);assert.equal(plan.schema,'DATED_H_SINGLETON_REPAIR_OVERLAY_PLAN_V1');assert.equal(replacementPackages.length,plan.replacements.length);assert(Array.isArray(newSourceReferences));for(const r of newSourceReferences)reference(r);
 const replacementByIndex=new Map();
 for(const [i,r] of replacementPackages.entries()){
  const expected=plan.replacements[i];assert.equal(r.package_index,expected.package_index);assert(!replacementByIndex.has(r.package_index));const prior=plan.packages[r.package_index].parent_package;
  // Changes may concern only newly rendered artifact references and explicit repair evidence.
  const allowed=new Set(['workbook_reference','expected_cells_reference','chart_source_index_reference','previews','byte_count','sha256','repair_evidence_reference']);
  const strip=o=>Object.fromEntries(Object.entries(o).filter(([k])=>!allowed.has(k)));same(strip(r),strip(prior));
  for(const v of [r.workbook_reference,r.expected_cells_reference,r.chart_source_index_reference,r.repair_evidence_reference,...r.previews]){reference(v);descendant(v.path,plan.output_root);}
  assert.equal(r.workbook_reference.path,expected.replacement_path);integer(r.byte_count);assert(r.byte_count>0&&r.byte_count<=50*1024**2);assert.equal(r.sha256,r.workbook_reference.sha256);assert.equal(r.previews.length,prior.previews.length);replacementByIndex.set(r.package_index,clone(r));
 }
 for(const r of [navigation.workbook_reference,navigation.expected_cells_reference,navigation.native_links_reference,...navigation.previews]){reference(r);descendant(r.path,plan.output_root);}
 assert.equal(navigation.previews.length,plan.parent_navigation_preserved.previews.length);assert.equal(navigation.link_count,1632);
 const packages=plan.packages.map(p=>replacementByIndex.get(p.package_index)??clone(p.parent_package));
 const links=plan.native_links.map(l=>({...clone(l),expected_workbook_reference:clone(packages[l.package_index].workbook_reference)}));
 return {schema:'DATED_H_SINGLETON_REPAIR_OVERLAY_EXPORT_V1',status:'EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',parent_manifest_reference:clone(plan.parent_manifest_reference),parent_publication_reference:clone(plan.parent_publication_reference),overlay_plan_sha256:plan.content_sha256,planned_task_count:1632,packaged_task_count:1632,unprocessed_task_count:0,packages,navigation:clone(navigation),native_links:links,replacement_map:clone(plan.replacements),replacement_package_count:plan.replacement_package_count,reused_package_count:plan.reused_package_count,machine_index_reference:clone(plan.machine_index_reference),parent_input_references_preserved:clone(plan.parent_input_references_preserved),parent_source_hashes_preserved:clone(plan.parent_source_hashes_preserved),parent_output_inventory_preserved:clone(plan.parent_output_inventory_preserved),new_source_references:clone(newSourceReferences),all_package_references_are_original_or_explicit_replacement:true,source_economic_replay_performed:false,manifest_composition_only_not_source_authentication:true,...flags};
}
