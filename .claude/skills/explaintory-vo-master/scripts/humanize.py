#!/usr/bin/env python3
"""
humanize.py — ExplainTory VO humanizer.

One call: raw TTS voiceover + script text  ->  paced, de-clipped, studio-mastered file.

    python3 humanize.py --audio vo.mp3 --script script.txt --out final.wav

Pipeline
    1. decode                 -> 48 kHz mono float, 16 kHz mono for alignment
    2. declip                 -> reconstruct over-full-scale runs by cubic fit
    3. forced alignment       -> torchaudio MMS_FA, chunked so it fits in RAM
    4. boundary detection     -> script punctuation + post-date + optional curated list
    5. pause insertion        -> per-boundary TRUE-SILENCE targeting
    6. studio master          -> matched EQ, harmonic exciter, de-esser
    7. loudnorm               -> -14 LUFS, -1.5 dBTP

Requires: ffmpeg on PATH; pip install numpy scipy torch torchaudio
Settings derived from the ExplainTory human VO stem. See --help for overrides.
"""
import argparse, csv, json, os, re, struct, subprocess, sys, tempfile, unicodedata, wave
import numpy as np

SR = 48000

# ---------------------------------------------------------------- settings
DEFAULTS = dict(comma=0.16, sentence=0.21, paragraph=0.25, tail=1.00,
                tempo=1.04, air=0.00)   # air 0 = no synthesised top end; approved 2026-07-29

# EQ correction derived once from the human stem: (Hz, dB)
EQ_CURVE = [
    (40, 0.0), (45, 0.0), (50, 0.14), (57, 0.39), (63, 1.31), (71, 2.57),
    (80, 3.35), (90, 4.39), (101, 4.81), (113, 4.37), (127, 3.07), (143, 1.48),
    (160, 1.1), (180, 1.78), (202, 0.88), (226, 0.2), (254, -0.76), (285, -2.0),
    (320, -0.8), (359, 1.64), (403, 1.7), (453, 0.06), (508, -1.54), (570, -2.36),
    (640, -1.83), (718, -0.54), (806, -0.04), (905, -0.16), (1016, -0.19), (1140, -0.26),
    (1280, -0.16), (1437, 0.51), (1613, 0.81), (1810, 0.89), (2032, 1.3), (2281, 1.79),
    (2560, 1.86), (2874, 2.01), (3225, 3.5), (3620, 5.0), (4064, 4.89), (4561, 4.16),
    (5120, 4.66), (5747, 5.99), (6451, 6.0), (7241, 5.72), (8127, 4.39), (9123, 4.05),
    (10240, 5.41), (11494, 6.0), (12902, 6.0), (14482, 4.56), (16255, 0.0), (18246, 0.0),
]

def log(m): print(f"[humanize] {m}", flush=True)

# ---------------------------------------------------------------- io helpers
def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode: raise RuntimeError(f"{cmd[0]} failed:\n{p.stderr[-2000:]}")
    return p.stdout

def decode_raw(src, out, rate):
    """Headerless float32 PCM. Avoids WAV header ambiguity entirely -- ffmpeg emits
    WAVE_FORMAT_EXTENSIBLE for float, which naive parsers read back as int16."""
    run(["ffmpeg", "-v", "error", "-i", src, "-ac", "1", "-ar", str(rate),
         "-f", "f32le", out, "-y"])

def read_raw(path):
    return np.fromfile(path, dtype=np.float32)

def write_raw(path, x):
    x.astype(np.float32).tofile(path)

def raw_filter(src, dst, rate, af):
    run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(rate), "-ac", "1",
         "-i", src, "-filter:a", af, "-f", "f32le", dst, "-y"])

