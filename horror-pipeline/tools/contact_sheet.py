#!/usr/bin/env python3
"""The human approval gate. One card per image, ticked in a browser, written
back to materials/<creature>.json.

Every canon failure in this channel's QC history traces to one root cause: the
materials sheet shipped without a locked per-creature image shortlist, so the
editor chose images himself. The wrong creature frozen for nine seconds. Fan
art contradicting the narration. An asset rotated 180 degrees so it read as the
opposite of the creature. Three mutually inconsistent designs in one section.
This page is the fix, and it is not advisory: nothing renders until every image
a sheet uses has approved: true, and until exactly one image carries the
design_lock for its creature.

PROVENANCE POLICY. Fan art is TOLERATED on this channel, per the owner's
explicit 21 Jul decision. The hard rule is that an image must never contradict
the narration line it plays under. So provenance is a LABEL on the card, never
an automatic rejection. Only four categories block, because each has actually
shipped and had to be pulled:

    licensed-character   real-identifiable-person   meme-photograph
    identifiable-minor

Those four are drawn in red, cannot be missed, and force the image unapproved.

Modes
  serve <materials.json> [--port 8765]
      Serves the page on 127.0.0.1 and accepts a POST that writes the JSON back
      to disk. This is the mode you want: a file:// page cannot write to disk.

  build <materials.json> [--out FILE]
      Emits one standalone self-contained HTML file with a "download JSON"
      fallback, for when the owner is not on the machine. Every thumbnail is
      inlined, so it survives being emailed and works with no network.

What each card shows, and why. The reviewer has to judge a matte in about a
second, so per docs/cutout-evaluation-2026-08-09.md section 8.2 each card
carries three panels: the source thumbnail, the same frame gamma-lifted to 0.45
(on unlifted dark horror art the limbs are invisible on a normal monitor), and
a 1-bit silhouette preview. The question the silhouette answers is not "is this
shape correct" but "is this shape findable at all" - if the blob looks like the
creature it is a cutout candidate, and if it is a smear that includes the
building it is not.
"""
import argparse, base64, hashlib, io, json, os, re, shutil, sys, tempfile

# ------------------------------------------------------------------ constants

HARD_FLAGS = ["licensed-character", "real-identifiable-person",
              "meme-photograph", "identifiable-minor"]

PROVENANCE = ["official-gallery", "creator-account", "fan-art", "game-model",
              "wallpaper-scrape", "unknown"]

# Fields the page is allowed to write. Everything else in the record (file,
# phash, source_url, size, meta) is machine-owned and a browser must never be
# able to overwrite it.
WRITABLE = ["description", "not_visible", "setting", "time_of_day",
            "design_variant", "provenance", "hard_flags", "cutout_suitable",
            "cutout_note", "cutout_status", "approved", "design_lock", "notes"]

# A creature occupying under about 2 percent of the frame is a strong warning
# sign that no model will find its edge. Measured: Heiscoming.jpg 1.1 percent
# (unmattable), Cartoon-cat.jpeg 9.0 percent (clean matte).
SUBJECT_PCT_WARN = 2.0


# ------------------------------------------------------------------ previews

def _otsu(hist, total):
    """Otsu threshold over a 256-bin histogram."""
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = w_b = 0.0
    best, best_t = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best:
            best, best_t = var, t
    return best_t


def panels(path, wide=340):
    """(thumb_jpg, lifted_jpg, silhouette_png, subject_pct) as raw bytes.

    The silhouette is model-free on purpose: it is instant, it needs no weights,
    and the reviewer is only being asked whether a shape is findable. It works
    on distance from the DOMINANT tone rather than absolute brightness, so it
    behaves the same on a pale creature over a dark sky and a dark creature over
    a light print.
    """
    from PIL import Image
    import numpy as np

    im = Image.open(path).convert("RGB")
    im.thumbnail((wide, wide))

    def jpg(pil, q=82):
        b = io.BytesIO(); pil.save(b, "JPEG", quality=q); return b.getvalue()

    a = np.asarray(im, dtype=np.float32) / 255.0
    lift = Image.fromarray((np.clip(a, 0, 1) ** 0.45 * 255).astype("uint8"))

    small = im.copy(); small.thumbnail((200, 200))
    lum = np.asarray(small.convert("L"), dtype=np.float32)
    diff = np.abs(lum - float(np.median(lum)))
    d8 = np.clip(diff, 0, 255).astype("uint8")
    hist = np.bincount(d8.ravel(), minlength=256).tolist()
    t = _otsu(hist, d8.size)
    mask = d8 > t
    pct = round(100.0 * float(mask.mean()), 1)

    sil = Image.fromarray(np.where(mask, 20, 245).astype("uint8"), "L").convert("1")
    b = io.BytesIO(); sil.save(b, "PNG"); sil_png = b.getvalue()

    return jpg(im), jpg(lift), sil_png, pct


