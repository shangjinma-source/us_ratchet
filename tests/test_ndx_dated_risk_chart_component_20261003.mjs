import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {validateRiskTasks,prepareRiskTables} from '../scripts/ndx_dated_risk_chart_component_20261003.mjs';
const saved=JSON.parse(fs.readFileSync(new URL('../tmp/dated_workbook_qa_20261003/path-chart-fixture.json',import.meta.url),'utf8'));
const fixture=()=>structuredClone(saved),ids=t=>t.map(r=>r.numerical_task_id);
test('all 127 days six roles and source groups preserved, shared controls reused',()=>{
 const t=fixture(),before=structuredClone(t);validateRiskTasks(t,ids(t));const out=prepareRiskTables(t,ids(t),{maxRowsPerSheet:100,maxGroupsPerBlock:128,maxTotalRows:250000});
 assert.deepEqual(t,before);assert(out.pages.every(p=>p.length<=100));assert(out.indexPages.every(p=>p.length<=100));
 const coordinates=out.indexPages.flat();assert.equal(coordinates.length,3*127);assert(coordinates.every(r=>r.length===38));
 const first=coordinates[0],secondTask=coordinates[127];assert.notDeepEqual(first.slice(8,14),secondTask.slice(8,14));assert.deepEqual(first.slice(20,26),secondTask.slice(20,26));
 assert(out.pages.flat().some(r=>r[4]==='UNKNOWN（原null）'));assert(out.pages.flat().some(r=>r[6]==='{"numerator":"0","denominator":"1"}'));
 assert.equal(out.taskIds.at(-1),ids(t).at(-1));assert.equal(out.engineEvidence.length,3);
});
test('cash and missing remain separate; null denominator is never zero',()=>{
 const t=fixture(),out=prepareRiskTables(t,ids(t));const rows=out.pages.flat();
 assert(rows.some(r=>r[2]==='candidate_integer'&&r[16]==='AVAILABLE'&&r[10]==='null'&&r[13]===1));
 assert(rows.some(r=>r[2]==='candidate_integer'&&r[16]==='NOT_EXECUTED_NONPOSITIVE_TARGET'&&r[7]==='未定义/超出展示精度'));
 assert(rows.filter(r=>r[10]==='null').every(r=>r[9]==='未定义/超出展示精度'));
});
test('wrong risk source/date/groups/authority cannot pass',()=>{
 const changes=[t=>{t[0].risk_tracks.candidate_integer.source_reference.sha256='f'.repeat(64);},t=>{t[0].risk_tracks.candidate_integer.rows[0].session='2026-03-21';},t=>{t[0].original_target_chain_evidence.candidate.aggregation.rows[0].unknown=false;},t=>{t[0].risk_tracks.incumbent_integer.rows[0].cash_usd_preserved=12;},t=>{t[0].risk_chains_reaggregated=true;}];
 for(const change of changes){const t=fixture();change(t);assert.throws(()=>validateRiskTasks(t,ids(t)));}
});
test('explicit resource bounds block without truncation and changed group counts survive',()=>{
 const t=fixture();assert.throws(()=>prepareRiskTables(t,ids(t),{maxRowsPerSheet:100001}));assert.throws(()=>prepareRiskTables(t,ids(t),{maxTotalRows:1}));assert.throws(()=>prepareRiskTables(t,ids(t),{maxGroupsPerBlock:1}));
 const out=prepareRiskTables(t,ids(t));assert(out.maxGroups>=2);assert.equal(out.riskReaggregated,false);
});
