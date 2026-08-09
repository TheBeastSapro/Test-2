#!/usr/bin/env python3
"""Turn an edit sheet into a watchable, scrubbable preview. No render.

The point: a full render is 18,000 frames and tens of minutes. Deciding whether
a cut works takes ten seconds of watching. This plays the sheet in a browser
immediately, with a timeline showing every shot, pop, icon and sound, so the
edit gets approved or rejected BEFORE anything is committed to frames.

The output is one self-contained HTML file with every image inlined as a data
URI, so it opens from disk, survives being emailed, and works on a phone.

Usage
  preview_sheet.py <sheet.json> --out preview.html [--assets DIR]

The sheet schema is the one in spec/BUILD-PACKET.md section 5.1. Anchors are
expected to be already resolved to t0/t1 by the build step; an unresolved
anchor is reported rather than guessed at, because a guessed time here would
hide exactly the error the preview exists to catch.
"""
import argparse, base64, json, mimetypes, os, sys

TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<title>__TITLE__ — edit preview</title>
<style>
  /* House faces inlined. The preview exists to judge an edit, and you cannot
     judge a title or a keyword pop rendered in a system fallback. */
  __FONTS__
  :root {
    --bg:#0d0d0f; --panel:#17171b; --line:#2a2a31; --ink:#f2f2f4; --dim:#8b8b96;
    --shot:#4a7fd4; --pop:#d62020; --icon:#d8a13a; --sfx:#3fa66a; --gag:#9b5fc9;
    --play:#f2f2f4;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--ink);
         font:14px/1.45 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  header { display:flex; align-items:center; gap:14px; flex-wrap:wrap;
           padding:12px 16px; border-bottom:1px solid var(--line); }
  h1 { font-size:15px; font-weight:650; letter-spacing:.2px; }
  .meta { color:var(--dim); font-size:12px; }
  button { background:var(--panel); color:var(--ink); border:1px solid var(--line);
           border-radius:7px; padding:7px 13px; font:inherit; font-size:13px; cursor:pointer; }
  button:hover { border-color:#3d3d47; }
  button[aria-pressed="true"] { background:var(--ink); color:#111; border-color:var(--ink); }

  /* ---- stage ---- */
  #stageWrap { padding:16px; display:flex; justify-content:center; }
  #stage { position:relative; width:100%; max-width:1120px; aspect-ratio:16/9;
           background:#fff; overflow:hidden; border-radius:6px; }
  .shot { position:absolute; inset:0; display:none; overflow:hidden; }
  .shot.on { display:block; }
  .shot img { position:absolute; left:0; top:0; transform-origin:0 0;
              will-change:transform; }
  .title { position:absolute; left:0; top:4.2%; width:100%; text-align:center;
           font-family:"HouseTitle",ui-sans-serif,sans-serif;
           font-weight:400; letter-spacing:.04em; text-transform:uppercase;
           color:#111; font-size:clamp(14px,3.4vw,44px); }
  .pop { position:absolute; left:0; width:100%; text-align:center;
         font-family:"HousePop",ui-sans-serif,sans-serif; font-weight:400;
         letter-spacing:.01em; font-size:clamp(11px,2.6vw,34px); white-space:nowrap; }
  .pop.band { bottom:5%; color:#111; }
  .pop.on   { bottom:22%; color:#fff; -webkit-text-stroke:.14em #111; paint-order:stroke fill; }
  .accent { color:#d62020; }
  .slot { position:absolute; right:8px; bottom:6px; font-size:10px; color:#8a8a8a;
          letter-spacing:.08em; font-weight:700; }

  /* ---- transport ---- */
  #transport { display:flex; align-items:center; gap:12px; padding:0 16px 12px; }
  #scrub { flex:1; accent-color:var(--play); }
  #clock { font-variant-numeric:tabular-nums; color:var(--dim); min-width:118px; }

  /* ---- timeline ---- */
  #tl { border-top:1px solid var(--line); padding:14px 16px 30px; overflow-x:auto; }
  .lane { position:relative; height:26px; margin-bottom:5px; }
  .lane .name { position:absolute; left:0; top:0; width:74px; height:26px;
                display:flex; align-items:center; color:var(--dim); font-size:11px;
                letter-spacing:.06em; text-transform:uppercase; }
  .track { position:absolute; left:78px; right:0; top:0; height:26px;
           background:var(--panel); border-radius:4px; }
  .blk { position:absolute; top:3px; height:20px; border-radius:3px; overflow:hidden;
         font-size:10px; line-height:20px; padding:0 5px; color:#0b0b0d; font-weight:700;
         white-space:nowrap; cursor:pointer; }
  .blk.point { width:3px !important; padding:0; border-radius:2px; }
  #playhead { position:absolute; top:0; bottom:22px; width:2px; background:var(--play);
              pointer-events:none; }
  #tlInner { position:relative; }
  #ruler { position:relative; height:18px; margin-left:78px; color:var(--dim); font-size:10px; }
  #ruler span { position:absolute; transform:translateX(-50%); }
  .legend { display:flex; gap:14px; flex-wrap:wrap; margin-top:8px; margin-left:78px;
            color:var(--dim); font-size:11px; }
  .legend i { display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:5px; }
  .hidden { display:none !important; }
  #warn { margin:0 16px 12px; padding:9px 12px; border-radius:6px;
          background:#3a2410; border:1px solid #6b4318; color:#f0c893; font-size:12px; }
</style>

<header>
  <h1>__TITLE__</h1>
  <span class="meta">__META__</span>
  <button id="bPlay">Play</button>
  <button id="bView" aria-pressed="true">Preview + timeline</button>
  <button id="bSlots" aria-pressed="false">Slot tags</button>
</header>

__WARN__

<div id="stageWrap"><div id="stage"></div></div>

<div id="transport">
  <input id="scrub" type="range" min="0" max="__DUR__" step="0.01" value="0">
  <span id="clock">0:00.00 / __DURTXT__</span>
</div>

<div id="tl"><div id="tlInner"></div></div>

<script>
const SHEET = __SHEET__;
const DUR = __DUR__;

const stage = document.getElementById('stage');
const tlInner = document.getElementById('tlInner');

// ---- build the stage -------------------------------------------------------
SHEET.shots.forEach((s, i) => {
  const d = document.createElement('div');
  d.className = 'shot'; d.dataset.i = i;
  const img = document.createElement('img');
  img.src = s._data || s.image;
  d.appendChild(img);
  if (s.slot != null) {
    const t = document.createElement('div');
    t.className = 'slot hidden'; t.textContent = 'ASSET SLOT ' + String(s.slot).padStart(2,'0');
    d.appendChild(t);
  }
  stage.appendChild(d);
});
const titleEl = document.createElement('div');
titleEl.className = 'title'; titleEl.textContent = SHEET.title || SHEET.creature || '';
stage.appendChild(titleEl);
SHEET.pops.forEach((p, i) => {
  const e = document.createElement('div');
  e.className = 'pop ' + (p.where === 'on' ? 'on' : 'band');
  e.dataset.i = i;
  e.innerHTML = p.accent ? '<span class="accent">' + p.text + '</span>' : p.text;
  e.style.display = 'none';
  stage.appendChild(e);
});

// ---- Ken Burns, transform only ---------------------------------------------
// Same rule as the renderer: animate transform, never width/height/left/top,
// and run the move LINEARLY. Easing stalls the shot at both ends and puts a
// low-motion window at the head and tail of every shot.
function kbAt(shot, u) {
  const from = shot.kbFrom || (shot.kb === 'in'  ? [0.5,0.5] : shot.kb === 'out' ? [0.5,0.5] : [0.30,0.5]);
  const to   = shot.kbTo   || (shot.kb === 'in'  ? [0.5,0.5] : shot.kb === 'out' ? [0.5,0.5] : [0.70,0.5]);
  const s0 = shot.kb === 'in' ? 1.05 : shot.kb === 'out' ? 1.18 : 1.10;
  const s1 = shot.kb === 'in' ? 1.18 : shot.kb === 'out' ? 1.05 : 1.10;
  const sc = s0 + (s1 - s0) * u;
  const fx = from[0] + (to[0] - from[0]) * u;
  const fy = from[1] + (to[1] - from[1]) * u;
  return {sc, fx, fy};
}

function paint(t) {
  SHEET.shots.forEach((s, i) => {
    const el = stage.querySelector('.shot[data-i="' + i + '"]');
    const on = t >= s.t0 && t < s.t1;
    el.classList.toggle('on', on);
    if (!on) return;
    const u = (t - s.t0) / Math.max(0.0001, s.t1 - s.t0);
    const {sc, fx, fy} = kbAt(s, u);
    const img = el.querySelector('img');
    const W = stage.clientWidth, H = stage.clientHeight;
    const nw = img.naturalWidth || 16, nh = img.naturalHeight || 9;
    const cover = Math.max(W / nw, H / nh) * sc;
    const dw = nw * cover, dh = nh * cover;
    img.style.width = dw + 'px'; img.style.height = dh + 'px';
    const x = -(dw - W) * fx, y = -(dh - H) * fy;
    img.style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)';
  });
  SHEET.pops.forEach((p, i) => {
    const el = stage.querySelector('.pop[data-i="' + i + '"]');
    el.style.display = (t >= p.t0 && t < p.t1) ? 'block' : 'none';
  });
}

// ---- timeline --------------------------------------------------------------
const LANES = [
  ['shots',    'shot', s => [s.t0, s.t1, s.image.split('/').pop()]],
  ['pops',     'pop',  p => [p.t0, p.t1, p.text]],
  ['icons',    'icon', o => [o.t0, o.t1, o.kind]],
  ['gags',     'gag',  g => [g.t0, g.t1, g.visual]],
  ['sfx',      'sfx',  x => [x.t0, x.t0 + 0.12, (x.file||'').split('/').pop()]],
];
function buildTimeline() {
  const ruler = document.createElement('div'); ruler.id = 'ruler';
  const step = DUR > 120 ? 30 : DUR > 40 ? 10 : 5;
  for (let t = 0; t <= DUR; t += step) {
    const s = document.createElement('span');
    s.style.left = (100 * t / DUR) + '%';
    s.textContent = Math.floor(t/60) + ':' + String(Math.floor(t%60)).padStart(2,'0');
    ruler.appendChild(s);
  }
  tlInner.appendChild(ruler);
  LANES.forEach(([key, cls, fn]) => {
    const items = SHEET[key] || [];
    const lane = document.createElement('div'); lane.className = 'lane';
    lane.innerHTML = '<div class="name">' + key + ' ' + items.length + '</div>';
    const track = document.createElement('div'); track.className = 'track';
    items.forEach(it => {
      const [a, b, label] = fn(it);
      if (a == null) return;
      const el = document.createElement('div');
      const w = 100 * Math.max(b - a, 0) / DUR;
      el.className = 'blk' + (w < 0.6 ? ' point' : '');
      el.style.left = (100 * a / DUR) + '%';
      el.style.width = w + '%';
      el.style.background = 'var(--' + cls + ')';
      el.title = label + '  ' + a.toFixed(2) + 's';
      if (w >= 4) el.textContent = label;
      el.onclick = () => seek(a);
      track.appendChild(el);
    });
    lane.appendChild(track);
    tlInner.appendChild(lane);
  });
  const ph = document.createElement('div'); ph.id = 'playhead'; ph.style.left = '78px';
  tlInner.appendChild(ph);
  const lg = document.createElement('div'); lg.className = 'legend';
  LANES.forEach(([k, c]) => lg.innerHTML += '<span><i style="background:var(--'+c+')"></i>'+k+'</span>');
  tlInner.appendChild(lg);
}
buildTimeline();

// ---- transport -------------------------------------------------------------
let t = 0, playing = false, last = 0;
const scrub = document.getElementById('scrub');
const clock = document.getElementById('clock');
const ph = document.getElementById('playhead');
function fmt(x){ return Math.floor(x/60)+':'+String((x%60).toFixed(2)).padStart(5,'0'); }
function seek(x){ t = Math.max(0, Math.min(DUR, x)); scrub.value = t; render(); }
function render(){
  paint(t);
  clock.textContent = fmt(t) + ' / ' + fmt(DUR);
  const track = tlInner.querySelector('.track');
  if (track) ph.style.left = (track.offsetLeft + track.clientWidth * (t / DUR)) + 'px';
}
function tick(now){
  if (playing) {
    t += (now - last) / 1000;
    if (t >= DUR) { t = DUR; playing = false; bPlay.textContent = 'Play'; }
    scrub.value = t; render();
  }
  last = now; requestAnimationFrame(tick);
}
requestAnimationFrame(n => { last = n; requestAnimationFrame(tick); });
scrub.oninput = e => seek(parseFloat(e.target.value));
const bPlay = document.getElementById('bPlay');
bPlay.onclick = () => { if (t >= DUR) t = 0; playing = !playing; bPlay.textContent = playing ? 'Pause' : 'Play'; };
document.onkeydown = e => {
  if (e.code === 'Space') { e.preventDefault(); bPlay.click(); }
  if (e.code === 'ArrowLeft')  seek(t - (e.shiftKey ? 1 : 1/30));
  if (e.code === 'ArrowRight') seek(t + (e.shiftKey ? 1 : 1/30));
};

// ---- toggles ---------------------------------------------------------------
const bView = document.getElementById('bView');
let mode = 0;  // 0 both, 1 preview only, 2 timeline only
const MODES = ['Preview + timeline', 'Preview only', 'Timeline only'];
bView.onclick = () => {
  mode = (mode + 1) % 3;
  bView.textContent = MODES[mode];
  document.getElementById('stageWrap').classList.toggle('hidden', mode === 2);
  document.getElementById('transport').classList.toggle('hidden', mode === 2);
  document.getElementById('tl').classList.toggle('hidden', mode === 1);
};
const bSlots = document.getElementById('bSlots');
bSlots.onclick = () => {
  const on = bSlots.getAttribute('aria-pressed') === 'false';
  bSlots.setAttribute('aria-pressed', on);
  stage.querySelectorAll('.slot').forEach(s => s.classList.toggle('hidden', !on));
};

render();
</script>
"""


def inline(path, assets):
    """Embed an image as a data URI so the preview is one portable file."""
    for cand in ([path] if os.path.isabs(path) else
                 [os.path.join(assets, path), path]):
        if os.path.exists(cand):
            mime = mimetypes.guess_type(cand)[0] or "image/jpeg"
            b = base64.b64encode(open(cand, "rb").read()).decode()
            return f"data:{mime};base64,{b}", os.path.getsize(cand)
    return None, 0


def font_face(name, path):
    """Inline a TTF as a data URI. The CSP on a published page blocks font CDNs,
    and a silent fallback would make the preview lie about how type reads."""
    if not os.path.exists(path):
        return "", f"font missing, type will fall back: {os.path.basename(path)}"
    b = base64.b64encode(open(path, "rb").read()).decode()
    return (f'@font-face{{font-family:"{name}";'
            f'src:url(data:font/ttf;base64,{b}) format("truetype");'
            f'font-display:block;}}\n  '), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--out", required=True)
    ap.add_argument("--assets", default=".")
    a = ap.parse_args()

    sheet = json.load(open(a.sheet))
    for k in ("shots", "pops", "icons", "gags", "sfx", "shakes", "glitches"):
        sheet.setdefault(k, [])

    warns, total = [], 0
    for s in sheet["shots"]:
        if "t0" not in s or "t1" not in s:
            warns.append(f"shot slot {s.get('slot','?')} has no resolved t0/t1 "
                         f"(anchor not resolved at build time)")
            continue
        uri, size = inline(s["image"], a.assets)
        if uri:
            s["_data"] = uri; total += size
        else:
            warns.append(f"image not found: {s['image']}")
    for p in sheet["pops"]:
        if "t0" not in p:
            warns.append(f"pop {p.get('text','?')!r} has no resolved t0")

    dur = sheet.get("t1")
    if dur is None:
        dur = max([s.get("t1", 0) for s in sheet["shots"]] + [0])
    dur = round(float(dur), 3)

    fonts_css, fw = "", []
    fdir = os.path.join(a.assets, "fonts")
    for nm, fn in (("HouseTitle", "anton-latin-400-normal.ttf"),
                   ("HousePop", "archivo-black-latin-400-normal.ttf")):
        css, w = font_face(nm, os.path.join(fdir, fn))
        fonts_css += css
        if w:
            fw.append(w)
    warns += fw

    warn_html = ""
    if warns:
        warn_html = ('<div id="warn"><b>' + str(len(warns)) + ' issue(s)</b><br>' +
                     "<br>".join(w.replace("<", "&lt;") for w in warns) + "</div>")

    meta = (f"{len(sheet['shots'])} shots · {len(sheet['pops'])} pops · "
            f"{len(sheet['icons'])} icons · {len(sheet['sfx'])} sfx · {dur:.2f}s")

    html = (TEMPLATE
            .replace("__SHEET__", json.dumps(sheet))
            .replace("__TITLE__", str(sheet.get("title") or sheet.get("creature") or "Edit"))
            .replace("__META__", meta)
            .replace("__FONTS__", fonts_css)
            .replace("__WARN__", warn_html)
            .replace("__DURTXT__", f"{dur:.2f}s")
            .replace("__DUR__", str(dur)))

    open(a.out, "w").write(html)
    mb = (len(html.encode()) / 1e6)
    print(f"{a.out}  {mb:.2f} MB  ({total/1e6:.2f} MB of images inlined)")
    print(f"  {meta}")
    for w in warns:
        print("  WARN:", w)


if __name__ == "__main__":
    main()
