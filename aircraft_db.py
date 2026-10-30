"""Optional free, cached aircraft metadata. Never provides live positions."""
import json
import threading
import time
from urllib.request import Request, urlopen

_lock=threading.Lock()
_cache={}
_last_request=0.0
FIELDS=('registration','manufacturer','type','registered_owner','registered_owner_country_name','operator_flag_code','source')
def _load(hexcode):
    data=None
    for source,url in (
        ('HexDB','https://hexdb.io/api/v2/aircraft/'+hexcode),
        ('ADSBdb','https://api.adsbdb.com/v0/aircraft/'+hexcode),
    ):
        try:
            req=Request(url,headers={'User-Agent':'ADSB-TV-Widget/2.0','Accept':'application/json'})
            with urlopen(req,timeout=5) as response:
                obj=json.load(response)
            if source=='ADSBdb':
                obj=(obj.get('response') or {}).get('aircraft') or {}
                candidate={
                    'registration':obj.get('registration'),'manufacturer':obj.get('manufacturer'),
                    'type':obj.get('type'),'registered_owner':obj.get('registered_owner'),
                    'registered_owner_country_name':obj.get('registered_owner_country_name'),
                    'operator_flag_code':obj.get('registered_owner_operator_flag_code'),'source':source}
            else:
                candidate={k:obj.get(k) for k in FIELDS if k!='source'}
                candidate['source']=source
            if any(candidate.get(k) for k in ('registration','manufacturer','registered_owner')):
                data={k:v for k,v in candidate.items() if k in FIELDS and isinstance(v,str) and v.strip()}
                break
        except Exception as exc:
            print('Aircraft metadata lookup failed:',source,hexcode,str(exc),flush=True)
    with _lock:
        _cache[hexcode]=(time.monotonic()+(86400 if data else 3600),data)

def lookup(hexcode):
    global _last_request
    code=str(hexcode or '').lower()
    if len(code)!=6 or any(c not in '0123456789abcdef' for c in code): return None
    now=time.monotonic()
    with _lock:
        cached=_cache.get(code)
        if cached and cached[0]>now: return cached[1]
        if now-_last_request<3: return None
        _last_request=now
        _cache[code]=(now+45,None)
    threading.Thread(target=_load,args=(code,),daemon=True).start()
    return None
