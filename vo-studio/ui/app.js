/* VO Studio front-end. Talks to the FastAPI backend in server.py. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const ICONS = {
  render:'M5 3v18l15-9z', voice:'M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3zM5 10v1a7 7 0 0 0 14 0v-1M12 19v3',
  lab:'M9 2v6L4 18a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3L15 8V2M9 2h6M7 14h10',
  settings:'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-4l-.4 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6c.06-.3.1-.66.1-1z',
  assistant:'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  play:'M5 3v18l15-9z', upload:'M12 16V4m0 0L7 9m5-5 5 5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
  undo:'M3 7v6h6M3 13a9 9 0 1 0 3-7', lock:'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4',
  save:'M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8',
  send:'M22 2 11 13M22 2l-7 20-4-9-9-4z', chev:'M9 18l6-6-6-6',
  clip:'M21.4 11.05 12.25 20.2a6 6 0 0 1-8.49-8.49l9.2-9.19a4 4 0 0 1 5.65 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48',
  close:'M18 6 6 18M6 6l12 12',
  image:'M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M8.5 9.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2z',
  wave:'M3 12h2l2-7 3 16 3-11 2 5h6',
  file:'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6',
};
function drawIcons(root = document) {
  $$('i[data-i]', root).forEach(el => {
    const d = ICONS[el.dataset.i]; if (!d) return;
    el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
      width="100%" height="100%"><path d="${d}"/></svg>`;
  });
}

const api = async (path, body) => {
  const r = await fetch(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  } : undefined);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* ── navigation ─────────────────────────────────────────────────────── */
const ORDER = ['voice', 'lab', 'render', 'result'];
const done = new Set();

function go(view) {
  $$('.view').forEach(v => v.classList.toggle('is-active', v.dataset.view === view));
  // Settings and Assistant are in the same rail, so highlight every row the
  // same way — but only the four numbered ones carry progress.
  $$('.nav-item').forEach(n => n.classList.toggle('is-active', n.dataset.view === view));
  const idx = ORDER.indexOf(view);
  $$('.step').forEach(s => {
    const i = ORDER.indexOf(s.dataset.view);
    s.classList.toggle('is-done', i > -1 && idx > -1 && i < idx || done.has(s.dataset.view));
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
$$('.nav-item, [data-view]').forEach(b => {
  if (!b.dataset.view || b.tagName !== 'BUTTON') return;
  b.onclick = () => go(b.dataset.view);
});
$$('[data-go]').forEach(b => b.onclick = () => go(b.dataset.go));

/* ── hardware badge ─────────────────────────────────────────────────── */
api('/api/hardware').then(h => {
  $('#hw-text').textContent = h.label;
  $('#hw .dot').className = 'dot ' + (h.gpu ? 'dot-ok' : 'dot-warn');
}).catch(() => { $('#hw-text').textContent = 'backend unreachable'; });

/* ── voice reference ────────────────────────────────────────────────── */
const drop = $('#voice-drop'), fileInput = $('#voice-file');
drop.onclick = () => fileInput.click();
['dragenter', 'dragover'].forEach(e => drop.addEventListener(e, ev => {
  ev.preventDefault(); drop.classList.add('over');
}));
['dragleave', 'drop'].forEach(e => drop.addEventListener(e, ev => {
  ev.preventDefault(); drop.classList.remove('over');
}));
drop.addEventListener('drop', ev => ev.dataTransfer.files[0] && upload(ev.dataTransfer.files[0]));
fileInput.onchange = () => fileInput.files[0] && upload(fileInput.files[0]);

async function upload(file) {
  const fd = new FormData(); fd.append('file', file);
  const r = await fetch('/api/voice', { method: 'POST', body: fd });
  const j = await r.json();
  $('#voice-audio').src = '/api/voice/audio?t=' + Date.now();
  $('#voice-name').textContent = `${j.name} · ${j.duration.toFixed(1)}s · peak ${j.peak.toFixed(1)} dBFS`;
  $('#voice-set').hidden = false;
  done.add('voice');
  $$('.step').forEach(s => { if (s.dataset.view === 'voice') s.classList.add('is-done'); });
  if (j.warning) toast(j.warning); else toast('Voice loaded');
}

/* ── render ─────────────────────────────────────────────────────────── */
$('#script').addEventListener('input', async e => {
  const t = e.target.value;
  const words = (t.match(/\S+/g) || []).length;
  $('#script-stat').textContent =
    `${words} words · about ${Math.max(1, Math.ceil(t.length / 300))} chunks`;
});

$('#btn-render').onclick = async () => {
  const script = $('#script').value.trim();
  if (!script) return toast('Paste a script first');
  go('result');
  $('#render-log').textContent = '';
  $('#render-player').hidden = true;
  const pill = $('#render-pill'); pill.className = 'pill run'; pill.textContent = 'rendering';
  $('#btn-render').disabled = true;

  try {
    const res = await fetch('/api/render', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script, title: $('#title').value }),
    });
    const reader = res.body.getReader(), dec = new TextDecoder();
    // NOT `done` — that name is the completed-steps Set in this scope, and
    // shadowing it makes done.add('render') throw at the end of a good render.
    let finished = false;
    while (!finished) {
      const { value, done: d } = await reader.read(); finished = d;
      if (!value) continue;
      const log = $('#render-log');
      log.textContent += dec.decode(value, { stream: true });
      log.scrollTop = log.scrollHeight;
    }
    const info = await api('/api/render/result');
    if (info.path) {
      $('#render-audio').src = '/api/render/audio?t=' + Date.now();
      $('#render-path').textContent = info.path;
      $('#render-player').hidden = false;
      pill.className = info.warn ? 'pill warn' : 'pill ok';
      pill.textContent = info.warn ? 'needs an ear' : 'done';
      done.add('render');
    } else { pill.className = 'pill bad'; pill.textContent = 'failed'; }
  } catch (e) {
    $('#render-log').textContent += `\n${e}`;
    pill.className = 'pill bad'; pill.textContent = 'failed';
  }
  $('#btn-render').disabled = false;
};