def data_uri(raw, mime):
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# ------------------------------------------------------------------ page

CSS = """
:root{--bg:#0d0d0f;--panel:#17171b;--line:#2a2a31;--ink:#f2f2f4;--dim:#8b8b96;
      --ok:#3fa66a;--warn:#d8a13a;--bad:#d62020;--lock:#4a7fd4;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);
     font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
     padding-bottom:90px}
a{color:#7fb0ff}
code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dim)}

header{position:sticky;top:0;z-index:20;background:#101014;
       border-bottom:1px solid var(--line);padding:12px 18px}
h1{font-size:15px;font-weight:650;letter-spacing:.2px;margin-bottom:8px}
h1 small{color:var(--dim);font-weight:400;margin-left:8px}
.stats{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:7px;
      padding:5px 11px;font-size:12px;letter-spacing:.02em}
.stat b{font-variant-numeric:tabular-nums;font-size:14px;margin-right:5px}
.stat.ok{border-color:var(--ok);color:#9ae2bb}
.stat.bad{border-color:var(--bad);color:#ff9b9b;background:#2a1214}
.stat.warn{border-color:var(--warn);color:#f2d59a}

.gate{margin-top:9px;padding:8px 12px;border-radius:7px;font-size:13px;
      font-weight:650;letter-spacing:.03em}
.gate.blocked{background:#2a1214;border:1px solid var(--bad);color:#ff9b9b}
.gate.clear{background:#122a1c;border:1px solid var(--ok);color:#9ae2bb}

.wrap{padding:16px 18px;display:grid;gap:14px;
      grid-template-columns:repeat(auto-fill,minmax(430px,1fr))}

.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
      overflow:hidden;display:flex;flex-direction:column}
.card.locked{border-color:var(--lock);box-shadow:0 0 0 1px var(--lock) inset}
.card.flagged{border-color:var(--bad);box-shadow:0 0 0 2px var(--bad) inset;
              background:#1d1214}

/* Fixed row height so every card's panels line up when you scan down the page.
   Three panels, one row, judgeable in about a second: what is there, what is
   there once the darkness is lifted, and whether the shape is findable. */
.imgs{display:grid;grid-template-columns:1.7fr 1fr 1fr;gap:1px;background:#000;
      height:196px}
.imgs figure{position:relative;background:#08080a;display:flex;align-items:center;
             justify-content:center;overflow:hidden}
.imgs img{width:100%;height:100%;object-fit:contain;display:block}
.imgs figcaption{position:absolute;left:0;bottom:0;background:rgba(0,0,0,.72);
                 color:var(--dim);font-size:9px;letter-spacing:.09em;
                 text-transform:uppercase;padding:2px 5px}

.body{padding:11px 13px;display:flex;flex-direction:column;gap:9px;flex:1}
.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.ttl{font-size:12px;font-weight:650;word-break:break-word}
.ord{color:var(--dim);font-size:11px;white-space:nowrap;font-variant-numeric:tabular-nums}

.chips{display:flex;gap:6px;flex-wrap:wrap;font-size:11px}
.chip{border:1px solid var(--line);border-radius:20px;padding:2px 9px;color:var(--dim)}
.chip.small{border-color:var(--warn);color:#f2d59a}
.chip.prov{border-color:#3d4a5e;color:#a8c0e0}
.chip.prov[data-p="fan-art"],.chip.prov[data-p="wallpaper-scrape"],
.chip.prov[data-p="game-model"]{border-color:var(--warn);color:#f2d59a}
.chip.prov[data-p="unknown"]{border-color:#5a4a2a;color:#c8b088}

/* The flag row is QUIET until a flag is actually set. Painting every card red
   would make red the page's resting state and the one genuinely flagged card
   would disappear into it, which is the opposite of the point. */
.flagbar{border:1px dashed var(--line);border-radius:7px;padding:7px 10px}
.flagbar .hdr{color:var(--dim);font-weight:650;font-size:10px;letter-spacing:.1em;
              text-transform:uppercase;margin-bottom:5px}
.flagbar label{display:inline-flex;align-items:center;gap:5px;margin:0 12px 3px 0;
               font-size:12px;color:var(--dim);cursor:pointer}
.flagbar input{accent-color:var(--bad);cursor:pointer}
.card.flagged .flagbar{border:1px solid var(--bad);background:#2a1214}
.card.flagged .flagbar .hdr,.card.flagged .flagbar label{color:#ff9b9b}
.card.flagged .flagbar .hdr{color:#ff5b5b;font-weight:800;font-size:11px}
.blocked-note{color:#ff5b5b;font-size:12px;font-weight:800;margin-top:6px;
              display:none;letter-spacing:.03em}
.card.flagged .blocked-note{display:block}
/* a flagged card is unmissable while scrolling, not just when you reach it */
.card.flagged::before{content:"HARD FLAG";position:absolute;top:0;left:0;z-index:5;
      background:var(--bad);color:#fff;font-size:10px;font-weight:800;
      letter-spacing:.14em;padding:4px 10px;border-radius:0 0 7px 0}
.card{position:relative}

label.f{display:block;font-size:10px;letter-spacing:.09em;text-transform:uppercase;
        color:var(--dim);margin-bottom:3px}
textarea,input[type=text],select{width:100%;background:#0f0f12;color:var(--ink);
        border:1px solid var(--line);border-radius:6px;padding:7px 8px;font:inherit;
        font-size:12.5px;resize:vertical}
textarea:focus,input:focus,select:focus{outline:none;border-color:#4a4a57}
textarea.desc{min-height:132px}
textarea.nv{min-height:58px}
textarea.notes{min-height:70px}

.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.row > div{flex:1;min-width:150px}
.ctl{display:flex;gap:14px;align-items:center;padding-top:4px;border-top:1px solid var(--line);
     margin-top:auto}
.ctl label{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer;
           user-select:none}
.ctl input[type=checkbox],.ctl input[type=radio]{width:17px;height:17px;cursor:pointer;
           accent-color:var(--ok)}
.ctl input[type=radio]{accent-color:var(--lock)}
.ctl .lockw{color:#a8c8ff}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg button{background:#0f0f12;color:var(--dim);border:0;padding:4px 10px;font:inherit;
            font-size:11.5px;cursor:pointer;border-right:1px solid var(--line)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed=true]{background:var(--ink);color:#111;font-weight:650}

footer{position:fixed;left:0;right:0;bottom:0;z-index:30;background:#101014;
       border-top:1px solid var(--line);padding:11px 18px;display:flex;gap:12px;
       align-items:center;flex-wrap:wrap}
button.act{background:var(--ink);color:#111;border:0;border-radius:7px;
           padding:9px 20px;font:inherit;font-size:13px;font-weight:650;cursor:pointer}
button.act.ghost{background:var(--panel);color:var(--ink);border:1px solid var(--line);
                 font-weight:400}
button.act:disabled{opacity:.4;cursor:not-allowed}
#msg{font-size:12.5px;color:var(--dim)}
#msg.ok{color:#9ae2bb}
#msg.err{color:#ff9b9b}
.legend{color:var(--dim);font-size:11px;margin-left:auto;text-align:right;line-height:1.35}
"""

