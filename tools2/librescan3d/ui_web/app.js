const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
async function api(ep, params = {}, body = null) {
  const q = new URLSearchParams({...params, t: window.TOKEN});
  const r = await fetch('/api/' + ep + '?' + q, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).error || m; } catch (e) {} throw new Error(m); }
  return r;
}
const getJ = async (ep, p) => (await api(ep, p)).json(), postJ = async (ep, b) => (await api(ep, {}, b)).json();
let S = {conf: {}, home: ''}, viewer = null, curJob = null, pollTimer = null, curDir = null;
const sep = () => (S.os === 'win32' ? '\\' : '/');
const base = p => p.split(/[\\/]/).filter(Boolean).pop() || p;
const last = {}; try { Object.assign(last, JSON.parse(localStorage.getItem('ls3d') || '{}')); } catch (e) {}
const remember = () => { try { localStorage.setItem('ls3d', JSON.stringify(last)); } catch (e) {} };

// ---------------------------------------------------------------- tabs
function showTab(n) { $$('.tab').forEach(e => e.classList.toggle('on', e.id === n)); $$('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === n));
  if (n === 'view') { ensureViewer(); loadProjects(); viewer && viewer.draw(); } if (n === 'track') fillTrackSel(); }
$$('#tabs button').forEach(b => b.onclick = () => showTab(b.dataset.tab));
$('#quit').onclick = async () => { if (!confirm('Stop LibreScanner3D? Running jobs will be stopped.')) return; try { await api('quit'); } catch (e) {} document.body.innerHTML = '<p style="padding:40px;font:16px system-ui">LibreScanner3D has stopped. You can close this tab.</p>'; };

// ---------------------------------------------------------------- folder / file picker
function pick(kind, start) {
  return new Promise(res => {
    const m = $('#modal'); m.hidden = false; let cur = null; $('#mo_title').textContent = kind === 'dir' ? 'Choose a folder' : 'Choose a file';
    $('#mo_ok').style.display = kind === 'dir' ? '' : 'none';
    const done = v => { m.hidden = true; res(v); };
    async function go(p) {
      try { const d = await getJ('browse', {path: p || ''}); cur = d; $('#mo_path').textContent = d.path + (d.frames ? '  (' + d.frames + ' frames)' : '');
        const L = $('#mo_list'); L.innerHTML = '';
        d.dirs.forEach(x => { const e = document.createElement('div'); e.innerHTML = '📁 ' + esc(x.name) + '<small>' + (x.frames ? x.frames + ' frames' : x.result ? 'result' : '') + '</small>'; e.onclick = () => go(d.path + sep() + x.name); L.appendChild(e); });
        if (kind === 'file') d.files.forEach(x => { const e = document.createElement('div'); e.innerHTML = '📄 ' + esc(x.name) + '<small>' + (x.size / 1024 | 0) + ' kB</small>'; e.onclick = () => done(d.path + sep() + x.name); L.appendChild(e); });
        if (!L.children.length) L.innerHTML = '<div class="hint">empty</div>';
      } catch (e) { $('#mo_path').textContent = 'Cannot open: ' + e.message; }
    }
    $('#mo_up').onclick = () => cur && cur.parent && go(cur.parent); $('#mo_ok').onclick = () => cur && done(cur.path); $('#mo_close').onclick = () => done(null);
    $('#mo_new').onclick = async () => { const n = prompt('Name of the new folder'); if (!n || !cur) return; try { await postJ('mkdir', {path: cur.path + sep() + n}); go(cur.path + sep() + n); } catch (e) { alert(e.message); } };
    go(start || last.dir || '');
  });
}
$$('[data-pick]').forEach(b => b.onclick = async () => { const t = $('#' + b.dataset.target); const p = await pick(b.dataset.pick, t.value && b.dataset.pick === 'dir' ? t.value : ''); if (p) { t.value = p; last.dir = p.replace(/[\\/][^\\/]*$/, ''); remember(); } });

// ---------------------------------------------------------------- jobs / drawer
const STAGES = [['run.py', 'Track'], ['mesh.py', 'Clean'], ['merge.py', 'Merge'], ['poisson.py', 'Mesh']];
function toggleDrawer(open) { $('#drawer').classList.toggle('closed', open === undefined ? !$('#drawer').classList.contains('closed') : !open); $('#d_toggle').textContent = $('#drawer').classList.contains('closed') ? 'Log ▴' : 'Log ▾'; }
$('#d_toggle').onclick = () => toggleDrawer();
async function startJob(kind, body) {
  try { const j = await postJ('run', {kind, ...body}); curJob = {id: j.id, from: 0, lines: [], kind, out: j.out}; $('#d_log').textContent = ''; toggleDrawer(true); poll(); }
  catch (e) { alert(e.message); }
}
async function poll() {
  clearTimeout(pollTimer); if (!curJob) return;
  try {
    const j = await getJ('job', {id: curJob.id, from: curJob.from}); curJob.from = j.n; curJob.lines.push(...j.lines);
    const log = $('#d_log'), atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 30; if (j.lines.length) { log.textContent += j.lines.join('\n') + '\n'; if (atEnd) log.scrollTop = log.scrollHeight; }
    $('#d_title').textContent = j.title; const b = $('#d_status'); b.textContent = j.status === 'running' ? 'running…' : j.status; b.className = 'badge ' + j.status;
    $('#d_stop').hidden = j.status !== 'running'; $('#d_open').hidden = !(j.status === 'done' && j.out); curJob.out = j.out;
    let cur = -1; curJob.lines.forEach(l => { if (l.startsWith('$ ')) STAGES.forEach((s, i) => { if (l.includes(s[0])) cur = i; }); });
    const st = $('#d_stages'); st.innerHTML = ''; if (j.kind === 'scan' && cur >= 0) STAGES.forEach((s, i) => { const e = document.createElement('span'); e.className = 'stg' + (j.status === 'done' ? ' done' : i < cur ? ' done' : i === cur ? ' on' : ''); e.textContent = s[1]; st.appendChild(e); });
    if (j.status === 'running') pollTimer = setTimeout(poll, 700); else if (j.status === 'done' && j.kind === 'scan') loadProjects();
  } catch (e) { pollTimer = setTimeout(poll, 2000); }
}
$('#d_stop').onclick = async () => { if (curJob) await getJ('stop', {id: curJob.id}); poll(); };
$('#d_open').onclick = async () => { showTab('view'); await loadProjects(); const o = curJob.out; const m = (window._projects || []).find(p => p.path === o || p.path.startsWith(o)); if (m) openProject(m); };

// ---------------------------------------------------------------- scan tab
const recs = [];
function drawRecs() { const d = $('#recs'); d.innerHTML = ''; recs.forEach((r, i) => { const e = document.createElement('div'); e.className = 'rec'; e.innerHTML = '<b>Pose ' + (i + 1) + '</b><span title="' + esc(r.path) + '">' + esc(r.path) + '</span><small class="hint">' + r.frames + ' frames</small>'; const x = document.createElement('button'); x.className = 'ghost'; x.textContent = '✕'; x.onclick = () => { recs.splice(i, 1); drawRecs(); }; e.appendChild(x); d.appendChild(e); }); if (!recs.length) d.innerHTML = '<p class="hint">None yet.</p>'; }
$('#addrec').onclick = async () => { const p = await pick('dir'); if (!p) return; try { const d = await getJ('browse', {path: p}); if (!d.frames) { alert('That folder has no frames (f_0001.png …). Choose the folder that contains them.'); return; } recs.push({path: d.path, frames: d.frames}); if (!$('#s_out').value) $('#s_out').value = (S.conf.work || S.home) + sep() + base(d.path) + '_result'; drawRecs(); } catch (e) { alert(e.message); } };
$('#s_run').onclick = () => { const m = $('#s_msg'); m.textContent = '';
  if (!recs.length) return m.textContent = 'Add at least one recording folder.'; if (!$('#s_calib').value) return m.textContent = 'Choose the calibration file.'; if (!$('#s_out').value) return m.textContent = 'Choose an output folder.';
  startJob('scan', {recs: recs.map(r => r.path), calib: $('#s_calib').value, out: $('#s_out').value, step: +$('#s_step').value, depth: +$('#s_depth').value, voxel: +$('#s_voxel').value, jobs: +$('#s_jobs').value, no_poisson: $('#s_nop').checked}); };

// ---------------------------------------------------------------- viewer tab
function ensureViewer() { if (viewer) return; try { viewer = new Viewer($('#gl')); if (!viewer.ok) $('#v_info').textContent = 'WebGL2 is not available in this browser.'; } catch (e) { $('#v_info').textContent = 'Viewer error: ' + e.message; } }
async function loadProjects() {
  try { const L = await getJ('projects', {}); window._projects = L; const d = $('#v_list'); d.innerHTML = '';
    L.forEach(p => { const e = document.createElement('div'); e.innerHTML = esc(p.name) + '<small>' + (p.files.includes('poisson_mesh.ply') ? 'mesh' : p.files.length ? 'cloud' : 'tracking') + '</small>'; e.onclick = () => { $$('#v_list div').forEach(x => x.classList.remove('sel')); e.classList.add('sel'); openProject(p); }; d.appendChild(e); });
    if (!L.length) d.innerHTML = '<div class="hint">No results in the work folder yet.</div>'; fillTrackSel(); } catch (e) { $('#v_list').innerHTML = '<div class="hint">' + esc(e.message) + '</div>'; }
}
async function openProject(p) { const f = ['poisson_mesh.ply', 'points_normals.ply', 'fused_dense.ply', 'fused.ply'].find(x => p.files.includes(x)); if (f) openFile(p.path + sep() + f); curDir = p.path; }
async function openFile(path) { ensureViewer(); if (!viewer || !viewer.ok) return; $('#v_info').textContent = 'Loading…';
  try { const buf = await (await api('cloud', {path, max: 600000})).arrayBuffer(); const i = viewer.setData(buf); $('#v_info').textContent = base(path) + ' · ' + i.points.toLocaleString() + ' points' + (i.faces ? ', ' + i.faces.toLocaleString() + ' triangles' : '') + ' · ' + i.size.map(v => v.toFixed(0)).join(' × ') + ' mm'; viewer.meshStyle = $('#v_style').value; viewer.draw(); }
  catch (e) { $('#v_info').textContent = 'Could not open: ' + e.message; } }
$('#v_open').onclick = async () => { const p = await pick('file'); if (p) openFile(p); };
$('#v_refresh').onclick = loadProjects; $('#v_reset').onclick = () => viewer && viewer.reset();
$('#v_mode').onchange = e => { viewer.mode = e.target.value; viewer.draw(); }; $('#v_style').onchange = e => { viewer.meshStyle = e.target.value; viewer.draw(); }; $('#v_ps').oninput = e => { viewer.pointSize = +e.target.value; viewer.draw(); };

// ---------------------------------------------------------------- tracking tab
let TK = null, srcDir = null, srcStep = 3;
function fillTrackSel() { const s = $('#t_sel'), old = s.value; s.innerHTML = ''; (window._projects || []).filter(p => p.tracking).forEach(p => { const o = document.createElement('option'); o.value = p.path; o.textContent = p.name; s.appendChild(o); }); if (old) s.value = old; }
function cssv(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function plot(cv, series, opts = {}) {
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = +cv.getAttribute('height'); cv.width = W * dpr; cv.height = H * dpr; const g = cv.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  const n = Math.max(...series.map(s => s.y.length), 1), L = 40, R = 8, T = 8, B = 20; let lo = opts.min ?? Infinity, hi = opts.max ?? -Infinity;
  if (opts.min === undefined || opts.max === undefined) series.forEach(s => s.y.forEach(v => { if (v >= 0 || !s.skipNeg) { lo = Math.min(lo, v); hi = Math.max(hi, v); } })); if (hi <= lo) hi = lo + 1;
  const X = i => L + (W - L - R) * i / Math.max(n - 1, 1), Y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  g.strokeStyle = cssv('--line'); g.fillStyle = cssv('--mut'); g.font = '11px system-ui'; g.lineWidth = 1;
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, y = Y(v); g.beginPath(); g.moveTo(L, y); g.lineTo(W - R, y); g.stroke(); g.fillText(v.toFixed(Math.abs(hi - lo) < 5 ? 2 : 0), 2, y + 4); }
  (opts.lost || []).forEach(i => { g.fillStyle = cssv('--bad') + '55'; g.fillRect(X(i) - 1.5, T, 3, H - T - B); });
  series.forEach(s => { g.strokeStyle = s.color; g.lineWidth = 1.6; g.beginPath(); let pen = false; s.y.forEach((v, i) => { if (s.skipNeg && v < 0) { pen = false; return; } pen ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v)); pen = true; }); g.stroke(); });
  g.fillStyle = cssv('--mut'); let lx = L; series.forEach(s => { g.fillStyle = s.color; g.fillRect(lx, H - 12, 10, 3); g.fillStyle = cssv('--mut'); g.fillText(s.name, lx + 14, H - 6); lx += 14 + g.measureText(s.name).width + 14; });
  cv._geo = {X, n, L, W, R};
}
async function loadTracking() {
  const d = $('#t_sel').value; if (!d) { $('#t_sum').textContent = 'No tracking results yet. Run a scan first.'; return; }
  try { TK = await getJ('tracking', {dir: d}); const ok = TK.ok || [], lost = ok.map((v, i) => v ? -1 : i).filter(i => i >= 0);
    const ang = TK.angles || []; const span = ang.length ? Math.max(...ang) - Math.min(...ang) : 0;
    $('#t_sum').textContent = (ang.length || ok.length) + ' frames · ' + lost.length + ' lost · turned ' + span.toFixed(0) + '°' + (TK.axis ? ' · axis ' + TK.axis.map(v => v.toFixed(3)).join(', ') : '');
    plot($('#c_ang'), [{name: 'angle', y: ang, color: cssv('--acc')}], {lost}); plot($('#c_q'), [{name: 'overlap', y: TK.overlap || [], color: cssv('--ok')}, {name: 'rms mm', y: (TK.rms || []).map(v => v), color: cssv('--warn'), skipNeg: true}], {lost, min: 0});
    srcDir = null; try { const sj = JSON.parse(await (await api('file', {path: d + sep() + 'source.json'})).text()); srcDir = sj.frames; srcStep = sj.step || 3; } catch (e) {}
    const n = srcDir ? (await getJ('frames', {dir: srcDir})).n : 0; const sl = $('#t_slider'); sl.max = Math.max(0, Math.max(n, 1) - 1); sl.value = 0; $('#t_img').style.display = n ? '' : 'none';
    $('#t_fq').textContent = n ? '' : 'Frames are not available for this result (re-run the scan once with this version to enable the preview).'; if (n) showFrame(0);
  } catch (e) { $('#t_sum').textContent = e.message; }
}
let frameTok = 0; async function showFrame(i) { const k = ++frameTok; $('#t_fi').textContent = '#' + i; const step = srcStep; $('#t_img').src = '/api/frame?' + new URLSearchParams({dir: srcDir, i, w: 800, t: window.TOKEN});
  const idx = Math.round(i / step); if (TK && TK.ok && idx < TK.ok.length) $('#t_fq').textContent = 'tracked frame ' + idx + ': ' + (TK.ok[idx] ? 'ok' : 'LOST') + ' · overlap ' + (TK.overlap[idx] ?? 0).toFixed(2) + ' · rms ' + (TK.rms[idx] ?? 0).toFixed(2) + ' mm · angle ' + (TK.angles ? (TK.angles[idx] ?? 0).toFixed(1) : '?') + '°'; }
