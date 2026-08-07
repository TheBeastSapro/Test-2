/* Forgecast — the chat.

   There is no routing here. Every message goes to Claude, which holds the studio's
   operations as MCP tools running in this app's own process: read a YouTube channel,
   create one, start a run, score a niche, build a preview. Deciding what you meant
   was a keyword table's job for about a day, and a keyword table is a worse listener
   than the thing already in the box.

   This file draws the conversation, keeps the right-hand panel showing whatever the
   last turn changed, and remembers which thread you were in. It does not decide
   anything. */

(() => {
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const api = async (path, body, method) => {
  const options = body !== undefined
    ? { method: method || 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) }
    : (method ? { method } : undefined);
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.status === 204 ? null : response.json();
};

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let toastTimer;
function toast(message) {
  const box = $('#toast');
  box.textContent = message;
  box.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove('show'), 2800);
}

/* ── markdown, the subset an agent actually emits ────────────────────────
   Escaped first, then marked up — never the other way round, because a reply
   can quote a video title containing a tag and that title is not markup. */
function render(src) {
  const fences = [];
  let text = String(src ?? '').replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    fences.push(`<pre><code>${esc(code.replace(/\n$/, ''))}</code></pre>`);
    return ` FENCE${fences.length - 1} `;
  });

  text = esc(text)
    .replace(/`([^`\n]+)`/g, (_, code) => `<code>${code}</code>`)
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
             '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const out = [];
  let list = null;
  for (const raw of text.split('\n')) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    const heading = line.match(/^(#{1,4})\s+(.*)$/);

    if (bullet || numbered) {
      const want = bullet ? 'ul' : 'ol';
      if (list !== want) { if (list) out.push(`</${list}>`); out.push(`<${want}>`); list = want; }
      out.push(`<li>${(bullet ? bullet[1] : numbered[2])}</li>`);
      continue;
    }
    if (list) { out.push(`</${list}>`); list = null; }

    if (heading) out.push(`<p><strong>${heading[2]}</strong></p>`);
    else if (line.trim()) out.push(`<p>${line}</p>`);
  }
  if (list) out.push(`</${list}>`);

  return out.join('')
    .replace(/ FENCE(\d+) /g, (_, i) => fences[+i])
    // A fence that landed inside a paragraph came from a line of its own.
    .replace(/<p>(<pre>[\s\S]*?<\/pre>)<\/p>/g, '$1');
}

/* ── what a tool call is called in English ──────────────────────────────── */
const TOOL_SAYS = {
  studio_status: 'checking this install',
  list_channels: 'listing your channels',
  study_youtube_channel: 'reading that channel',
  create_channel: 'creating the channel',
  update_channel: 'updating the channel',
  list_runs: 'looking at your runs',
  start_run: 'starting the run',
  run_status: 'checking the run',
  decide_gate: 'answering the gate',
  cancel_run: 'cancelling the run',
  preview_run: 'building the preview',
  run_files: 'looking at the files',
  research_channel: 'mining that channel for outliers',
  score_videos: 'scoring those numbers',
  list_styles: 'listing editing styles',
  apply_style: 'applying the style',
  blend_styles: 'blending the styles',
  Read: 'reading a file', Write: 'writing a file', Edit: 'editing a file',
  Bash: 'running a command', Glob: 'searching for files', Grep: 'searching the code',
  WebSearch: 'searching the web', WebFetch: 'fetching a page',
};
// Plumbing, not work. The agent loading its own tool definitions is not something
// worth a line in the transcript — it is the equivalent of narrating an import.
const HIDDEN_TOOLS = new Set(['ToolSearch', 'TodoWrite', 'Task']);

const toolLabel = name => {
  const bare = String(name || '').split('__').pop();
  return TOOL_SAYS[bare] || `calling ${bare}`;
};
const worthShowing = name => !HIDDEN_TOOLS.has(String(name || '').split('__').pop());

/* ── state ──────────────────────────────────────────────────────────────── */
let THREAD = null;          // {id, title, ...}
let THREADS = [];
let ATTACHED = [];
let SENDING = false;

const chat = () => $('#chat');
const scrollDown = () => { const c = chat(); c.scrollTop = c.scrollHeight; };

function bubble(html, who = 'ai', host = null) {
  const box = chat();
  const target = host || box;
  // Clear the placeholder only when writing into the live transcript. Clearing it
  // unconditionally is the other half of the cross-thread leak: a turn still running
  // in another thread would wipe the greeter of the conversation you just opened, and
  // then append its own content somewhere you cannot see — so the new chat looked
  // like it had started and then lost its own opening screen.
  if (target === box) {
    const first = box.firstElementChild;
    if (first && (first.classList.contains('empty') ||
                  first.classList.contains('opener'))) box.innerHTML = '';
  }
  const el = document.createElement('div');
  el.className = `msg ${who}`;
  el.innerHTML = html;
  // `host` is the running turn's own container, and it is used even after it has
  // been detached — which is the whole point.
  //
  // Switching threads calls `chat().innerHTML = ''`, so the container of a turn that
  // is still streaming comes out of the document. An `isConnected` check here looks
  // like defensive programming and is precisely the bug: it falls back to the live
  // transcript, so the running turn's tool cards and prose land in whichever
  // conversation was just opened, and `box.innerHTML = ''` above wipes that
  // conversation's greeter on the way in. Writing into the detached node is correct —
  // nobody sees it, the server persists the reply, and reopening the thread shows the
  // finished answer.
  target.append(el);
  scrollDown();
  return el;
}

/* ── tool cards ─────────────────────────────────────────────────────────────
   A card, not a chip. The chip said a tool ran; the card says what it returned,
   and the numbers are the part worth scrolling back to. Collapsed by default so
   a long result does not bury the answer, and open on failure because a failure
   you have to click to read is a failure you will not read. */

// The one argument worth putting on the collapsed row: the thing the call is
// ABOUT. A JSON dump of every parameter is noise at this size.
const HEADLINE_ARG = ['url', 'channel', 'topic', 'style', 'name', 'run_id',
                      'file_path', 'pattern', 'query', 'command'];

function argSummary(input) {
  if (!input || typeof input !== 'object') return '';
  for (const key of HEADLINE_ARG) {
    if (input[key] !== undefined && input[key] !== '' && input[key] !== null) {
      return String(input[key]).slice(0, 90);
    }
  }
  const first = Object.values(input)[0];
  return first === undefined ? '' : String(first).slice(0, 90);
}

function toolCard(call, { into } = {}) {
  const card = document.createElement('div');
  card.className = 'tool running';
  card.dataset.id = call.id || '';
  // Which tool this was, kept on the element because the result arrives in a separate
  // event that carries only the id. `fillToolCard` needs the name to know whether the
  // result is something the operator has to decide about.
  card.dataset.tool = String(call.name || '').split('__').pop();
  card.innerHTML = `
    <div class="tool-head">
      <span class="tool-chev">›</span>
      <span class="tool-what">${esc(toolLabel(call.name))}</span>
      <span class="grow"></span>
      <span class="tool-arg">${esc(argSummary(call.input))}</span>
    </div>`;
  const head = card.querySelector('.tool-head');
  head.onclick = () => {
    const body = card.querySelector('.tool-body');
    if (!body) return;
    card.classList.toggle('open');
    body.hidden = !card.classList.contains('open');
  };
  // Same rule as bubble(): a detached turn container is still the right target. See
  // the comment there for why falling back to the live transcript is the bug.
  (into || chat()).append(card);
  scrollDown();
  return card;
}

function fillToolCard(card, { text, isError }) {
  if (!card) return;
  card.classList.remove('running');
  card.classList.add(isError ? 'failed' : 'done');
  let body = card.querySelector('.tool-body');
  if (!body) {
    body = document.createElement('div');
    body.className = 'tool-body';
    card.append(body);
  }
  body.innerHTML = `<pre>${esc(text || '(no output)')}</pre>`;
  // A failure is opened for you. Everything else waits to be asked for.
  body.hidden = !isError;
  card.classList.toggle('open', !!isError);
  if (!isError) editGate(card, text);
}

/* ── the paper edit's approval, which is the operator's and nobody else's ──
   `plan_edit` writes a paper edit and cuts nothing. `cut_plan` refuses any plan that
   has not been approved, and `approve_edit` is deliberately withheld from the agent —
   approving is the one cheap place to disagree with the machine, and an agent that
   approves its own plan has turned that into a formality.

   Which left the decision with nowhere to be made. The endpoint existed, the refusal
   existed, and the operator had no button — so every plan stayed drafted and the cutter
   behind it was unreachable. This is that button. */
function editGate(card, text) {
  if (card.dataset.tool !== 'plan_edit' || card.querySelector('.editgate')) return;
  let plan;
  try { plan = JSON.parse(text); } catch { return; }
  if (!plan || !plan.plan_id) return;

  const row = document.createElement('div');
  row.className = 'editgate';
  card.append(row);

  // Set the moment the operator commits, and never cleared. The state check below is a
  // network round trip; without this, a decision taken while it was in flight would be
  // painted back over with the buttons that made it — which reads as the click having
  // been dropped, and the second click is a second POST.
  let decided = false;

  const settled = (state, note) => {
    row.innerHTML = `<span class="editgate-state">${esc(state)}</span>`
      + (note ? ` <span class="editgate-note">${esc(note)}</span>` : '');
  };

  const decide = async (approve, cut) => {
    decided = true;
    row.querySelectorAll('button').forEach(b => { b.disabled = true; });
    let note = '';
    if (!approve) {
      // What was wrong with it. The next draft is made against this rather than against
      // a blank page, so an empty rejection is worth one prompt to avoid.
      note = window.prompt('What was wrong with this edit?') || '';
    }
    try {
      const result = await api(`/api/edit/plans/${encodeURIComponent(plan.plan_id)}/decision`,
                               { approve, cut, note });
      if (!approve) { settled('Rejected', note); toast('Edit rejected'); return; }
      settled('Approved', cut ? 'cutting…' : 'not cut yet');
      toast(cut ? 'Cutting' : 'Approved');
      if (cut && result.cut && (result.cut.running || result.cut.started)) watchCut(row);
    } catch (error) {
      settled('Could not record that', `${error.message || error}`.slice(0, 160));
      row.querySelectorAll('button').forEach(b => { b.disabled = false; });
    }
  };

  const paint = state => {
    if (decided) return;
    if (state && state !== 'drafted') { settled(state === 'approved' ? 'Approved' : 'Rejected'); return; }
    row.innerHTML =
      `<span class="editgate-ask">Nothing has been cut yet.</span>`
      + `<button class="btn-sm primary" data-role="cut">Approve &amp; cut</button>`
      + `<button class="btn-sm" data-role="hold">Approve only</button>`
      + `<button class="btn-sm" data-role="no">Reject</button>`;
    row.querySelector('[data-role="cut"]').onclick = () => decide(true, true);
    row.querySelector('[data-role="hold"]').onclick = () => decide(true, false);
    row.querySelector('[data-role="no"]').onclick = () => decide(false, false);
  };

  // A replayed transcript can be days old, so the state in the stored result is not the
  // current one. Ask, and fall back to the buttons if the plan has since been deleted —
  // a dead button that says why beats a card that silently drops the decision.
  paint(plan.state);
  api(`/api/edit/plans/${encodeURIComponent(plan.plan_id)}`, undefined, 'GET')
    .then(current => paint(current.state))
    .catch(() => {});
}

/* Progress for a cut already running on the server. The decision endpoint starts it on
   a worker thread and returns without waiting, because an encode outlasts a request. */
function watchCut(row) {
  const tick = async () => {
    let state;
    try { state = await api('/api/edit/cut', undefined, 'GET'); } catch { return; }
    if (state.running) {
      const last = (state.log || []).slice(-1)[0] || 'encoding…';
      row.innerHTML = `<span class="editgate-state">Cutting</span>`
        + ` <span class="editgate-note">${esc(last)}</span>`;
      setTimeout(tick, 1500);
      return;
    }
    const done = state.result || {};
    if (done.error) {
      row.innerHTML = `<span class="editgate-state">Cut failed</span>`
        + ` <span class="editgate-note">${esc(done.error)}</span>`;
      return;
    }
    // A cut nobody can watch is not finished work, so the link is the point of the row
    // once it exists. `media_url` is signed, expiring and for this account only.
    row.innerHTML = `<span class="editgate-state">Cut</span>`
      + ` <span class="editgate-note">${esc(done.summary || done.relative || '')}</span>`
      + (done.media_url ? ` <a class="btn btn-sm" href="${esc(done.media_url)}" target="_blank" rel="noopener">Watch</a>` : '')
      + (done.relative ? ` <a class="btn btn-sm" href="/files?path=${encodeURIComponent(done.relative)}">Files</a>` : '');
  };
  tick();
}

function replayTools(calls) {
  for (const call of calls || []) {
    if (!worthShowing(call.name)) continue;
    const card = toolCard(call);
    if (call.result !== undefined) {
      fillToolCard(card, { text: call.result, isError: call.is_error });
    } else {
      card.classList.remove('running');
      card.classList.add('done');
    }
  }
}

/* ── threads ────────────────────────────────────────────────────────────── */
const when = iso => {
  if (!iso) return '';
  const then = new Date(iso), mins = (Date.now() - then.getTime()) / 60000;
  if (mins < 1) return 'now';
  if (mins < 60) return `${Math.round(mins)}m`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h`;
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

