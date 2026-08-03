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
  chev:'M9 18l6-6-6-6', plus:'M12 5v14M5 12h14',
  dots:'M12 6.6h.01M12 12h.01M12 17.4h.01',
  trash:'M4 6h16M9 6V4h6v2M7 6l1 14h8l1-14',
};
function drawIcons(root = document) {
  $$('i[data-i]', root).forEach(el => {
    const d = ICONS[el.dataset.i]; if (!d) return;
    // data-w overrides the stroke. The three-dot menu glyph is drawn as three
    // zero-length round-capped strokes, so its weight IS its dot size — at the
    // shared 1.8 it is a barely visible speck.
    el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="${el.dataset.w || 1.8}" stroke-linecap="round" stroke-linejoin="round"
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
  upgradePlayers(el);
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
  let polling = 0;

  const id = setInterval(async () => {
    tick.textContent = mmss((performance.now() - t0) / 1000);
    // A single hung request would otherwise leave polling true forever and
    // freeze the bar at whatever width it had reached.
    if (polling && Date.now() - polling < 5000) return;
    polling = Date.now();
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
    polling = 0;
  }, 700);

  return { stop: () => { clearInterval(id); return (performance.now() - t0) / 1000; } };
}


/* ── the transport ───────────────────────────────────────────────────
   THE one thing in here that is not a default.

   Every piece of audio used to be a stock <audio controls>: a white slab
   with a three-dot menu in a near-black window, and the loudest "assembled
   from parts" signal in the app. It was also useless for the work. This
   studio exists to argue about PAUSES — comma beats, chapter gaps, the
   133 ms orphan that survived six repairs — and a waveform shows those
   before you press play. You can see the shape of a read and compare two
   takes with your eyes while your ears catch up.

   Decoded once per file and cached; a failed decode falls back to a plain
   progress line rather than to Chrome's. */
const PEAKS = new Map();
const AC = () => (window.__ac ||= new (window.AudioContext || window.webkitAudioContext)());

async function peaks(src, buckets = 420) {
  if (PEAKS.has(src)) return PEAKS.get(src);
  const job = (async () => {
    const r = await fetch(src);
    // A 404 hands back an HTML error page, which decodeAudioData reports as
    // EncodingError — the same message a genuinely corrupt file gives. Checked
    // here so a replayed take whose audio has been deleted says so instead of
    // looking like a broken decoder.
    if (!r.ok) throw new Error(`${r.status} for ${src}`);
    const buf = await AC().decodeAudioData(await r.arrayBuffer());
    const raw = buf.getChannelData(0);
    const step = Math.max(1, Math.floor(raw.length / buckets));
    const out = new Float32Array(buckets);
    for (let b = 0; b < buckets; b++) {
      let peak = 0;
      const start = b * step, end = Math.min(raw.length, start + step);
      for (let i = start; i < end; i++) { const v = Math.abs(raw[i]); if (v > peak) peak = v; }
      out[b] = peak;
    }
    // Normalised to the loudest bucket: a quiet take should still be legible,
    // and absolute level is what the LUFS reading is for.
    const max = Math.max(...out) || 1;
    return { data: out.map(v => v / max), duration: buf.duration };
  })();
  // The PROMISE is cached, so a file is decoded once however many players show
  // it. A rejection is dropped rather than kept: a take that 404'd while it was
  // still being written would otherwise never draw a waveform again.
  job.catch(() => PEAKS.delete(src));
  PEAKS.set(src, job);
  return job;
}

const clock = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

function makePlayer(src, label = '') {
  const el = document.createElement('div');
  el.className = 'vo';
  el.innerHTML = `
    <button class="vo-play" aria-label="Play"><svg viewBox="0 0 24 24" width="15" height="15"
      fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg></button>
    <div class="vo-body">
      <canvas class="vo-wave" aria-hidden="true"></canvas>
      <div class="vo-meta"><span class="vo-label">${esc(label)}</span><span class="vo-time">--:--</span></div>
    </div>`;
  const audio = new Audio(src);
  audio.preload = 'metadata';
  const btn = el.querySelector('.vo-play');
  const cv = el.querySelector('.vo-wave');
  const time = el.querySelector('.vo-time');
  const ctx = cv.getContext('2d');
  let shape = null, dur = 0;

  const css = getComputedStyle(document.documentElement);
  const ACCENT = css.getPropertyValue('--accent').trim() || '#34d399';
  const REST = css.getPropertyValue('--line-lit').trim() || '#2a322e';

  function draw() {
    const w = cv.clientWidth, h = cv.clientHeight, dpr = devicePixelRatio || 1;
    if (!w || !h) return;
    cv.width = w * dpr; cv.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const played = dur ? audio.currentTime / dur : 0;
    const n = shape ? shape.length : 90;
    const gap = 1, bar = Math.max(1, w / n - gap);
    for (let i = 0; i < n; i++) {
      const x = i * (bar + gap);
      // No waveform yet (or decode failed): a flat rule, not a fake one.
      const v = shape ? shape[i] : 0.12;
      const barH = Math.max(2, v * (h - 2));
      ctx.fillStyle = (x / w) <= played ? ACCENT : REST;
      ctx.fillRect(x, (h - barH) / 2, bar, barH);
    }
  }

  const tick = () => {
    time.textContent = dur ? `${clock(audio.currentTime)} / ${clock(dur)}` : '--:--';
    draw();
  };

  btn.onclick = () => {
    if (audio.paused) { document.querySelectorAll('audio').forEach(a => a !== audio && a.pause()); audio.play(); }
    else audio.pause();
  };
  const icon = playing => {
    btn.innerHTML = playing
      ? `<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><rect x="6" y="4.5" width="4" height="15" rx="1"/><rect x="14" y="4.5" width="4" height="15" rx="1"/></svg>`
      : `<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><path d="M7 4.5v15l13-7.5z"/></svg>`;
    btn.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  };
  audio.onplay = () => { icon(true); el.classList.add('is-playing'); requestAnimationFrame(function f() {
    if (!audio.paused) { tick(); requestAnimationFrame(f); } }); };
  audio.onpause = () => { icon(false); el.classList.remove('is-playing'); tick(); };
  audio.onended = () => { audio.currentTime = 0; tick(); };
  audio.onloadedmetadata = () => { if (isFinite(audio.duration)) { dur = audio.duration; tick(); } };

  const seek = e => {
    if (!dur) return;
    const r = cv.getBoundingClientRect();
    audio.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur;
    tick();
  };
  cv.onpointerdown = e => { cv.setPointerCapture(e.pointerId); seek(e); };
  cv.onpointermove = e => { if (cv.hasPointerCapture(e.pointerId)) seek(e); };

  peaks(src).then(p => { shape = p.data; if (!dur) dur = p.duration; tick(); })
            .catch(() => tick());
  new ResizeObserver(draw).observe(cv);
  tick();
  return el;
}

/* Replace any <audio> the app still writes as markup. One place to change,
   and nothing can accidentally ship a stock player. */
function upgradePlayers(root) {
  root.querySelectorAll('audio[controls]').forEach(a => {
    const src = a.getAttribute('src');
    if (!src) return;
    a.replaceWith(makePlayer(src, a.dataset.label || ''));
  });
}

/* ── voice reference ────────────────────────────────────────────────── */
let VOICE = { loaded: false };

function paintVoice(v) {
  VOICE = v;
  $('#ref-empty').hidden = !!v.loaded;
  $('#ref-set').hidden = !v.loaded;
  if (!v.loaded) return;
  // Only re-stamped when the clip actually changed — otherwise every turn
  // reloaded it and killed whatever you were listening to.
  const want = '/api/voice/audio?t=' + (v.name || '') + (v.duration || '');
  const ref = $('#ref-set');
  if (ref.dataset.src !== want) {
    ref.dataset.src = want;
    ref.querySelector('.vo')?.remove();
    ref.prepend(makePlayer(want, 'reference'));
  }
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

/* A clipboard bitmap arrives with no name, or with the same "image.png" every
   time, which would make every screenshot overwrite the last in the attachment
   tray. Anything copied as a real file keeps the name it already has. */
const EXT = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif',
              'image/webp': 'webp', 'audio/mpeg': 'mp3', 'audio/wav': 'wav',
              'audio/x-wav': 'wav', 'audio/flac': 'flac', 'audio/mp4': 'm4a',
              'audio/ogg': 'ogg', 'text/plain': 'txt', 'application/pdf': 'pdf' };
let pasteSeq = 0;
function named(f) {
  if (f.name && f.name !== 'image.png') return f;
  const ext = EXT[f.type] || (f.type.split('/')[1] || 'bin').replace(/[^a-z0-9]/gi, '');
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  return new File([f], `pasted-${stamp}-${++pasteSeq}.${ext}`, { type: f.type });
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

/* Tool results come back as JSON text. The only part worth drawing is a
   rendered file — everything else the agent will say in its own words. */
function takeFrom(text) {
  try {
    const j = JSON.parse(text);
    return j && j.file && /take-\d+\.wav$/.test(j.file) ? j : null;
  } catch { return null; }
}

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
  // Turns are serialised on the server; sending into a running one would just
  // queue a second turn behind it with no sign that it had happened.
  if (BUSY) return toast('Still working on the last one');
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

let BUSY = false;

async function stream(text, files = []) {
  BUSY = true;
  $('#btn-send').disabled = true;
  const bubble = say('<span class="msg-wait">…</span>');
  // The bubble is a SEQUENCE, not one string. It used to be rebuilt with
  // innerHTML on every text event, which silently deleted anything appended
  // between them -- including the player for a take that had just rendered.
  // Text goes into its own span; a player or a progress bar is a sibling, and
  // the next text after one starts a fresh span so order is preserved.
  let text_span = null, wrote = false;
  let live = null;
  // Every startClock() opens a 700 ms poller. Removing its DOM node does NOT
  // stop it, so a session with twenty renders ended up firing ~29 requests a
  // second at an idle server, writing to nodes that could never be collected.
  const clocks = [];

  const write = chunk => {
    if (!text_span) {
      text_span = document.createElement('div');
      bubble.append(text_span);
      text_span.dataset.text = '';
    }
    text_span.dataset.text += chunk;
    text_span.innerHTML = asText(text_span.dataset.text);
    wrote = true;
    chat().scrollTop = chat().scrollHeight;
  };
  const block = () => { text_span = null; };   // next text starts a new span

  try {
    const res = await fetch('/api/assistant', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, files }),
    });
    if (!res.ok) throw new Error(`backend ${res.status}: ${(await res.text()).slice(0, 300)}`);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (value) buf += dec.decode(value, { stream: true });
      // Flush the decoder and keep the remainder on the last read: a stream
      // cut short (agent crash, window reload) would otherwise silently eat
      // its final event — which is the one carrying the error or the file.
      if (done) buf += dec.decode();          // flush the decoder's tail
      const lines = buf.split('\n');
      // On the last read, keep the remainder as a line: a stream cut short
      // (agent crash, window reload) would otherwise silently drop its final
      // event — the one carrying the error or the rendered file.
      buf = done ? '' : lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        let ev; try { ev = JSON.parse(line); } catch { continue; }

        if (ev.type === 'text') {
          if (live) { live.remove(); live = null; block(); }
          if (!wrote) bubble.innerHTML = '';
          write(ev.text);
        } else if (ev.type === 'tool') {
          const label = TOOL_SAYS[ev.name?.split('__').pop()] || 'working';
          if (!wrote) bubble.innerHTML = '';
          live?.remove();
          live = document.createElement('div');
          bubble.append(live);
          block();
          // Only the slow ones get a bar; a status check does not need one.
          if (/render/.test(ev.name || '')) clocks.push(startClock(live, label + '…'));
          else live.innerHTML = `<span class="msg-wait">${esc(label)}…</span>`;
          chat().scrollTop = chat().scrollHeight;
        } else if (ev.type === 'result') {
          // The tool just rendered something. Put it on screen where it was
          // asked for, rather than describing a path on disk.
          const take = takeFrom(ev.text);
          if (take) {
            live?.remove(); live = null;
            if (!wrote) bubble.innerHTML = '';
            const el = document.createElement('div');
            el.className = 'took-audio';
            el.innerHTML =
              `<audio controls src="/api/lab/audio?name=${encodeURIComponent($('#prof').value)}` +
              `&file=${encodeURIComponent(take.file)}" data-label="${esc(take.file)}"></audio>` +
              (take.seconds ? `<div class="took">${esc(take.seconds)}s on the GPU</div>` : '');
            upgradePlayers(el);
            bubble.append(el);
            block();
            wrote = true;
            chat().scrollTop = chat().scrollHeight;
          }
        } else if (ev.type === 'error') {
          write((wrote ? '\n\n' : '') + ev.text);
        }
      }
      if (done) break;
    }
  } catch (e) {
    if (!wrote) bubble.innerHTML = '';     // clear the … placeholder first
    write(String(e));
  }
  clocks.forEach(c => c.stop());
  if (live) live.remove();
  if (!wrote) bubble.innerHTML = '<span class="msg-wait">(no reply)</span>';
  BUSY = false;
  $('#btn-send').disabled = false;

  // Whatever it just did is now the truth about the voice — repaint the panel
  // from the server rather than guessing from the conversation.
  refreshPanel();
  // And the rail: this turn just named an untitled conversation and moved it
  // to the top of the list.
  api('/api/conversations').then(paintConvos).catch(() => {});
}

