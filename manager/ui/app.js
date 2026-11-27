/* Interface of the database manager. Plain JavaScript, no dependencies, no network except
   the local back end (manager/server.py). Every change goes: plan -> confirm -> apply. */
'use strict';

const TOKEN = (location.hash.match(/t=([^&]+)/) || [])[1] || sessionStorage.getItem('t') || '';
if (TOKEN) sessionStorage.setItem('t', TOKEN);
history.replaceState(null, '', location.pathname);

const $ = (sel, el = document) => el.querySelector(sel);
const main = $('#main');
const sheetEl = $('#sheet');
const sheetBody = $('#sheet-body');
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const int = (n) => (n === null || n === undefined ? '–' : new Intl.NumberFormat('en-US').format(n));
const plural = (n, word) => `${int(n)} ${word}${n === 1 ? '' : 's'}`;
const NOT_REPORTED = 'not reported in the information source';

class Disconnected extends Error {}
async function api(path, body) {
	let res;
	try {
		res = await fetch(path, {
			method: body ? 'POST' : 'GET',
			headers: { 'X-Token': TOKEN, ...(body ? { 'Content-Type': 'application/json' } : {}) },
			body: body ? JSON.stringify(body) : undefined
		});
	} catch {
		// the request never reached the back end: it has stopped or is restarting
		throw new Disconnected('The manager\u2019s back end is not responding.');
	}
	const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
	if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
	return data;
}

let S = null; // state of the three places
let view = { name: 'overview' };
let archive = null;
let db = null;

/* ------------------------------------------------------------------ sheets (modal dialogs) */
function openSheet(html, wide = false) {
	sheetEl.classList.toggle('wide', wide);
	sheetBody.innerHTML = html;
	if (!sheetEl.open) sheetEl.showModal();
	const first = sheetBody.querySelector('[autofocus]') || sheetBody.querySelector('input, select, textarea, button');
	first?.focus();
}
function closeSheet() {
	if (sheetEl.open) sheetEl.close();
}
sheetEl.addEventListener('cancel', (e) => {
	if (sheetBody.dataset.locked === '1') e.preventDefault(); // a running operation cannot be dismissed
});
function alertSheet(title, message) {
	openSheet(`<h2>${esc(title)}</h2><p style="white-space:pre-wrap">${esc(message)}</p><div class="sheet-actions"><button class="btn primary" data-close>OK</button></div>`);
}
sheetBody.addEventListener('click', (e) => {
	if (e.target.closest('[data-close]')) closeSheet();
});

/** Describe the operation, wait for the user's decision, then carry it out and show progress. */
async function review(op, { danger = false, confirmLabel = 'Confirm', after } = {}) {
	let plan;
	try {
		plan = await api('/api/plan', op);
	} catch (e) {
		alertSheet('This cannot be done', e.message);
		return false;
	}
	openSheet(`
		<p class="caption" style="margin:0">Please review before anything is changed</p>
		<h2>${esc(plan.title)}</h2>
		<pre class="plan">${esc(plan.lines.join('\n'))}</pre>
		${plan.warnings.map((w) => `<div class="note">${esc(w)}</div>`).join('')}
		<div><h3 style="margin-bottom:6px">Where this takes effect</h3><ul class="where">${plan.where.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></div>
		<div class="sheet-actions">
			<button class="btn" data-close autofocus>Cancel</button>
			<button class="btn ${danger ? 'danger solid' : 'primary'}" id="go">${esc(confirmLabel)}</button>
		</div>`);
	return new Promise((resolve) => {
		const onClose = () => resolve(false);
		sheetEl.addEventListener('close', onClose, { once: true });
		$('#go').addEventListener('click', async () => {
			sheetEl.removeEventListener('close', onClose);
			const ok = await runJob(plan.token, plan.title);
			if (ok && after) after();
			resolve(ok);
		});
	});
}

async function runJob(token, title) {
	sheetBody.dataset.locked = '1';
	openSheet(`<h2><span class="spin"></span>${esc(title)}</h2><pre class="log" id="log">Starting…</pre><div class="sheet-actions"><button class="btn primary" id="done" disabled>Working…</button></div>`);
	let ok = false;
	try {
		await api('/api/apply', { token });
		for (;;) {
			await new Promise((r) => setTimeout(r, 900));
			const job = await api('/api/job');
			const el = $('#log');
			el.textContent = job.log.join('\n') || 'Working…';
			el.scrollTop = el.scrollHeight;
			if (job.status !== 'running') {
				ok = job.status === 'done';
				break;
			}
		}
	} catch (e) {
		$('#log').textContent += `\n\n${e.message}`;
	}
	await refresh(true); // the three places are re-read before the sheet can be closed
	sheetBody.dataset.locked = '';
	$('h2', sheetBody).innerHTML = esc(ok ? 'Done' : 'Not done');
	const btn = $('#done');
	btn.disabled = false;
	btn.textContent = 'Close';
	btn.addEventListener('click', closeSheet);
	return ok;
}

/* ------------------------------------------------------------------ state */
async function refresh(all = false) {
	try {
		S = await api(`/api/state${all ? '?fresh=1' : ''}`);
		if (all || !db) db = await api('/api/database');
		if (all || !archive) archive = await api('/api/archive');
	} catch (e) {
		const lost = e instanceof Disconnected;
		main.innerHTML = `<div class="empty"><strong>${lost ? 'The manager lost the connection to its back end.' : 'The manager cannot read the database.'}</strong><br>${
			lost ? 'It is restarted automatically; this view reloads in a moment. Your database is not affected.' : esc(e.message)
		}<br><br><button class="btn primary" id="retry">Try again</button></div>`;
		$('#retry').onclick = () => refresh(true);
		if (lost) setTimeout(() => !S || (document.querySelector('#retry') && refresh(true)), 4000);
		return;
	}
	const pending = archive.filter((r) => r.status === 'new' || r.status === 'update').length;
	$('#n-archive').textContent = pending || '';
	$('#n-changes').textContent = S.unpublished.commits.length || '';
	$('#publish').hidden = !S.unpublished.commits.length;
	$('#conn').textContent = S.online ? 'Connected to GitHub' : 'GitHub not reachable; showing the last known state';
	render();
}

let researchTimer = null;
function go(next) {
	clearTimeout(researchTimer);
	if (view.name === 'table' && draftSize() && next.name !== 'table') {
		if (!confirm('You have changes in this table that are not saved yet. Leave and drop them?')) return;
	}
	view = next;
	draft = newDraft();
	for (const b of document.querySelectorAll('#nav button')) b.classList.toggle('on', b.dataset.view === (view.root || view.name));
	render();
	main.focus();
}
$('#nav').addEventListener('click', (e) => {
	const b = e.target.closest('button[data-view]');
	if (b) go({ name: b.dataset.view });
});
$('#publish').addEventListener('click', publish);

function publish() {
	return review({ op: 'publish' }, { confirmLabel: 'Publish' });
}

