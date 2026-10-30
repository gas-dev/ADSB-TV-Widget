"""Free supplementary aircraft metadata, cached and loaded off the ADS-B request path."""
import json
import threading
import time
from urllib.request import Request, urlopen

_lock=threading.Lock()
_cache={}
_last_request=0.0
FIELDS=('registration','manufacturer','type','registered_owner','registered_owner_country_name','operator_flag_code','source')

def _load(hexcode):
    data={}
    providers=[]
    for source,url in (
        ('HexDB','https://hexdb.io/api/v2/aircraft/'+hexcode),
        ('ADSBdb','https://api.adsbdb.com/v0/aircraft/'+hexcode),
    ):
        try:
            req=Request(url,headers={'User-Agent':'ADSB-TV-Widget/2.1','Accept':'application/json'})
            with urlopen(req,timeout=5) as response:
                obj=json.load(response)
            if not isinstance(obj,dict):
                continue
            if source=='ADSBdb':
                obj=(obj.get('response') or {}).get('aircraft') or {}
                if not isinstance(obj,dict): continue
            candidate={
                'registration':obj.get('registration'),
                'manufacturer':obj.get('manufacturer'),
                'type':obj.get('type'),
                'registered_owner':obj.get('registered_owner'),
                'registered_owner_country_name':obj.get('registered_owner_country_name'),
                'operator_flag_code':obj.get('operator_flag_code') or obj.get('registered_owner_operator_flag_code')
            }
            used=False
            for key,value in candidate.items():
                if key not in data and isinstance(value,str) and value.strip():
                    data[key]=value.strip()
                    used=True
            if used: providers.append(source)
        except Exception as exc:
            print('Aircraft metadata lookup failed:',source,hexcode,str(exc),flush=True)
    if data: data['source']=', '.join(providers)
    with _lock:
        _cache[hexcode]=(time.monotonic()+(86400 if data else 300),data or None)

def lookup(hexcode):
    global _last_request
    code=str(hexcode or '').lower()
    if len(code)!=6 or any(c not in '0123456789abcdef' for c in code): return None
    now=time.monotonic()
    with _lock:
        cached=_cache.get(code)
        if cached and cached[0]>now: return cached[1]
        if now-_last_request<2: return None
        _last_request=now
        _cache[code]=(now+30,None)
    threading.Thread(target=_load,args=(code,),daemon=True).start()
    return None
