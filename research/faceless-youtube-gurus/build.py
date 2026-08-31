#!/usr/bin/env python3
"""Build the faceless-YouTube playbook page from the harvested corpus."""
import json, re, html

THREADS = json.load(open('threads_clean.json'))

AUTHORS = {
    'noahmorris':    ('Noah Morris', 'noah'),
    'wannercashcow': ('Wanner',      'wanner'),
    'PhedEU':        ('phed',        'phed'),
    '1of10media':    ('1 of 10',     'oneoften'),
    'Richard_YTS':   ('1 of 10',     'oneoften'),
}

TOPICS = [
    ('niches',   'Niches'),
    ('ideas',    'Ideas'),
    ('titles',   'Titles'),
    ('thumbs',   'Thumbnails'),
    ('scripts',  'Scripts & retention'),
    ('algo',     'Algorithm'),
    ('rpm',      'RPM & money'),
    ('ai',       'AI & production'),
    ('ops',      'Scaling & ops'),
    ('start',    'Getting started'),
    ('cases',    'Case studies'),
]

TOPIC_NOTE = {
    'niches':  "Where all four of them say the money actually is. The recurring claim: the niche decides your RPM before a single edit does.",
    'ideas':   "Ideation as a search problem, not a creative one — find the pattern that already works, then bring it somewhere it hasn't been.",
    'titles':  "Fill-in-the-blank formats they've watched work across hundreds of channels. Treat them as scaffolding, not scripture.",
    'thumbs':  "Packaging is the half of the job that decides whether the other half gets seen.",
    'scripts': "The first fifteen seconds, the open loop, and the structure that keeps a viewer past the point where they usually leave.",
    'algo':    "How the system decides. Most of this is inference from public research and their own channel data — treat it as informed theory, not documentation.",
    'rpm':     "The same view is worth wildly different amounts. This is the chapter on making it worth more.",
    'ai':      "Where the production cost went. Every one of them now builds with AI in the loop; these are the specific workflows.",
    'ops':     "What changes when it stops being one channel and becomes a business.",
    'start':   "What they'd do from zero, and the mistakes they each paid to learn.",
    'cases':   "Real channels, real numbers, worked backwards.",
}