function refreshPanel() {
  api('/api/voice/status').then(paintVoice).catch(() => {});
  loadProfile();                      // no name: read the server, do not set it
  api('/api/lab/latest').then(j => {
    const box = $('#last-take');
    if (!j.file) { box.innerHTML = ''; return; }   // a fresh profile has none
    const src = `/api/lab/audio?name=${encodeURIComponent(j.name)}&file=${encodeURIComponent(j.file)}`;
    // Rebuilt only when it is a DIFFERENT take. Rebuilding every turn stopped
    // playback dead and rewound to 0:00 the moment you sent a message.
    if (box.firstElementChild?.getAttribute('src') === src) return;
    box.innerHTML = `<audio controls src="${src}" data-label="${esc(j.file)}"></audio>`;
    upgradePlayers(box);
  }).catch(() => {});
}

/* ── conversations ───────────────────────────────────────────────────
   A LIST, NOT A BUTTON.

   "New conversation" used to be one button in the Claude card, and pressing
   it threw the transcript away with nothing to go back to. The transcript is
   where the script is, and the takes, and every note about the read — so they
   are files now, listed in the left rail, and each one can be deleted from
   its own menu.

   The server owns which one is open and what is in it. Nothing here caches a
   transcript: every list, open and delete comes back with the same shape and
   this repaints from it. */
