/* VO Studio front-end. Talks to the FastAPI backend in server.py.

   IT IS CLAUDE, AND THE STUDIO IS ITS TOOLS

   There is no routing here. Every message goes to Claude, which holds the
   pipeline as MCP tools running in the app's own process — load a reference,
   render a take, move a dial, read a script, render it. Deciding what you
   meant was a keyword table's job for about a day, and a keyword table is a
   worse listener than the thing already in the box.

   This file draws the conversation and keeps the right-hand panel showing
   whatever Claude just changed. It does not decide anything. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const ICONS = {
  settings:'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-4l-.4 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.6h4l.4-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6c.06-.3.1-.66.1-1z',
  assistant:'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  clip:'M21.4 11.05 12.25 20.2a6 6 0 0 1-8.49-8.49l9.2-9.19a4 4 0 0 1 5.65 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48',
  close:'M18 6 6 18M6 6l12 12', up:'M12 19V5M5 12l7-7 7 7',
  image:'M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M8.5 9.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2z',
  wave:'M3 12h2l2-7 3 16 3-11 2 5h6',
  file:'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6',
  chev:'M9 18l6-6-6-6',
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

const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Text into HTML, keeping the line breaks a person typed.
const asText = s => esc(s).replace(/\n/g, '<br>');
const mmss = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* ── navigation ─────────────────────────────────────────────────────── */
function go(view) {
  $$('.view').forEach(v => v.classList.toggle('is-active', v.dataset.view === view));
  $$('.nav-item').forEach(n => n.classList.toggle('is-active', n.dataset.view === view));
}
$$('.nav-item').forEach(b => b.onclick = () => go(b.dataset.view));

/* ── the transcript ─────────────────────────────────────────────────── */
const chat = () => $('#chat');
function say(html, cls = 'ai') {
  const c = chat();
  if (c.firstElementChild?.classList.contains('empty')) c.innerHTML = '';
  const el = document.createElement('div');
  el.className = `msg ${cls}`;
  el.innerHTML = html;
  c.append(el);
  drawIcons(el);
  c.scrollTop = c.scrollHeight;
  return el;
}

/* A status bar, not a spinner. Nothing is measurable from INSIDE one
   generate() call, but the two things that make it slow are measurable from
   outside: the first run pulls ~1 GB of weights, and every take after that
   runs at roughly the pace of the last. The server owns both; this polls it. */
function startClock(el, label) {
  const t0 = performance.now();
  el.innerHTML = `<div class="prog inline">
      <div class="prog-track"><div class="prog-fill sweep"></div></div>
      <div class="prog-meta"><span class="what">${esc(label)}</span><span class="tick">0:00</span></div>
    </div>`;
  const fill = el.querySelector('.prog-fill');
  const what = el.querySelector('.what');
  const tick = el.querySelector('.tick');
  let polling = false;

  const id = setInterval(async () => {
    tick.textContent = mmss((performance.now() - t0) / 1000);
    if (polling) return;
    polling = true;
    try {
      const j = await api('/api/job');
      if (j.label) what.textContent = j.label;
      if (j.phase === 'loading' && j.mb_total) {
        fill.classList.remove('sweep');
        fill.style.width = Math.min(99, j.mb / j.mb_total * 100).toFixed(1) + '%';
      } else if (j.phase === 'generating' && j.expect) {
        // Held at 97 rather than allowed to sit at 100 while still working —
        // a bar that finishes before the thing does is worse than no bar.
        fill.classList.remove('sweep');
        fill.style.width = Math.min(97, j.elapsed / j.expect * 100).toFixed(1) + '%';
      } else {
        fill.classList.add('sweep');
      }
    } catch { /* the take is what matters; the bar is not worth an error */ }
    polling = false;
  }, 700);

  return { stop: () => { clearInterval(id); return (performance.now() - t0) / 1000; } };
}

/* ── voice reference ────────────────────────────────────────────────── */
let VOICE = { loaded: false };

function paintVoice(v) {
  VOICE = v;
  $('#ref-empty').hidden = !!v.loaded;
  $('#ref-set').hidden = !v.loaded;
  if (!v.loaded) return;
  $('#ref-audio').src = '/api/voice/audio?t=' + Date.now();
  $('#ref-name').textContent =
    `${v.name}${v.duration ? ` · ${v.duration}s` : ''}${v.peak != null ? ` · peak ${v.peak} dBFS` : ''}`;
}