# thread index -> (topic, title)
THREAD_MAP = {
    0:  ('start',   'Your first 1,000 subscribers'),
    1:  ('cases',   'How Ruhi Çenet averages 23M views a video'),
    2:  ('algo',    'The only 5 metrics you need'),
    3:  ('ideas',   '17 ideas proven to go viral'),
    4:  ('titles',  '17 title templates that are working now'),
    5:  ('start',   'If I were starting a channel in 2024'),
    6:  ('ideas',   'How to find killer ideas that go viral'),
    7:  ('start',   'If I were starting a channel in 2025'),
    8:  ('titles',  '12 title formats to go viral with'),
    9:  ('titles',  '12 more title formats killing it right now'),
    10: ('cases',   'How MrBeast got to 266 million subscribers'),
    11: ('titles',  '13 title formats to go viral in 2024'),
    12: ('ideas',   'Trend jacking'),
    13: ('rpm',     'How to get monetized with one video'),
    14: ('cases',   "Why Jubilee's one format got 50M views in a month"),
    15: ('ideas',   'The psychological triggers behind a share'),
    16: ('ai',      'Channels actually using AI well'),
    17: ('thumbs',  '50 faceless thumbnails worth studying'),
    18: ('algo',    'Why the algorithm deliberately kills your reach'),
    19: ('algo',    'Why news content gets throttled'),
    20: ('thumbs',  'AI thumbnails in about a minute'),
    21: ('scripts', 'Why the first 15 seconds beat your whole edit'),
    22: ('scripts', 'AI scripts in about a minute'),
    23: ('algo',    'How YouTube tests a new channel before trusting it'),
    24: ('algo',    'Same video, opposite results'),
    25: ('algo',    'How the algorithm treats each niche differently'),
    26: ('niches',  "Your niche isn't saturated — your format is"),
    27: ('scripts', 'The viral script blueprint'),
    28: ('algo',    'The algorithm rewards satisfaction, not quality'),
    29: ('cases',   'How I would enter a $15K/month niche with AI'),
    30: ('ai',      'Building a cartoon channel with AI'),
    31: ('algo',    'Why switching formats too often kills your reach'),
    32: ('cases',   'The system viral documentary channels use'),
    33: ('ideas',   'Viral video ideas that work every time'),
    34: ('rpm',     'How to actually get rich with YouTube'),
    35: ('cases',   '10 Shorts channels, 150 days in'),
    36: ('cases',   '34 AI long-form channels, two weeks in'),
    39: ('cases',   'What 62 billion views say about going viral'),
    40: ('start',   'What 80+ creators said actually drives growth'),
    41: ('ideas',   '80% of a blowup is the idea'),
    42: ('ideas',   'The one thing every viral video has in common'),
    43: ('thumbs',  '4 changes that took a video from 35K to 300K'),
    44: ('cases',   'From 100 views a video to 100K'),
    45: ('niches',  'The best niche on YouTube, per 300,000 videos'),
    46: ('start',   'Brutally honest truths about YouTube automation'),
    47: ('ops',     'The YouTube CMS nobody talks about'),
    48: ('start',   'Twenty years to a $7M faceless empire'),
    49: ('algo',    'Trust scores explained'),
    50: ('ai',      '$10K/month from videos that cost $5'),
    51: ('thumbs',  'Viral thumbnails with AI'),
    52: ('start',   'The 10 biggest mistakes in YouTube automation'),
    53: ('ai',      'Using VEO 3 without paying $250 a month'),
    54: ('ai',      'Running a faceless channel with an AI agent'),
    56: ('ops',     'Buy one established channel, build an empire'),
    57: ('niches',  'Niche bending and niche blending'),
    58: ('ai',      'Consistent 3D AI animation, step by step'),
    59: ('rpm',     'How to get $15–50 RPMs'),
    60: ('ideas',   'The whole ideation process'),
    61: ('scripts', 'Scripts that keep people watching'),
    62: ('ops',     'Being live 24/7 without being live'),
}