def write_wav(path, x, rate=SR):
    x = np.clip(x, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((x * 32767).astype(np.int16).tobytes())

# ---------------------------------------------------------------- 2. declip
def declip(x, thr=0.95, guard=8):
    m = np.abs(x) >= thr
    if not m.any(): return x, 0
    y = x.copy(); n = len(x); runs = []; i = 0
    while i < n:
        if m[i]:
            j = i
            while j < n and m[j]: j += 1
            runs.append((i, j)); i = j
        else: i += 1
    for a, b in runs:
        a0, b1 = max(0, a-guard), min(n, b+guard)
        xs = np.concatenate([np.arange(a0, a), np.arange(b, b1)])
        if len(xs) < 6: continue
        c = np.polyfit(xs - a, x[xs], 3)
        rec = np.polyval(c, np.arange(a, b) - a)
        sg = np.sign(x[a:b])
        y[a:b] = np.where(np.sign(rec) == sg, rec, x[a:b])
    return y, len(runs)

# ---------------------------------------------------------------- 2b. glitch repair
def _runs(m):
    o=[];i=0
    while i<len(m):
        if m[i]:
            j=i
            while j<len(m) and m[j]: j+=1
            o.append((i,j)); i=j
        else: i+=1
    return o

def fix_glitches(x):
    """Remove orphan fragments left by segment splices.

    TTS rendered per-segment and butt-joined leaves detached scraps of the last
    phoneme sitting alone next to the join -- a 35 ms copy of the /s/ in "Ages"
    that has already been spoken, which reads as a tick or hiss. Only fragments
    that are BOTH isolated by silence AND within 50 ms of a hard digital splice
    are removed; ordinary short fricatives mid-sentence are left alone.
    """
    hop = int(0.005*SR); n = len(x)//hop
    if n < 4: return x, []
    db = 20*np.log10(np.sqrt(np.array([np.mean(x[i*hop:(i+1)*hop]**2)
                                       for i in range(n)]))+1e-12)
    edges = [e*0.005 for a, b in _runs(db < -150) for e in (a, b)]
    if not edges: return x, []
    removed = []
    for a, b in _runs(db > -50):
        dur = (b-a)*0.005
        if dur > 0.25: continue
        pk = db[a:b].max()
        pre = db[max(0, a-16):a].max() if a > 0 else -240.0
        post = db[b:min(n, b+16)].max() if b < n else -240.0
        if not (pre < -50 and post < -50 and (pk - max(pre, post)) >= 15): continue
        ts, te = a*0.005, b*0.005
        if not any(min(abs(ts-e), abs(te-e)) <= 0.05 for e in edges): continue
        s0, s1 = int(ts*SR), int(te*SR)
        f = int(0.002*SR)
        x[max(0, s0-f):s0] *= np.linspace(1, 0, min(f, s0))
        x[s0:s1] = 0.0
        x[s1:s1+f] *= np.linspace(0, 1, len(x[s1:s1+f]))
        removed.append((ts, dur, pk))
    return x, removed

# ---------------------------------------------------------------- 2c. QC pass
def qc_report(x, label="source"):
    """Standard engineering QC. Run it unprompted -- defects should come from the
    tool, not from the client noticing them on playback."""
    from scipy import signal
    out = []
    pk = float(np.abs(x).max())
    if pk >= 0.999:
        out.append(f"CLIP    sample peak {20*np.log10(pk):+.2f} dBFS, "
                   f"{int((np.abs(x) >= 0.999).sum())} samples at full scale")
    elif pk > 0.891:
        out.append(f"HOT     sample peak {20*np.log10(pk):+.2f} dBFS (over -1 dBFS)")
    dc = float(x.mean())
    if abs(dc) > 0.001:
        out.append(f"DC      offset {dc:+.4f} -- high-pass before mastering")
    hop = int(0.01*SR); n = len(x)//hop
    db = 20*np.log10(np.sqrt(np.array([np.mean(x[i*hop:(i+1)*hop]**2)
                                       for i in range(n)]))+1e-12)
    floor = float(np.percentile(db, 5)); speech = float(np.percentile(db, 70))
    if speech - floor < 35:
        out.append(f"NOISE   floor {floor:.0f} dB vs speech {speech:.0f} dB "
                   f"-- only {speech-floor:.0f} dB of range, expect audible hiss")
    # No click detector here on purpose. Sample-step tests do not work on speech at
    # 48 kHz -- calibration showed 724 false positives on a verified-clean file while
    # 40 injected clicks moved the count by only 49. Edit artifacts are caught by
    # fix_glitches() instead, which keys on digital-silence splices and is reliable.
    mid = signal.sosfilt(signal.butter(4, [300, 3000], "bp", fs=SR, output="sos"), x)
    hm = np.array([np.sqrt(np.mean(mid[i*hop:(i+1)*hop]**2)) for i in range(n)])
    # rumble: sustained sub-60 Hz, which speech has no business producing
    rb = signal.sosfilt(signal.butter(4, 60, "lp", fs=SR, output="sos"), x)
    hr = np.array([np.sqrt(np.mean(rb[i*hop:(i+1)*hop]**2)) for i in range(n)])
    voiced = hm > np.percentile(hm, 70)
    if voiced.any():
        rr = 20*np.log10(hr[voiced].mean()/(hm[voiced].mean()+1e-12)+1e-12)
        if rr > -30:
            out.append(f"RUMBLE  sub-60 Hz sits {rr:+.0f} dB under the voice -- high-pass it")
    sib = signal.sosfilt(signal.butter(4, [5500, 9500], "bp", fs=SR, output="sos"), x)
    hs = np.array([np.sqrt(np.mean(sib[i*hop:(i+1)*hop]**2)) for i in range(n)])
    if voiced.any():
        r = float(np.percentile(hs[voiced]/(hm[voiced]+1e-9), 99))
        if r > 1.2:
            out.append(f"SIBILANT peak s/mid ratio {r:.2f} -- de-esser will be working hard")
    log(f"QC ({label}): " + ("clean" if not out else f"{len(out)} finding(s)"))
    for o in out: log(f"    {o}")
    return out

# ---------------------------------------------------------------- 3. align
_ONES = ["zero","one","two","three","four","five","six","seven","eight","nine",
         "ten","eleven","twelve","thirteen","fourteen","fifteen","sixteen",
         "seventeen","eighteen","nineteen"]
_TENS = ["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"]


def _under100(n):
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + (_ONES[n % 10] if n % 10 else "")


def _spell(n):
    """1547 -> 'fifteenfortyseven'. Year-style for four digits, plain otherwise."""
    if n < 100:
        return _under100(n)
    if n < 1000:
        return _ONES[n // 100] + "hundred" + (_under100(n % 100) if n % 100 else "")
    if 1000 <= n < 10000:
        hi, lo = n // 100, n % 100
        if n % 1000 == 0:
            return _under100(n // 1000) + "thousand"
        if lo == 0:                       # 1900 -> nineteenhundred
            return _under100(hi) + "hundred"
        return _under100(hi) + _under100(lo)          # 1547 -> fifteenfortyseven
    return _under100(n // 1000) + "thousand" + (_spell(n % 1000) if n % 1000 else "")


def norm_tok(w):
    """Alignable form of a script token.

    Numerals used to be stripped to nothing and dropped from the alignment
    entirely. Everything downstream then worked on a token stream with holes in
    it: a boundary near "between 1547 and 1550, described" had no idea where
    either year was, so the beat meant for the comma after 1550 was placed by
    guesswork and landed inside the range instead -- audible as a stumble at
    0:57, and as a missing comma pause right after it. 35 tokens of this script
    were invisible for the same reason.

    Digits are spelled the way they are spoken, so the aligner can find them:
    four-digit numbers year-style ("fifteenfortyseven"), everything else plainly.
    """
    w = unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode()
    core = re.sub(r"[^0-9a-zA-Z']", "", w)
    if core.isdigit():
        try:
            return _spell(int(core))
        except (ValueError, IndexError, KeyError):
            return ""
    return re.sub(r"[^a-zA-Z']", "", w).lower()

def align(wav16_path, lines, chunk_s=40):
    import torch, torchaudio, gc
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=False); model.eval()
    tok = bundle.get_tokenizer(); aligner = bundle.get_aligner()
    wav = torch.from_numpy(read_raw(wav16_path)).unsqueeze(0)
    T = wav.shape[1]; C = chunk_s*16000; OV = 2*16000
    ems = []
    with torch.inference_mode():
        pos = 0
        while pos < T:
            a = max(0, pos-OV); b = min(T, pos+C)
            e, _ = model(wav[:, a:b])
            fps = e.shape[1]/(b-a)
            ems.append(e[:, int(round((pos-a)*fps)):, :].clone())
            pos = b; del e; gc.collect()
            log(f"  aligning {pos/16000:.0f}s / {T/16000:.0f}s")
    em = torch.cat(ems, 1); del ems; gc.collect()
    toks, meta = [], []
    for li, l in enumerate(lines):
        for ow in l.split():
            n = norm_tok(ow)
            if n: toks.append(n); meta.append((li, ow))
    spans = aligner(em[0], tok(toks))
    ratio = T/em.shape[1]/16000
    return [dict(line=li, w=ow, s=round(sp[0].start*ratio, 3), e=round(sp[-1].end*ratio, 3),
                 score=round(sum(t.score*len(t) for t in sp)/sum(len(t) for t in sp), 3))
            for (li, ow), sp in zip(meta, spans)]

# ---------------------------------------------------------------- 4/5. pacing
# Silence below this at a comma means the voice deliberately read through it.
RUNTHROUGH = 0.030

ABB = re.compile(r"^[A-Z]\.$")
NUMY = re.compile(r"^[\d]")
ERA = re.compile(r"^(BC|AD|BCE|CE)[.,;:]?$", re.I)

# Words that join two halves of ONE date span: "between 1547 and 1550",
# "from 1966 to 1970", "1914-18".
RANGE_JOINERS = {"and", "to", "or", "until", "through", "till"}


def _is_range(seq, p, nw):
    """True when the year at seq[p] is the FIRST half of a date range.

    The post-date rule gives a year a comma-length beat whenever the next word
    is not itself a year, which is right for "in 1547, the viceroy..." and wrong
    for "between 1547 and 1550" — one span, read without a break. The beat lands
    mid-phrase there and is audible as a stumble: it put 150 ms between "1547"
    and "and" in a delivered master.

    A range is the joiner followed by another year, so both are required. That
    keeps the beat on "he waited until 1550, then left", where "until" is doing
    ordinary work and no second year follows.
    """
    if nw.strip(".,;:").lower() not in RANGE_JOINERS:
        return False
    if re.search(r"[,;:.!?]\"?$", nw):        # "…until 1550, and then" is a real break
        return False
    after = seq[p + 2][1] if p + 2 < len(seq) else ""
    return bool(NUMY.match(after) or ERA.match(after))

def is_card(line):
    """A short line with no terminal punctuation is a section/era card."""
    return len(line.split()) <= 5 and not re.search(r"[.!?]\"?$", line.strip())

def sentence_rates(words, lines):
    """Per-sentence speaking rate, for outlier levelling."""
    out=[];cur=[]
    for i,w in enumerate(words):
        cur.append(i)
        if (re.search(r'[.!?]"?$',w["w"]) and not ABB.match(w["w"])) or \
           (i+1<len(words) and words[i+1]["line"]!=w["line"]) or i==len(words)-1:
            out.append(cur);cur=[]
    S=[]
    for sn in out:
        a,b=words[sn[0]],words[sn[-1]]; d=b["e"]-a["s"]
        if d<=0.4 or len(sn)<5: continue
        S.append(dict(i0=sn[0],i1=sn[-1],s=a["s"],e=b["e"],wpm=len(sn)/d*60,
                      txt=" ".join(words[k]["w"] for k in sn)))
    return S

def build(x, words, lines, tgt, curated, tempo, max_wpm=None, min_factor=0.87,
          level_skip_start=25.0, adaptive=False, ceiling=250.0):
    hop = int(0.01*SR); nf = len(x)//hop
    db = 20*np.log10(np.sqrt(np.array([np.mean(x[i*hop:(i+1)*hop]**2)
                                       for i in range(nf)]))+1e-12)
    if not adaptive:
        for w in words: w["s"] /= tempo; w["e"] /= tempo

    seq = []; wi = 0
    for li, l in enumerate(lines):
        for ow in l.split():
            if norm_tok(ow): seq.append((li, ow, wi)); wi += 1
            else: seq.append((li, ow, None))
    assert wi == len(words), "internal token bookkeeping error"

    def next_aligned(p):
        for q in range(p+1, len(seq)):
            if seq[q][2] is not None: return seq[q][2]
        return None

    targets = {}
    for p in range(len(seq)-1):
        li, ow, _ = seq[p]; nli, nw, _ = seq[p+1]
        kind = None
        if nli != li:
            kind = None if (is_card(lines[nli]) or is_card(lines[li])) else "paragraph"
        elif re.search(r"[.!?]\"?$", ow) and not ABB.match(ow):
            kind = "sentence"
        elif re.search(r"[,;:]\"?$", ow):
            kind = "comma"
        elif ((NUMY.match(ow) or ERA.match(ow))
              and not (NUMY.match(nw) or ERA.match(nw))
              and not _is_range(seq, p, nw)):
            kind = "comma"                                    # post-date
        elif (ow.strip(".,;:"), nw.strip(".,;:")) in curated:
            kind = "comma"                                    # missing-comma break
        if not kind: continue
        nb = next_aligned(p)
        if nb is None or nb == 0 or nb >= len(words): continue
        if nb not in targets or tgt[kind] > targets[nb][0]:
            targets[nb] = (tgt[kind], kind)

    def true_sil(nb):
        a, b = words[nb-1], words[nb]
        lo = int((max(a["e"], b["s"]-0.35)-0.05)*100); hi = int((b["s"]+0.05)*100)
        return float((db[lo:hi] < -45).sum())*0.01 if hi > lo else 0.0

    def cut(nb):
        ge = words[nb]["s"]; gs = words[nb-1]["e"]
        a = int(max(gs, ge-0.30)*SR); b = int((ge-0.02)*SR)
        if b-a < 240: return max(0, int((ge-0.03)*SR))
        seg = np.abs(x[a:b]); win = 120; k = len(seg)//win
        if k < 2: return (a+b)//2
        e = np.array([seg[j*win:(j+1)*win].mean() for j in range(k)])
        return a + int(np.argmin(e))*win + win//2

    # ---- adaptive tempo -----------------------------------------------------
    # A uniform speed-up compounds on passages that were already fast. Instead,
    # give each sentence only as much speed-up as it can take without crossing
    # the ceiling. Normal passages get the full amount; fast ones get none.
    stretch = {}     # aligned word index -> factor (<1 = slower, >1 = faster)
    leveled = []
    if adaptive and tempo > 1.0:
        for sn in sentence_rates(words, lines):
            f_ = min(tempo, max(1.0, ceiling/sn["wpm"]))
            for k in range(sn["i0"], sn["i1"]+1): stretch[k] = f_
            if f_ < tempo - 0.002:
                leveled.append((sn["s"], sn["wpm"], sn["wpm"]*f_, f_, sn["txt"]))

    # ---- rate levelling: slow only the sentences that run away ----
    if max_wpm:
        for sn in sentence_rates(words, lines):
            if sn["wpm"] <= max_wpm: continue
            # NEVER slow the cold open. It is the hook and it decides the video.
            if sn["s"]*tempo < level_skip_start: continue
            f_ = max(min_factor, max_wpm/sn["wpm"])
            for k in range(sn["i0"], sn["i1"]+1): stretch[k] = f_
            leveled.append((sn["s"]*tempo, sn["wpm"], sn["wpm"]*f_, f_, sn["txt"]))

    F = int(0.004*SR)
    def fade(a):
        a = a.copy(); n = min(F, len(a)//2)
        if n: a[:n] *= np.linspace(0, 1, n); a[-n:] *= np.linspace(1, 0, n)
        return a

    import tempfile as _tf, subprocess as _sp, wave as _wave, os as _os
    _td = _tf.mkdtemp(prefix="hz_stretch_")
    def _stretch(arr, f_, tag):
        p0 = _os.path.join(_td, f"{tag}.raw"); p1 = _os.path.join(_td, f"{tag}o.raw")
        arr.astype(np.float32).tofile(p0)
        _sp.run(["ffmpeg","-v","error","-f","f32le","-ar",str(SR),"-ac","1","-i",p0,
                 "-filter:a",f"atempo={f_:.4f}","-f","f32le",p1,"-y"], check=True)
        return np.fromfile(p1, dtype=np.float32)

    out = []; rep = []; prev = 0; added = 0.0; nstretch = 0
    for nb in sorted(targets):
        t, kind = targets[nb]
        c = cut(nb)
        if c <= prev: continue
        chunk = x[prev:c]
        f_ = stretch.get(max(0, nb-1))
        if f_ and len(chunk) > 480:
            chunk = _stretch(chunk, f_, str(nb)); nstretch += 1
        out.append(fade(chunk))
        have = true_sil(nb); ins = max(0.0, t-have)

        # When the voice renders a comma with essentially NO silence of its own, it
        # ran the phrase through on purpose -- "from Cusco to Quito, twelve hundred
        # and fifty miles" is one breath, and the comma is grammar, not a beat.
        # Padding that to target does not add pacing, it inserts a stumble into a
        # line that was already right. Sapro heard it at 0:03 and it survived every
        # section-level fix, because this ran afterwards and put it back each time.
        #
        # Only near-zero counts. A comma the voice gave 40-90 ms still wants
        # topping up to target; that is the case this pipeline was built for.
        if kind == "comma" and have < RUNTHROUGH:
            ins = 0.0
        if ins > 0.005:
            out.append(np.zeros(int(ins*SR), np.float32)); added += ins
            rep.append(dict(time=round(words[nb]["s"]*tempo, 2), kind=kind,
                            silence_before=round(have, 3), target=t, inserted=round(ins, 3),
                            context=" ".join(w["w"] for w in words[max(0, nb-5):nb]) + " || " +
                                    " ".join(w["w"] for w in words[nb:nb+4])))
        prev = c
    out.append(fade(x[prev:]))
    out.append(np.zeros(int(tgt["tail"]*SR), np.float32)); added += tgt["tail"]
    return np.concatenate(out), rep, added, leveled, nstretch

# ---------------------------------------------------------------- 6. master
def _srms(v, ms=40):
    from scipy import signal
    p = signal.sosfilt(signal.butter(2, 1000.0/ms, "lp", fs=SR, output="sos"), v*v)
    return np.sqrt(np.maximum(p, 0))

def master(y, air, mode="classic"):
    """EQ to the human curve, then synthesise the top end the lossy source lost.

    mode="classic"  the approved ExplainTory sound. Exciter level is set from the
                    file's global RMS and shaped by tanh drive. Technically cruder
                    than "local", but this is the version signed off by ear and it
                    is what the locked settings refer to. Default.
    mode="local"    exciter tracks the local signal level and uses square-law
                    generation instead of tanh. Cleaner in quiet passages and less
                    intermodulation, but a different top end -- needs roughly
                    2x the --air value for comparable brightness. Re-audition
                    before shipping.
    """
    from scipy import signal
    f = np.fft.rfftfreq(4096, 1/SR)
    g = np.interp(f, [p[0] for p in EQ_CURVE], [p[1] for p in EQ_CURVE], left=0.0, right=0.0)
    fn = np.clip(np.concatenate(([0], f[1:]/(SR/2))), 0, 1); fn[-1] = 1.0
    fir = signal.firwin2(2047, fn, 10**(g/20), fs=2.0)
    y = signal.fftconvolve(y, fir, mode="same")

    if air > 0 and mode == "classic":
        drive = signal.sosfilt(signal.butter(4, 5500, "hp", fs=SR, output="sos"), y)
        exc = np.tanh(drive*8.0)
        e1 = signal.sosfilt(signal.butter(4, [8500, 14000], "bp", fs=SR, output="sos"), exc)
        e2 = signal.sosfilt(signal.butter(4, [13000, 19000], "bp", fs=SR, output="sos"), exc)
        env = np.abs(signal.sosfilt(signal.butter(2, 20, "lp", fs=SR, output="sos"), np.abs(y)))
        env = np.clip(env/(env.max() + 1e-9)*4, 0, 1)
        ref = np.sqrt((y**2).mean())
        y = y + (e1/(np.sqrt((e1**2).mean()) + 1e-12))*ref*air*0.55*env \
              + (e2/(np.sqrt((e2**2).mean()) + 1e-12))*ref*air*0.85*env
    elif air > 0 and mode == "local":
        AIR_SCALE = 11.4
        band = signal.sosfilt(signal.butter(4, [5000, 9500], "bp", fs=SR, output="sos"), y)
        h = band*np.abs(band)
        h = signal.sosfilt(signal.butter(4, [9000, 18000], "bp", fs=SR, output="sos"), h)
        eh = _srms(h); floor = 0.10*np.sqrt((h*h).mean() + 1e-20)
        loc = _srms(signal.sosfilt(signal.butter(4, [6000, 12000], "bp", fs=SR, output="sos"), y))
        gate = np.clip((20*np.log10(_srms(y, 60) + 1e-12) + 50.0)/12, 0, 1)
        y = y + (h/(eh + floor))*loc*air*AIR_SCALE*gate

    y = signal.sosfilt(signal.butter(3, 55, "hp", fs=SR, output="sos"), y)

    sib = signal.sosfilt(signal.butter(4, [5200, 9500], "bp", fs=SR, output="sos"), y)
    D = 16; DR = SR/D
    def pool(v):
        n = (len(v)//D)*D
        return np.abs(v[:n]).reshape(-1, D).max(1)
    def env_f(v, at, rl):
        a_ = np.exp(-1/(DR*at)); r_ = np.exp(-1/(DR*rl))
        o = np.empty_like(v); p = 0.0
        for i in range(len(v)):
            c = a_ if v[i] > p else r_
            p = c*p + (1-c)*v[i]; o[i] = p
        return o
    ps, py_ = pool(sib), pool(y)
    ratio = env_f(ps, .001, .040)/(env_f(py_, .005, .150) + 1e-6)
    gr = np.ones_like(ratio); TH = 0.42
    o = ratio > TH; gr[o] = (TH/ratio[o])**0.55
    gr = np.interp(np.arange(len(y)), np.arange(len(gr))*D + D/2, gr, left=1.0, right=1.0)
    gr = np.clip(signal.sosfilt(signal.butter(2, 120, "lp", fs=SR, output="sos"), gr), .45, 1.)
    return y - sib*(1-gr)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Humanize an AI voiceover.")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--script", required=True, help="plain text, one paragraph per line")
    ap.add_argument("--out", required=True, help=".wav or .mp3")
    ap.add_argument("--report", help="CSV of every inserted pause")
    ap.add_argument("--curated", help="optional text file, one 'wordA|wordB' pair per line, "
                                      "marking clause breaks the script forgot to punctuate")
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k}", type=float, default=v)
    ap.add_argument("--no-master", action="store_true", help="pacing only, skip EQ chain")
    ap.add_argument("--keep-glitches", action="store_true",
                    help="skip splice-fragment removal")
    ap.add_argument("--max-wpm", type=float, default=0.0,
                    help="slow only sentences that are UNUSUALLY fast. 250 = where the "
                         "human read tops out (its p90 is 254); catches ~4 per video. "
                         "Do not lower this toward the file median -- that flattens the "
                         "read. OFF by default: the un-levelled read was the one approved.")
    ap.add_argument("--adaptive-tempo", action="store_true", default=True,
                    help="apply the speed-up per sentence instead of globally, so "
                         "already-fast passages are not pushed further (default on)")
    ap.add_argument("--uniform-tempo", dest="adaptive_tempo", action="store_false",
                    help="old behaviour: one global atempo across the whole file")
    ap.add_argument("--ceiling", type=float, default=250.0,
                    help="no sentence is sped up past this wpm (human read tops out ~254)")
    ap.add_argument("--level-skip-start", type=float, default=25.0,
                    help="never rate-level the first N seconds -- the hook must stay fast")
    ap.add_argument("--min-factor", type=float, default=0.87,
                    help="hardest allowed slowdown, 0.87 = 13%% (below ~0.85 is audible)")
    ap.add_argument("--align-cache", help="save/reuse the forced alignment; makes "
                                          "re-runs with different settings near-instant")
    ap.add_argument("--exciter", choices=["classic", "local"], default="classic",
                    help="classic = the approved sound (default); local = cleaner "
                         "in quiet passages, needs ~2x --air, re-audition first")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="humanize_")
    w48, w16 = os.path.join(tmp, "a48.raw"), os.path.join(tmp, "a16.raw")
    log("decoding")
    decode_raw(a.audio, w48, SR); decode_raw(a.audio, w16, 16000)
    x = read_raw(w48)
    log(f"  {len(x)/SR:.1f}s, peak {20*np.log10(np.abs(x).max()+1e-9):+.2f} dBFS")

    qc_report(x, "source")

    orig_len = len(x)
    x, nclip = declip(x)
    log(f"declipped {nclip} over-full-scale region(s)")

    if not a.keep_glitches:
        x, gl = fix_glitches(x)
        log(f"removed {len(gl)} splice fragment(s)")
        for t, d_, p in gl:
            log(f"    {int(t//60)}:{t%60:06.3f}  {d_*1000:.0f} ms  {p:.0f} dB")

    lines = [l.strip() for l in open(a.script, encoding="utf-8").read().split("\n") if l.strip()]
    log(f"script: {len(lines)} lines, {sum(len(l.split()) for l in lines)} words")

    if a.tempo != 1.0 and not a.adaptive_tempo:
        dc, sp = os.path.join(tmp, "dc.raw"), os.path.join(tmp, "sp.raw")
        write_raw(dc, x); raw_filter(dc, sp, SR, f"atempo={a.tempo}")
        x = read_raw(sp)
        log(f"tempo x{a.tempo} -> {len(x)/SR:.1f}s")

    import hashlib
    key = hashlib.sha1(("\n".join(lines)).encode()).hexdigest()[:16] + f"_{orig_len}"
    words = None
    if a.align_cache and os.path.exists(a.align_cache):
        try:
            c = json.load(open(a.align_cache))
            if c.get("key") == key:
                words = c["words"]; log(f"reusing cached alignment ({len(words)} words)")
        except Exception:
            pass
    if words is None:
        log("forced alignment (this is the slow part)")
        words = align(w16, lines)
        if a.align_cache:
            json.dump({"key": key, "words": words}, open(a.align_cache, "w"))
            log(f"  cached -> {a.align_cache}")
    dur = len(x)/SR
    wpm = len(words)/dur*60
    mean_sc = float(np.mean([w["score"] for w in words]))
    weak = sum(1 for w in words if w["score"] < 0.4)/max(len(words), 1)
    log(f"  {len(words)} words aligned | {wpm:.0f} wpm | mean confidence {mean_sc:.2f} "
        f"| {weak*100:.0f}% weak")
    if not (90 <= wpm <= 260):
        sys.exit(f"[humanize] ABORT: script implies {wpm:.0f} wpm over {dur:.0f}s of audio. "
                 "The script almost certainly does not match this recording.")
    if mean_sc < 0.55 or weak > 0.25:
        sys.exit(f"[humanize] ABORT: alignment confidence {mean_sc:.2f} ({weak*100:.0f}% weak). "
                 "Check the script matches the read, and that numbers are written the way "
                 "they are spoken.")

    curated = set()
    if a.curated:
        for ln in open(a.curated, encoding="utf-8"):
            if "|" in ln:
                p, q = ln.strip().split("|", 1); curated.add((p.strip(), q.strip()))
        log(f"curated clause breaks: {len(curated)}")

    tgt = dict(comma=a.comma, sentence=a.sentence, paragraph=a.paragraph, tail=a.tail)
    y, rep, added, leveled, nst = build(x, words, lines, tgt, curated, a.tempo,
                                        a.max_wpm, a.min_factor, a.level_skip_start,
                                        a.adaptive_tempo, a.ceiling)
    if leveled:
        what = "held back from the speed-up" if a.adaptive_tempo else "slowed"
        log(f"{len(leveled)} sentence(s) {what} ({nst} chunks stretched)")
        for t_, was, now, f_, txt in leveled[:14]:
            log(f"    {int(t_//60)}:{t_%60:04.1f}  {was:.0f} wpm  x{f_:.3f} -> {now:.0f}   {txt[:52]}")
        if len(leveled) > 14: log(f"    ... and {len(leveled)-14} more")
    from collections import Counter
    log(f"inserted {added:.1f}s at {len(rep)} boundaries {dict(Counter(r['kind'] for r in rep))}")

    if not a.no_master:
        log(f"studio master ({a.exciter}, air {a.air})")
        y = master(y, a.air, a.exciter)

    pre = os.path.join(tmp, "pre.wav"); write_wav(pre, y)
    log("loudnorm -14 LUFS / -1.5 dBTP")
    run(["ffmpeg", "-v", "error", "-i", pre, "-af",
         "loudnorm=I=-14:TP=-1.5:LRA=7:linear=true", "-ar", str(SR), "-ac", "1",
         *(["-c:a", "libmp3lame", "-b:a", "256k"] if a.out.lower().endswith(".mp3")
           else ["-c:a", "pcm_s16le"]), a.out, "-y"])

    if a.report and rep:
        with open(a.report, "w", newline="", encoding="utf-8") as f:
            c = csv.DictWriter(f, fieldnames=list(rep[0].keys())); c.writeheader(); c.writerows(rep)
    fin = os.path.join(tmp, "final.raw")
    decode_raw(a.out, fin, SR)
    qc_report(read_raw(fin), "delivered file")
    d = len(y)/SR
    log(f"done -> {a.out}  ({int(d//60)}:{d%60:05.2f})")

if __name__ == "__main__":
    main()