/* ── voice lab ──────────────────────────────────────────────────────── */
const RANGES = { exaggeration: [.2, .9], cfg_weight: [.2, .9], temperature: [.4, 1.1], speed: [.85, 1.25] };
function paintParams(p) {
  $('#params').innerHTML = Object.entries(RANGES).map(([k, [lo, hi]]) => {
    const v = p[k], pct = ((v - lo) / (hi - lo)) * 100;
    const name = k === 'cfg_weight' ? 'reference adherence' : k;
    return `<div class="param">
      <span class="param-name">${name}</span>
      <span class="param-val">${k === 'speed' ? v.toFixed(2) + '×' : v.toFixed(2)}</span>
      <div class="param-bar"><div class="param-fill" style="width:${pct}%"></div></div>
    </div>`;
  }).join('');
}
async function loadProfile() {
  paintParams(await api('/api/profile?name=' + encodeURIComponent($('#prof').value)));
}
$('#prof').addEventListener('change', loadProfile);

$('#btn-sample').onclick = async () => {
  const b = $('#btn-sample'); b.disabled = true;
  $('#lab-player').innerHTML = '<div class="empty">rendering…</div>';
  try {
    const j = await api('/api/lab/sample', { name: $('#prof').value });
    if (j.error) { $('#lab-player').innerHTML = `<div class="empty">${j.error}</div>`; }
    else {
      $('#lab-player').innerHTML = `<audio controls src="/api/lab/audio?t=${Date.now()}"></audio>`;
      paintParams(j.profile);
    }
  } catch (e) { $('#lab-player').innerHTML = `<div class="empty">${e}</div>`; }
  b.disabled = false;
};

$$('.chip').forEach(c => c.onclick = () => {
  const i = $('#lab-fb');
  i.value = i.value ? `${i.value} and ${c.textContent}` : c.textContent;
  i.focus();
});

