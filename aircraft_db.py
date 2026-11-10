"""Free, optional aircraft metadata. Local ADS-B remains authoritative."""
import json
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

_lock=threading.Lock()
_cache={}
_last_request=0.0
FIELDS=('registration','manufacturer','type','registered_owner','registered_owner_country_name','operator_flag_code')

def _fetch(url):
    try:
        req=Request(url,headers={'User-Agent':'ADSB-TV-Widget/2.2','Accept':'application/json'})
        with urlopen(req,timeout=5) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code==404:
            return None  # Missing aircraft is normal, not a service failure.
        print('Aircraft metadata HTTP error:',exc.code,url,flush=True)
    except Exception as exc:
        print('Aircraft metadata connection error:',str(exc),flush=True)
    return None

def _load(hexcode,reg):
    result={}
    providers=[]
    requests=[
        ('HexDB','https://hexdb.io/api/v2/aircraft/'+hexcode,'hex'),
        ('ADSBdb','https://api.adsbdb.com/v0/aircraft/'+hexcode,'hex'),
    ]
    if reg and len(reg)<=14 and all(c.isalnum() or c=='-' for c in reg):
        requests.extend([
            ('HexDB','https://hexdb.io/api/v2/aircraft?registration='+quote(reg,safe=''),'reg'),
            ('ADSBdb','https://api.adsbdb.com/v0/aircraft/'+quote(reg,safe=''),'reg'),
        ])
    for source,url,method in requests:
        raw=_fetch(url)
        if not isinstance(raw,dict): continue
        if source=='HexDB' and method=='reg':
            rows=raw.get('results') or []
            raw=next((a for a in rows if isinstance(a,dict) and str(a.get('hex','')).lower()==hexcode),None)
        elif source=='ADSBdb':
            raw=(raw.get('response') or {}).get('aircraft')
        if not isinstance(raw,dict): continue
        actual=raw.get('hex') or raw.get('mode_s')
        if actual and str(actual).lower()!=hexcode: continue
        if method=='reg' and not actual: continue  # Never join unverified registrations.
        candidate={
            'registration':raw.get('registration'),
            'manufacturer':raw.get('manufacturer'),
            'type':raw.get('type'),
            'registered_owner':raw.get('registered_owner'),
            'registered_owner_country_name':raw.get('registered_owner_country_name'),
            'operator_flag_code':raw.get('operator_flag_code') or raw.get('registered_owner_operator_flag_code'),
        }
        used=False
        for key,value in candidate.items():
            if key not in result and isinstance(value,str) and value.strip():
                result[key]=value.strip()
                used=True
        if used and source not in providers: providers.append(source)
        if all(result.get(k) for k in ('registration','manufacturer','type','registered_owner','registered_owner_country_name')):
            break
    if result: result['source']=', '.join(providers)
    with _lock:
        _cache[(hexcode,reg)]=(time.monotonic()+(86400 if result else 900),result or None)

def lookup(hexcode,registration=None):
    global _last_request
    code=str(hexcode or '').lower()
    reg=str(registration or '').strip().upper()
    if len(code)!=6 or any(c not in '0123456789abcdef' for c in code): return None
    key=(code,reg)
    now=time.monotonic()
    with _lock:
        item=_cache.get(key)
        if item and item[0]>now: return item[1]
        if now-_last_request<2: return None
        _last_request=now
        _cache[key]=(now+30,None)
    threading.Thread(target=_load,args=(code,reg),daemon=True).start()
    return None