/* ------------------------------------------------------------------ views */
function render() {
	if (!S) return;
	({ overview, archive: archiveView, database: databaseView, analyte: analyteView, table: tableView, changes: changesView, settings: settingsView, screening: screeningView, research: researchView })[view.name]();
}

function placeCard(where, d, extra) {
	return `<div class="card"><div class="where">${where}</div><div class="big">${int(d.rows)}</div>
		<p class="muted">evidence rows · ${int(d.analytes)} analytes${d.tables !== undefined ? ` · ${int(d.tables)} tables` : ''}</p>
		<p class="caption" style="margin-top:10px">${extra}</p></div>`;
}

function overview() {
	const u = S.unpublished.commits.length;
	const w = S.website;
	const run = w.last_run;
	const building = run && run.status !== 'completed';
	const failed = run && run.status === 'completed' && run.conclusion !== 'success';
	const siteBehind = w.reachable && w.rows !== S.github.rows;
	const pending = archive.filter((r) => r.status === 'new' || r.status === 'update');
	main.innerHTML = `
		<div class="head"><div><h1>Overview</h1><p class="muted">Where the database stands, in its three places.</p></div>
			<button class="btn" id="reload">Refresh</button></div>
		<div class="places">
			${placeCard('This Mac', S.local, S.local.head ? `Last change: ${esc(S.local.head.subject)}` : '')}
			${placeCard('GitHub', S.github, S.repo_url ? `<a href="${esc(S.repo_url)}" target="_blank">${esc(S.repo_url.replace('https://', ''))}</a>` : 'no GitHub remote')}
			${w.reachable ? placeCard('Website', w, `<a href="${esc(w.url)}" target="_blank">${esc(w.url.replace('https://', ''))}</a>`) : `<div class="card"><div class="where">Website</div><div class="big">–</div><p class="muted">not reachable</p></div>`}
		</div>
		<div class="link-row">
			<div class="sync ${u ? 'attn' : S.behind ? 'warn' : ''}">
				<span><span class="dot ${u ? 'attn' : S.behind ? 'warn' : ''}"></span>${
					u ? `${plural(u, 'change')} on this Mac ${u === 1 ? 'is' : 'are'} not on GitHub yet` : S.behind ? `GitHub has ${plural(S.behind, 'change')} that ${S.behind === 1 ? 'is' : 'are'} not on this Mac` : 'This Mac and GitHub hold the same data'
				}</span>
				${u ? '<button class="btn primary" id="pub">Publish…</button>' : S.behind ? '<button class="btn" id="pull">Update this Mac…</button>' : ''}
			</div>
			<div class="sync ${failed ? 'warn' : building || siteBehind ? 'attn' : ''}">
				<span><span class="dot ${failed ? 'warn' : building || siteBehind ? 'attn' : w.reachable ? '' : 'off'}"></span>${
					failed ? 'The last website build failed; the website shows the previous version' : building ? 'The website is being rebuilt from GitHub…' : !w.reachable ? 'The website could not be reached' : siteBehind ? 'The website does not show the latest GitHub data yet' : 'The website shows what is on GitHub'
				}</span>
				${run ? `<a class="btn" href="${esc(run.url)}" target="_blank">Details</a>` : ''}
			</div>
		</div>
		${S.uncommitted.length ? `<div class="note" style="margin-bottom:20px">There are ${S.uncommitted.length} changed files in the repository that this app did not make (for example ${esc(S.uncommitted[0])}). Commit or discard them before making changes here.</div>` : ''}
		<div class="section"><h2>New in the archive</h2>
			${pending.length ? `<div class="list">${pending.slice(0, 6).map(runItem).join('')}</div>${pending.length > 6 ? `<p class="caption" style="margin-top:8px">and ${pending.length - 6} more in “New from archive”.</p>` : ''}` : `<div class="empty">Every run of the archive that can be imported is already in the database.</div>`}
		</div>
		<div class="section"><h2>Not published yet</h2>
			${u ? `<div class="list">${S.unpublished.commits.map((c) => `<div class="item"><div class="grow"><div class="t">${esc(c.subject)}</div><div class="s mono">${esc(c.sha)} · ${esc((c.date || '').replace('T', ' ').slice(0, 16))}</div></div><span class="chip new">only on this Mac</span></div>`).join('')}</div>` : `<div class="empty">Nothing is waiting to be published.</div>`}
		</div>`;
	$('#reload').onclick = () => refresh(true);
	if ($('#pub')) $('#pub').onclick = publish;
	if ($('#pull')) $('#pull').onclick = () => review({ op: 'pull' }, { confirmLabel: 'Update this Mac' });
	bindRuns();
}

const RUN_CHIP = { new: ['new', 'Not in the database'], update: ['new', 'Differs from the database'], imported: ['ok', 'In the database'], rejected: ['', 'All rows rejected'], invalid: ['warn', 'Cannot be imported'], no_table: ['', 'No extraction table'] };
function runItem(r) {
	const [cls, label] = RUN_CHIP[r.status] || ['', r.status];
	const can = r.status === 'new' || r.status === 'update';
	return `<div class="item"><div class="grow">
			<div class="t">${esc(r.analyte || r.topic.split('__')[0])} · ${esc(r.interferent || r.topic.split('__')[1] || '')}</div>
			<div class="s">${r.rows !== undefined ? `${plural(r.rows, 'row')}${r.status === 'update' ? ` (database has ${int(r.local_rows)})` : ''} · ` : ''}${r.aps !== null && r.aps !== undefined ? `APS ${esc(r.aps)} % · ` : ''}${esc(r.run)}${r.versions > 1 ? ` · ${r.versions} versions, latest used` : ''}${r.left_out && r.status !== 'rejected' ? ` · ${plural(r.left_out, 'row')} left out by the criteria` : ''}${r.note ? ` · ${esc(r.note)}` : ''}</div>
		</div><span class="chip ${cls}">${label}</span>
		${can ? `<button class="btn primary" data-import="${esc(r.path)}">${r.status === 'update' ? 'Update…' : 'Import…'}</button>` : ''}</div>`;
}
function bindRuns() {
	for (const b of main.querySelectorAll('[data-import]')) b.onclick = () => importSheet(b.dataset.import);
}

function archiveView() {
	main.innerHTML = `<div class="head"><div><h1>New from archive</h1><p class="muted">${esc(S.archive)}</p></div><button class="btn" id="reload">Rescan</button></div>
		${!S.archive_exists ? `<div class="empty">The archive folder was not found. Set it in Settings.</div>` : archive.length ? `<div class="list">${archive.map(runItem).join('')}</div>` : `<div class="empty">No runs found in the archive folder.</div>`}`;
	$('#reload').onclick = () => refresh(true);
	bindRuns();
}