// Everything attaches, audio included. Claude decides what a clip is FOR --
// a reference to clone, or a take to measure — which is the whole point of it
// holding the tools rather than this file guessing from a file extension.
async function takeFiles(files) {
  for (const f of files) await attach(f);
  $('#chat-input').focus();
}

/* ── attachments for Claude ─────────────────────────────────────────── */
let ATTACHED = [];
const fileURL = a => '/api/assistant/file?path=' + encodeURIComponent(a.path);

function attBody(a) {
  if (a.kind === 'image') return `<img src="${fileURL(a)}" alt="${esc(a.name)}">`;
  if (a.kind === 'audio') return `<audio controls preload="metadata" src="${fileURL(a)}"></audio>`;
  return `<span class="att-plain"><i data-i="file"></i><b>${esc(a.name)}</b></span>`;
}
function paintAttached() {
  const box = $('#attached');
  box.hidden = !ATTACHED.length;
  box.innerHTML = ATTACHED.map((a, i) => `
    <span class="att att-${a.kind}" title="${esc(a.path)}">
      ${attBody(a)}
      <span class="att-meta"><b>${esc(a.name)}</b>
        <span class="att-kind">${a.kind === 'audio' ? 'measured, not heard' : a.kind}</span></span>
      <button data-drop="${i}" aria-label="Remove"><i data-i="close"></i></button>
    </span>`).join('');
  drawIcons(box);
  $$('#attached [data-drop]').forEach(b => b.onclick = () => {
    const [gone] = ATTACHED.splice(+b.dataset.drop, 1);
    paintAttached();
    api('/api/assistant/detach', { path: gone.path }).catch(() => {});
  });
}
async function attach(f) {
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/api/assistant/attach', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error || `failed (${r.status})`);
    ATTACHED.push(j); paintAttached();
  } catch (e) { toast(`${f.name} — ${e.message || e}`); }
}

$('#btn-attach').onclick = () => $('#attach-file').click();
$('#attach-file').onchange = e => { takeFiles(e.target.files); e.target.value = ''; };

const card = $('#chat-card');
['dragenter', 'dragover'].forEach(ev => card.addEventListener(ev, e => {
  e.preventDefault(); card.classList.add('over');
}));
['dragleave', 'drop'].forEach(ev => card.addEventListener(ev, e => {
  e.preventDefault(); card.classList.remove('over');
}));
card.addEventListener('drop', e => e.dataTransfer.files.length && takeFiles(e.dataTransfer.files));

/* ── one turn ───────────────────────────────────────────────────────── */
const TOOL_SAYS = {
  voice_status: 'checking the voice',
  use_voice_reference: 'loading the reference',
  render_take: 'rendering a take',
  adjust_voice: 'adjusting the voice',
  set_voice_parameter: 'setting a dial',
  analyse_script: 'reading the script',
  render_script: 'rendering the script',
  read_render_log: 'reading the log',
};

async function send() {
  const input = $('#chat-input'), text = input.value.trim();
  if (!text && !ATTACHED.length) return;
  input.value = ''; input.style.height = 'auto';

  const files = ATTACHED.map(a => a.path);
  const shown = ATTACHED.map(a =>
    a.kind === 'image' ? `<img class="att-sent-img" src="${fileURL(a)}" alt="">`
    : a.kind === 'audio' ? `<audio class="att-sent-audio" controls preload="metadata" src="${fileURL(a)}"></audio>`
    : `<span class="att-sent">${esc(a.name)}</span>`).join('');
  ATTACHED = []; paintAttached();
  say((shown ? `<div class="att-row">${shown}</div>` : '') + asText(text), 'me');

  await stream(text, files);
}

