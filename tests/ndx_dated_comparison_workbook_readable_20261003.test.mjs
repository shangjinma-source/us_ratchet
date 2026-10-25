import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {layoutPlan,buildReadableWorkbook} from '../scripts/ndx_dated_comparison_workbook_readable_layout_20261003.mjs';
import {bound,publish,diagnosticAttachment,verifyOutputInventory} from '../scripts/ndx_dated_comparison_workbook_readable_publish_20261003.mjs';
import {fixture} from './ndx_dated_comparison_workbook_20261003.test.mjs';
test('layout only touches D width/wrap and source B wrap/width plus row heights',()=>{
 const payload=fixture();payload.display.tables[4].rows[0][3]='security:'+ 'a'.repeat(55);payload.display.tables[5].rows[0][1]='E:/'+ 'path/'.repeat(50);
 const original=structuredClone(payload),changes=[];
 const workbook={worksheets:{getItem:sheet=>({getRangeByIndexes:(...range)=>({format:new Proxy({},{set:(o,key,value)=>{changes.push({sheet,range,key,value});return true;}})})})}};
 const builder={buildWorkbook:()=>({workbook,renderRegions:[]})};
 const result=buildReadableWorkbook({},payload,builder);assert.deepEqual(payload,original);assert.equal(result.layoutAdjustments.security_id.width,70);assert.equal(changes.length,9);assert(changes.every(x=>['columnWidth','wrapText','rowHeight'].includes(x.key)));assert.equal(changes[4].value,96);
});
test('resource layout caps explicit, never truncates data',()=>{
 const p=fixture();p.display.tables[4].rows[0][3]='a'.repeat(121);assert.throws(()=>layoutPlan(p));
 const q=fixture();q.display.tables[5].rows[0][1]='a'.repeat(2000);assert.throws(()=>layoutPlan(q));
});
test('publication refused without explicit permission or anchor before IO',async()=>{
 await assert.rejects(publish(),/Explicit/);const h=bound.layout.sha256;bound.layout.sha256=null;
 try{await assert.rejects(publish({execute:true}),/anchors pending/);}finally{bound.layout.sha256=h;}
});
test('opaque runtime diagnostic bound; exact inventory detects drift and residue',async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'readable-workbook-'));
 try{
 const names=['started.json','条件历史比较.xlsx','条件历史比较.xlsx.inspect.ndjson',...Array.from({length:6},(_,i)=>`preview_${i}.png`)];const hashes={};
 for(const name of names){const file=path.join(dir,name);await fs.writeFile(file,Buffer.from([0,255,2]));hashes[file]=(await diagnosticAttachment(file)).reference.sha256;}
 const a=await diagnosticAttachment(path.join(dir,names[2]));assert.equal(a.manifest_bound,true);assert.equal(a.content_interpreted,false);assert.equal(a.numeric_input,false);
 await verifyOutputInventory(dir,hashes,false);
 await fs.writeFile(path.join(dir,'extra'),Buffer.from('extra'));await assert.rejects(verifyOutputInventory(dir,hashes,false),/inventory/);await fs.unlink(path.join(dir,'extra'));
 await fs.writeFile(path.join(dir,names[2]),Buffer.from('changed'));await assert.rejects(verifyOutputInventory(dir,hashes,false),/drift/);
 }finally{await fs.rm(dir,{recursive:true,force:true});}
});
