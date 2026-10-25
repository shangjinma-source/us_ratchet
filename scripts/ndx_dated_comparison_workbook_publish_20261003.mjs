/** One-time export of externally anchored display data; pending acceptance. */
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const source = fileURLToPath(import.meta.url);
const root = path.dirname(path.dirname(source));
export const bound = {
  presentation: { path: path.join(root, 'data/cache/research/dated_comparison_presentation_20261003_v1/presentation.json'), sha256: 'a586ab8ee02f6cc0b87bd0bddda9b38bb4cfcc5364873b40e6f77458afd3231c' },
  publication: { path: path.join(root, 'data/cache/research/dated_comparison_presentation_20261003_v1/publication.json'), sha256: '79120009b95bd74675112ddb120dd29b2cab4deb4f67748acbd0af03ba2397ef' },
  builder: { path: path.join(root, 'scripts/ndx_dated_comparison_workbook_20261003.mjs'), sha256: '8bbbc945191a9ca4166574f5fdb916e9aa09f48bb710f0ddba056fc1763714b1' },
};
const output = path.join(root, 'outputs/01a0cc4a-c717-7813-843e-86aca0d15714/dated_comparison_workbook_20261003_v1');
const runtime = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node';
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const loadedSha = digest(await fs.readFile(source));

export function validateReceipt(payload, publication, references) {
  assert.equal(publication.schema, 'DATED_COMPARISON_PRESENTATION_PUBLICATION_V1');
  assert.equal(publication.status, 'PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY');
  assert.deepEqual(publication.presentation_reference, references.presentation);
  assert.deepEqual(publication.source_hashes, payload.source_hashes);
  for (const object of [payload, publication]) for (const flag of ['formal_comparison_passed', 'future_independent_oos', 'promotion_allowed', 'point_in_time_verified', 'economics_recomputed', 'workbook_created']) assert.equal(object[flag], false, flag);
  for (const reference of Object.values(payload.input_references)) assert.equal(payload.source_hashes[reference.path], reference.sha256, 'Every input reference covered');
}

async function guard(sources) {
  for (const [file, sha256] of Object.entries(sources)) {
    assert.match(sha256, /^[a-f0-9]{64}$/);
    assert.equal(digest(await fs.readFile(file)), sha256, `Source drift: ${file}`);
  }
}

async function saveJson(file, value) {
  const bytes = Buffer.from(JSON.stringify(value, null, 2));
  const handle = await fs.open(file, 'wx');
  try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
  assert.deepEqual(await fs.readFile(file), bytes);
  return { path: file, sha256: digest(bytes) };
}

export async function publish({ execute = false } = {}) {
  assert.equal(execute, true, 'Explicit execution required');
  for (const reference of Object.values(bound)) assert(typeof reference.sha256 === 'string' && /^[a-f0-9]{64}$/.test(reference.sha256), 'Actual display anchors pending');
  const sources = { [source]: loadedSha };
  const bytes = {};
  for (const [role, reference] of Object.entries(bound)) {
    bytes[role] = await fs.readFile(reference.path);
    assert.equal(digest(bytes[role]), reference.sha256, `Consumed source differs: ${role}`);
    sources[reference.path] = reference.sha256;
  }
  await guard(sources);
  const payload = JSON.parse(bytes.presentation.toString('utf8'));
  const publication = JSON.parse(bytes.publication.toString('utf8'));
  validateReceipt(payload, publication, bound);
  for (const [file, sha256] of Object.entries(payload.source_hashes)) {
    assert(sources[file] === undefined || sources[file] === sha256, 'Source reference conflict');
    sources[file] = sha256;
  }
  await guard(sources);
  // Evaluate exactly the authenticated builder bytes; do not reuse a path cache.
  const builder = await import(`data:text/javascript;base64,${bytes.builder.toString('base64')}`);
  builder.validateDisplay(payload);
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.mkdir(output); // Exclusive directory: an earlier failure is never overwritten.
  try {
    await saveJson(path.join(output, 'started.json'), { status: 'STARTED_DIAGNOSTIC_EXPORT', input_references: bound, source_hashes: sources });
    const dependencyRequire = createRequire(path.join(runtime, 'package.json'));
    const { Workbook, SpreadsheetFile } = await import(pathToFileURL(dependencyRequire.resolve('@oai/artifact-tool')).href);
    const { workbook, renderRegions } = builder.buildWorkbook(Workbook, payload);
    for (const table of payload.display.tables) {
      const sheet = workbook.worksheets.getItem(table.name);
      assert.deepEqual(sheet.getRangeByIndexes(4, 0, table.rows.length, table.headers.length).values, table.rows.map(row => row.map(builder.literal)));
    }
    const previews = [];
    for (const [index, region] of renderRegions.entries()) {
      const preview = await workbook.render({ sheetName: region.sheetName, range: region.range, format: 'png', scale: 1 });
      const bytes = Buffer.from(await preview.arrayBuffer());
      const file = path.join(output, `preview_${index}.png`);
      await fs.writeFile(file, bytes, { flag: 'wx' });
      previews.push({ path: file, sha256: digest(bytes), sheet: region.sheetName, range: region.range });
    }
    await guard(sources);
    const workbookPath = path.join(output, '条件历史比较.xlsx');
    const file = await SpreadsheetFile.exportXlsx(workbook);
    await file.save(workbookPath);
    const workbookReference = { path: workbookPath, sha256: digest(await fs.readFile(workbookPath)) };
    await guard(sources);
    const manifestReference = await saveJson(path.join(output, 'export_manifest.json'), {
      schema: 'DATED_COMPARISON_WORKBOOK_EXPORT_V1', status: 'EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',
      workbook_reference: workbookReference, previews, input_references: bound, source_hashes: sources,
      runtime_bundle: '26.909.12148', in_memory_table_values_verified: true,
      exported_cell_values_independently_verified: false, visual_acceptance_passed: false,
      known_preview_limitation: 'Numeric-looking text may render rounded or without leading zeros; exported text requires independent verification',
      formal_comparison_passed: false, future_independent_oos: false, economics_recomputed: false,
    });
    await guard(sources);
    await guard({ [manifestReference.path]: manifestReference.sha256, [workbookReference.path]: workbookReference.sha256 });
    return manifestReference;
  } catch (error) {
    await saveJson(path.join(output, 'failure.json'), { status: 'FAILED_DO_NOT_CONSUME', error: String(error), retry_allowed: false });
    throw error;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === source) console.log(await publish({ execute: process.argv.includes('--execute') }));