const STATUS_CHIP = { new: ['new', 'only on this Mac'], changed: ['new', 'changed on this Mac'], published: ['ok', 'published'] };
function databaseView() {
	main.innerHTML = `<div class="head"><div><h1>Database</h1><p class="muted">${int(S.local.rows)} evidence rows in ${int(S.local.tables)} tables on this Mac.</p></div></div>
		<div class="list">${db.map((a) => {
			const pend = a.tables.filter((t) => t.status !== 'published').length;
			return `<div class="item click" data-analyte="${esc(a.folder)}"><div class="grow"><div class="t">${esc(a.component)}</div><div class="s">${esc(a.system)} · ${esc(a.unit)} · APS ${esc(a.aps)} %</div></div>
				${pend ? `<span class="chip new">${plural(pend, 'table')} not published</span>` : ''}<span class="num muted">${plural(a.tables.length, 'table')} · ${plural(a.rows, 'row')}</span></div>`;
		}).join('')}</div>`;
	for (const el of main.querySelectorAll('[data-analyte]')) el.onclick = () => go({ name: 'analyte', root: 'database', analyte: el.dataset.analyte });
}

function analyteView() {
	const a = db.find((x) => x.folder === view.analyte);
	if (!a) return go({ name: 'database' });
	main.innerHTML = `<div class="crumbs"><button id="back">Database</button> ›</div>
		<div class="head"><div><h1>${esc(a.component)}</h1><p class="muted">${esc(a.system)} · ${esc(a.unit)} · APS ${esc(a.aps)} % · <span class="mono">${esc(a.folder)}</span></p></div>
			<div class="row-actions"><button class="btn" id="edit-an">Edit analyte…</button><button class="btn danger" id="del-an">Delete analyte…</button></div></div>
		<h2 style="margin-bottom:12px">Evidence tables</h2>
		<div class="list">${a.tables.map((t) => {
			const [cls, label] = STATUS_CHIP[t.status] || ['', t.status];
			return `<div class="item click" data-file="${esc(t.file)}"><div class="grow"><div class="t">${esc(t.interferent)}${t.multi ? ' <span class="muted" style="font-weight:400">and related causes</span>' : ''}</div><div class="s mono">${esc(t.file)}</div></div>
				<span class="chip ${cls}">${label}</span><span class="num muted">${plural(t.rows, 'row')}${t.github_rows !== null && t.github_rows !== undefined && t.github_rows !== t.rows ? ` (GitHub ${int(t.github_rows)})` : ''}</span></div>`;
		}).join('')}</div>
		<div class="section"><h2>Interference causes</h2><div class="list">${a.causes.map((c) => `<div class="item"><div class="grow"><div class="t">${esc(c.name)}</div><div class="s"><span class="mono">${esc(a.id)}.${esc(c.key)}</span> · concept ${esc(c.concept)}${c.tables ? '' : ' · no table of its own'}</div></div><button class="btn" data-cause="${esc(c.key)}">Rename…</button></div>`).join('')}</div></div>`;
	$('#back').onclick = () => go({ name: 'database' });
	for (const el of main.querySelectorAll('[data-file]')) el.onclick = () => openTable(a.folder, el.dataset.file);
	for (const el of main.querySelectorAll('[data-cause]')) el.onclick = () => renameCauseSheet(a, a.causes.find((c) => c.key === el.dataset.cause));
	$('#edit-an').onclick = () => editAnalyteSheet(a);
	$('#del-an').onclick = () => review({ op: 'delete_analyte', analyte: a.folder }, { danger: true, confirmLabel: 'Delete analyte', after: () => go({ name: 'database' }) });
}

function editAnalyteSheet(a) {
	const f = (id, label, value, hint = '') => `<div class="field"><label for="${id}">${label}</label><input id="${id}" value="${esc(value)}">${hint ? `<span class="caption">${hint}</span>` : ''}</div>`;
	openSheet(`<h2>Edit analyte</h2><p class="caption mono" style="margin:0">${esc(a.folder)} · id prefix ${esc(a.id)} (these cannot be changed: every row id depends on them)</p>
		<div class="two">${f('e-component', 'Component (name)', a.component)}${f('e-system', 'System / specimen', a.system)}
		${f('e-kind', 'Kind of property', a.kind_of_property)}${f('e-unit', 'Unit', a.unit)}
		${f('e-aps', 'APS, percent (allowable bias, relative)', a.aps)}${f('e-syn', 'Synonyms, separated by ;', a.synonyms)}</div>
		${f('e-note', 'APS note', a.aps_note)}
		<div class="sheet-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Review…</button></div>`);
	$('#ok').onclick = () => review({ op: 'edit_analyte', analyte: a.folder, component: $('#e-component').value, system: $('#e-system').value, kind_of_property: $('#e-kind').value, unit: $('#e-unit').value, aps_percent: $('#e-aps').value, synonyms: $('#e-syn').value, aps_note: $('#e-note').value }, { confirmLabel: 'Save on this Mac' });
}

function renameCauseSheet(a, c) {
	const concepts = [...new Set(db.flatMap((x) => x.causes.map((y) => y.concept)))].sort();
	openSheet(`<h2>Rename an interference cause</h2><p class="caption mono" style="margin:0">${esc(a.id)}.${esc(c.key)} · ${esc(a.component)}</p>
		<div class="field"><label for="c-name">Canonical name, in English</label><input id="c-name" value="${esc(c.name)}" autofocus></div>
		<div class="field"><label for="c-concept">Concept (links the cause across analytes)</label><input id="c-concept" list="c-list" value="${esc(c.concept)}"><datalist id="c-list">${concepts.map((x) => `<option value="${esc(x)}">`).join('')}</datalist></div>
		<p class="caption">The id stays the same. The wording used by each paper, kept in the rows, is not changed.</p>
		<div class="sheet-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Review…</button></div>`);
	$('#ok').onclick = () => review({ op: 'rename_cause', analyte: a.folder, key: c.key, name: $('#c-name').value, concept: $('#c-concept').value }, { confirmLabel: 'Save on this Mac' });
}

/* ------------------------------------------------------------------ inclusion screening */
/** Show what the rejection criteria say about a run or a table, let the user decide row by row,
    and hand the final list of rejected rows to `next`. Nothing is changed here. */