async function stream(text, files = []) {
  const bubble = say('<span class="msg-wait">…</span>');
  let body = '', started = false;
  // A tool that renders gets its own progress line, because that is the one
  // that takes minutes and a still transcript reads as a hang.
  let live = null;

  const paint = () => {
    bubble.innerHTML = asText(body) || '<span class="msg-wait">…</span>';
    chat().scrollTop = chat().scrollHeight;
  };

  try {
    const res = await fetch('/api/assistant', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, files }),
    });
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (value) buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        let ev; try { ev = JSON.parse(line); } catch { continue; }

        if (ev.type === 'text') {
          if (live) { live.remove(); live = null; }
          started = true; body += ev.text; paint();
        } else if (ev.type === 'tool') {
          const label = TOOL_SAYS[ev.name?.split('__').pop()] || 'working';
          if (!started) bubble.innerHTML = '';
          live?.remove();
          live = document.createElement('div');
          bubble.append(live);
          // Only the slow ones get a bar; a status check does not need one.
          if (/render/.test(ev.name || '')) startClock(live, label + '…');
          else live.innerHTML = `<span class="msg-wait">${esc(label)}…</span>`;
          chat().scrollTop = chat().scrollHeight;
        } else if (ev.type === 'error') {
          body += (body ? '\n\n' : '') + ev.text; paint();
        }
      }
      if (done) break;
    }
  } catch (e) {
    body += `\n${e}`; paint();
  }
  if (live) live.remove();
  if (!body.trim()) bubble.innerHTML = '<span class="msg-wait">(no reply)</span>';

  // Whatever it just did is now the truth about the voice — repaint the panel
  // from the server rather than guessing from the conversation.
  refreshPanel();
}

function refreshPanel() {
  api('/api/voice/status').then(paintVoice).catch(() => {});
  loadProfile();
  api('/api/lab/latest').then(j => {
    if (j.file) $('#last-take').innerHTML =
      `<audio controls src="/api/lab/audio?name=${encodeURIComponent(j.name)}&file=${encodeURIComponent(j.file)}"></audio>`;
  }).catch(() => {});
}

/* ── takes ──────────────────────────────────────────────────────────── */
async function renderTake(into, text) {
  if (!VOICE.loaded) { say('<span class="msg-bad">No voice loaded — drop an audio clip in first.</span>'); return; }
  const holder = into || say('');
  const slot = document.createElement('div');
  holder.append(slot);
  const clock = startClock(slot, 'starting…');
  $('#btn-take').disabled = true;
  try {
    const body = { name: $('#prof').value };
    if (text) body.text = text;
    const j = await api('/api/lab/sample', body);
    const took = clock.stop();
    if (j.error) { slot.innerHTML = `<span class="msg-bad">${esc(j.error)}</span>`; }
    else {
      paintParams(j.profile);
      slot.innerHTML =
        (j.note ? `<div class="msg-bad">${esc(j.note)}</div>` : '') +
        `<audio controls src="/api/lab/audio?name=${encodeURIComponent($('#prof').value)}` +
        `&file=${encodeURIComponent(j.audio || '')}"></audio>` +
        `<div class="took">${(j.seconds ?? took).toFixed(1)}s on the GPU</div>`;
    }
  } catch (e) { clock.stop(); slot.innerHTML = `<span class="msg-bad">${esc(e)}</span>`; }
  $('#btn-take').disabled = false;
  chat().scrollTop = chat().scrollHeight;
}
$('#btn-take').onclick = () => renderTake();

/* ── voice profile panel ────────────────────────────────────────────── */
const RANGES = { exaggeration: [.2, .9], cfg_weight: [.2, .9], temperature: [.4, 1.1], speed: [.85, 1.25] };
function paintParams(p) {
  $('#params').innerHTML = Object.entries(RANGES).map(([k, [lo, hi]]) => {
    const v = p[k], name = k === 'cfg_weight' ? 'reference adherence' : k;
    return `<div class="param">
      <span class="param-name">${name}</span>
      <span class="param-val" id="pv-${k}">${k === 'speed' ? v.toFixed(2) + '×' : v.toFixed(2)}</span>
      <input type="range" class="param-range" data-key="${k}"
             min="${lo}" max="${hi}" step="0.01" value="${v}">
    </div>`;
  }).join('');
  $$('.param-range').forEach(r => {
    const out = $(`#pv-${r.dataset.key}`);
    r.oninput = () => {
      out.textContent = (+r.value).toFixed(2) + (r.dataset.key === 'speed' ? '×' : '');
    };
    // Saved on release, not per pixel — dragging fires input dozens of times.
    r.onchange = async () => {
      await api('/api/lab/params', {
        name: $('#prof').value, values: { [r.dataset.key]: +r.value },
      }).catch(() => null);
      say(`<div class="chg"><span>${r.dataset.key} set to ${(+r.value).toFixed(2)}</span></div>` +
          `Render a take to hear it.`);
    };
  });
}
const loadProfile = () => api('/api/profile?name=' + encodeURIComponent($('#prof').value))
  .then(paintParams).catch(() => {});