# author, date, topic, verbatim text
TIPS = [
 ('noahmorris','2025-10-10','niches',"If you can't find a good recent niche, just look at niches that were exploding 1-2 years ago and everyone forgot about. Then revive them with a new format."),
 ('noahmorris','2024-12-31','niches',"2025 niche strategy: find audiences that already are used to watching extremely long form content, and make recaps, explainers, in depth lore videos."),
 ('noahmorris','2024-12-03','niches',"One of the underrated faceless niche markets is female-oriented niches. They are the biggest consumers — if you ever go to a mall you would know a good 80% of the shops are woman oriented."),
 ('noahmorris','2024-11-04','niches',"The 4 niches I have earned most my money with, in order: TV shows · celebrity · politics · sports."),
 ('noahmorris','2025-05-03','niches',"I recommend everyone looking for niches in 2025 to go for something extremely safe. YouTube is super fragile these days."),
 ('noahmorris','2024-06-01','niches',"The biggest mistake people make researching niches: they ask why they SHOULD jump into a niche instead of why they SHOULDN'T. They fall for confirmation and survivorship bias."),
 ('noahmorris','2022-10-07','niches',"The most underrated piece of advice for YouTube is high school economics — demand and supply. I find niches that have high demand and low supply, then build a channel around it."),
 ('noahmorris','2023-09-10','ideas',"The secret to YouTube growth is to find low quality content that a lot of people already are watching, and then 10X the quality. This is true for all creators."),
 ('noahmorris','2024-02-27','ideas',"Copying other channels earns you your first $10,000. Remixing them, finding what works for you, sticking to that format, then upping the quality and stakes of every video is what earns you your first $1 million."),
 ('noahmorris','2023-10-08','titles',"3 title formats that have been getting me 1/10s: When [X character] realizes [X thing] · He [did X thing] then [did X thing] · How [insignificant character] [verb] [significant thing]."),
 ('noahmorris','2023-10-03','rpm',"Best practices to increase RPM: 16-20 min videos for best ROI · aim for US, German or Scandinavian viewers · mid-rolls on cliffhangers · duplicate profitable content, not just high-view content."),
 ('noahmorris','2023-11-17','rpm',"These 1 hour+ videos are my new favourite YouTube meta. If you find a simple format you can get 30-100k views on, with a low cost per video and simple editing, even 30-60k views makes good money."),
 ('noahmorris','2024-01-16','rpm',"Faceless channel 2023 breakdown: $150k revenue in 365 days. $70 a video, 5 videos a week, 260 videos. Total cost $19,500. Total profit $130,500."),
 ('noahmorris','2023-09-15','start',"If you're starting today you have a huge advantage. YouTube is pushing new channels like crazy to compete with TikTok on discoverability. Don't think the algorithm is against small creators — the opposite is true."),
 ('noahmorris','2024-04-21','start',"The number 1 YouTube growth hack: patience. Patience doesn't mean complacency. It means the discipline to push through while keeping a long-term perspective."),
 ('noahmorris','2025-08-20','start',"So many people claim they want to do YouTube for the next decade, but 90% operate like it's a hobby — giving up or panicking when the first 100 videos don't work out."),
 ('noahmorris','2025-01-25','start',"Being good at faceless YouTube = great at pattern recognition · great at creative problem solving · great at human psychology · great at human resources."),
 ('noahmorris','2025-04-28','ideas',"Creators should start studying Veritasium more than MrBeast. Not just packaging, storytelling and pacing — their production structure is genius, letting different people own parts of the process."),
 ('noahmorris','2025-06-27','ops',"The faceless strategies actually working in 2025: cheap, extremely long-form, semi-evergreen videos posted once a day across 3-5 channels at the same time."),
 ('noahmorris','2024-11-04','ideas',"Niche and ideation technique: create an alt Google account, subscribe to channels and watch videos in broad niches like sports or politics, then use YouTube's filters and your homepage as a research feed."),
 ('noahmorris','2025-04-20','algo',"We entered the YouTube SEO era with this new trust score system. Bunch of hacks and tricks. Really not a fan."),
 ('wannercashcow','2025-11-08','rpm',"Focus on premium countries (US/UK/CA/AUS) · older viewers (45+ with money) · audiences with buying intent · longer videos (2 hours+) · \"to fall asleep to\" content · videos that work well on TV · evergreen topics."),
 ('wannercashcow','2025-10-05','rpm',"Focus on longer videos. Focus on stuff people can fall asleep to. Focus on videos that do well on TV. Doing all 3 is literally the cheat code to high RPMs."),
 ('wannercashcow','2025-10-20','rpm',"Make longer videos. Make longer videos. Make longer videos. Make longer videos. Make longer videos."),
 ('wannercashcow','2025-03-14','niches',"The most profitable niches right now: bedtime stories · sleep meditation · relaxation sounds · study music. Why? People watch them for 20+ minutes. More watch time = more ad revenue."),
 ('wannercashcow','2025-02-04','niches',"Two faceless channels both got 6M views. One made $10,000, the other made $45,000. The only difference was their niche."),
 ('wannercashcow','2025-10-28','scripts',"Grab attention in the first 5 seconds · promise a clear benefit right away · structure like a story (hook → setup → payoff) · use open loops so people have to keep watching · use casual language."),
 ('wannercashcow','2025-07-15','ideas',"YouTube is literally just pattern recognition. You don't need new ideas — you need to notice what formats, titles and styles are repeating across niches, then move them."),
 ('PhedEU','2023-12-17','rpm',"I recently started posting 1 hour+ videos frequently. The results have been astonishing."),
 ('PhedEU','2024-10-22','rpm',"$27 RPM. You really only need 370,000 views a month to make $10K."),
 ('PhedEU','2025-06-14','niches',"Your video didn't flop because the niche is oversaturated. It flopped because your format is."),
 ('PhedEU','2024-08-02','start',"Less overthinking. More experimenting."),
 ('PhedEU','2025-09-25','niches',"Sometimes it's okay to just change the niche."),
]

def esc(s):
    return html.escape(s, quote=False)

STEP_DROP = re.compile(
    r"(bookmark to come back|re-?read this thread|i post a lot of|before we get into it"
    r"|bookmark this|save this for later|follow for more|repost the first|share this thread"
    r"|turn on notifications|that's a wrap|thanks for reading|if you found this)", re.I)

