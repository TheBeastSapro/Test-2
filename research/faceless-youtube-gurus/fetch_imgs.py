import io, json, os, sys, hashlib, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

urls = [u.strip() for u in open('img_urls.txt') if u.strip()]
MAXW = 340
def key(u): return hashlib.sha1(u.encode()).hexdigest()[:16]

def grab(u):
    out = f'imgcache/{key(u)}.jpg'
    if os.path.exists(out) and os.path.getsize(out) > 0: return ('cached', u)
    full = u + ('&' if '?' in u else '?') + 'format=jpg&name=small'
    try:
        req = urllib.request.Request(full, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        raw = urllib.request.urlopen(req, timeout=25).read()
        im = Image.open(io.BytesIO(raw)).convert('RGB')
        im.thumbnail((MAXW, MAXW*3))
        im.save(out, 'JPEG', quality=64, optimize=True, progressive=True)
        return ('ok', u)
    except Exception as e:
        return ('fail:%s' % type(e).__name__, u)

with ThreadPoolExecutor(max_workers=10) as ex:
    res = list(ex.map(grab, urls))
from collections import Counter
print(Counter(r[0] for r in res))
tot = sum(os.path.getsize(f'imgcache/{key(u)}.jpg') for u in urls if os.path.exists(f'imgcache/{key(u)}.jpg'))
print('cached bytes', tot, '=', round(tot/1024/1024,2), 'MB')