const CONVOS = { active: null, items: [] };

const ago = t => {
  const s = Date.now() / 1000 - (t || 0);
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  if (s < 172800) return 'yesterday';
  return new Date((t || 0) * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

function paintConvos(view) {
  if (view) { CONVOS.active = view.active; CONVOS.items = view.items || []; }
  const box = $('#convos');
  if (!CONVOS.items.length) {
    box.innerHTML = '<div class="convos-empty">Nothing saved yet. What you say here is kept.</div>';
    return;
  }
  box.innerHTML = CONVOS.items.map(c => `
    <div class="convo${c.id === CONVOS.active ? ' is-active' : ''}" data-id="${esc(c.id)}" role="listitem">
      <button class="convo-open" title="${esc(c.title)}">
        <span class="convo-title">${esc(c.title)}</span>
        <span class="convo-when">${esc(ago(c.updated))}${c.turns ? ` · ${c.turns} message${c.turns === 1 ? '' : 's'}` : ''}</span>
      </button>
      <button class="convo-more" aria-label="More for ${esc(c.title)}" aria-haspopup="menu">
        <i data-i="dots" data-w="3.2"></i></button>
    </div>`).join('');
  drawIcons(box);
  $$('.convo', box).forEach(row => {
    const id = row.dataset.id;
    $('.convo-open', row).onclick = () => openConvo(id);
    $('.convo-more', row).onclick = e => { e.stopPropagation(); showMenu(row, id); };
  });
}

/* One menu at a time, positioned against the button rather than nested inside
   a row that clips its own overflow. */
let MENU = null;
function closeMenu() {
  MENU?.remove(); MENU = null;
  $$('.convo.menu-open').forEach(r => r.classList.remove('menu-open'));
}
function showMenu(row, id) {
  const open = row.classList.contains('menu-open');
  closeMenu();
  if (open) return;                       // clicking the dots again closes it
  row.classList.add('menu-open');
  MENU = document.createElement('div');
  MENU.className = 'convo-menu';
  MENU.setAttribute('role', 'menu');
  MENU.innerHTML = `<button role="menuitem"><i data-i="trash"></i>Delete conversation</button>`;
  document.body.append(MENU);
  drawIcons(MENU);
  const r = row.getBoundingClientRect();
  MENU.style.left = `${Math.round(r.right - 8)}px`;
  // Flipped up near the bottom of the window rather than hanging off it.
  const below = window.innerHeight - r.bottom;
  MENU.style.top = below > MENU.offsetHeight + 12
    ? `${Math.round(r.bottom + 4)}px`
    : `${Math.round(r.top - MENU.offsetHeight - 4)}px`;
  MENU.querySelector('button').onclick = () => { closeMenu(); deleteConvo(id); };
  MENU.querySelector('button').focus();
}
document.addEventListener('pointerdown', e => {
  if (MENU && !MENU.contains(e.target) && !e.target.closest('.convo-more')) closeMenu();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
window.addEventListener('resize', closeMenu);

/* Deleting takes the transcript with it — and if it was the one you were in,
   the agent's session too. Asked once, because there is no undo: the file is
   removed, not flagged. */
async function deleteConvo(id) {
  const it = CONVOS.items.find(c => c.id === id);
  if (!confirm(`Delete “${it ? it.title : 'this conversation'}”?\n\n` +
               'The transcript is gone for good. Voices, settings and rendered ' +
               'audio are not touched.')) return;
  try {
    const view = await api('/api/conversations/delete', { id });
    paintConvos(view);
    if (view.opened) replay(view.turns);
    toast('Conversation deleted');
  } catch (e) { toast(String(e)); }
}

async function newConvo() {
  if (BUSY) return toast('Still working on the last one — that turn belongs to this conversation');
  try {
    const view = await api('/api/conversations/new', {});
    paintConvos(view);
    replay([]);
    $('#chat-input').focus();
  } catch (e) { toast(String(e)); }
}
$('#btn-new').onclick = newConvo;

async function openConvo(id) {
  if (id === CONVOS.active) return;
  if (BUSY) return toast('Still working on the last one');
  try {
    const view = await api('/api/conversations/open?id=' + encodeURIComponent(id));
    paintConvos(view);
    replay(view.turns);
  } catch (e) { toast(String(e)); }
}

/* Redraw a saved transcript.

   What was written down is the text, the names of anything attached, and the
   file name of any take. Not the audio itself — that lives under projects/
   with its own numbering, and a second copy would be a second thing to keep
   in step. A take whose file has since been deleted replays as a player that
   will not load, which is the truth about it. */
function replay(turns) {
  const c = chat();
  c.innerHTML = '';
  for (const t of turns || []) {
    if (t.role === 'me') {
      const chips = (t.files || []).map(f =>
        `<span class="att-sent">${esc(f.name)}</span>`).join('');
      say((chips ? `<div class="att-row">${chips}</div>` : '') + asText(t.text || ''), 'me');
    } else {
      const players = (t.takes || []).map(k =>
        `<div class="took-audio"><audio controls src="/api/lab/audio?name=` +
        `${encodeURIComponent(k.name)}&file=${encodeURIComponent(k.file)}" ` +
        `data-label="${esc(k.file)}"></audio>` +
        (k.seconds ? `<div class="took">${esc(k.seconds)}s on the GPU</div>` : '') +
        `</div>`).join('');
      if ((t.text || '').trim() || players) say(asText(t.text || '') + players);
    }
  }
  if (!c.firstElementChild) showEmpty();
  c.scrollTop = c.scrollHeight;
}

/* ── takes ──────────────────────────────────────────────────────────── */
async function renderTake() {
  if (!VOICE.loaded) { say('<span class="msg-bad">No voice loaded — drop an audio clip in first.</span>'); return; }
  const holder = say('');
  const slot = document.createElement('div');
  holder.append(slot);
  const clock = startClock(slot, 'starting…');
  $('#btn-take').disabled = true;
  try {
    const j = await api('/api/lab/sample', { name: $('#prof').value });
    const took = clock.stop();
    if (j.error) { slot.innerHTML = `<span class="msg-bad">${esc(j.error)}</span>`; }
    else {
      paintParams(j.profile);
      slot.innerHTML =
        (j.note ? `<div class="msg-bad">${esc(j.note)}</div>` : '') +
        `<audio controls src="/api/lab/audio?name=${encodeURIComponent($('#prof').value)}` +
        `&file=${encodeURIComponent(j.audio || '')}" data-label="${esc(j.audio || 'take')}"></audio>` +
        `<div class="took">${(j.seconds ?? took).toFixed(1)}s on the GPU</div>`;
      upgradePlayers(slot);
    }
  } catch (e) { clock.stop(); slot.innerHTML = `<span class="msg-bad">${esc(e)}</span>`; }
  finally { clock.stop(); }
  $('#btn-take').disabled = false;
  chat().scrollTop = chat().scrollHeight;
}
$('#btn-take').onclick = () => renderTake();

/* ── voice profile panel ────────────────────────────────────────────── */
const RANGES = { exaggeration: [.2, .9], cfg_weight: [.2, .9], temperature: [.4, 1.1], speed: [.85, 1.25] };
function paintParams(p) {
  $('#params').innerHTML = Object.entries(RANGES).map(([k, [lo, hi]]) => {
    // A profile.json missing one key used to throw inside .map and leave the
    // panel empty with no console error, while the PREVIOUS profile's sliders
    // stayed on screen looking authoritative.
    const v = typeof p[k] === 'number' ? p[k] : (lo + hi) / 2;
    const name = k === 'cfg_weight' ? 'reference adherence' : k;
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
/* THE SERVER OWNS THE PROFILE NAME.
   Asking with a name SETS it, so calling this on page load with the box's
   hardcoded "explaintory" silently rewrote whatever profile was actually
   active — and doing it again after every turn undid profile switches Claude
   had just made. A name is sent ONLY when you type one. */
async function loadProfile(name) {
  try {
    const p = await api('/api/profile' + (name ? '?name=' + encodeURIComponent(name) : ''));
    if (p.name) $('#prof').value = p.name;
    paintParams(p);
  } catch { /* the panel is not worth an error */ }
}
$('#prof').addEventListener('change', e => loadProfile(e.target.value.trim()));

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

  // Ctrl+V for anything on the clipboard — a screenshot, an mp3 copied in
  // Explorer, a text file, several at once. Windows' Snipping Tool puts an
  // image on the clipboard and nothing on disk, so a file dialog cannot reach
  // it at all; the paste event is the only way in.
  el.addEventListener('paste', e => {
    const files = [...(e.clipboardData?.files || [])];
    if (!files.length) return;              // plain text pastes normally
    e.preventDefault();
    takeFiles(files.map(named));
  });
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

/* An empty screen is an instruction, not a status line. Drawn from whatever
   the voice panel currently knows, so it says the right thing whether you have
   just opened the app or just deleted the conversation you were in. */
function showEmpty() {
  chat().innerHTML = `<div class="empty" id="chat-empty">${
    VOICE.loaded
      ? `<span class="empty-title">Voice loaded — ${esc(VOICE.name)}</span>` +
        `Paste a script and you will see what it becomes — sections, chapter headers, ` +
        `how long it runs, how long it takes — before anything renders.<br><br>` +
        `Or say <kbd>render a take</kbd> to hear where the voice is sitting right now.`
      : `<span class="empty-title">Start with a voice</span>` +
        `Drop an audio clip anywhere in this panel and it becomes the voice everything ` +
        `is read in. The best reference is a cut of a voiceover you already delivered: ` +
        `<b>8 to 12 seconds</b> of continuous speech, no music, no long pauses.<br><br>` +
        `Then paste your script.`}</div>`;
}

drawIcons();
loadProfile();
refreshAuth();

refreshPanel();
// The voice first, because the empty state is written from it — then whatever
// conversation was open when the app was last closed, replayed into the panel.
api('/api/voice/status')
  .then(paintVoice)
  .catch(() => {})
  .then(() => api('/api/conversations'))
  .then(view => {
    paintConvos(view);
    return api('/api/conversations/open?id=' + encodeURIComponent(view.active));
  })
  .then(view => { paintConvos(view); replay(view.turns); })
  .catch(e => {
    const box = $('#chat-empty');
    if (box) box.innerHTML = `The backend is not answering (${esc(e)}). ` +
      `Close the app and open it again — if it keeps happening, runtime\\last-run.log has the reason.`;
  });
