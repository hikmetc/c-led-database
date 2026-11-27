// End-to-end test of the manager's interface against a throwaway clone (see run.sh).
// Every step drives the real interface and then checks the repository itself.
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

// Playwright comes from the website's node_modules; run.sh starts this script from site/
const { chromium } = createRequire(path.join(process.cwd(), 'package.json'))('@playwright/test');
const mode = process.argv[2] ?? 'main';
const URL_ = process.env.MANAGER_TEST_URL;
const REPO = process.env.MANAGER_TEST_REPO;
const ORIGIN = process.env.MANAGER_TEST_ORIGIN;
const git = (...a) => execFileSync('git', a, { cwd: REPO, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
const head = () => git('rev-parse', 'HEAD');
const clean = () => git('diff', '--name-only', 'HEAD') === '' && git('ls-files', '--others', '--exclude-standard') === '';
let step = 0;
const ok = (cond, what) => {
	if (!cond) throw new Error(`FAILED: ${what}`);
	console.log(`  ok ${String(++step).padStart(2)}  ${what}`);
};
function csvRows(rel) {
	// a small RFC 4180 reader, enough to check the tables
	const text = fs.readFileSync(path.join(REPO, rel), 'utf8');
	const rows = [];
	let row = [], cell = '', q = false;
	for (let i = 0; i < text.length; i++) {
		const c = text[i];
		if (q) {
			if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c;
		} else if (c === '"') q = true;
		else if (c === ',') { row.push(cell); cell = ''; }
		else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
		else if (c !== '\r') cell += c;
	}
	if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
	return rows;
}
const rejected = () => (fs.existsSync(path.join(REPO, 'meta/rejected_rows.csv')) ? csvRows('meta/rejected_rows.csv').slice(1) : []);

const browser = await chromium.launch(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {});
const page = await browser.newPage({ viewport: { width: 1320, height: 860 } });
const errors = [];
const alerts = [];
page.on('pageerror', (e) => errors.push(e.message));
// a refused plan answers 400 on purpose; the browser logs that as a console error, which is expected
page.on('console', (m) => m.type() === 'error' && !/favicon|status of 400/.test(m.text()) && errors.push(m.text()));
page.on('dialog', (d) => { alerts.push(d.message()); d.accept(); });

const nav = async (name) => { await page.click(`button[data-view=${name}]`); await page.waitForSelector('#main h1'); };
/** Wait for the running operation to end; returns its title ("Done" / "Not done") and log. */
async function finish() {
	await page.waitForFunction(() => document.querySelector('#done') && !document.querySelector('#done').disabled, null, { timeout: 600000 });
	const title = await page.textContent('#sheet-body h2');
	const log = await page.textContent('#log');
	await page.click('#done');
	return { title, log };
}
/** The plan sheet is open: read it, then confirm or cancel. */
async function plan({ confirm = true } = {}) {
	try {
		await page.waitForSelector('#go', { timeout: 20000 });
	} catch {
		// say what the interface showed instead of a plan
		throw new Error(`no plan was shown. The sheet says: ${(await page.textContent('#sheet-body')).replace(/\s+/g, ' ').slice(0, 400)}`);
	}
	const text = await page.textContent('#sheet-body');
	if (!confirm) { await page.click('#sheet-body [data-close]'); return { text }; }
	await page.click('#go');
	return { text, ...(await finish()) };
}
const DB = () => page.evaluate(() => db);
const openTable = async (analyte, file) => { await nav('database'); await page.click(`[data-analyte="${analyte}"]`); await page.click(`[data-file="${file}"]`); await page.waitForSelector('table.grid'); };

await page.goto(URL_);
await page.waitForSelector('.places');

if (mode === 'rollback') {
	// the server was started so that every build fails: nothing may remain changed
	const db0 = await DB();
	const a = db0.find((x) => x.tables.length > 1);
	const t = a.tables[0];
	const before = head();
	const file = `${a.folder}/database/${t.file}`;
	const content = fs.readFileSync(path.join(REPO, file));
	await openTable(a.folder, t.file);
	await page.click('td.cell[data-row="1"][data-col="25"]'); await page.fill('#val', 'must be rolled back'); await page.click('#ok');
	await page.click('#save');
	let r = await plan();
	ok(r.title === 'Not done' && /Restored\. Nothing was changed/.test(r.log), 'a failed edit reports "Not done" and restores the files');
	ok(head() === before && clean() && fs.readFileSync(path.join(REPO, file)).equals(content), 'after the failed edit the repository is exactly as before');
	await openTable(a.folder, t.file);
	await page.click('#deltable');
	r = await plan();
	ok(r.title === 'Not done' && head() === before && clean() && fs.existsSync(path.join(REPO, file)), 'a failed table deletion is undone: file and registry are back');
	ok(errors.length === 0, `no JavaScript errors (${errors.join(' | ')})`);
	await browser.close();
	process.exit(0);
}

// ---------------------------------------------------------------- overview and archive
let s = await page.evaluate(() => S);
ok(s.local.rows === s.github.rows && s.unpublished.commits.length === 0, 'overview: this Mac and GitHub start with the same data');
ok((await page.textContent('#n-archive')) === '2', 'two archive runs are waiting to be imported');
await nav('archive');
const chips = await page.$$eval('.item', (els) => els.map((e) => e.textContent.replace(/\s+/g, ' ')));
ok(chips.some((c) => /bad header/.test(c) && /Cannot be imported/.test(c) && !/Import…/.test(c)), 'a run with the wrong columns is shown as not importable, without an Import button');
ok(chips.some((c) => /No extraction table/.test(c)), 'a run without an extraction table is shown as such');
await page.click('#reload'); await page.waitForSelector('.list');
ok(!(await page.textContent('#main')).includes('cannot read') && (await page.$$('[data-import]')).length === 2, 'Rescan reloads the archive list');

// ---------------------------------------------------------------- edit, delete, add in a large table (second page)
let db = await DB();
const big = db.flatMap((a) => a.tables.map((t) => ({ ...t, analyte: a.folder }))).sort((x, y) => y.rows - x.rows)[0];
const bigFile = `${big.analyte}/database/${big.file}`;
let rows0 = csvRows(bigFile);
const notes = rows0[0].indexOf('Notes');
await openTable(big.analyte, big.file);
await page.click('#next'); await page.waitForSelector('td.cell[data-row="150"]');
await page.click(`td.cell[data-row="150"][data-col="${notes}"]`); await page.fill('#val', 'edited by the manager test, "quoted", with a comma'); await page.click('#ok');
await page.check('[data-del="160"]');
await page.click('#add'); await page.check('#copy'); await page.fill(`#f${notes}`, 'row added by the manager test'); await page.click('#ok');
let h0 = head();
await page.click('#save');
let p = await plan({ confirm: false });
ok(/\.0150\b/.test(p.text) && /\.0160\b/.test(p.text) && /Add a row at the end/.test(p.text) && /renumbers/.test(p.text), 'the plan names the edited row, the deleted row, the added row, and warns about renumbering');
ok(head() === h0 && clean(), 'cancelling the plan changes nothing');
await page.click('#save');
p = await plan();
let rows1 = csvRows(bigFile);
ok(p.title === 'Done' && git('rev-list', '--count', `${h0}..HEAD`) === '1', 'confirming saves one local commit');
ok(rows1.length === rows0.length && rows1[150][notes] === 'edited by the manager test, "quoted", with a comma', 'the edited value is stored exactly, quotes and comma included');
ok(JSON.stringify(rows1[160]) === JSON.stringify(rows0[161]) && rows1[rows1.length - 1][notes] === 'row added by the manager test', 'row 160 is gone, the next row moved up, the new row is last');
ok(JSON.stringify(rows1.slice(0, 150)) === JSON.stringify(rows0.slice(0, 150)), 'every other row is untouched');
ok(clean(), 'the working tree is clean after the operation');

// ---------------------------------------------------------------- a foreign uncommitted change blocks operations
fs.appendFileSync(path.join(REPO, 'README.md'), '\nstray edit\n');
await openTable(big.analyte, big.file);
await page.click('#deltable'); await page.waitForSelector('#sheet-body');
ok(/uncommitted changes/.test(await page.textContent('#sheet-body')), 'an operation is refused while the repository holds changes the app did not make');
await page.click('#sheet-body [data-close]');
git('checkout', '--', 'README.md');

// ---------------------------------------------------------------- screening of the database, rejection
await nav('screening'); await page.waitForSelector('#rescan', { timeout: 180000 });
const sa = await page.evaluate(() => screenAll);
const target = sa.tables.find((t) => t.rejected >= 2);
ok(!!target, 'the database-wide screening lists tables with rows to reject');
const tFile = `${target.analyte}/database/${target.file}`;
let n0 = csvRows(tFile).length, rj0 = rejected().length;
await page.click(`[data-screen="${target.analyte}|${target.file}"]`); await page.waitForSelector('[data-auto]');
const reasons = await page.$$eval('.srow .why', (els) => els.map((e) => e.textContent));
ok(reasons.length >= 2 && reasons.every((r) => r.length > 20), 'each rejected row comes with a concrete reason');
await page.uncheck('[data-auto]'); // keep the first one anyway
await page.click('#ok');
p = await plan();
ok(p.title === 'Done' && csvRows(tFile).length === n0 - (target.rejected - 1), 'the unticked row is kept, the others are removed');
let rj = rejected();
ok(rj.length === rj0 + target.rejected - 1 && rj[rj.length - 1][4] === 'automatic' && rj[rj.length - 1][3].length > 20, 'rejected rows are archived with criterion, reason and "automatic"');

// manual rejection of ticked rows
const small = db.flatMap((a) => a.tables.map((t) => ({ ...t, analyte: a.folder }))).filter((t) => t.rows > 5 && t.file !== big.file && t.file !== target.file)[0];
await openTable(small.analyte, small.file);
await page.check('[data-del="2"]'); await page.click('#rejectsel');
await page.selectOption('#why', 'other'); await page.click('#ok');
ok(alerts.some((a) => /describe the reason/.test(a)), 'a manual rejection for "other" needs a note');
await page.fill('#note', 'manager test: wrong paper'); await page.click('#ok');
p = await plan();
rj = rejected();
ok(p.title === 'Done' && rj[rj.length - 1][4] === 'manual' && /manager test: wrong paper/.test(rj[rj.length - 1][3]), 'the manual rejection is archived with the note');

// ---------------------------------------------------------------- import: new cause for an existing analyte
await nav('archive');
await page.click('[data-import$="potassium__testcause/2026-11-27_1100__APS-0.4"]'); await page.waitForSelector('#an');
ok((await page.inputValue('#an')) === 'potassium_serum' && (await page.inputValue('#cause')) === '__new__' && (await page.inputValue('#key')) === 'test_cause', 'the import form recognises the analyte and proposes a new cause');
await page.fill('#concept', 'toxin'); await page.click('#ok');
await page.waitForSelector('#dois'); await page.click('#ok');
p = await plan();
ok(p.title === 'Done' && csvRows('potassium_serum/database/potassium_testcause_20261127-1100_APS0.4_extraction_table.csv').length === 6, 'the run is imported into the database folder with its 5 rows');
ok(/"test_cause": \("Test cause", "toxin"\)/.test(fs.readFileSync(path.join(REPO, 'scripts/registry.py'), 'utf8')), 'the new cause is registered');

// ---------------------------------------------------------------- import: new analyte, with screening
await nav('archive');
await page.click('[data-import$="magnesium__hemolysis/2026-11-27_1000__APS-4"]'); await page.waitForSelector('#an');
ok((await page.inputValue('#an')) === '__new__', 'an unknown analyte opens the new-analyte form');
await page.click('#ok');
ok(alerts.some((a) => /Please fill in/.test(a)), 'the form asks for the missing fields instead of guessing');
await page.fill('#folder', 'magnesium_serum'); await page.fill('#prefix', 'mg'); await page.fill('#system', 'Serum');
await page.fill('#kind', 'Substance concentration'); await page.fill('#unit', 'mmol/L');
await page.fill('#key', 'hemolysis'); await page.fill('#concept', 'hemolysis'); await page.fill('#cname', 'Hemolysis');
await page.click('#ok'); await page.waitForSelector('[data-auto]');
const sheet = await page.textContent('#sheet-body');
ok(/14 rows/.test(sheet) && /6<\/strong>|6 rejected/.test(await page.innerHTML('#sheet-body')), 'screening the run: 14 rows, 6 rejected');
for (const c of ['Criterion 1', 'Criterion 3', 'Criterion 8', 'Criterion 17', 'Criterion 21', 'Criterion 22']) ok(sheet.includes(c), `the screening reports ${c.toLowerCase()}`);
ok(/animal origin \("rat"\)/.test(sheet) && /defined in serum[^.]*the specimen is plasma/.test(sheet), 'the animal study and the wrong specimen are explained in words');
rj0 = rejected().length;
await page.click('#ok');
p = await plan();
ok(p.title === 'Done' && csvRows('magnesium_serum/database/magnesium_hemolysis_20261127-1000_APS4_extraction_table.csv').length === 9, 'the 8 rows that pass are in the database folder');
ok(rejected().length === rj0 + 6, 'the 6 rejected rows are archived');
db = await DB();
ok(db.length === 9 && db.some((a) => a.folder === 'magnesium_serum' && a.aps === 4), 'the new analyte is in the database with the APS of the run');
ok((await page.textContent('#n-archive')) === '', 'nothing is left to import');

// ---------------------------------------------------------------- analyte and cause management
await nav('database'); await page.click('[data-analyte="magnesium_serum"]');
await page.click('#edit-an'); await page.fill('#e-aps', '5'); await page.fill('#e-unit', 'mmol/L (mg/dL)'); await page.click('#ok');
p = await plan();
let reg = fs.readFileSync(path.join(REPO, 'scripts/registry.py'), 'utf8');
ok(p.title === 'Done' && /recomputed/.test(p.text) && /aps_percent=5\.0/.test(reg) && /unit="mmol\/L \(mg\/dL\)"/.test(reg), 'editing an analyte changes APS and unit in the registry, after a warning about the verdicts');
await page.waitForSelector('[data-cause="hemolysis"]'); await page.click('[data-cause="hemolysis"]');
await page.fill('#c-name', 'Hemolysis (free haemoglobin)'); await page.click('#ok');
p = await plan();
ok(p.title === 'Done' && /"hemolysis": \("Hemolysis \(free haemoglobin\)", "hemolysis"\)/.test(fs.readFileSync(path.join(REPO, 'scripts/registry.py'), 'utf8')), 'renaming a cause changes its name and keeps its id');

await openTable('potassium_serum', 'potassium_testcause_20261127-1100_APS0.4_extraction_table.csv');
await page.click('#deltable');
p = await plan();
reg = fs.readFileSync(path.join(REPO, 'scripts/registry.py'), 'utf8');
ok(p.title === 'Done' && !fs.existsSync(path.join(REPO, 'potassium_serum/database/potassium_testcause_20261127-1100_APS0.4_extraction_table.csv')) && !/test_cause/.test(reg), 'deleting a table removes the file, its registration and the cause nothing else uses');

await nav('database'); await page.click('[data-analyte="magnesium_serum"]'); await page.click('#del-an');
p = await plan();
ok(p.title === 'Done' && !fs.existsSync(path.join(REPO, 'magnesium_serum')) && !/magnesium_serum/.test(fs.readFileSync(path.join(REPO, 'scripts/registry.py'), 'utf8')), 'deleting an analyte removes its folder and all its registry entries');
ok((await DB()).length === 8 && clean(), 'the database is back to 8 analytes and the working tree is clean');

// ---------------------------------------------------------------- publish, pull, discard
const origin = (...a) => execFileSync('git', ['--git-dir', ORIGIN, ...a], { encoding: 'utf8' }).trim();
ok(origin('rev-parse', 'main') !== head(), 'before publishing, GitHub does not have the local changes');
await nav('changes');
ok((await page.$$('.list .item')).length > 0, 'the unpublished changes are listed');
await page.click('#pub');
p = await plan();
ok(p.title === 'Done' && origin('rev-parse', 'main') === head(), 'publishing sends every local change to GitHub');
s = await page.evaluate(() => S);
ok(s.unpublished.commits.length === 0 && s.local.rows === s.github.rows, 'after publishing the two places agree');

// someone else changes GitHub
const other = fs.mkdtempSync(path.join(path.dirname(REPO), 'other-'));
execFileSync('git', ['clone', '-q', ORIGIN, other]);
fs.appendFileSync(path.join(other, 'CHANGELOG.md'), '\nremote change\n');
execFileSync('git', ['-c', 'user.name=o', '-c', 'user.email=o@example.invalid', 'commit', '-qam', 'remote change'], { cwd: other });
execFileSync('git', ['push', '-q'], { cwd: other, stdio: 'ignore' });
await nav('overview'); await page.click('#reload'); await page.waitForSelector('#pull', { timeout: 60000 });
await page.click('#pull');
p = await plan();
ok(p.title === 'Done' && head() === origin('rev-parse', 'main'), '"Update this Mac" brings a change from GitHub');

// a local change, then discard
await openTable(small.analyte, small.file);
await page.click('td.cell[data-row="1"][data-col="25"]'); await page.fill('#val', 'to be discarded'); await page.click('#ok'); await page.click('#save');
p = await plan();
ok(p.title === 'Done' && head() !== origin('rev-parse', 'main'), 'a new local change is saved');
await nav('changes'); await page.click('#discard');
p = await plan();
ok(p.title === 'Done' && head() === origin('rev-parse', 'main') && clean(), 'discarding returns this Mac to exactly what is on GitHub');

// ---------------------------------------------------------------- research: start, follow, finish, stop
// (Claude Code is replaced by manager/tests/fake_claude.py, which writes a run into the test archive)
await nav('research');
ok((await page.$$('.checks .dot.warn')).length === 0, 'the Research section reports that everything it needs is in place');
await page.click('#start'); await page.waitForSelector('#sheet-body [data-close]');
ok(/Please give the analyte/.test(await page.textContent('#sheet-body')), 'a search cannot start without analyte, interferent and APS');
await page.click('#sheet-body [data-close]');
// the model list comes from Claude Code; which models work is learned by asking each one
let opts = await page.$$eval('#r-model option', (els) => els.map((e) => ({ v: e.value, t: e.textContent, d: e.disabled })));
ok(opts.some((o) => o.v === '') && opts.some((o) => o.v === 'claude-test-9-1') && opts.every((o) => !o.d), 'the model list shows the default and every specific model, all selectable before a check');
await page.fill('#r-an', 'Potassium');
await page.click('#check-models'); await page.click('#go-check');
await page.waitForFunction(() => /Availability checked/.test(document.querySelector('#model-box')?.textContent || ''), null, { timeout: 60000 });
opts = await page.$$eval('#r-model option', (els) => els.map((e) => ({ v: e.value, t: e.textContent, d: e.disabled })));
ok(opts.find((o) => o.v === 'claude-bad-1').d && /not available/.test(opts.find((o) => o.v === 'claude-bad-1').t) && /✓/.test(opts.find((o) => o.v === 'claude-test-9-1').t), 'after the check, a model that does not answer is marked and cannot be chosen; the others are marked as working');
ok((await page.inputValue('#r-an')) === 'Potassium', 'checking the models does not disturb what was typed in the form');
await page.fill('#r-in', 'research stub'); await page.fill('#r-aps', '%0.4'); await page.selectOption('#r-model', 'claude-test-9-1');
await page.click('#start');
p = await plan({ confirm: false });
ok(/uses your own Claude account/.test(p.text) && /fixed set of permissions/.test(p.text) && /not touched/.test(p.text), 'the plan explains the usage, the permissions and that the database is not touched');
ok((await page.inputValue('#r-an')) === 'Potassium', 'cancelling keeps what was typed');
await page.click('#start');
p = await plan();
ok(p.title === 'Done', 'confirming starts the session');
await page.waitForFunction(() => /Last session: finished/.test(document.querySelector('#main').textContent), null, { timeout: 60000 });
const live = await page.textContent('#live');
ok(/pubmed_search/.test(live) && /Tablo hazır/.test(live), 'the steps and messages of the session are shown');
ok(/Literature search: completed/.test(await page.textContent('.steps')) && /2 of 3/.test(await page.textContent('.steps')), 'the stages of the run are shown from the archive');
await page.click('#toarchive');
await page.waitForFunction(() => document.querySelector('#main h1')?.textContent === 'New from archive', null, { timeout: 60000 });
ok((await page.$$('[data-import*="potassium__research-stub"]')).length === 1, 'the finished run appears under "New from archive", ready to import');
ok(clean() && head() === origin('rev-parse', 'main'), 'the research changed nothing in the database');

await nav('research');
await page.fill('#r-an', 'Potassium'); await page.fill('#r-in', 'slow'); await page.fill('#r-aps', '%0.4');
await page.click('#start'); await plan();
await page.waitForSelector('#stop', { timeout: 30000 });
ok((await page.textContent('#n-research')) === '1' && !(await page.$('#start')), 'while a session runs, the section shows it and offers no second start');
await page.click('#stop');
p = await plan();
await page.waitForFunction(() => /Last session: stopped/.test(document.querySelector('#main').textContent), null, { timeout: 30000 });
ok(p.title === 'Done' && !!(await page.$('#start')), 'the session can be stopped, after which a new search can be started');

ok(errors.length === 0, `no JavaScript errors during the whole run (${errors.join(' | ')})`);
await browser.close();
