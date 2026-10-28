"""Small background airport-country lookup using public-domain OurAirports data."""
import csv
import io
import json
import os
import threading
import time
from pathlib import Path
from urllib.request import urlopen

CACHE = Path('/home/pi/.cache/adsb-tv/airports.json')
BASE_URL = 'https://davidmegginson.github.io/ourairports-data/'
_lock = threading.Lock()
_index = {}
_loading = False
_last_attempt = 0.0

def _download(name):
    with urlopen(BASE_URL + name, timeout=30) as r:
        return r.read().decode('utf-8-sig')

def _refresh():
    global _index, _loading
    try:
        with _lock:
            current = dict(_index)
        if not current and CACHE.exists():
            try:
                current = json.loads(CACHE.read_text(encoding='utf-8'))
            except (OSError,ValueError):
                current = {}
        if not current or time.time() - CACHE.stat().st_mtime > 30*86400:
            country_rows = csv.DictReader(io.StringIO(_download('countries.csv')))
            countries = {row['code']: row['name'] for row in country_rows
                         if row.get('code') and row.get('name')}
            airport_rows = csv.DictReader(io.StringIO(_download('airports.csv')))
            updated = {}
            for row in airport_rows:
                country = countries.get(row.get('iso_country'))
                if not country:
                    continue
                item = {'country':country}
                try:
                    item['lat'] = float(row['latitude_deg'])
                    item['lon'] = float(row['longitude_deg'])
                except (ValueError,KeyError,TypeError):
                    pass
                for key in ('iata_code','icao_code'):
                    code = (row.get(key) or '').strip().upper()
                    if code and len(code) in (3,4):
                        updated[code] = item
            if updated:
                current = updated
                CACHE.parent.mkdir(parents=True,exist_ok=True)
                tmp = CACHE.with_suffix('.tmp')
                tmp.write_text(json.dumps(updated,separators=(',',':')),encoding='utf-8')
                os.replace(tmp,CACHE)
        with _lock:
            _index = current
    except Exception as exc:
        print('Airport lookup update failed:',str(exc),flush=True)
    finally:
        with _lock:
            _loading = False

def lookup(code):
    global _loading, _last_attempt
    code = str(code or '').strip().upper()
    if not code:
        return None
    now=time.monotonic()
    with _lock:
        item=_index.get(code)
        if item:
            return dict(item)
        if not _loading and now-_last_attempt>120:
            _loading=True
            _last_attempt=now
            threading.Thread(target=_refresh,daemon=True).start()
    return None