async function screenSheet(target, next, { checkDois = false, intro = '' } = {}) {
	openSheet('<h2><span class="spin"></span>Screening…</h2><p class="caption">Checking every row against the rejection criteria.</p>', true);
	let r;
	try {
		r = await api('/api/screen', { ...target, check_dois: checkDois });
	} catch (e) {
		return alertSheet('The screening could not run', e.message);
	}
	const sm = r.summary;
	const auto = r.rows.filter((x) => x.reject.length);
	const hints = r.rows.filter((x) => !x.reject.length && x.check.length);
	const manual = Object.entries(r.criteria).filter(([, c]) => !c.auto);
	const LIMIT = 250;
	const ctx = (x) => `${esc(x.preview.interferent)} · ${esc(x.preview.platform)} · ${x.preview.change === null ? 'no numeric change' : esc(x.preview.change) + ' %'} · ${esc(x.preview.citation)}`;
	const counts = Object.entries(sm.by_criterion).sort((a, b) => b[1] - a[1]);
	openSheet(`<p class="caption" style="margin:0">Inclusion screening · nothing is changed yet</p><h2>${esc(r.label)}</h2>
		${intro ? `<p class="caption">${esc(intro)}</p>` : ''}
		<p><strong>${plural(sm.rows, 'row')}</strong>: ${int(sm.rows - sm.rejected)} pass, <strong>${int(sm.rejected)}</strong> rejected by an automatic criterion, ${int(sm.to_check)} to look at by hand. APS used: ${esc(r.aps ?? 'not set')} %.</p>
		${counts.length ? `<dl class="crit">${counts.map(([code, n]) => `<dt>Criterion ${r.criteria[code].no}</dt><dd>${esc(r.criteria[code].title)}</dd><dd class="num"><strong>${int(n)}</strong></dd>`).join('')}</dl>` : ''}
		${sm.by_criterion.verdict_inconsistent && r.aps_note ? `<div class="note">About criterion 17 for this analyte: ${esc(r.aps_note)} A verdict based on an absolute difference can therefore be right although the relative change says otherwise. Untick such rows to keep them.</div>` : ''}
		${auto.length ? `<h3>Rejected automatically <span class="muted" style="font-weight:400">(untick a row to keep it anyway)</span></h3>
		<div class="srows">${auto.slice(0, LIMIT).map((x) => `<label class="srow"><input type="checkbox" data-auto="${x.row}" checked><div><div><strong>Row ${x.row}</strong> · ${x.reject.map((e) => `criterion ${e.no}`).join(', ')}</div>${x.reject.map((e) => `<div class="why">${esc(e.detail)}</div>`).join('')}<div class="ctx">${ctx(x)}</div></div></label>`).join('')}</div>
		${auto.length > LIMIT ? `<p class="caption">Showing the first ${LIMIT} of ${int(auto.length)}; the rest are rejected too.</p>` : ''}` : '<p class="caption">No row is rejected by an automatic criterion.</p>'}
		${hints.length ? `<h3>To look at by hand <span class="muted" style="font-weight:400">(kept unless you choose a reason)</span></h3>
		<div class="srows">${hints.slice(0, LIMIT).map((x) => `<div class="srow"><select data-manual="${x.row}" aria-label="Decision for row ${x.row}"><option value="">Keep</option>${manual.map(([code, c]) => `<option value="${code}">Reject: ${esc(c.title)}</option>`).join('')}</select><div><div><strong>Row ${x.row}</strong></div>${x.check.map((e) => `<div class="why">${esc(e.detail)}</div>`).join('')}<div class="ctx">${ctx(x)}</div></div></div>`).join('')}</div>
		${hints.length > LIMIT ? `<p class="caption">Showing the first ${LIMIT} of ${int(hints.length)}; the others are kept.</p>` : ''}` : ''}
		<label class="check"><input type="checkbox" id="dois" ${r.dois_checked ? 'checked disabled' : ''}> Also ask doi.org whether each DOI exists (sends only the DOIs)${r.dois_checked && r.dois_unreachable ? ` · ${r.dois_unreachable} could not be checked` : ''}</label>
		<div class="sheet-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Continue…</button></div>`, true);
	if (!r.dois_checked) $('#dois').onchange = () => screenSheet(target, next, { checkDois: true, intro });
	$('#ok').onclick = () => {
		const unticked = new Set([...sheetBody.querySelectorAll('[data-auto]')].filter((el) => !el.checked).map((el) => Number(el.dataset.auto)));
		const rejects = auto.filter((x) => !unticked.has(x.row)).map((x) => ({ row: x.row, criteria: x.reject.map((e) => `${e.no} ${e.code}`).join('; '), reason: x.reject.map((e) => e.detail).join(' | '), decided: 'automatic' }));
		for (const el of sheetBody.querySelectorAll('[data-manual]')) {
			if (!el.value) continue;
			const x = hints.find((h) => h.row === Number(el.dataset.manual));
			rejects.push({ row: x.row, criteria: `${r.criteria[el.value].no} ${el.value}`, reason: `${r.criteria[el.value].title}. ${x.check.map((e) => e.detail).join(' | ')}`, decided: 'manual' });
		}
		next(rejects, sm);
	};
}

let screenAll = null;
async function screeningView() {
	if (!screenAll) {
		main.innerHTML = `<div class="head"><div><h1>Screening</h1><p class="muted">Checking every table against the rejection criteria…</p></div></div><div class="empty"><span class="spin"></span>This reads the whole database and takes a few seconds.</div>`;
		try {
			screenAll = await api('/api/screen_all');
		} catch (e) {
			main.innerHTML = `<div class="empty">${esc(e.message)}</div>`;
			return;
		}
		if (view.name !== 'screening') return;
	}
	const t = screenAll.tables;
	const total = t.reduce((n, x) => n + x.rejected, 0);
	const by = {};
	for (const x of t) for (const [k, n] of Object.entries(x.by_criterion)) by[k] = (by[k] || 0) + n;
	main.innerHTML = `<div class="head"><div><h1>Screening</h1><p class="muted">The database on this Mac against the rejection criteria. Nothing is rejected until you review a table and confirm.</p></div><button class="btn" id="rescan">Screen again</button></div>
		<div class="card" style="margin-bottom:20px"><p><strong>${int(total)}</strong> rows in ${plural(t.filter((x) => x.rejected).length, 'table')} fail an automatic criterion.</p>
			<dl class="crit">${Object.entries(screenAll.criteria).sort((a, b) => a[1].no - b[1].no).map(([code, c]) => `<dt>Criterion ${c.no}</dt><dd>${esc(c.title)}${c.auto ? '' : ' <span class="muted">(decided by hand)</span>'}</dd><dd class="num">${c.auto ? `<strong>${int(by[code] || 0)}</strong>` : ''}</dd>`).join('')}</dl></div>
		${t.length ? `<div class="list">${t.map((x) => `<div class="item"><div class="grow"><div class="t">${esc(x.component)}</div><div class="s mono">${esc(x.file)}</div></div>
			${x.rejected ? `<span class="chip warn">${plural(x.rejected, 'row')} to reject</span>` : ''}${x.to_check ? `<span class="chip">${int(x.to_check)} to look at</span>` : ''}
			<button class="btn" data-screen="${esc(x.analyte)}|${esc(x.file)}">Review…</button></div>`).join('')}</div>` : `<div class="empty">Every row passes the automatic criteria.</div>`}`;
	$('#rescan').onclick = () => { screenAll = null; screeningView(); };
	for (const el of main.querySelectorAll('[data-screen]')) el.onclick = () => { const [analyte, file] = el.dataset.screen.split('|'); screenTable(analyte, file); };
}

function screenTable(analyte, file, after) {
	screenSheet({ kind: 'table', analyte, file }, (rejects) => {
		if (!rejects.length) return alertSheet('Nothing to reject', 'No row is marked for rejection, so the table stays as it is.');
		review({ op: 'reject_rows', analyte, file, rejects }, { danger: true, confirmLabel: 'Reject and remove', after: () => { screenAll = null; after ? after() : view.name === 'screening' && render(); } });
	});
}