$('#t_load').onclick = loadTracking; $('#t_slider').oninput = e => showFrame(+e.target.value);

// ---------------------------------------------------------------- tools
const need = (ids, m) => { for (const i of ids) if (!$('#' + i).value) { alert(m); return false; } return true; };
$('#m_run').onclick = () => need(['m_a', 'm_b', 'm_out'], 'Choose both scans and an output folder.') && startJob('merge', {a: $('#m_a').value, b: $('#m_b').value, out: $('#m_out').value, partial: $('#m_partial').checked, fpfh: $('#m_fpfh').checked});
$('#p_run').onclick = () => need(['p_dir'], 'Choose the folder.') && startJob('poisson', {dir: $('#p_dir').value, depth: +$('#p_depth').value, voxel: +$('#p_voxel').value, trim: +$('#p_trim').value, smooth: +$('#p_smooth').value});
$('#c_run').onclick = () => need(['c_a', 'c_b'], 'Choose both files.') && startJob('compare', {a: $('#c_a').value, b: $('#c_b').value});
$('#sp_run').onclick = () => need(['sp_dir'], 'Choose the result folder.') && startJob('speedtest', {dir: $('#sp_dir').value, calib: S.conf.calib});
$('#r_run').onclick = () => need(['r_out'], 'Choose the output folder.') && startJob('record', {out: $('#r_out').value});

// ---------------------------------------------------------------- settings
$('#c_save').onclick = async () => { try { const r = await postJ('config', {calib: $('#c_calib').value, work: $('#c_work').value, record_sh: $('#c_rec').value}); S.conf = r.conf; $('#s_calib').value = S.conf.calib || ''; $('#c_msg').textContent = 'Saved.'; loadProjects(); } catch (e) { $('#c_msg').textContent = e.message; } };
(async () => { try { S = await getJ('state'); const c = S.conf; $('#s_calib').value = c.calib || ''; $('#c_calib').value = c.calib || ''; $('#c_work').value = c.work || ''; $('#c_rec').value = c.record_sh || '';
  $('#c_info').textContent = 'System: ' + S.os + ' · Python: ' + S.python; drawRecs(); const js = await getJ('jobs'); if (js.length && js[0].status === 'running') { curJob = {id: js[0].id, from: 0, lines: []}; toggleDrawer(true); poll(); } } catch (e) { document.body.insertAdjacentHTML('afterbegin', '<p style="padding:20px;color:#c33">Cannot reach the program: ' + esc(e.message) + '</p>'); } })();