// Three dots, drawn rather than typed: a glyph would inherit whatever the system font
// makes of U+22EF, and the three sizes it comes out as across platforms are all wrong
// next to a 22px target. `currentColor` so the rules in app.css — including the brighter
// one for the selected row — are the only place the colour is decided.
const DOTS = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" '
  + 'focusable="false"><circle cx="3" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/>'
  + '<circle cx="13" cy="8" r="1.5"/></svg>';

function paintThreads() {
  const list = $('#thread-list');
  // A repaint throws away the button the open menu is anchored to, and a menu floating
  // beside a row that no longer exists is worse than no menu.
  closeRowMenu();
  if (!THREADS.length) {
    list.innerHTML = `<div class="muted" style="padding:10px 11px;font-size:12.5px">
      No chats yet.</div>`;
    return;
  }
  // A div rather than a button, because the overflow control is a button and a button
  // inside a button is not valid markup — browsers recover from it by dropping one of
  // them, and which one is up to the browser.
  list.innerHTML = THREADS.map(t => `
    <div class="thread ${THREAD && t.id === THREAD.id ? 'on' : ''}" data-id="${t.id}"
         role="button" tabindex="0">
      <div class="t">${t.pinned ? '📌 ' : ''}${esc(t.title)}</div>
      <div class="p">${esc(t.preview || 'empty')}</div>
      <div class="when">${when(t.updated_at)}</div>
      <button class="thread-more" type="button" data-menu="${t.id}"
              title="Rename, pin or delete this chat"
              aria-label="Actions for ${esc(t.title)}"
              aria-haspopup="menu" aria-expanded="false">${DOTS}</button>
    </div>`).join('');
  $$('#thread-list .thread').forEach(row => {
    row.onclick = () => openThread(+row.dataset.id);
    // Enter and Space, because the row stopped being a real button above and a list you
    // cannot reach from the keyboard is a list some people cannot use at all.
    row.onkeydown = (event) => {
      // Only when the row itself has focus. Enter on the dots button also bubbles here,
      // and answering it would open the chat behind the menu that just opened.
      if (event.target !== row) return;
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openThread(+row.dataset.id);
      }
    };
  });
  $$('#thread-list .thread-more').forEach(button => {
    button.onclick = (event) => {
      // Without this the click also opens the chat the menu belongs to — everything
      // else inside the row is meant to open it, and this is the one thing that is not.
      event.stopPropagation();
      openRowMenu(button, +button.dataset.menu);
    };
  });
}

