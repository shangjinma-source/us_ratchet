import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {buildReadableWorkbook} from '../scripts/ndx_dated_comparison_workbook_readable_layout_20261003.mjs';
import {bound,publish,verifyOutputInventory} from '../scripts/ndx_dated_comparison_workbook_readable_publish_20261003.mjs';

const payload=()=>({display:{tables:[{},{},{},{},{name:'原始目标权重',headers:['a','b','c','证券身份'],rows:[[1,'0001','T','security:001',null,0],[2,'0002','Q','security:002',null,null]]},{name:'来源索引',rows:Array.from({length:5},(_,i)=>['source'+i,'E:/目录/'+('nested/'.repeat(i*8)),'a'.repeat(64)])}]}});

test('layout cannot write values or number formats; source mutation is rejected',()=>{
 const p=payload(),before=structuredClone(p),writes=[];
 const workbook={worksheets:{getItem:sheet=>({getRangeByIndexes:(...coords)=>new Proxy({format:new Proxy({},{set:(target,key,value)=>{assert(['columnWidth','rowHeight','wrapText'].includes(key));writes.push({sheet,coords,key,value});return true;}})},{set(){throw Error('Unexpected cell or numberformat assignment');},get(target,key){assert.notEqual(key,'setNumberFormat');return target[key];}})})}};
 const result=buildReadableWorkbook({},p,{buildWorkbook:()=>({workbook,renderRegions:[]})});
 assert.deepEqual(p,before);assert.equal(writes.length,9);
 assert(writes.filter(x=>x.key==='rowHeight').every(x=>x.value>=72&&x.value<=400));
 assert.equal(result.layoutAdjustments.values_changed,false);assert.equal(result.layoutAdjustments.text_styles_changed,false);
 assert.throws(()=>buildReadableWorkbook({},p,{buildWorkbook:(_,input)=>{input.display.tables[4].rows[0][5]=1;return {workbook};}}),/preserve input/);
});

test('incorrect authenticated source is rejected before any output mkdir',async()=>{
 const oldRead=fs.readFile,oldMkdir=fs.mkdir;let reads=0,mkdirs=0;
 fs.readFile=async filename=>{assert.equal(filename,bound.presentation.path);reads++;return Buffer.from('{}');};
 fs.mkdir=async()=>{mkdirs++;throw Error('Must not create output');};
 try{await assert.rejects(publish({execute:true}),/Consumed source differs/);assert.equal(reads,1);assert.equal(mkdirs,0);}
 finally{fs.readFile=oldRead;fs.mkdir=oldMkdir;}
});

test('final output inventory detects changed manifest and outside reference',async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'readable-independent-'));
 try{
  const names=['started.json','条件历史比较.xlsx','条件历史比较.xlsx.inspect.ndjson','export_manifest.json',...Array.from({length:6},(_,i)=>`preview_${i}.png`)];
  const hashes={};for(const name of names){const p=path.join(dir,name),b=Buffer.from([255,0,1]);await fs.writeFile(p,b);hashes[p]=createHash('sha256').update(b).digest('hex');}
  await verifyOutputInventory(dir,hashes,true);
  await assert.rejects(verifyOutputInventory(dir,{...hashes,[path.join(dir+'-sibling','extra')]:Object.values(hashes)[0]},true),/containment/);
  await fs.writeFile(path.join(dir,'export_manifest.json'),'changed');
  await assert.rejects(verifyOutputInventory(dir,hashes,true),/drift/);
 }finally{await fs.rm(dir,{recursive:true,force:true});}
});