$('#prof').addEventListener('change', loadProfile);

$('#btn-lock').onclick = async () => {
  const j = await api('/api/lab/lock', { name: $('#prof').value });
  say(`<b>Saved.</b> ${esc(j.message)}`); toast(j.message);
};
$('#btn-revert').onclick = async () => {
  const j = await api('/api/lab/revert', { name: $('#prof').value });
  paintParams(j.profile);
  say(`<b>Reverted.</b> ${esc(j.message)} Render a take to hear it.`);
};

/* ── Claude ─────────────────────────────────────────────────────────── */
async function askClaude(text, files = []) {
  const bubble = say('<span class="msg-wait">…</span>');
  try {
    const j = await api('/api/assistant', { message: text, files });
    bubble.innerHTML = asText(j.reply || '(no output)');
  } catch (e) { bubble.innerHTML = `<span class="msg-bad">${esc(e)}</span>`; }
  chat().scrollTop = chat().scrollHeight;
}

function paintAuth(a) {
  $('#auth-card').innerHTML = a.ok ? esc(a.detail)
    : `<b>Not ready.</b><br><span style="white-space:pre-wrap">${esc(a.detail)}</span>`;
  $('#auth-actions').hidden = a.ok;
  $('#btn-login').hidden = !a.can_login;
}
const refreshAuth = () => api('/api/auth').then(paintAuth).catch(() => {});
$('#btn-login').onclick = async () => toast((await api('/api/auth/login', {})).message);
$('#btn-recheck').onclick = () => refreshAuth().then(() => toast('Checked'));

api('/api/assistant/prefs').then(p => {
  $('#model-pick').innerHTML = p.models.map(m =>
    `<option value="${m.id}"${m.id === p.model ? ' selected' : ''} title="${esc(m.note)}">${esc(m.label)}</option>`).join('');
  $('#confirm-calls').checked = p.confirm_calls;
}).catch(() => {});
const savePrefs = body => api('/api/assistant/prefs', body).catch(() => {});
$('#model-pick').onchange = e => {
  savePrefs({ model: e.target.value });
  toast(`Answering with ${e.target.selectedOptions[0].textContent}`);
};
$('#confirm-calls').onchange = e => {
  savePrefs({ confirm_calls: e.target.checked });
  toast(e.target.checked ? 'Every edit will ask first'
                         : 'It will edit without asking — projects and voices stay off limits');
};