/* ── the row menu ────────────────────────────────────────────────────────────
   One menu element for the whole list, living in chat.html outside the scrolling
   list — see the comment there for why it cannot live in the row. Opening it for a
   second row therefore closes the first without any bookkeeping, because there is
   only ever one.

   Everything below is about where it is and when it goes away. What the items do is
   further down: dropThread, renameThread, pinThread. */
let MENU_FOR = null;               // id of the thread whose menu is open, or null

const rowMenu = () => $('#thread-menu');
const dotsFor = id => $(`#thread-list .thread-more[data-menu="${id}"]`);

function closeRowMenu(returnFocus = false) {
  const menu = rowMenu();
  if (!menu || MENU_FOR === null) return;
  const opener = dotsFor(MENU_FOR);
  MENU_FOR = null;
  menu.hidden = true;
  $$('#thread-list .thread-more').forEach(b => b.setAttribute('aria-expanded', 'false'));
  // Only on Escape and on picking an item. Closing by clicking elsewhere must leave
  // focus where the click put it.
  if (returnFocus && opener) opener.focus();
}

// Against the viewport, from the button's own rect, and flipped above the row when
// there is no room below — the bottom of the list is exactly where a menu that only
// ever opens downwards loses its last item.
function placeRowMenu(menu, button) {
  const rect = button.getBoundingClientRect();
  const gap = 6, edge = 8;
  const { offsetWidth: width, offsetHeight: height } = menu;
  let top = rect.bottom + gap;
  if (top + height > window.innerHeight - edge) {
    top = Math.max(edge, rect.top - gap - height);
  }
  const left = Math.min(
    Math.max(edge, rect.right - width), window.innerWidth - width - edge);
  menu.style.top = `${Math.round(top)}px`;
  menu.style.left = `${Math.round(left)}px`;
}

function openRowMenu(button, id) {
  const menu = rowMenu();
  if (!menu) return;
  if (MENU_FOR === id) { closeRowMenu(true); return; }   // a second click closes it
  closeRowMenu();
  const thread = THREADS.find(t => t.id === id);
  MENU_FOR = id;
  menu.dataset.id = String(id);
  menu.setAttribute('aria-label', `Actions for ${thread ? thread.title : 'this chat'}`);
  // The one item whose label depends on the row it was opened from.
  $('#thread-menu-pin').textContent = thread && thread.pinned ? 'Unpin' : 'Pin to top';
  menu.hidden = false;                  // shown before measuring: a hidden box has no size
  placeRowMenu(menu, button);
  button.setAttribute('aria-expanded', 'true');
  const first = menu.querySelector('.rowmenu-item');
  if (first) first.focus();
}

