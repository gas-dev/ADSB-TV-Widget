"""Cached photos for the exact aircraft, using ICAO24 and registration."""
import json
import threading
import time
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
_lock=threading.Lock()
_cache={}

def fetch(url):
    req=Request(url,headers={'User-Agent':'ADSB-TV-Widget/1.3','Accept':'application/json'})
    with urlopen(req,timeout=6) as response:
        return json.load(response)

def planespotters(part):
    data=fetch('https://api.planespotters.net/pub/photos/'+part)
    for p in data.get('photos',[]):
        for field in ('thumbnail','thumbnail_large'):
            image=p.get(field) or {}
            url=image.get('src') if isinstance(image,dict) else None
            host=urlparse(url or '').hostname or ''
            if urlparse(url or '').scheme=='https' and (host=='planespotters.net' or host.endswith('.planespotters.net')):
                return {'url':url,'photographer':p.get('photographer') or 'Planespotters.net',
                        'link':p.get('link') or 'https://www.planespotters.net/',
                        'source':'Planespotters.net'}
    return None

def lookup(hexcode, registration=None):
    reg=str(registration or '').strip().upper()
    key=(hexcode,reg)
    now=time.monotonic()
    with _lock:
        cached=_cache.get(key)
        if cached and cached[0]>now:
            return cached[1]
    result=None
    try:
        result=planespotters('hex/'+hexcode)
    except Exception as exc:
        print('Photo hex lookup failed:',str(exc),flush=True)
    if not result and reg and len(reg)<=14 and all(c.isalnum() or c=='-' for c in reg):
        try:
            result=planespotters('reg/'+quote(reg,safe=''))
        except Exception as exc:
            print('Photo reg lookup failed:',str(exc),flush=True)
    if not result:
        try:
            data=fetch('https://hexdb.io/api/v2/aircraft/'+hexcode)
            url=(data.get('images') or {}).get('thumbnail')
            parsed=urlparse(url or '')
            if parsed.scheme=='https' and parsed.hostname=='hexdb.io':
                result={'url':url,'photographer':None,'source':'HexDB','link':'https://hexdb.io/'}
        except Exception as exc:
            print('HexDB lookup failed:',str(exc),flush=True)
    with _lock:
        _cache[key]=(now+(86400 if result else 900),result)
        if len(_cache)>1000:
            _cache.clear()
    return result
