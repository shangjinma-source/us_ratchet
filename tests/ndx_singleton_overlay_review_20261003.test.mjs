import {test} from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {fixture} from './test_ndx_dated_singleton_overlay_plan_20261003.mjs';
import {planSingletonOverlay,composeSingletonOverlayManifest} from '../scripts/ndx_dated_singleton_overlay_plan_20261003.mjs';

function actualShape() {
 const a=fixture();
 for(const p of a.parentManifest.packages){p.byte_count=100;delete p.bytes;}
 return a;
}
test('real package byte_count supports changed export size without stale size alias',()=>{
 const p=planSingletonOverlay(actualShape()),r=structuredClone(p.packages[0].parent_package);
 const ref=n=>({path:path.win32.join(p.output_root,n),sha256:'c'.repeat(64)});
 Object.assign(r,{workbook_reference:ref(r.filename),sha256:'c'.repeat(64),byte_count:201,expected_cells_reference:ref('cells.jsonl'),chart_source_index_reference:ref('chart.json'),repair_evidence_reference:ref('repair.json'),previews:[ref('preview.png')]});
 const nav={workbook_reference:ref('navigation.xlsx'),expected_cells_reference:ref('navigation-cells.jsonl'),native_links_reference:ref('links.json'),previews:[ref('nav.png')],link_count:1632};
 const out=composeSingletonOverlayManifest({plan:p,replacementPackages:[r],navigation:nav,newSourceReferences:[p.repair_reference]});
 assert.equal(out.packages[0].byte_count,201);assert(!('bytes' in out.packages[0]));
 assert.deepEqual(out.packages[1],p.packages[1].parent_package);
});
test('parent self claims must match sealed artifact inventory and original identity',()=>{
 for(const edit of [a=>a.parentManifest.packages[0].byte_count=101,a=>a.parentManifest.packages[0].sha256='f'.repeat(64),a=>a.parentManifest.packages[0].tasks[0].navigation_row=3,a=>a.parentManifest.packages[0].workbook_reference.path='D:\\saved\\original-evil\\package-0000.xlsx']){
  const a=actualShape();edit(a);assert.throws(()=>planSingletonOverlay(a));
 }
});
test('all1632 links retain original ordinal identity and missing singleton stays external',()=>{
 const a=actualShape(),before=structuredClone(a),p=planSingletonOverlay(a);
 assert.deepEqual(a,before);assert.equal(p.native_links.length,1632);
 for(let i=0;i<1632;i++){assert.equal(p.native_links[i].cell,`H${i+2}`);assert.equal(p.native_links[i].numerical_task_id,a.dataIndex.task_index[i].numerical_task_id);}
 assert.equal(p.packages[2].action,'REUSE_PARENT_EXACT_REFERENCES');
 assert.equal(p.native_links[1001].target,'../original/package-0002.xlsx');
 assert.equal(p.visual_acceptance_passed,false);assert.equal(p.workbook_delivered,false);
});