function wireRowMenu() {
  const menu = rowMenu();
  if (!menu) return;

  menu.onclick = event => {
    // A click on the menu is not a click "elsewhere", so it must not reach the closer
    // below before the item it landed on has been read.
    event.stopPropagation();
    const item = event.target.closest('.rowmenu-item');
    if (!item) return;
    const id = +menu.dataset.id;
    // Focus back on the dots before the action runs: the item it was sitting on is
    // about to be hidden, and focus on a hidden element falls to the body, which is
    // nowhere. Rename and Pin therefore leave you on the row you acted on.
    closeRowMenu(true);
    if (item.dataset.act === 'delete') dropThread(id);
    else if (item.dataset.act === 'rename') renameThread(id);
    else if (item.dataset.act === 'pin') pinThread(id);
  };

  menu.onkeydown = event => {
    const items = $$('.rowmenu-item', menu);
    const at = items.indexOf(document.activeElement);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      items[(Math.max(at, 0) + step + items.length) % items.length].focus();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      closeRowMenu(true);
    } else if (event.key === 'Tab') {
      // Tabbing out of a menu that stays open leaves it hanging over the list. No
      // preventDefault: focus goes back to the dots here, and the browser's own Tab
      // then carries on from there, which is where a menu button leaves you.
      closeRowMenu(true);
    }
  };

  // Anywhere else. The dots button stops its own click from getting here, which is what
  // makes "click the dots again" a toggle rather than a close-then-open.
  document.addEventListener('click', () => closeRowMenu());
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeRowMenu(true);
  });
  // The menu is placed against the viewport, so anything that moves the row underneath
  // it separates the two. Closing is honest; re-measuring on every scroll frame is not.
  window.addEventListener('resize', () => closeRowMenu());
  $('#thread-list').addEventListener('scroll', () => closeRowMenu());
}

async function renameThread(id) {
  const thread = THREADS.find(t => t.id === id);
  const asked = prompt('Rename this chat', thread ? thread.title : '');
  if (asked === null) return;                  // cancelled, which is not a rename to ''
  const title = asked.trim();
  if (!title || (thread && title === thread.title)) return;
  try {
    const saved = await api(`/api/agent/threads/${id}`, { title }, 'PATCH');
    if (thread) thread.title = saved.title;    // the server truncates, so take its answer
    if (THREAD && THREAD.id === id) THREAD.title = saved.title;
  } catch (error) {
    toast('Could not rename: ' + String(error.message || error));
    return;
  }
  paintThreads();
}

async function pinThread(id) {
  const thread = THREADS.find(t => t.id === id);
  if (!thread) return;
  try {
    await api(`/api/agent/threads/${id}`, { pinned: !thread.pinned }, 'PATCH');
  } catch (error) {
    toast('Could not pin: ' + String(error.message || error));
    return;
  }
  // Re-read rather than re-sort here: pinned-first is the server's ordering, and a
  // local guess at it is a second sort that has to be kept in step with the first.
  await loadThreads();
  markThreadBusy();
}

async function dropThread(id) {
  const doomed = THREADS.find(t => t.id === id);
  // Confirmed because it cannot be undone — the messages are the record and there is no
  // archive behind this. Named in the question, since the list is a wall of similar rows.
  if (!confirm(`Delete "${doomed ? doomed.title : 'this chat'}"? This cannot be undone.`)) return;

  const running = RUNNING.get(id);
  if (running) {
    toast('That chat is mid-turn. Let it finish, or stop it, before deleting.');
    return;
  }
  try {
    // Third argument, not second: the second is a JSON body, and passing an options
    // object there would POST `{"method":"DELETE"}` to the thread instead.
    await api(`/api/agent/threads/${id}`, undefined, 'DELETE');
  } catch (error) {
    toast('Could not delete: ' + String(error.message || error));
    return;
  }
  THREADS = THREADS.filter(t => t.id !== id);
  if (THREAD && THREAD.id === id) {
    // The open chat was the one deleted, so land somewhere real rather than on a
    // transcript whose thread is gone.
    THREAD = null;
    localStorage.removeItem('forgecast.thread');
    chat().innerHTML = '';
    if (THREADS.length) await openThread(THREADS[0].id);
    else await newThread();
  } else {
    paintThreads();
  }
}

async function loadThreads() {
  try {
    THREADS = (await api('/api/agent/threads')).threads || [];
  } catch { THREADS = []; }
  paintThreads();
}

async function openThread(id) {
  try {
    const data = await api(`/api/agent/threads/${id}`);
    THREAD = data;
    localStorage.setItem('forgecast.thread', String(id));
    chat().innerHTML = '';
    if (!data.messages.length) greet();
    for (const message of data.messages) {
      if (message.role === 'user') {
        const shown = (message.attachments || []).map(a => attachmentHTML(a, true)).join('');
        bubble((shown ? `<div class="att-row">${shown}</div>` : '') + render(message.text), 'me');
      } else {
        // Tools first, then the reply — the order they happened in, so reading the
        // thread back shows the work leading to the answer rather than after it.
        replayTools(message.tools);
        if ((message.text || '').trim()) bubble(render(message.text));
      }
    }
    paintThreads();
    markThreadBusy();
    turnLockUI();
    if (RUNNING.has(id)) {
      // The turn is still streaming into a container that was detached when this
      // transcript was repainted. Say so, rather than showing a conversation that
      // appears to have stopped mid-thought.
      // Same line, same clock. Repainting the transcript used to reset the wait to a
      // sentence with no number in it, so a four-minute turn looked like a fresh one.
      progressLine(chat(), {
        since: RUNNING.get(id) || Date.now(),
        label: 'Still working on your last message',
      });
    }
    scrollDown();
  } catch (error) { toast(String(error.message || error)); }
}

async function newThread() {
  const created = await api('/api/agent/threads', {});
  THREAD = { ...created, messages: [] };
  THREADS.unshift(created);
  localStorage.setItem('forgecast.thread', String(created.id));
  chat().innerHTML = '';
  greet();
  paintThreads();
  markThreadBusy();
  turnLockUI();
  $('#chat-input').focus();
}

/* ── attachments ────────────────────────────────────────────────────────── */
const fileURL = a => '/api/agent/file?path=' + encodeURIComponent(a.path);

function attachmentHTML(a, sent = false) {
  if (a.kind === 'image')
    return `<img class="att-sent-img" src="${fileURL(a)}" alt="${esc(a.name)}">`;
  if (a.kind === 'audio')
    return `<audio controls preload="metadata" src="${fileURL(a)}"></audio>`;
  return sent ? `<span class="att-sent">📎 ${esc(a.name)}</span>`
              : `<span>📎 ${esc(a.name)}</span>`;
}

function paintAttached() {
  const box = $('#attached');
  box.hidden = !ATTACHED.length;
  box.innerHTML = ATTACHED.map((a, i) => `
    <span class="att" title="${esc(a.path)}">
      ${attachmentHTML(a)}
      <span class="att-meta"><b>${esc(a.name)}</b>
        <span class="att-kind">${a.kind === 'audio' || a.kind === 'video'
          ? 'measured, not watched' : a.kind}</span></span>
      <button data-drop="${i}" aria-label="Remove">✕</button>
    </span>`).join('');
  $$('#attached [data-drop]').forEach(button => {
    button.onclick = () => {
      const [gone] = ATTACHED.splice(+button.dataset.drop, 1);
      paintAttached();
      api('/api/agent/detach', { path: gone.path }).catch(() => {});
    };
  });
}