$('#lab-fb').addEventListener('keydown', async e => {
  if (e.key !== 'Enter' || !e.target.value.trim()) return;
  const fb = e.target.value; e.target.value = '';
  const j = await api('/api/lab/feedback', { name: $('#prof').value, feedback: fb });
  const log = $('#lab-log');
  if (log.classList.contains('empty')) { log.classList.remove('empty'); log.textContent = ''; }
  done.add('lab');
  log.insertAdjacentHTML('beforeend',
    `<div><span class="r-fb">› ${fb}</span>\n` +
    j.changes.map(c => `   <span class="r-ch">${c}</span>`).join('\n') + '\n</div>');
  log.scrollTop = log.scrollHeight;
  paintParams(j.profile);
  $('#btn-sample').click();
});

$('#btn-lock').onclick = async () => {
  const j = await api('/api/lab/lock', { name: $('#prof').value });
  toast(j.message);
};
$('#btn-revert').onclick = async () => {
  const j = await api('/api/lab/revert', { name: $('#prof').value });
  paintParams(j.profile); toast(j.message);
};

/* ── settings ───────────────────────────────────────────────────────── */
let SCHEMA = null;
function paintSettings(schema) {
  SCHEMA = schema;
  // Categories on the left, one panel showing. Every panel stays in the DOM so
  // saving still reads all of them — only one is displayed at a time.
  $('#settings-nav').innerHTML = schema.map((g, gi) =>
    `<button class="${gi === 0 ? 'is-active' : ''}" data-group="${g.key}">${g.title}</button>`).join('');
  $('#settings-groups').innerHTML = schema.map((g, gi) => `
    <div class="group${gi === 0 ? ' open' : ''}" data-group="${g.key}">
      <div class="group-head"><h3>${g.title}</h3></div>
      <div class="group-body">${g.items.map(it => settingRow(g.key, it)).join('')}</div>
    </div>`).join('');
  drawIcons($('#settings-groups'));
  $$('#settings-nav button').forEach(b => b.onclick = () => {
    $$('#settings-nav button').forEach(o => o.classList.toggle('is-active', o === b));
    $$('.group').forEach(g => g.classList.toggle('open', g.dataset.group === b.dataset.group));
  });
  $$('#settings-groups input[type=range]').forEach(r => r.oninput = () => {
    r.closest('.setting').querySelector('.setting-val').textContent =
      (+r.value).toFixed(r.dataset.dp || 2) + (r.dataset.unit || '');
  });
}
function settingRow(group, it) {
  const id = `set-${group}-${it.key}`;
  const control = it.type === 'bool'
    ? `<label class="switch"><input type="checkbox" id="${id}" data-group="${group}" data-key="${it.key}" ${it.value ? 'checked' : ''}><span></span></label>`
    : it.type === 'choice'
      ? `<select class="select" id="${id}" data-group="${group}" data-key="${it.key}">${it.options.map(o => `<option${o === it.value ? ' selected' : ''}>${o}</option>`).join('')}</select>`
      : '';
  const slider = it.type === 'number'
    ? `<input type="range" id="${id}" data-group="${group}" data-key="${it.key}" data-dp="${it.dp}" data-unit="${it.unit || ''}" min="${it.min}" max="${it.max}" step="${it.step}" value="${it.value}">`
    : '';
  const shown = it.type === 'number' ? (+it.value).toFixed(it.dp) + (it.unit || '') : '';
  return `<div class="setting">
    <div class="setting-top">
      <span class="setting-name">${it.name}</span>
      ${it.type === 'number' ? `<span class="setting-val">${shown}</span>` : control}
    </div>
    ${slider}
    ${it.why ? `<div class="setting-why">${it.why}</div>` : ''}
  </div>`;
}
api('/api/settings').then(paintSettings);

$('#btn-save').onclick = async () => {
  const values = {};
  $$('#settings-groups [data-key]').forEach(el => {
    values[`${el.dataset.group}.${el.dataset.key}`] =
      el.type === 'checkbox' ? el.checked : (el.tagName === 'SELECT' ? el.value : +el.value);
  });
  const j = await api('/api/settings', { values });
  toast(j.message);
};
$('#btn-reset').onclick = async () => { paintSettings(await api('/api/settings/reset', {})); toast('Reset — not saved yet'); };