/* ------------------------------------------------------------------ one evidence table */
let T = null; // the table on screen
let draft = newDraft();
function newDraft() {
	return { edits: new Map(), deletes: new Set(), adds: [] };
}
function draftSize() {
	return draft.edits.size + draft.deletes.size + draft.adds.length;
}
const PAGE = 100;

async function openTable(analyte, file) {
	try {
		T = await api(`/api/table?analyte=${encodeURIComponent(analyte)}&file=${encodeURIComponent(file)}`);
	} catch (e) {
		return alertSheet('The table cannot be opened', e.message);
	}
	go({ name: 'table', root: 'database', analyte, file, page: 0 });
}

function tableView() {
	const a = db.find((x) => x.folder === view.analyte);
	const meta = a?.tables.find((t) => t.file === view.file);
	const n = T.rows.length;
	const pages = Math.max(1, Math.ceil(n / PAGE));
	view.page = Math.min(view.page, pages - 1);
	const from = view.page * PAGE;
	const slice = T.rows.slice(from, from + PAGE);
	const cell = (i, c, v) => {
		const key = `${i}|${c}`;
		const edited = draft.edits.has(key);
		const val = edited ? draft.edits.get(key) : v;
		return `<td class="cell ${edited ? 'edited' : ''} ${val === NOT_REPORTED ? 'nr' : ''}" data-row="${i}" data-col="${c}" title="${esc(T.columns[c])}"><div>${esc(val)}</div></td>`;
	};
	main.innerHTML = `<div class="crumbs"><button id="b1">Database</button> › <button id="b2">${esc(a?.component || view.analyte)}</button> ›</div>
		<div class="head"><div><h1>${esc(meta?.interferent || view.file)}</h1><p class="muted mono">${esc(view.analyte)}/database/${esc(view.file)}</p></div>
			<div class="row-actions"><button class="btn" id="screen">Screen…</button><button class="btn" id="add">Add row…</button><button class="btn danger" id="deltable">Delete table…</button></div></div>
		<p class="caption">Click a value to change it. Tick rows to delete them. Nothing is saved until you review and confirm.</p>
		<div class="grid-wrap"><table class="grid"><thead><tr><th class="pin">Row</th>${T.columns.map((c) => `<th title="${esc(T.definitions[c] || '')}">${esc(c)}</th>`).join('')}</tr></thead>
		<tbody>${slice.map((r, k) => {
			const i = from + k + 1;
			const del = draft.deletes.has(i);
			return `<tr class="${del ? 'deleted' : ''}"><td class="pin"><label class="check"><input type="checkbox" data-del="${i}" ${del ? 'checked' : ''} aria-label="Delete row ${i}"><span class="mono" title="${esc(T.row_ids[i - 1])}">${String(i).padStart(4, '0')}</span></label></td>${r.map((v, c) => cell(i, c, v)).join('')}</tr>`;
		}).join('')}
		${view.page === pages - 1 ? draft.adds.map((r, k) => `<tr class="added"><td class="pin"><button class="btn" data-unadd="${k}">Remove</button> <span class="caption">new</span></td>${T.columns.map((c) => `<td><div>${esc(r[c] || '')}</div></td>`).join('')}</tr>`).join('') : ''}
		</tbody></table></div>
		<div class="bar"><span class="caption">${plural(n, 'row')}${pages > 1 ? ` · page ${view.page + 1} of ${pages} <button class="btn" id="prev" ${view.page ? '' : 'disabled'}>Previous</button> <button class="btn" id="next" ${view.page < pages - 1 ? '' : 'disabled'}>Next</button>` : ''}</span>
			<span class="row-actions"><span class="caption">${draftSize() ? `${draft.edits.size} changed · ${draft.deletes.size} to delete · ${draft.adds.length} to add` : 'No changes'}</span>
			<button class="btn" id="rejectsel" ${draft.deletes.size && !draft.edits.size && !draft.adds.length ? '' : 'disabled'} title="Remove the ticked rows and archive them with a reason">Reject ticked rows…</button>
			<button class="btn" id="drop" ${draftSize() ? '' : 'disabled'}>Drop changes</button><button class="btn primary" id="save" ${draftSize() ? '' : 'disabled'}>Review changes…</button></span></div>`;
	$('#b1').onclick = () => go({ name: 'database' });
	$('#b2').onclick = () => go({ name: 'analyte', root: 'database', analyte: view.analyte });
	if ($('#prev')) $('#prev').onclick = () => { view.page -= 1; render(); };
	if ($('#next')) $('#next').onclick = () => { view.page += 1; render(); };
	$('#drop').onclick = () => { draft = newDraft(); render(); };
	$('#add').onclick = addRowSheet;
	const reload = async () => { draft = newDraft(); T = await api(`/api/table?analyte=${encodeURIComponent(view.analyte)}&file=${encodeURIComponent(view.file)}`); render(); };
	$('#screen').onclick = () => (draftSize() ? alertSheet('Save or drop your changes first', 'The screening works on the table as it is saved.') : screenTable(view.analyte, view.file, reload));
	$('#rejectsel').onclick = () => rejectTickedSheet(reload);
	$('#deltable').onclick = () => review({ op: 'delete_table', analyte: view.analyte, file: view.file }, { danger: true, confirmLabel: 'Delete table', after: () => go({ name: 'analyte', root: 'database', analyte: view.analyte }) });
	$('#save').onclick = saveDraft;
	for (const el of main.querySelectorAll('td.cell')) el.onclick = () => editCell(Number(el.dataset.row), Number(el.dataset.col));
	for (const el of main.querySelectorAll('[data-del]')) el.onchange = () => { const i = Number(el.dataset.del); el.checked ? draft.deletes.add(i) : draft.deletes.delete(i); render(); };
	for (const el of main.querySelectorAll('[data-unadd]')) el.onclick = () => { draft.adds.splice(Number(el.dataset.unadd), 1); render(); };
}

function rejectTickedSheet(after) {
	const reasons = [['wrong_analyte', 4, 'The source did not measure this analyte'], ['wrong_document', 5, 'The cited file is not the article'], ['out_of_scope', 10, 'Out of scope (not analytical interference or pre-analytical error)'], ['other', 0, 'Other reason (describe below)']];
	const rows = [...draft.deletes].sort((a, b) => a - b);
	openSheet(`<h2>Reject ${plural(rows.length, 'row')}</h2><p class="caption">The rows are removed from the table and archived in full, with this reason, in meta/rejected_rows.csv. Plain deletion (Review changes) does not archive.</p>
		<div class="field"><label for="why">Reason</label><select id="why">${reasons.map(([code, , title]) => `<option value="${code}">${esc(title)}</option>`).join('')}</select></div>
		<div class="field"><label for="note">Note (what you found)</label><input id="note" placeholder="e.g. the paper reports chloride, not pH"></div>
		<div class="sheet-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Review…</button></div>`);
	$('#ok').onclick = () => {
		const [code, no, title] = reasons.find((x) => x[0] === $('#why').value);
		const note = $('#note').value.trim();
		if (code === 'other' && !note) return alert('Please describe the reason.');
		const rejects = rows.map((row) => ({ row, criteria: no ? `${no} ${code}` : 'other', reason: note ? `${title}. ${note}` : title, decided: 'manual' }));
		review({ op: 'reject_rows', analyte: view.analyte, file: view.file, rejects }, { danger: true, confirmLabel: 'Reject and remove', after });
	};
}