JS = r"""
const DOC = __DOC__;
const MODE = "__MODE__";
const HARD = __HARD__;

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

function cardState(el) {
  const flags = $$('input.hf', el).filter(i => i.checked).map(i => i.value);
  return {
    order: +el.dataset.order,
    description: $('.desc', el).value.trim(),
    not_visible: $('.nv', el).value.split('\n').map(s => s.trim()).filter(Boolean),
    setting: $('.setting', el).value.trim(),
    time_of_day: $('.tod', el).value.trim(),
    design_variant: $('.variant', el).value.trim(),
    provenance: $('.prov', el).value,
    hard_flags: flags,
    cutout_suitable: (() => { const v = $('.cutgrp', el).dataset.v;
                              return v === '' ? null : v === 'true'; })(),
    cutout_note: $('.cutnote', el).value.trim(),
    cutout_status: $('.cutgrp', el).dataset.v === 'true' ? 'pending' : 'n/a',
    approved: $('.approve', el).checked,
    design_lock: $('.lock', el).checked,
    notes: $('.notes', el).value.trim(),
  };
}

function collect() { return $$('.card').map(cardState); }

/* A hard flag BLOCKS. It is not advice. Each of these four has shipped on this
   channel and had to be pulled, so the gate refuses to let one through even if
   the reviewer ticks approve afterwards. */
function enforce(el) {
  const flagged = $$('input.hf', el).some(i => i.checked);
  const ap = $('.approve', el), lk = $('.lock', el);
  el.classList.toggle('flagged', flagged);
  if (flagged) { ap.checked = false; lk.checked = false; }
  ap.disabled = flagged;
  lk.disabled = flagged || !ap.checked;
  if (!ap.checked) lk.checked = false;
  el.classList.toggle('locked', lk.checked);
}

function refresh() {
  $$('.card').forEach(enforce);
  const st = collect();
  const n = st.length;
  const described = st.filter(s => s.description).length;
  const approved = st.filter(s => s.approved).length;
  const locks = st.filter(s => s.design_lock).length;
  const flagged = st.filter(s => s.hard_flags.length).length;
  const unjudged = st.filter(s => s.cutout_suitable === null).length;

  const set = (id, v, cls) => {
    const e = $('#' + id); $('b', e).textContent = v;
    e.className = 'stat' + (cls ? ' ' + cls : '');
  };
  set('s-total', n);
  set('s-desc', described + '/' + n, described === n ? 'ok' : 'warn');
  set('s-appr', approved, approved ? 'ok' : 'warn');
  set('s-lock', locks, locks === 1 ? 'ok' : 'bad');
  set('s-flag', flagged, flagged ? 'bad' : '');
  set('s-cut', unjudged, unjudged ? 'warn' : 'ok');

  const problems = [];
  if (approved === 0) problems.push('nothing approved yet');
  if (locks === 0) problems.push('DESIGN LOCK NOT SET, exactly one image must carry it');
  if (locks > 1) problems.push('DESIGN LOCK SET ON ' + locks + ' IMAGES, exactly one is allowed');
  if (described < n) problems.push((n - described) + ' image(s) still undescribed, the canon validator cannot run');
  if (flagged) problems.push(flagged + ' image(s) carry a hard flag and are forced unapproved');

  const g = $('#gate');
  if (problems.length) {
    g.className = 'gate blocked';
    g.textContent = 'BLOCKED: ' + problems.join('  |  ');
  } else {
    g.className = 'gate clear';
    g.textContent = 'GATE CLEAR: ' + approved + ' of ' + n +
      ' images approved, design lock set, every image described. Save to write it back.';
  }
}

function wire() {
  $$('.card').forEach(el => {
    $$('input,textarea,select', el).forEach(i =>
      i.addEventListener('input', refresh));
    $$('.cutgrp button', el).forEach(b => b.addEventListener('click', () => {
      const g = b.parentElement; g.dataset.v = b.dataset.v;
      $$('button', g).forEach(x => x.setAttribute('aria-pressed', x === b));
      refresh();
    }));
    /* A radio group cannot express "none", so clicking the checked lock clears
       it. Without this the reviewer can never get back to zero to start over. */
    $('.lock', el).addEventListener('click', ev => {
      if (el.dataset.wasLocked === '1') { ev.target.checked = false; }
      $$('.card').forEach(c => c.dataset.wasLocked = $('.lock', c).checked ? '1' : '0');
      refresh();
    });
  });
  $$('.card').forEach(c => c.dataset.wasLocked = $('.lock', c).checked ? '1' : '0');
  refresh();
}

function merged() {
  const by = {}; collect().forEach(s => by[s.order] = s);
  const out = JSON.parse(JSON.stringify(DOC));
  out.images.forEach(r => Object.assign(r, by[r.order] || {}));
  return out;
}

function say(t, cls) { const m = $('#msg'); m.textContent = t; m.className = cls || ''; }

async function save() {
  const btn = $('#save'); btn.disabled = true; say('saving...');
  try {
    const r = await fetch('/save', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({images: collect()}),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.error || ('HTTP ' + r.status));
    say('written to ' + j.path + '  (' + j.approved + ' approved, ' +
        j.locked + ' design lock)', 'ok');
  } catch (e) {
    say('SAVE FAILED, nothing was written: ' + e.message, 'err');
  } finally { btn.disabled = false; }
}

function download() {
  const blob = new Blob([JSON.stringify(merged(), null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = DOC.creature + '.json';
  a.click(); URL.revokeObjectURL(a.href);
  say('downloaded ' + DOC.creature + '.json, copy it over projects/<slug>/materials/' +
      DOC.creature + '.json', 'ok');
}

document.addEventListener('DOMContentLoaded', () => {
  wire();
  if (MODE === 'serve') $('#save').addEventListener('click', save);
  $('#download').addEventListener('click', download);
});
"""


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _jsonjs(obj):
    """JSON safe to drop inside a <script> block. A description that happened to
    contain the characters `</script>` would otherwise close the tag and take
    the rest of the page with it, and descriptions are free text a human types."""
    return (json.dumps(obj).replace("</", "<\\/")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render(doc, root, remote_thumbs=False):
    creature = doc.get("creature", "creature")
    imgs = doc.get("images", [])
    cards = []

    for rec in imgs:
        order = rec.get("order", 0)
        title = (rec.get("wiki_title") or os.path.basename(rec.get("file", "")))
        if title.lower().startswith("file:"):
            title = title[5:]
        w, h = (rec.get("size") or [0, 0])[:2]

        # Panels. Local generation beats the wiki thumb URL: the page then works
        # offline, survives being emailed, and cannot be changed under us by a
        # re-upload on the wiki.
        pct = None
        src = os.path.join(root, rec.get("file", "")) if rec.get("file") else None
        if src and os.path.exists(src) and not remote_thumbs:
            try:
                t, l, s, pct = panels(src)
                thumb = data_uri(t, "image/jpeg")
                lifted = data_uri(l, "image/jpeg")
                silh = data_uri(s, "image/png")
            except Exception as e:
                print(f"  preview failed for {title}: {e}", file=sys.stderr)
                thumb = rec.get("thumb") or ""
                lifted = silh = ""
        else:
            thumb = rec.get("thumb") or ""
            lifted = silh = ""

        flags = rec.get("hard_flags") or []
        cut = rec.get("cutout_suitable")
        cutv = "" if cut is None else ("true" if cut else "false")

        chips = [f'<span class="chip">{w}x{h}</span>']
        if w and h and min(w, h) < 900:
            chips.append(f'<span class="chip small">under 900px, upscale</span>')
        p = rec.get("provenance") or "unknown"
        chips.append(f'<span class="chip prov" data-p="{esc(p)}">{esc(p)}</span>')
        if pct is not None:
            cls = "chip small" if pct < SUBJECT_PCT_WARN else "chip"
            # Honest label: this is everything that differs from the dominant
            # tone, which is an upper bound on the subject, not the subject. It
            # is only load-bearing at the bottom end, where a tiny number means
            # no model will find an edge.
            chips.append(f'<span class="{cls}" title="share of the frame that '
                         f'differs from the dominant tone; under '
                         f'{SUBJECT_PCT_WARN}% means no model will find an edge">'
                         f'off-background ~{pct}%</span>')
        if rec.get("wiki_page"):
            chips.append(f'<a class="chip" href="{esc(rec["wiki_page"])}" '
                         f'target="_blank" rel="noopener">wiki file page</a>')

        provopts = "".join(
            f'<option value="{esc(o)}"{" selected" if o == p else ""}>{esc(o)}</option>'
            for o in PROVENANCE)

        flagboxes = "".join(
            f'<label><input type="checkbox" class="hf" value="{esc(f)}"'
            f'{" checked" if f in flags else ""}> {esc(f)}</label>'
            for f in HARD_FLAGS)

        segbtn = "".join(
            f'<button type="button" data-v="{v}" aria-pressed="{str(v == cutv).lower()}">'
            f'{lab}</button>'
            for v, lab in (("true", "cuttable"), ("false", "plate only"), ("", "unjudged")))

        figs = []
        for uri, cap in ((thumb, "source"), (lifted, "gamma 0.45"), (silh, "silhouette")):
            if uri:
                figs.append(f'<figure><img src="{uri}" alt="{esc(cap)}" loading="lazy">'
                            f'<figcaption>{cap}</figcaption></figure>')
        while len(figs) < 3:
            figs.append('<figure><figcaption>no preview</figcaption></figure>')

        cards.append(f"""
<section class="card{' flagged' if flags else ''}{' locked' if rec.get('design_lock') else ''}"
         data-order="{order}">
  <div class="imgs">{''.join(figs)}</div>
  <div class="body">
    <div class="top">
      <div class="ttl">{esc(title)}</div>
      <div class="ord">page #{order}</div>
    </div>
    <div class="chips">{''.join(chips)}</div>

    <div class="flagbar">
      <div class="hdr">hard flags: blocking. Each of these four has shipped and been pulled</div>
      {flagboxes}
      <div class="blocked-note">FLAGGED. This image cannot be approved and cannot hold the design lock.</div>
    </div>

    <div><label class="f">description: what is literally visible</label>
      <textarea class="desc" spellcheck="false">{esc(rec.get('description'))}</textarea></div>

    <div><label class="f">not visible: one per line, the validator diffs these against the VO</label>
      <textarea class="nv" spellcheck="false">{esc(chr(10).join(rec.get('not_visible') or []))}</textarea></div>

    <div class="row">
      <div><label class="f">setting</label>
        <input type="text" class="setting" value="{esc(rec.get('setting'))}"></div>
      <div><label class="f">time of day</label>
        <input type="text" class="tod" value="{esc(rec.get('time_of_day'))}"></div>
    </div>
    <div class="row">
      <div><label class="f">design variant</label>
        <input type="text" class="variant" value="{esc(rec.get('design_variant'))}"></div>
      <div><label class="f">provenance: a label, never a rejection</label>
        <select class="prov">{provopts}</select></div>
    </div>

    <div class="row">
      <div><label class="f">cutout suitable</label>
        <span class="seg cutgrp" data-v="{cutv}">{segbtn}</span></div>
      <div><label class="f">cutout note</label>
        <input type="text" class="cutnote" value="{esc(rec.get('cutout_note'))}"></div>
    </div>

    <div><label class="f">notes</label>
      <textarea class="notes" spellcheck="false">{esc(rec.get('notes'))}</textarea></div>

    <div class="ctl">
      <label><input type="checkbox" class="approve"
        {' checked' if rec.get('approved') else ''}> approved</label>
      <label class="lockw"><input type="radio" name="design_lock" class="lock"
        {' checked' if rec.get('design_lock') else ''}> design lock</label>
    </div>
  </div>
</section>""")

    body = f"""<title>{esc(creature)}: image approval gate</title>
<style>{CSS}</style>
<header>
  <h1>{esc(creature)}<small>{esc(doc.get('wiki',''))} / {esc(doc.get('page',''))}
      &middot; fetched {esc(doc.get('fetched',''))}
      &middot; <a href="{esc(doc.get('source_of_truth',''))}" target="_blank"
                  rel="noopener">source of truth</a></small></h1>
  <div class="stats">
    <span class="stat" id="s-total"><b>0</b>images</span>
    <span class="stat" id="s-desc"><b>0</b>described</span>
    <span class="stat" id="s-appr"><b>0</b>approved</span>
    <span class="stat" id="s-lock"><b>0</b>design lock</span>
    <span class="stat" id="s-flag"><b>0</b>hard flagged</span>
    <span class="stat" id="s-cut"><b>0</b>cutout unjudged</span>
  </div>
  <div class="gate" id="gate"></div>
</header>
<main class="wrap">{''.join(cards)}</main>
<footer>
  <button class="act" id="save"{'' if True else ''}>Save to disk</button>
  <button class="act ghost" id="download">Download JSON</button>
  <span id="msg"></span>
  <span class="legend">Fan art is allowed. Contradiction is not.<br>
    The silhouette panel answers "is this shape findable", not "is it correct".</span>
</footer>
<script>{JS.replace('__DOC__', _jsonjs(doc)).replace('__MODE__', '{MODE}').replace('__HARD__', _jsonjs(HARD_FLAGS))}</script>
"""
    return body


def build_html(doc, root, mode, remote_thumbs=False):
    html = render(doc, root, remote_thumbs)
    html = html.replace("{MODE}", mode)
    if mode != "serve":
        html = html.replace('<button class="act" id="save">Save to disk</button>',
                            '<button class="act" id="save" disabled '
                            'title="build mode is read-only: run '
                            '`contact_sheet.py serve` to write to disk">'
                            'Save to disk (serve mode only)</button>')
    return "<!doctype html>\n<meta charset=utf-8>\n" + html


# ------------------------------------------------------------------ write-back

def merge_and_write(path, incoming):
    """Merge the page's edits into the file ON DISK and write it atomically.

    Deliberately a merge, not a replace: the page only owns the reviewer's
    fields. file, phash, source_url, size and meta stay whatever the crawler
    recorded, so a stale tab cannot silently rewrite provenance data, and a
    half-loaded page cannot truncate the record.
    """
    doc = json.load(open(path))
    by = {int(r["order"]): r for r in incoming if "order" in r}
    seen = 0
    for rec in doc.get("images", []):
        src = by.get(int(rec.get("order", -1)))
        if not src:
            continue
        seen += 1
        for k in WRITABLE:
            if k in src:
                rec[k] = src[k]
        if rec.get("hard_flags"):          # blocking, enforced server-side too
            rec["approved"] = False
            rec["design_lock"] = False

    locks = [r for r in doc["images"] if r.get("design_lock")]
    if len(locks) > 1:                      # a radio group cannot do this, a bad
        for r in locks[1:]:                 # POST can. Keep the first, drop the rest.
            r["design_lock"] = False
        locks = locks[:1]

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)) or ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh, indent=2)
        shutil.move(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return {"matched": seen,
            "approved": sum(1 for r in doc["images"] if r.get("approved")),
            "locked": len(locks)}


# ------------------------------------------------------------------ modes

def project_root(path):
    """materials/<creature>.json -> the project dir, because `file` is stored
    relative to the project root, not to the JSON."""
    return os.path.dirname(os.path.dirname(os.path.abspath(path)))


def cmd_build(path, out, remote_thumbs):
    doc = json.load(open(path))
    root = project_root(path)
    html = build_html(doc, root, "build", remote_thumbs)
    out = out or os.path.join(os.path.dirname(os.path.abspath(path)),
                              "contact-sheet.html")
    with open(out, "w") as fh:
        fh.write(html)
    kb = os.path.getsize(out) / 1024
    print(f"{len(doc.get('images', []))} cards -> {out}  ({kb:.0f} KB, self-contained)")
    print("build mode is read-only. Tick, then click Download JSON and copy the file")
    print(f"over {path}. To write directly to disk instead:")
    print(f"  contact_sheet.py serve {path}")
    return out


def cmd_serve(path, port, host="127.0.0.1", remote_thumbs=False):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    root = project_root(path)
    abspath = os.path.abspath(path)

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            sys.stderr.write("  %s\n" % (fmt % a))

        def _send(self, code, body, ctype):
            raw = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html"):
                return self._send(404, "not found", "text/plain")
            # Re-read on every load so an edit made elsewhere is never silently
            # overwritten by a page that was opened before it.
            doc = json.load(open(abspath))
            self._send(200, build_html(doc, root, "serve", remote_thumbs),
                       "text/html; charset=utf-8")

        def do_POST(self):
            if self.path.split("?")[0] != "/save":
                return self._send(404, '{"ok":false,"error":"not found"}',
                                  "application/json")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 8 * 1024 * 1024:
                    raise ValueError("payload too large")
                data = json.loads(self.rfile.read(n) or b"{}")
                res = merge_and_write(abspath, data.get("images") or [])
                print(f"  SAVED {abspath}: {res['matched']} records, "
                      f"{res['approved']} approved, {res['locked']} design lock")
                self._send(200, json.dumps({"ok": True, "path": abspath, **res}),
                           "application/json")
            except Exception as e:
                self._send(500, json.dumps({"ok": False,
                                            "error": f"{type(e).__name__}: {e}"}),
                           "application/json")

    srv = ThreadingHTTPServer((host, port), H)
    doc = json.load(open(abspath))
    print(f"{doc.get('creature')}: {len(doc.get('images', []))} images")
    print(f"approval gate on http://{host}:{srv.server_port}/")
    print(f"writes back to {abspath}")
    print("bound to loopback only. Ctrl-C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="serve the page and write the JSON back")
    s.add_argument("materials")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--remote-thumbs", action="store_true",
                   help="link the wiki thumb URLs instead of inlining local ones")

    b = sub.add_parser("build", help="emit a standalone HTML with a download fallback")
    b.add_argument("materials")
    b.add_argument("--out")
    b.add_argument("--remote-thumbs", action="store_true")

    a = ap.parse_args()
    if a.cmd == "build":
        cmd_build(a.materials, a.out, a.remote_thumbs)
    else:
        cmd_serve(a.materials, a.port, a.host, a.remote_thumbs)


if __name__ == "__main__":
    main()