/* ── assistant ──────────────────────────────────────────────────────── */
function paintAuth(a) {
  $('#auth-card').innerHTML = a.ok
    ? a.detail
    : `<b>Not ready.</b><br><span style="white-space:pre-wrap">${a.detail}</span>`;
  // The Sign in button only appears when signing in is actually the problem.
  // Offering it for a missing CLI would just fail differently.
  $('#auth-actions').hidden = a.ok;
  $('#btn-login').hidden = !a.can_login;
}
const refreshAuth = () => api('/api/auth').then(paintAuth).catch(() => {});
refreshAuth();
$('#btn-login').onclick = async () => {
  const j = await api('/api/auth/login', {});
  toast(j.message);
};
$('#btn-recheck').onclick = () => refreshAuth().then(() => toast('Checked'));
/* Attachments. Uploaded on drop rather than on send, so an unreadable file or a
   name clash surfaces while you are still typing — not after you hit Send. */
let ATTACHED = [];
const ICON_FOR = { image: 'image', audio: 'wave', file: 'file' };

function paintAttached() {
  const box = $('#attached');
  box.hidden = !ATTACHED.length;
  box.innerHTML = ATTACHED.map((a, i) => `
    <span class="att" title="${a.path}">
      <i data-i="${ICON_FOR[a.kind] || 'file'}"></i>
      <b>${a.name}</b>
      <span class="att-kind">${a.kind === 'audio' ? 'measured, not heard' : a.kind}</span>
      <button data-drop="${i}" aria-label="Remove"><i data-i="close"></i></button>
    </span>`).join('');
  drawIcons(box);
  $$('#attached [data-drop]').forEach(b => b.onclick = async () => {
    const [gone] = ATTACHED.splice(+b.dataset.drop, 1);
    paintAttached();
    api('/api/assistant/detach', { path: gone.path }).catch(() => {});
  });
}

async function attach(files) {
  for (const f of files) {
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await fetch('/api/assistant/attach', { method: 'POST', body: fd });
      if (!r.ok) throw new Error(await r.text());
      ATTACHED.push(await r.json());
      paintAttached();
    } catch (e) { toast(`${f.name} — ${e}`); }
  }
}

$('#btn-attach').onclick = () => $('#attach-file').click();
$('#attach-file').onchange = e => { attach(e.target.files); e.target.value = ''; };

const chatCard = $('#chat-card');
['dragenter', 'dragover'].forEach(ev => chatCard.addEventListener(ev, e => {
  e.preventDefault(); chatCard.classList.add('over');
}));
['dragleave', 'drop'].forEach(ev => chatCard.addEventListener(ev, e => {
  e.preventDefault(); chatCard.classList.remove('over');
}));
chatCard.addEventListener('drop', e => e.dataTransfer.files.length && attach(e.dataTransfer.files));

async function send() {
  const input = $('#chat-input'), text = input.value.trim();
  if (!text && !ATTACHED.length) return;
  input.value = '';
  const chat = $('#chat');
  if (chat.firstElementChild?.classList.contains('empty')) chat.innerHTML = '';
  const files = ATTACHED.map(a => a.path);
  const shown = ATTACHED.map(a => `<span class="att-sent">${a.name}</span>`).join('');
  ATTACHED = []; paintAttached();
  chat.insertAdjacentHTML('beforeend',
    `<div class="msg me">${shown ? `<div class="att-row">${shown}</div>` : ''}${text}</div>`);
  const bubble = document.createElement('div');
  bubble.className = 'msg ai'; bubble.textContent = '…';
  chat.append(bubble); chat.scrollTop = chat.scrollHeight;
  try {
    const j = await api('/api/assistant', { message: text, files, mode: $('#perm').value });
    bubble.textContent = j.reply || '(no output)';
  } catch (e) { bubble.textContent = String(e); }
  chat.scrollTop = chat.scrollHeight;
}
$('#btn-send').onclick = send;
$('#chat-input').addEventListener('keydown', e => e.key === 'Enter' && send());

drawIcons();
loadProfile().catch(() => {});