def clean_part(t):
    t = re.sub(r'https?://t\.co/\S+', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'^\d{1,2}\s*[\.\)/]\s+', '', t)   # <ol> already numbers the steps
    return t

# ---- assemble ----
items = {k: {'plays': [], 'tips': []} for k, _ in TOPICS}
counts_author = {}

for idx, (topic, title) in sorted(THREAD_MAP.items()):
    t = THREADS[idx]
    name, slug = AUTHORS[t['author']]
    parts = [clean_part(p) for p in t['parts']]
    parts = [parts[0]] + [p for p in parts[1:] if len(p) > 3 and not (STEP_DROP.search(p) and len(p) < 320)]
    items[topic]['plays'].append({'title': title, 'author': name, 'slug': slug, 'parts': parts})
    counts_author[slug] = counts_author.get(slug, 0) + 1

for author, date, topic, text in TIPS:
    name, slug = AUTHORS[author]
    items[topic]['tips'].append({'date': date, 'author': name, 'slug': slug, 'text': text})
    counts_author[slug] = counts_author.get(slug, 0) + 1

out = []
w = out.append

w('<title>The Faceless YouTube Playbook</title>')
w('<link rel="preconnect" href="https://fonts.googleapis.com">')
w('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
w('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')
w('''<style>
  :root{
    --bg:#eceeea; --surface:#ffffff; --ink:#161a15; --ink-2:#333a30; --muted:#5f6b58;
    --faint:#8a9483; --line:#d4d9cf; --line-soft:#e4e8df;
    --accent:#8a6a12; --accent-wash:#f0e6c9; --accent-ink:#ffffff;
    --shadow:0 1px 0 rgba(22,26,21,.05), 0 12px 32px -22px rgba(22,26,21,.45);
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --bg:#10120e; --surface:#181b15; --ink:#eceee7; --ink-2:#c9cec1; --muted:#95a08b;
      --faint:#727c69; --line:#2b3126; --line-soft:#212619;
      --accent:#e0b341; --accent-wash:#33290f; --accent-ink:#1a1405;
      --shadow:0 1px 0 rgba(0,0,0,.3), 0 18px 40px -26px rgba(0,0,0,.9);
    }
  }
  :root[data-theme="dark"]{
    --bg:#10120e; --surface:#181b15; --ink:#eceee7; --ink-2:#c9cec1; --muted:#95a08b;
    --faint:#727c69; --line:#2b3126; --line-soft:#212619;
    --accent:#e0b341; --accent-wash:#33290f; --accent-ink:#1a1405;
    --shadow:0 1px 0 rgba(0,0,0,.3), 0 18px 40px -26px rgba(0,0,0,.9);
  }
  *{box-sizing:border-box}
  body{background:var(--bg);color:var(--ink);
    font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
  .wrap{max-width:900px;margin:0 auto;padding:0 clamp(16px,4vw,40px) 96px}

  header.masthead{padding:clamp(38px,7vw,80px) 0 clamp(24px,4vw,34px);border-bottom:1px solid var(--line)}
  .eyebrow{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;font-weight:500;
    letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0;
    display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .eyebrow .dot{width:7px;height:7px;border-radius:50%;background:var(--accent);flex:none}
  h1{font-family:"Bricolage Grotesque","IBM Plex Sans",sans-serif;font-weight:800;
    font-size:clamp(2.3rem,6vw,4.2rem);line-height:.98;letter-spacing:-.03em;
    text-wrap:balance;margin:.32em 0 0;max-width:15ch}
  .standfirst{margin:20px 0 0;max-width:64ch;font-size:1.05rem;color:var(--ink-2)}
  .caveat{margin:16px 0 0;max-width:64ch;font-size:.93rem;color:var(--muted);
    border-left:2px solid var(--accent);padding-left:14px}
  .meta{margin:28px 0 0;display:flex;flex-wrap:wrap;border:1px solid var(--line);
    border-radius:2px;background:var(--surface);box-shadow:var(--shadow);overflow:hidden}
  .meta div{flex:1 1 140px;padding:13px 17px;border-right:1px solid var(--line-soft)}
  .meta div:last-child{border-right:0}
  .meta dt{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.65rem;
    letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin:0 0 4px}
  .meta dd{margin:0;font-size:1.02rem;font-weight:500;font-variant-numeric:tabular-nums}

  .toolbar{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 0 10px;
    border-bottom:1px solid var(--line)}
  .chiprow{display:flex;gap:7px;overflow-x:auto;padding-bottom:9px;
    scrollbar-width:none;-ms-overflow-style:none;align-items:center}
  .chiprow::-webkit-scrollbar{display:none}
  .chiprow .lbl{flex:none;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.63rem;
    letter-spacing:.13em;text-transform:uppercase;color:var(--faint);padding-right:3px}
  .chip{flex:none;display:inline-flex;align-items:baseline;gap:6px;padding:6px 12px;
    border-radius:999px;cursor:pointer;border:1px solid var(--line);background:var(--surface);
    color:var(--ink-2);font:inherit;font-size:.88rem;font-weight:500;white-space:nowrap}
  .chip .n{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.7rem;
    color:var(--faint);font-variant-numeric:tabular-nums}
  .chip:hover{border-color:var(--accent);color:var(--accent)}
  .chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
  .chip[aria-pressed="true"]:hover{color:var(--accent-ink)}
  .chip[aria-pressed="true"] .n{color:var(--accent-ink);opacity:.7}
  .searchrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding-top:3px}
  .search{flex:1 1 260px;display:flex;align-items:center;gap:9px;background:var(--surface);
    border:1px solid var(--line);border-radius:2px;padding:8px 12px;box-shadow:var(--shadow)}
  .search svg{flex:none;color:var(--faint)}
  .search input{border:0;background:transparent;color:var(--ink);font:inherit;
    font-size:.94rem;width:100%;outline:none}
  .search input::placeholder{color:var(--faint)}
  .count{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.75rem;color:var(--muted);
    font-variant-numeric:tabular-nums;white-space:nowrap}

  section.topic{padding:32px 0 6px;scroll-margin-top:90px}
  section.topic + section.topic{border-top:1px solid var(--line)}
  h2{font-family:"Bricolage Grotesque","IBM Plex Sans",sans-serif;font-weight:600;
    font-size:clamp(1.32rem,2.6vw,1.7rem);letter-spacing:-.02em;margin:0 0 6px;text-wrap:balance}
  .topic-note{color:var(--muted);font-size:.96rem;margin:0 0 18px;max-width:62ch}

  .play{border:1px solid var(--line);border-radius:2px;background:var(--surface);
    margin-bottom:10px;box-shadow:var(--shadow)}
  .play summary{list-style:none;cursor:pointer;padding:13px 16px;display:flex;
    gap:12px;align-items:baseline;flex-wrap:wrap}
  .play summary::-webkit-details-marker{display:none}
  .play summary::after{content:"+";margin-left:auto;color:var(--faint);
    font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:1.05rem;line-height:1}
  .play[open] summary::after{content:"–"}
  .play summary:hover .ptitle{color:var(--accent)}
  .ptitle{font-weight:600;font-size:1.03rem;flex:1 1 auto;min-width:12ch}
  .byline{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.7rem;
    letter-spacing:.06em;text-transform:uppercase;color:var(--faint);white-space:nowrap}
  .play ol{margin:0;padding:2px 20px 18px 40px;display:flex;flex-direction:column;gap:11px}
  .play ol li{color:var(--ink-2);font-size:.98rem}
  .play ol li::marker{color:var(--accent);font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.78rem}
  .lede{padding:0 16px 4px;margin:0 0 8px;color:var(--ink);font-size:.99rem;
    border-left:2px solid var(--accent-wash);margin-left:16px}

  ul.tips{list-style:none;margin:14px 0 0;padding:0;display:flex;flex-direction:column}
  li.tip{display:grid;grid-template-columns:1fr;gap:4px;padding:13px 0;border-top:1px solid var(--line-soft)}
  li.tip:first-child{border-top:1px solid var(--line)}
  @media (min-width:640px){li.tip{grid-template-columns:120px minmax(0,1fr);gap:0 20px;align-items:baseline}}
  .stamp{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;color:var(--faint);
    font-variant-numeric:tabular-nums;white-space:nowrap;padding-top:.3em}
  .stamp b{display:block;font-weight:500;color:var(--muted);text-transform:none;letter-spacing:0}
  .ttext{font-size:1.02rem;margin:0;color:var(--ink)}
  .hide{display:none !important}

  footer{margin-top:48px;padding-top:24px;border-top:1px solid var(--line);
    color:var(--muted);font-size:.92rem;max-width:72ch}
  footer h3{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.67rem;
    letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin:0 0 10px;font-weight:500}
  footer h3 + h3{margin-top:22px}
  footer p{margin:0 0 12px}
  .empty{display:none;padding:38px 0;color:var(--muted)}
  .empty.show{display:block}
  :focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:2px}
</style>''')

w('<div class="wrap">')
w('  <header class="masthead">')
w('    <p class="eyebrow"><span class="dot"></span> Noah Morris · Wanner · phed · 1 of 10</p>')
w('    <h1>The Faceless YouTube Playbook</h1>')
w('    <p class="standfirst">Everything four faceless-YouTube operators have taught on X, pulled out of their posts and their threads and sorted by what you are trying to do. Threads are unrolled in full — open one and you get every step, in their words. Filter by who said it, by topic, or both.</p>')
w('    <p class="caveat">These are operators selling courses, coaching and tools, and a lot of this is marketing as much as method. The numbers are their own claims, unverified. The algorithm chapter in particular is inference from public research and their own channels, not documentation. Read it as a well-informed hypothesis you should test on your own channel.</p>')
w('    <dl class="meta">')
w('      <div><dt>Playbooks</dt><dd id="nplays">—</dd></div>')
w('      <div><dt>Single tips</dt><dd id="ntips">—</dd></div>')
w('      <div><dt>Thread steps</dt><dd id="nsteps">—</dd></div>')
w('      <div><dt>Operators</dt><dd>4</dd></div>')
w('    </dl>')
w('  </header>')

w('  <main>')
w('    <div class="toolbar">')
w('      <div class="chiprow" id="whoChips" role="group" aria-label="Filter by operator"><span class="lbl">Who</span></div>')
w('      <div class="chiprow" id="topicChips" role="group" aria-label="Filter by topic"><span class="lbl">What</span></div>')
w('      <div class="searchrow">')
w('        <label class="search"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"></circle><path d="M11 11l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path></svg>')
w('        <input id="q" type="search" placeholder="Search — RPM, hook, sleep content, trust score…" aria-label="Search"></label>')
w('        <span class="count" id="count"></span>')
w('      </div>')
w('    </div>')
w('    <p class="empty" id="empty">Nothing matches. Clear the search, or tap <em>All</em> on both rows.</p>')

total_steps = 0
nplays = 0
ntips = 0

for tid, tname in TOPICS:
    blk = items[tid]
    if not blk['plays'] and not blk['tips']:
        continue
    w(f'    <section class="topic" id="{tid}" data-chip="{esc(tname)}">')
    w(f'      <h2>{esc(tname)}</h2>')
    w(f'      <p class="topic-note">{esc(TOPIC_NOTE[tid])}</p>')
    for p in blk['plays']:
        nplays += 1
        lede, steps = p['parts'][0], p['parts'][1:]
        total_steps += len(steps)
        w(f'      <details class="play" data-who="{p["slug"]}">')
        w(f'        <summary><span class="ptitle">{esc(p["title"])}</span>'
          f'<span class="byline">{esc(p["author"])} · {len(steps)} steps</span></summary>')
        w(f'        <p class="lede">{esc(lede)}</p>')
        w('        <ol>')
        for s in steps:
            w(f'          <li>{esc(s)}</li>')
        w('        </ol>')
        w('      </details>')
    if blk['tips']:
        w('      <ul class="tips">')
        for t in blk['tips']:
            ntips += 1
            w(f'        <li class="tip" data-who="{t["slug"]}">'
              f'<span class="stamp">{t["date"]}<b>{esc(t["author"])}</b></span>'
              f'<p class="ttext">{esc(t["text"])}</p></li>')
        w('      </ul>')
    w('    </section>')

w('    <footer>')
w('      <h3>Where this came from</h3>')
w('      <p>None of these accounts are archived by the Wayback Machine, so the deep-history method used for YouTube\'s own account does not work on them. Instead: their logged-out timelines were read through the syndication endpoint (about 100 posts each), and every thread either of them has had unrolled on Thread Reader was fetched and cleaned — 63 threads, 777 steps after de-duplication and stripping the sales pitches from the tails.</p>')
w('      <h3>Who is missing</h3>')
w('      <p>Julian (@julianfaceless) has no unrolled threads and his timeline endpoint was rate-limited every time it was tried; Gold has not been identified yet. Both slot straight into this page once there is a handle and the endpoint lets go — the filters are built to take more operators.</p>')
w('      <h3>1 of 10</h3>')
w('      <p>Posts credited to 1 of 10 come from the brand account and from Richard, its co-founder, who writes most of the long threads.</p>')
w('    </footer>')
w('  </main>')
w('</div>')

w('''<script>
(function(){
  var sections = [].slice.call(document.querySelectorAll('section.topic'));
  var cards = [].slice.call(document.querySelectorAll('.play, li.tip'));
  var whoBar = document.getElementById('whoChips');
  var topicBar = document.getElementById('topicChips');
  var q = document.getElementById('q');
  var countEl = document.getElementById('count');
  var empty = document.getElementById('empty');
  var who = 'all', topic = 'all';

  var WHO = [['all','All'],['noah','Noah Morris'],['wanner','Wanner'],['phed','phed'],['oneoften','1 of 10']];

  function mk(bar, id, label, n, onpick, isActive){
    var b = document.createElement('button');
    b.type='button'; b.className='chip'; b.dataset.target=id;
    b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    b.innerHTML = label + (n!=null ? ' <span class="n">'+n+'</span>' : '');
    b.addEventListener('click', function(){ onpick(id); });
    bar.appendChild(b);
    return b;
  }

  WHO.forEach(function(pair){
    var n = pair[0]==='all' ? cards.length
          : cards.filter(function(c){ return c.dataset.who===pair[0]; }).length;
    mk(whoBar, pair[0], pair[1], n, function(id){
      who = (who===id || id==='all') ? (who===id && id!=='all' ? 'all' : id) : id;
      sync(); render();
    }, pair[0]==='all');
  });

  mk(topicBar, 'all', 'All', cards.length, function(id){ topic='all'; sync(); render(); }, true);
  sections.forEach(function(s){
    var n = s.querySelectorAll('.play, li.tip').length;
    mk(topicBar, s.id, s.dataset.chip, n, function(id){
      topic = (topic===id) ? 'all' : id; sync(); render();
      if (topic!=='all') window.scrollTo({top:0, behavior:'smooth'});
    }, false);
  });

  function sync(){
    [].forEach.call(whoBar.querySelectorAll('.chip'), function(c){
      c.setAttribute('aria-pressed', c.dataset.target===who ? 'true':'false'); });
    [].forEach.call(topicBar.querySelectorAll('.chip'), function(c){
      c.setAttribute('aria-pressed', c.dataset.target===topic ? 'true':'false'); });
  }

  function render(){
    var t = q.value.trim().toLowerCase();
    var shown = 0;
    sections.forEach(function(s){
      var inTopic = (topic==='all' || topic===s.id);
      var any = false;
      [].forEach.call(s.querySelectorAll('.play, li.tip'), function(c){
        var hit = inTopic
          && (who==='all' || c.dataset.who===who)
          && (!t || c.textContent.toLowerCase().indexOf(t) !== -1);
        c.classList.toggle('hide', !hit);
        if (hit){ any = true; shown++; }
      });
      s.classList.toggle('hide', !any);
    });
    empty.classList.toggle('show', shown===0);
    countEl.textContent = shown + (shown===1 ? ' entry' : ' entries');
  }

  q.addEventListener('input', render);
  render();
})();
</script>''')

open('playbook.html','w',encoding='utf-8').write('\n'.join(out))
print('plays', nplays, 'tips', ntips, 'steps', total_steps)
print('bytes', sum(len(x) for x in out))
