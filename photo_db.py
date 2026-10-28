"""Plane photo lookup, cached by ICAO hex for one day."""
import json
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlparse
_lock=threading.Lock()
_cache={}
def lookup(hexcode):
    now=time.monotonic()
    with _lock:
        cached=_cache.get(hexcode)
        if cached and cached[0]>now:
            return cached[1]
    result=None
    try:
        req=Request('https://api.planespotters.net/pub/photos/hex/'+hexcode,headers={'User-Agent':'ADSB-TV-Widget/1.2'})
        with urlopen(req, timeout=5) as r:
            data=json.load(r)
        photos=data.get('photos',[])
        if photos:
            p=photos[0]
            url=(p.get('thumbnail') or {}).get('src')
            host=urlparse(url or '').hostname or ''
            if urlparse(url or '').scheme=='https' and (host=='planespotters.net' or host.endswith('.planespotters.net')):
                result={'url':url,'photographer':p.get('photographer') or 'Planespotters.net',
                        'link':p.get('link') or 'https://www.planespotters.net/'}
    except Exception as e:
        print('Photo lookup failed:',str(e),flush=True)
    with _lock:
        _cache[hexcode]=(now+(86400 if result else 3600),result)
        if len(_cache)>1000:
            _cache.clear()
    return result