/* MIME type to extension, for the cases the clipboard actually produces.
   A pasted screenshot arrives as a File with an empty name — the browser gives you
   the bytes and the type and nothing else — so the extension has to be derived or
   the server cannot tell an image from a text file, and the agent is told it has "a
   file" it cannot open. */
const EXT_FOR = {
  'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp',
  'image/bmp': 'bmp', 'image/svg+xml': 'svg', 'image/heic': 'heic',
  'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/wave': 'wav',
  'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/mp4': 'm4a', 'audio/aac': 'aac',
  'audio/flac': 'flac', 'audio/x-flac': 'flac', 'audio/ogg': 'ogg',
  'audio/webm': 'weba', 'audio/opus': 'opus',
  'video/mp4': 'mp4', 'video/quicktime': 'mov', 'video/webm': 'webm',
  'video/x-matroska': 'mkv',
  'application/pdf': 'pdf', 'application/json': 'json', 'application/zip': 'zip',
  'text/plain': 'txt', 'text/markdown': 'md', 'text/csv': 'csv', 'text/html': 'html',
};

let pasteCount = 0;

function nameFor(file) {
  // A real filename wins — a copied file from Explorer or Finder has one, and it is
  // more informative than anything derivable.
  if (file.name && file.name.trim() && file.name !== 'blob') return file.name;

  const type = (file.type || '').split(';')[0].toLowerCase();
  const ext = EXT_FOR[type] || (type.split('/')[1] || 'bin').replace('x-', '');
  const kind = type.startsWith('image/') ? 'pasted-image'
             : type.startsWith('audio/') ? 'pasted-audio'
             : type.startsWith('video/') ? 'pasted-video' : 'pasted-file';
  // Counted within the page so two pastes in one sitting do not collide before the
  // server's own de-duplication has to guess which is which.
  return `${kind}-${++pasteCount}.${ext}`;
}

async function attach(file, nameHint) {
  const name = nameHint || nameFor(file);
  const form = new FormData();
  // The third argument is the filename the server sees. Without it a clipboard blob
  // uploads as "blob" with no extension.
  form.append('file', file, name);
  try {
    const response = await fetch('/api/agent/attach', { method: 'POST', body: form });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || `failed (${response.status})`);
    ATTACHED.push(data);
    paintAttached();
  } catch (error) { toast(`${name} — ${error.message || error}`); }
}

/* Paste. Any file on the clipboard, not just images — a copied audio clip, a PDF, a
   whole folder's worth of files — because "I copied it on the PC" is the most direct
   way anything gets into this app, and the file picker is a worse version of it.

   Text is deliberately left alone: pasting a script into the composer has to keep
   working as text, and hijacking it into an attachment would be maddening. */
async function takePaste(event) {
  const data = event.clipboardData;
  if (!data) return;

  const files = [];
  // `items` carries clipboard entries; `files` carries only real files. Both are
  // needed: Chrome puts a screenshot in items with no entry in files, and Firefox
  // does the reverse for a copied file.
  for (const item of data.items || []) {
    if (item.kind !== 'file') continue;
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  for (const file of data.files || []) {
    if (!files.some(f => f.name === file.name && f.size === file.size)) files.push(file);
  }
  if (!files.length) return;              // plain text: leave it to the textarea

  event.preventDefault();
  for (const file of files) await attach(file);
  toast(files.length === 1 ? 'Attached the pasted file'
                           : `Attached ${files.length} pasted files`);
  $('#chat-input').focus();
}

/* ── one turn ─────────────────────────────────────────────────────────────
   Per thread, not per page. A long turn used to grey out the composer in every
   other conversation with nothing on screen to explain why, and switching threads
   mid-turn poured the running turn's tool cards and prose into whichever
   conversation you had just opened.

   Both come from the same mistake: treating "a turn" as a property of the window
   instead of a property of the thread it belongs to. So each turn owns a container
   element created when it starts. If you switch away, that container is detached
   with the rest of the transcript and the turn keeps writing into something nobody
   is looking at — which is exactly right, because the server is still working and
   the reply is persisted, so reopening the thread shows the finished answer. */
/* ── the progress line ──────────────────────────────────────────────────────

   "Still working on your last message" is true and useless. A turn that installs
   yt-dlp, reads a channel and writes a plan spends minutes inside a single tool, and
   with no elapsed time and no activity the line reads identically at four seconds and
   at four minutes — so the honest question it provokes is "has this hung?", which the
   UI cannot answer and the operator cannot either.

   Two things fix that and neither needs the backend to send anything new: how long it
   has been, and what it is doing right now. The tool events already carry the second. */

function humanElapsed(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  if (total < 60) return `${total}s`;
  return `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, '0')}s`;
}

function progressLine(host, { since = Date.now(), label = '' } = {}) {
  const el = document.createElement('div');
  el.className = 'thinking';
  el.innerHTML = '<i><b></b><b></b><b></b></i>'
    + '<span class="what"></span><span class="elapsed"></span>';
  const what = el.querySelector('.what');
  const elapsed = el.querySelector('.elapsed');

  what.textContent = label || 'Thinking with Claude…';
  // Ticked every second rather than driven by events, because the gap this exists to
  // fill is exactly the stretch where no events arrive.
  const tick = () => { elapsed.textContent = humanElapsed(Date.now() - since); };
  tick();
  const timer = setInterval(tick, 1000);

  el.say = text => { what.textContent = text || 'Thinking with Claude…'; };
  el.stop = () => clearInterval(timer);
  // Cleared when the node leaves the document, so a repainted transcript does not leave
  // a timer running against an element nobody can see.
  const observer = new MutationObserver(() => {
    if (!el.isConnected) { clearInterval(timer); observer.disconnect(); }
  });
  observer.observe(host, { childList: true });

  host.append(el);
  return el;
}

/* The progress line says what the tool is doing, in the words `TOOL_SAYS` already
   uses for the tool card beside it. A second table here would be a second answer to
   "what is this call called", and the two would disagree the first time either was
   edited — `toolLabel` already falls back to `calling <name>` for anything unlisted. */
function activityLabel(name) {
  const said = toolLabel(name);
  return said.charAt(0).toUpperCase() + said.slice(1);
}

const RUNNING = new Map();          // thread id -> turn start time while streaming

function turnLockUI() {
  const busy = THREAD && RUNNING.has(THREAD.id);
  $('#btn-send').disabled = !!busy;
  $('#chat-input').placeholder = busy
    ? 'still working on the last message…'
    : 'talk to the agent — paste a channel, ask what is waiting on you, or kick off a video';
}

async function send() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text && !ATTACHED.length) return;
  if (THREAD && RUNNING.has(THREAD.id)) return;

  // Claimed before the first await. A check and a set on either side of a
  // suspension point is not a lock: two quick presses of Enter both pass the check,
  // both create a thread, and two turns race to write the session id.
  SENDING = true;
  $('#btn-send').disabled = true;
  try {
    if (!THREAD) await newThread();
  } catch (error) {
    SENDING = false;
    turnLockUI();
    toast(`Could not start a chat — ${error.message || error}`);
    return;
  }

  const turnThread = THREAD.id;
  // Held, not discarded. The composer used to be cleared before the POST was known
  // to have succeeded, so a 413 on a long paste lost the text as well as rejecting
  // it — and the text was the thing that took work to write.
  const heldAttachments = ATTACHED.slice();
  const files = heldAttachments.map(a => a.path);
  const shown = heldAttachments.map(a => attachmentHTML(a, true)).join('');

  input.value = '';
  input.style.height = 'auto';
  ATTACHED = [];
  paintAttached();

  const host = document.createElement('div');
  host.className = 'turn';
  host.dataset.thread = String(turnThread);
  chat().append(host);
  bubble((shown ? `<div class="att-row">${shown}</div>` : '') + render(text), 'me', host);

  RUNNING.set(turnThread, Date.now());
  SENDING = false;
  turnLockUI();
  markThreadBusy();

  let failed = null;
  try {
    failed = await stream(text, files, host);
  } finally {
    RUNNING.delete(turnThread);
    turnLockUI();
    markThreadBusy();
  }

  if (failed) {
    // Give the message back. Losing what you typed because the server said no is
    // two failures where there should be one.
    host.remove();
    input.value = text;
    input.dispatchEvent(new Event('input'));
    ATTACHED = heldAttachments;
    paintAttached();
    toast(failed);
    return;
  }

  loadThreads();
  refreshPanel();
}