/* ── settings ───────────────────────────────────────────────────────── */
function paintSettings(schema) {
  $('#settings-nav').innerHTML = schema.map((g, gi) =>
    `<button class="${gi === 0 ? 'is-active' : ''}" data-group="${g.key}">${esc(g.title)}</button>`).join('');
  $('#settings-groups').innerHTML = schema.map((g, gi) => `
    <div class="group${gi === 0 ? ' open' : ''}" data-group="${g.key}">
      <div class="group-head"><h3>${esc(g.title)}</h3></div>
      <div class="group-body">${g.items.map(it => settingRow(g.key, it)).join('')}</div>
    </div>`).join('');
  $$('#settings-nav button').forEach(b => b.onclick = () => {
    $$('#settings-nav button').forEach(o => o.classList.toggle('is-active', o === b));
    $$('.group').forEach(g => g.classList.toggle('open', g.dataset.group === b.dataset.group));
  });
  // The slider and the box are two views of one value. Dragging to 0.040 with
  // a 0.005 step is a fight you should not have to have — type it instead.
  $$('#settings-groups input[type=range]').forEach(r => {
    const box = r.closest('.setting').querySelector('.setting-num');
    r.oninput = () => { box.value = (+r.value).toFixed(+r.dataset.dp || 2); };
    box.oninput = () => { if (box.value !== '') r.value = box.value; };
    box.onchange = () => {
      // Clamp on commit, not per keystroke — clamping mid-type makes "0.04"
      // unreachable because "0.0" gets snapped to the minimum first.
      const v = Math.min(+r.max, Math.max(+r.min, +box.value || +r.min));
      r.value = v; box.value = v.toFixed(+r.dataset.dp || 2);
    };
  });
}
function settingRow(group, it) {
  const id = `set-${group}-${it.key}`;
  const control = it.type === 'bool'
    ? `<label class="switch"><input type="checkbox" id="${id}" data-group="${group}" data-key="${it.key}" ${it.value ? 'checked' : ''}><span></span></label>`
    : it.type === 'choice'
      ? `<select class="select" id="${id}" data-group="${group}" data-key="${it.key}">${it.options.map(o => `<option${o === it.value ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>`
      // A key is masked on screen. It still lands in settings.json in plain
      // text, which the row's own note says — hiding it here and pretending
      // otherwise would be worse than not hiding it.
      : it.type === 'text'
        ? `<input class="setting-text" type="${it.key.includes('key') ? 'password' : 'text'}"
                  id="${id}" data-group="${group}" data-key="${it.key}"
                  value="${esc(it.value ?? '')}" spellcheck="false">`
        : '';
  const slider = it.type === 'number'
    ? `<input type="range" data-dp="${it.dp}" min="${it.min}" max="${it.max}" step="${it.step}" value="${it.value}">` : '';
  const num = it.type === 'number'
    ? `<span class="setting-val">
         <input class="setting-num" type="number" id="${id}" data-group="${group}" data-key="${it.key}"
                min="${it.min}" max="${it.max}" step="${it.step}" value="${(+it.value).toFixed(it.dp)}">
         ${it.unit ? `<em>${esc(it.unit.trim())}</em>` : ''}</span>` : '';
  return `<div class="setting">
    <div class="setting-top"><span class="setting-name">${esc(it.name)}</span>
      ${it.type === 'number' ? num : control}</div>
    ${slider}
    ${it.why ? `<div class="setting-why">${esc(it.why)}</div>` : ''}
  </div>`;
}
api('/api/settings').then(paintSettings).catch(() => {});
$('#btn-save').onclick = async () => {
  const values = {};
  $$('#settings-groups [data-key]').forEach(el => {
    values[`${el.dataset.group}.${el.dataset.key}`] =
      el.type === 'checkbox' ? el.checked
        : (el.tagName === 'SELECT' || el.type === 'text' || el.type === 'password')
          ? el.value : +el.value;
  });
  toast((await api('/api/settings', { values })).message);
};
$('#btn-reset').onclick = async () => {
  paintSettings(await api('/api/settings/reset', {})); toast('Reset — not saved yet');
};

/* ── composer ───────────────────────────────────────────────────────── */
$('#btn-send').onclick = send;
(function wireComposer(el) {
  const grow = () => { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 220) + 'px'; };
  el.addEventListener('input', grow);
  el.addEventListener('keydown', e => {
    // Enter sends, Shift+Enter breaks the line — and a pasted script arrives
    // through paste, not keystrokes, so this never eats one.
    if (e.key !== 'Enter' || e.shiftKey) return;
    e.preventDefault(); send();
    requestAnimationFrame(() => { el.style.height = 'auto'; });
  });
})($('#chat-input'));

/* ── open ───────────────────────────────────────────────────────────── */
api('/api/hardware').then(h => {
  $('#hw-text').textContent = h.label;
  $('#hw .dot').className = 'dot ' + (h.gpu ? 'dot-ok' : 'dot-warn');
}).catch(() => { $('#hw-text').textContent = 'backend unreachable'; });

drawIcons();
loadProfile();
refreshAuth();

api('/api/voice/status').then(v => {
  paintVoice(v);
  const box = $('#chat-empty');
  if (!box) return;
  box.innerHTML = v.loaded
    ? `Voice is <b>${esc(v.name)}</b>. Paste a script and I will tell you what it ` +
      `becomes before rendering it — or press <b>Render a take</b> to hear where the voice is.`
    : `Drop an audio clip anywhere in here and it becomes the voice. 8–12 seconds ` +
      `of continuous speech, no music. Then paste a script.`;
}).catch(() => {});