function editCell(i, c) {
	const key = `${i}|${c}`;
	const original = T.rows[i - 1][c];
	const current = draft.edits.has(key) ? draft.edits.get(key) : original;
	const col = T.columns[c];
	openSheet(`<p class="caption mono" style="margin:0">${esc(T.row_ids[i - 1])}</p><h2>${esc(col)}</h2>
		<p class="caption">${esc(T.definitions[col] || '')}</p>
		<div class="field"><label for="val">Value</label><textarea id="val" autofocus>${esc(current)}</textarea></div>
		<p class="caption">Stored value: “${esc(original.length > 200 ? original.slice(0, 200) + '…' : original)}”</p>
		<div class="sheet-actions"><button class="btn" id="nr">Set to “not reported”</button><span style="flex:1"></span><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Keep change</button></div>`);
	$('#nr').onclick = () => ($('#val').value = NOT_REPORTED);
	$('#ok').onclick = () => {
		const v = $('#val').value;
		v === original ? draft.edits.delete(key) : draft.edits.set(key, v);
		closeSheet();
		render();
	};
}

function addRowSheet() {
	const last = T.rows[T.rows.length - 1] || [];
	openSheet(`<h2>Add an evidence row</h2><p class="caption">The row is added at the end of the table, so no existing row id changes. Values the source does not state are written as “${NOT_REPORTED}”.</p>
		<label class="check"><input type="checkbox" id="copy"> Start from the values of the last row</label>
		<div id="fields" style="display:grid;gap:10px;max-height:46vh;overflow:auto;padding-right:6px">${T.columns.map((c, k) => `<div class="field"><label for="f${k}" title="${esc(T.definitions[c] || '')}">${esc(c)}</label><input id="f${k}" value="${esc(k === 0 ? last[0] || '' : NOT_REPORTED)}"></div>`).join('')}</div>
		<div class="sheet-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Add to changes</button></div>`);
	$('#copy').onchange = (e) => T.columns.forEach((c, k) => ($(`#f${k}`).value = e.target.checked ? last[k] || '' : k === 0 ? last[0] || '' : NOT_REPORTED));
	$('#ok').onclick = () => {
		const row = {};
		T.columns.forEach((c, k) => (row[c] = $(`#f${k}`).value));
		draft.adds.push(row);
		closeSheet();
		view.page = 1e9;
		render();
	};
}

async function saveDraft() {
	const edits = [...draft.edits].map(([key, value]) => {
		const [row, c] = key.split('|').map(Number);
		return { row, column: T.columns[c], value };
	});
	const { analyte, file } = view;
	const ok = await review({ op: 'change_table', analyte, file, edits, deletes: [...draft.deletes], adds: draft.adds }, { danger: draft.deletes.size > 0, confirmLabel: 'Save on this Mac' });
	if (ok) {
		draft = newDraft();
		try {
			T = await api(`/api/table?analyte=${encodeURIComponent(analyte)}&file=${encodeURIComponent(file)}`);
		} catch {
			return go({ name: 'analyte', root: 'database', analyte });
		}
		render();
	}
}