function markThreadBusy() {
  $$('#thread-list .thread').forEach(row => {
    row.classList.toggle('busy', RUNNING.has(+row.dataset.id));
  });
}

async function stream(text, files, host) {
  // A turn is a sequence of things happening, not one blob that appears at the end.
  // Tool cards and prose land in the chat in the order they occur, so the transcript
  // reads as the work rather than as a summary of it written afterwards.
  const cards = new Map();          // tool_use_id -> card element
  let reply = null;                 // the prose block currently being written into
  let body = '';

  const thinking = progressLine(host);
  scrollDown();

  const paint = () => {
    if (!reply) { reply = bubble('', 'ai', host); }
    reply.innerHTML = render(body) || '<span class="msg-wait">…</span>';
    scrollDown();
  };

  // A new tool call after some prose means that prose is finished. Starting a fresh
  // block keeps the order honest instead of appending later text to an earlier
  // paragraph that was written before the tool ran.
  const closeProse = () => { reply = null; body = ''; };

  try {
    const response = await fetch(`/api/agent/threads/${THREAD.id}/chat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, files }),
    });
    if (!response.ok) {
      // A refusal, not a crash: the server said why, and the caller restores the
      // composer instead of leaving the text lost with an error where it used to be.
      let detail = await response.text();
      try { detail = JSON.parse(detail).detail || detail; } catch { /* plain text */ }
      thinking.remove();
      return `${detail}`.slice(0, 240);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (value) buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        let event;
        try { event = JSON.parse(line); } catch { continue; }

        if (event.type === 'text') {
          thinking.hidden = true;
          thinking.say('');
          body += event.text;
          paint();
        } else if (event.type === 'tool') {
          // Kept visible now rather than hidden: the tool is the slow part, and the
          // spinner naming it is the only thing on screen during the wait it causes.
          thinking.say(activityLabel(event.name) + '…');
          thinking.hidden = false;
          host.append(thinking);
          if (worthShowing(event.name)) {
            closeProse();
            cards.set(event.id, toolCard(event, { into: host }));
          }
        } else if (event.type === 'tool_result') {
          const card = cards.get(event.id);
          if (card) fillToolCard(card, { text: event.text, isError: event.is_error });
          // The agent goes quiet again between a result and its next sentence.
          thinking.say('');
          thinking.hidden = false;
          host.append(thinking);
          scrollDown();
        } else if (event.type === 'notice') {
          closeProse();
          const note = document.createElement('div');
          note.className = 'act done';
          note.textContent = event.text;
          host.append(note);
          scrollDown();
        } else if (event.type === 'setup') {
          // Not a reply. The backend is not installed or not signed in, so no turn
          // ran and nothing was spent — rendered as a card with the buttons that fix
          // it rather than as text in the agent's bubble.
          thinking.hidden = true;
          closeProse();
          host.append(setupCard(event));
          // The banner at the top says the same thing and outlives the scroll, so it
          // is still there once this card has been scrolled past.
          paintAgentSetup(event);
          scrollDown();
        } else if (event.type === 'error') {
          thinking.hidden = true;
          closeProse();
          body = event.text;
          paint();
          if (reply) reply.classList.add('msg-bad');
        }
      }
      if (done) break;
    }
  } catch (error) {
    closeProse();
    body = `Could not reach the agent: ${error.message || error}`;
    paint();
  }

  thinking.remove();
  // Any card still marked running never got a result — the turn ended first. Saying
  // so beats a spinner that spins forever.
  for (const card of cards.values()) {
    if (card.classList.contains('running')) {
      card.classList.replace('running', 'failed');
      fillToolCard(card, { text: 'The turn ended before this returned.', isError: true });
    }
  }
  if (reply && !body.trim()) reply.remove();
  scrollDown();
  return null;
}

/* ── the state panel ────────────────────────────────────────────────────── */
function paintStatus(s) {
  const pane = $('#pane-status');
  if (s.error) { pane.innerHTML = `<h3>This install</h3><p class="sub">${esc(s.error)}</p>`; return; }

  const byFormat = s.channels?.by_format || {};
  const rows = Object.entries(byFormat)
    .map(([slug, tally]) => `<div class="kv"><span>${esc(slug)}</span><span>${tally.channels || 0} ch · ${tally.runs || 0} runs</span></div>`)
    .join('');

  pane.innerHTML = `<h3>This install</h3>
    <div class="kv"><span>Mode</span><span style="color:${s.mode === 'live' ? 'var(--ok)' : 'var(--warn)'}">${esc(s.mode)}</span></div>
    <div class="kv"><span>Credits</span><span>${s.credits}</span></div>
    <div class="kv"><span>ffmpeg</span><span style="color:${s.ffmpeg ? 'var(--ok)' : 'var(--err)'}">${s.ffmpeg ? 'present' : 'missing'}</span></div>
    <div class="kv"><span>Channels</span><span>${s.channels?.total ?? 0}</span></div>
    ${rows}
    <p class="sub" style="margin-top:10px">${esc(s.mode_means || '')}</p>`;

  const waiting = s.runs_waiting_on_you || [];
  $('#pane-waiting').hidden = !waiting.length;
  $('#waiting-body').innerHTML = waiting.map(w => `
    <div class="gatecard">
      <b>Run ${w.run}</b> — ${esc(w.channel)}<br>
      <span class="muted">${esc(w.topic)}</span><br>
      <a href="/runs/${w.run}" style="font-size:12px">open it →</a>
    </div>`).join('');

  paintStudio(s.studio || {});
}

/* ── the Studio ─────────────────────────────────────────────────────────────
   Dormant until there is something to draw, and it says which. An empty player
   is a worse answer to "what is this panel" than one sentence explaining that no
   run has written a script yet. */
let STUDIO_RUN = null;

function paintStudio(studio) {
  const badge = $('#studio-state');
  const body = $('#studio-body');
  const open = $('#studio-open');
  badge.className = 'livedot ' + (studio.state || 'asleep');
  badge.textContent = studio.state || 'asleep';

  if (studio.state === 'live' && studio.url) {
    open.hidden = false;
    open.href = studio.url.replace('?embed=1', '');
    // Only rebuilt when the run changes — replacing the iframe on every poll would
    // restart the player mid-scrub, every few seconds, forever.
    if (STUDIO_RUN !== studio.run) {
      STUDIO_RUN = studio.run;
      body.innerHTML =
        `<iframe class="studio-frame" src="${esc(studio.url)}" title="Preview"></iframe>
         <p class="sub" style="margin-top:9px">Run ${studio.run} · ${esc(studio.channel || '')}<br>
         <span class="muted">${esc(studio.topic || '')}</span></p>`;
    }
    return;
  }

  STUDIO_RUN = null;
  open.hidden = true;
  body.innerHTML = studio.run
    ? `<p class="sub">${esc(studio.reason || 'Nothing to draw yet.')}</p>
       <button class="btn-sm w-full" style="margin-top:9px"
               onclick="location.href='/runs/${studio.run}'">Open run ${studio.run}</button>`
    : `<p class="sub">${esc(studio.reason || 'No run to preview yet.')}</p>`;
}

function paintAuth(a) {
  $('#claude-detail').innerHTML = a.ok
    ? esc(a.detail) + (a.account ? `<br><span class="muted">${esc(a.account)}</span>` : '')
    : `<b style="color:var(--warn)">${esc(a.headline)}</b><br>${esc(a.detail)}`
      + ((a.fixes || []).length
          ? `<pre style="margin-top:9px;white-space:pre-wrap">${esc(a.fixes.join('\n'))}</pre>` : '');
  $('#claude-actions').hidden = a.ok;
  $('#btn-login').hidden = !a.can_login;
  paintAgentSetup(a);
}

/* ── the agent's own setup ──────────────────────────────────────────────────
   An uninstalled backend is not a failed turn: nothing ran, nothing was spent, and
   what fixes it is a button rather than a rephrased question. So it gets the banner a
   missing tool gets, and — when it is discovered mid-send — a card in the transcript
   that is visibly not the agent talking.

   Both are painted from the same fields, because both are describing the same thing.
   The sign-in check on page load fills them in before anything is typed, which is the
   half that stops it being discovered by asking a question and being answered with an
   npm command. */
/* Both sources carry it: `/api/agent/auth` adds it in `engines.auth_check`, and the
   chat route stamps it onto a setup event as it goes past. The fallback is for a build
   where one of them forgot — a card headed "This agent" is wrong-ish, a card headed
   "undefined" is broken. */
function agentSetupName(report) {
  return report.engine_label || 'This agent';
}

function paintAgentSetup(report) {
  const banner = $('#toolbar-agent');
  if (!banner) return;
  if (!report || report.ok) { banner.hidden = true; return; }
  $('#agent-setup-text').innerHTML =
    `<b>${esc(agentSetupName(report))} — ${esc(report.headline)}</b> `
    + `<span class="muted">${esc(report.detail || '')}</span>`;
  $('#agent-setup-login').hidden = !report.can_login;
  banner.hidden = false;
}

function setupCard(report) {
  const box = document.createElement('div');
  box.className = 'setupcard';
  const fixes = (report.fixes || []).join('\n');
  box.innerHTML =
    `<b>${esc(agentSetupName(report))} — ${esc(report.headline)}</b>`
    + `<div>${esc(report.detail || '')}</div>`
    + (fixes ? `<pre>${esc(fixes)}</pre>` : '')
    + `<div class="row">`
    + (report.can_login ? `<button class="btn-sm primary" data-role="login">Sign in</button>` : '')
    + `<button class="btn-sm" data-role="check">Check again</button>`
    + `<a class="btn btn-sm" href="/settings#agent">Open settings</a></div>`;
  const login = box.querySelector('[data-role="login"]');
  if (login) login.onclick = () => startLogin();
  box.querySelector('[data-role="check"]').onclick = () =>
    refreshAuth().then(() => toast('Checked'));
  return box;
}

async function startLogin() {
  const result = await api('/api/agent/auth/login', {});
  toast(result.message);
}

const refreshAuth = () => api('/api/agent/auth').then(paintAuth).catch(() => {});

/* Published on `window` because the engine picker lives in an inline script in
   chat.html, outside this module's closure. It was already calling
   `typeof refreshAuth === 'function'` before repainting — which is always false from
   there, so the call silently did nothing and the panel kept showing the *previous*
   agent's sign-in state under the new agent's heading. Reported: the ChatGPT panel said
   "Claude can run this studio" and "max subscription" while listing ChatGPT's limits.
   A guard that can never pass is worse than no guard: it reads as handled. */
window.forgecastRefreshAuth = refreshAuth;
const refreshPanel = () => api('/api/agent/status').then(paintStatus).catch(() => {});

/* The empty state. One obvious first move, then three concrete starting points —
   whole sentences you can send as they are, not category labels you would then have
   to write the actual request for. */
const IDEAS = [
  { icon: '▶', title: 'Model an existing channel',
    say: 'Set up a channel modelled on https://youtube.com/@  — read what they '
       + 'publish first and show me what you measured before creating anything.' },
  { icon: '◎', title: 'Mine a niche for outliers',
    say: 'Find what is genuinely outperforming in this niche, quote the multiples, '
       + 'and tell me what transfers and what was specific to them.' },
  { icon: '✦', title: 'See what is waiting on me',
    say: 'What is waiting on a decision right now, and what is each gate holding?' },
];

function greet() {
  const box = document.createElement('div');
  box.className = 'opener';
  box.id = 'chat-empty';
  box.innerHTML = `
    <div class="glyph">◆</div>
    <h2>What are we making?</h2>
    <p>Paste a channel and I will read what it actually publishes, or describe the
       idea and I will shape it. I hold this studio as tools, so I can do the work
       rather than tell you which button to press.</p>
    <button class="primary" id="opener-go">Set up a channel from a link</button>
    <div class="or">or start from an idea</div>
    ${IDEAS.map((idea, index) => `
      <button class="idea" data-idea="${index}">
        <span class="ico">${idea.icon}</span>
        <span class="txt"><b>${esc(idea.title)}</b><span>${esc(idea.say)}</span></span>
        <span class="go">→</span>
      </button>`).join('')}`;
  chat().append(box);

  const prefill = say => {
    const input = $('#chat-input');
    input.value = say;
    input.focus();
    input.dispatchEvent(new Event('input'));
    // Cursor where the link goes, so the first thing you type lands in the gap
    // rather than after the full stop.
    const gap = say.indexOf('@ ');
    if (gap > -1) input.setSelectionRange(gap + 1, gap + 1);
  };
  $('#opener-go').onclick = () => prefill(IDEAS[0].say);
  $$('#chat-empty [data-idea]').forEach(button => {
    button.onclick = () => prefill(IDEAS[+button.dataset.idea].say);
  });
}

/* ── wiring ─────────────────────────────────────────────────────────────── */
$('#btn-new').onclick = () => newThread().catch(e => toast(String(e.message || e)));
// Once, on the one menu element — not per row, which would rebind on every repaint and
// leave a document-level closer behind each time.
wireRowMenu();
$('#btn-send').onclick = () => send().catch(
  error => toast(String(error.message || error)));
$('#btn-attach').onclick = () => $('#attach-file').click();
$('#attach-file').onchange = async event => {
  for (const file of event.target.files) await attach(file);
  event.target.value = '';
  $('#chat-input').focus();
};

const dropZone = $('#chatcol');
['dragenter', 'dragover'].forEach(name => dropZone.addEventListener(name, event => {
  event.preventDefault(); dropZone.classList.add('over');
}));
['dragleave', 'drop'].forEach(name => dropZone.addEventListener(name, event => {
  event.preventDefault(); dropZone.classList.remove('over');
}));
dropZone.addEventListener('drop', async event => {
  for (const file of event.dataTransfer.files) await attach(file);
});
document.addEventListener('paste', takePaste);

(function composer(el) {
  const grow = () => {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 220) + 'px';
  };
  el.addEventListener('input', grow);
  el.addEventListener('keydown', event => {
    // Enter sends, Shift+Enter breaks the line. A pasted script arrives through
    // paste rather than keystrokes, so this never eats one.
    if (event.key !== 'Enter' || event.shiftKey) return;
    // Enter also accepts an IME candidate. Sending here would fire off the raw
    // pre-conversion reading and clear the box — so anyone typing Japanese, Chinese
    // or Korean could not write a channel name at all. keyCode 229 is the same
    // signal on browsers that do not set isComposing.
    if (event.isComposing || event.keyCode === 229) return;
    if (event.repeat) return;             // held Enter is one message, not thirty
    event.preventDefault();
    send().catch(error => toast(String(error.message || error)));
    requestAnimationFrame(() => { el.style.height = 'auto'; });
  });
})($('#chat-input'));

$('#btn-login').onclick = () => startLogin();
$('#btn-recheck').onclick = () => refreshAuth().then(() => toast('Checked'));
if ($('#agent-setup-login')) $('#agent-setup-login').onclick = () => startLogin();
if ($('#agent-setup-check')) {
  $('#agent-setup-check').onclick = () => refreshAuth().then(() => toast('Checked'));
}

api('/api/agent/prefs').then(p => {
  $('#model-pick').innerHTML = (p.models || []).map(m =>
    `<option value="${m.id}"${m.id === p.model ? ' selected' : ''} title="${esc(m.note)}">${esc(m.label)}</option>`
  ).join('');
  $('#confirm-edits').checked = p.confirm_edits;
}).catch(() => {});

const savePrefs = body => api('/api/agent/prefs', body).catch(() => {});
$('#model-pick').onchange = event => {
  savePrefs({ model: event.target.value });
  toast(`Answering with ${event.target.selectedOptions[0].textContent}`);
};
$('#confirm-edits').onchange = event => {
  savePrefs({ confirm_edits: event.target.checked });
  toast(event.target.checked ? 'It will ask before editing a file'
                             : 'It will edit and tell you afterwards');
};

/* ── open ───────────────────────────────────────────────────────────────── */
(async function start() {
  refreshAuth();
  refreshPanel();
  await loadThreads();

  // A link handed over from the workspace always starts its own thread. Dropping it
  // into whichever conversation happened to be open would bury it under unrelated
  // history and give the agent the wrong context to answer from.
  const opening = ($('.studio')?.dataset.opening || '').trim();
  if (opening) {
    history.replaceState(null, '', '/');
    await newThread();
    $('#chat-input').value = opening;
    await send();
    return;
  }

  const remembered = +(localStorage.getItem('forgecast.thread') || 0);
  if (remembered && THREADS.some(t => t.id === remembered)) await openThread(remembered);
  else if (THREADS.length) await openThread(THREADS[0].id);
  else { chat().innerHTML = ''; greet(); }
})();

})();