/* ------------------------------------------------------------------ importing a run */
async function importSheet(path) {
	let p;
	try {
		p = await api(`/api/run?path=${encodeURIComponent(path)}`);
	} catch (e) {
		return alertSheet('This run cannot be imported', e.message);
	}
	const NEW = '__new__';
	const draw = () => {
		const folder = $('#an')?.value ?? p.analyte_folder ?? NEW;
		const isNewAnalyte = folder === NEW;
		const causes = isNewAnalyte ? [] : p.causes[folder] || [];
		const chosen = $('#cause')?.value ?? (isNewAnalyte ? NEW : p.interferent_key || NEW);
		const cause = causes.some((c) => c.key === chosen) ? chosen : NEW;
		const others = !isNewAnalyte && cause !== NEW ? (p.tables_by_cause[folder]?.[cause] || []) : [];
		const keep = (id, fallback) => esc($(`#${id}`)?.value ?? fallback ?? '');
		openSheet(`<h2>Import from the archive</h2>
			<p class="caption mono" style="margin:0">${esc(p.table)} · ${plural(p.rows, 'row')}</p>
			<div class="field"><label for="an">Analyte (the run says “${esc(p.analyte_label)}”)</label><select id="an">
				${p.analytes.map((a) => `<option value="${esc(a.folder)}" ${a.folder === folder ? 'selected' : ''}>${esc(a.component)} · ${esc(a.system)} (APS ${esc(a.aps)} %)</option>`).join('')}
				<option value="${NEW}" ${isNewAnalyte ? 'selected' : ''}>New analyte…</option></select></div>
			${isNewAnalyte ? `<div class="two">
				<div class="field"><label for="folder">Folder name</label><input id="folder" placeholder="magnesium_serum" value="${keep('folder')}"></div>
				<div class="field"><label for="prefix">Short prefix for ids</label><input id="prefix" placeholder="mg" value="${keep('prefix')}"></div>
				<div class="field"><label for="component">Component</label><input id="component" value="${keep('component', p.analyte_label)}"></div>
				<div class="field"><label for="system">System / specimen</label><input id="system" placeholder="Serum" value="${keep('system')}"></div>
				<div class="field"><label for="kind">Kind of property</label><input id="kind" placeholder="Substance concentration" value="${keep('kind')}"></div>
				<div class="field"><label for="unit">Unit</label><input id="unit" placeholder="mmol/L" value="${keep('unit')}"></div>
				<div class="field"><label for="aps">APS, percent</label><input id="aps" value="${keep('aps', p.aps)}"></div>
				<div class="field"><label for="syn">Synonyms, separated by ;</label><input id="syn" value="${keep('syn')}"></div></div>` : ''}
			<div class="field"><label for="cause">Interference cause (the run says “${esc(p.interferent_label)}”)</label><select id="cause">
				${causes.map((c) => `<option value="${esc(c.key)}" ${c.key === cause ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}
				<option value="${NEW}" ${cause === NEW ? 'selected' : ''}>New cause…</option></select></div>
			${cause === NEW ? `<div class="two">
				<div class="field"><label for="key">Key</label><input id="key" value="${keep('key', p.new_key)}"></div>
				<div class="field"><label for="concept">Concept (links the cause across analytes)</label><input id="concept" list="concepts" value="${keep('concept', p.concept_guess)}"><datalist id="concepts">${p.concepts.map((c) => `<option value="${esc(c)}">`).join('')}</datalist></div></div>
				<div class="field"><label for="cname">Canonical name, in English</label><input id="cname" value="${keep('cname', p.new_name)}"></div>` : ''}
			${others.length ? `<div class="note">This cause already has ${plural(others.length, 'other table')}: ${esc(others.join(', '))}. If they hold the same studies, the evidence would be counted twice.</div>
				<label class="check"><input type="checkbox" id="dup" ${$('#dup')?.checked ? 'checked' : ''}> They hold different studies. Import this as an additional table.</label>` : ''}
			<div class="sheet-actions"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ok">Screen and review…</button></div>`);
		$('#an').onchange = draw;
		$('#cause').onchange = draw;
		$('#ok').onclick = () => {
			const v = (id) => $(`#${id}`)?.value.trim();
			const op = { op: 'import', path, allow_duplicate: !!$('#dup')?.checked };
			if (isNewAnalyte) Object.assign(op, { analyte_folder: v('folder'), prefix: v('prefix'), component: v('component'), system: v('system'), kind_of_property: v('kind'), unit: v('unit'), aps: v('aps'), synonyms: v('syn') });
			else op.analyte_folder = folder;
			if (cause === NEW) Object.assign(op, { interferent_key: v('key'), interferent_name: v('cname'), concept: v('concept') });
			else op.interferent_key = cause;
			const missing = Object.entries(op).filter(([k, x]) => k !== 'synonyms' && (x === '' || x === undefined)).map(([k]) => k.replace(/_/g, ' '));
			if (missing.length) return alert(`Please fill in: ${missing.join(', ')}`);
			const target = { kind: 'run', path, analyte_folder: op.analyte_folder, component: op.component, prefix: op.prefix, synonyms: op.synonyms, aps: op.aps };
			screenSheet(target, (rejects) => review({ ...op, rejects }, { confirmLabel: 'Import to this Mac' }), { intro: 'Rows that fail a rejection criterion are left out of the import and archived with their reasons. The rows that pass go into the database folder.' });
		};
	};
	draw();
}

/* ------------------------------------------------------------------ research (literature pipeline) */
let R = null; // readiness and the current or last session
const STAGES = [['screening', 'Literature search'], ['download', 'Full texts'], ['conversion', 'PDF to text'], ['extraction', 'Extraction'], ['report', 'Report']];

async function researchView(keepForm = false) {
	clearTimeout(researchTimer);
	const form = keepForm ? null : Object.fromEntries([...main.querySelectorAll('[data-f]')].map((el) => [el.dataset.f, el.value]));
	try {
		R = await api('/api/research');
	} catch (e) {
		if (view.name === 'research') main.innerHTML = `<div class="empty">${esc(e.message)}<br><br><button class="btn primary" id="retry">Try again</button></div>`;
		if ($('#retry')) $('#retry').onclick = () => researchView();
		return;
	}
	$('#n-research').textContent = R.session?.state === 'running' ? '1' : '';
	if (view.name !== 'research') return;
	const rd = R.ready;
	const se = R.session;
	const check = (ok, yes, no) => `<li><span class="dot ${ok ? '' : 'warn'}"></span>${ok ? yes : no}</li>`;
	const running = se?.state === 'running';
	const stageChip = (key, label) => {
		const run = se?.run;
		let st = run?.stages?.[key];
		if (key === 'download' && run?.total) st = `${run.downloaded ?? 0} of ${run.total}`;
		if (key === 'report' && /report ready/.test(run?.status || '')) st = 'completed';
		return `<span class="chip ${st === 'completed' ? 'ok' : st ? 'new' : ''}">${label}${st ? `: ${esc(st)}` : ''}</span>`;
	};
	const unfinished = (archive || []).filter((r) => r.run_id && r.status === 'no_table');
	const live = $('#live');
	const atEnd = live ? live.scrollTop + live.clientHeight >= live.scrollHeight - 30 : true;
	const title = running ? '<span class="spin"></span>Session running' : se?.state === 'done' ? 'Last session: finished' : se?.state === 'stopped' ? 'Last session: stopped' : 'Last session: ended without a result';
	const what = se ? (se.params.continue_run ? `Continuing ${esc(se.params.continue_run)}` : `${esc(se.params.analyte)} · ${esc(se.params.interferent)} · APS ${esc(se.params.aps)}`) : '';
	const models = [['', 'Default of your Claude Code settings'], ['opus', 'Opus'], ['sonnet', 'Sonnet'], ['haiku', 'Haiku']];
	const field = (id, key, label, placeholder = '', cls = '') => `<div class="field ${cls}"><label for="${id}">${label}</label><input id="${id}" data-f="${key}" placeholder="${esc(placeholder)}" value="${esc(form?.[key] || '')}"></div>`;
	main.innerHTML = `<div class="head"><div><h1>Research</h1><p class="muted">Search the literature, fetch the full texts and extract the evidence table into the archive, with your Claude pipeline skill.</p></div></div>
		<div class="card" style="margin-bottom:20px"><ul class="checks">
			${check(!!rd.claude, 'Claude Code is available', 'Claude Code was not found (open the Claude desktop app once)')}
			${check(rd.pubmed && rd.crossref, 'PubMed and Crossref search are set up', 'PubMed / Crossref search servers are not set up in the Claude desktop app')}
			${check(rd.archive_tool, 'The archive tool is in place', 'The archive tool was not found in the archive folder')}
			${check(rd.firefox_polling, 'Firefox is watching the download queue', rd.firefox_minutes_ago === null ? 'Firefox has not been seen: open it and sign in with university access' : `Firefox last answered ${esc(rd.firefox_minutes_ago)} min ago: open it and sign in with university access`)}
			${check(rd.converter_ready, 'The PDF to Markdown converter is ready', 'The PDF to Markdown converter is not ready')}
		</ul></div>
		${se ? `<div class="section" style="margin-top:0"><h2>${title}</h2>
			<p class="caption">${what} · model ${esc(se.model)} · started ${esc(se.started.replace('T', ' ').slice(0, 16))}${se.run ? ` · folder <span class="mono">${esc(se.run.folder)}</span>` : ''}</p>
			<div class="steps">${STAGES.map(([k, l]) => stageChip(k, l)).join('')}${se.run?.md_running ? '<span class="chip new">converting PDFs…</span>' : ''}</div>
			<pre class="live" id="live">${esc(se.lines.join('\n\n')) || 'Starting…'}</pre>
			<div class="row-actions" style="margin-top:12px">
				${running ? '<button class="btn danger" id="stop">Stop the session…</button>' : '<button class="btn" id="toarchive">Open “New from archive”</button>'}
				${se.result ? `<span class="caption">${esc(se.result.minutes)} min · ${esc(se.result.turns)} steps${se.result.cost_usd ? ` · about $${Number(se.result.cost_usd).toFixed(2)} of usage` : ''}</span>` : ''}
			</div></div>` : ''}
		${running ? '' : `<div class="section"><h2>New search</h2><div class="card"><div class="form-grid">
			${field('r-an', 'analyte', 'Analyte (English; also names the folder)', 'Carboxyhemoglobin')}
			${field('r-in', 'interferent', 'Interferent (English)', 'methylene blue')}
			${field('r-aps', 'aps', 'Analytical performance specification', '%1')}
			<div class="field"><label for="r-model">Model</label><select id="r-model" data-f="model">${models.map(([v, l]) => `<option value="${v}" ${form?.model === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
			${field('r-st', 'sample_type', 'Sample type (optional)', 'blood')}
			${field('r-dr', 'date_range', 'Date range (optional)', '2000-2026')}
			${field('r-pl', 'platforms', 'Platforms (optional)', '', 'full')}
			</div><div class="row-actions" style="margin-top:16px"><button class="btn primary" id="start">Review and start…</button><span class="caption">Nothing starts until you confirm.</span></div></div></div>
		${unfinished.length ? `<div class="section"><h2>Unfinished runs</h2><div class="list">${unfinished.map((r) => `<div class="item"><div class="grow"><div class="t">${esc(r.analyte || r.topic)} · ${esc(r.interferent || '')}</div><div class="s mono">${esc(r.run_id)}</div></div><span class="chip">no extraction table yet</span><button class="btn" data-continue="${esc(r.run_id)}">Continue…</button></div>`).join('')}</div></div>` : ''}`}`;
	if ($('#live') && atEnd) $('#live').scrollTop = $('#live').scrollHeight;
	if ($('#stop')) $('#stop').onclick = () => review({ op: 'research_stop' }, { danger: true, confirmLabel: 'Stop', after: () => researchView(true) });
	if ($('#toarchive')) $('#toarchive').onclick = async () => { archive = null; await refresh(true); go({ name: 'archive' }); };
	const startOp = (op) => review(op, { confirmLabel: 'Start', after: () => (view.name === 'research' ? researchView(true) : go({ name: 'research' })) });
	if ($('#start')) $('#start').onclick = () => startOp({ op: 'research', ...Object.fromEntries([...main.querySelectorAll('[data-f]')].map((el) => [el.dataset.f, el.value.trim()])) });
	for (const el of main.querySelectorAll('[data-continue]')) el.onclick = () => startOp({ op: 'research', continue_run: el.dataset.continue, model: $('#r-model')?.value || '' });
	// while a session runs, the view follows it; an open sheet is never disturbed
	if (running) researchTimer = setTimeout(function tick() { if (view.name !== 'research') return; if (sheetEl.open) researchTimer = setTimeout(tick, 4000); else researchView(); }, 4000);
}

/* ------------------------------------------------------------------ changes and settings */
function changesView() {
	const u = S.unpublished;
	main.innerHTML = `<div class="head"><div><h1>Unpublished changes</h1><p class="muted">Saved on this Mac, not yet on GitHub or the website.</p></div>
		<div class="row-actions"><button class="btn danger" id="discard" ${u.commits.length ? '' : 'disabled'}>Discard all…</button><button class="btn primary" id="pub" ${u.commits.length ? '' : 'disabled'}>Publish…</button></div></div>
		${u.commits.length ? `<div class="list">${u.commits.map((c) => `<div class="item"><div class="grow"><div class="t">${esc(c.subject)}</div><div class="s mono">${esc(c.sha)} · ${esc((c.date || '').replace('T', ' ').slice(0, 16))}</div></div></div>`).join('')}</div>
		<div class="section"><h2>Evidence tables affected</h2>${u.tables.length ? `<div class="list">${u.tables.map((t) => `<div class="item"><div class="grow"><div class="t mono">${esc(t.file)}</div><div class="s">${esc(t.analyte)}</div></div><span class="chip ${t.kind === 'deleted' ? 'warn' : 'new'}">${t.kind}</span><span class="num muted">this Mac ${int(t.local_rows)} · GitHub ${int(t.github_rows)}</span></div>`).join('')}</div>` : `<div class="empty">No evidence table differs; only other files changed.</div>`}</div>`
		: `<div class="empty">Nothing is waiting. This Mac and GitHub hold the same data.</div>`}`;
	$('#pub').onclick = publish;
	$('#discard').onclick = () => review({ op: 'discard' }, { danger: true, confirmLabel: 'Discard changes' });
}

function settingsView() {
	main.innerHTML = `<div class="head"><div><h1>Settings</h1></div></div>
		<div class="card" style="display:grid;gap:14px;max-width:720px">
			<div class="field"><label for="arch">Literature archive folder</label><input id="arch" value="${esc(S.archive)}"></div>
			<div class="row-actions"><button class="btn primary" id="savecfg">Save</button><span class="caption" id="cfgmsg"></span></div>
			<p class="caption" style="margin:0">Database on this Mac: <span class="mono">${esc(S.repo)}</span><br>The archive is only read. Full-text PDFs are never copied into the database.</p>
		</div>`;
	$('#savecfg').onclick = async () => {
		try {
			await api('/api/config', { archive: $('#arch').value });
			$('#cfgmsg').textContent = 'Saved.';
			archive = null;
			refresh(true);
		} catch (e) {
			$('#cfgmsg').textContent = e.message;
		}
	};
}

/* ------------------------------------------------------------------ self-test (Manager --selftest) */
window.__errors = [];
addEventListener('error', (e) => window.__errors.push(e.message));
addEventListener('unhandledrejection', (e) => window.__errors.push(String(e.reason?.message || e.reason)));
/** Opens every section, one analyte, one table and the screening of that table; changes nothing. */
window.__selftest = async () => {
	const wait = async (test, ms = 90000) => { const t = Date.now(); while (!test() && Date.now() - t < ms) await new Promise((r) => setTimeout(r, 200)); return test(); };
	const seen = [];
	await wait(() => S && db && archive);
	for (const name of ['overview', 'research', 'archive', 'database', 'changes', 'settings', 'screening']) {
		go({ name });
		const ok = await wait(() => $('h1', main) && (name !== 'screening' || !!screenAll) && (name !== 'research' || $('h1', main).textContent === 'Research'));
		seen.push(`${name}=${ok ? $('h1', main).textContent : 'FAILED'}`);
	}
	if (db?.length) {
		go({ name: 'analyte', root: 'database', analyte: db[0].folder });
		seen.push(`analyte=${$('h1', main)?.textContent}`);
		await openTable(db[0].folder, db[0].tables[0].file);
		seen.push(`table=${main.querySelectorAll('table.grid tbody tr').length} rows shown`);
		let shown = false;
		screenSheet({ kind: 'table', analyte: db[0].folder, file: db[0].tables[0].file }, () => {});
		shown = await wait(() => !!$('#ok', sheetBody) || /could not/.test(sheetBody.textContent), 30000);
		seen.push(`screen sheet=${shown ? 'shown' : 'FAILED'}`);
		closeSheet();
	}
	await refresh(true);
	seen.push(`rescan=${S ? 'ok' : 'FAILED'}`);
	go({ name: 'overview' });
	return JSON.stringify({ seen, errors: window.__errors, places: [S.local.rows, S.github.rows, S.website.rows] });
};

refresh(true);
setInterval(() => !sheetEl.open && view.name !== 'table' && view.name !== 'research' && refresh(false), 60000);
