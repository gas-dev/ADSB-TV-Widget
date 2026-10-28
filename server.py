#!/usr/bin/env python3
"""Lightweight, dependency-free ADS-B TV companion."""
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen, Request

BASE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8080/data/'
PORT = int(os.environ.get('ADSB_TV_PORT', '8090'))

ROUTES_URL = 'https://adsb.im/api/0/routeset'
route_cache = {}
route_lock = threading.Lock()
last_route_request = 0.0

def load_route(callsign, lat, lon):
    try:
        payload = json.dumps({'planes':[{'callsign':callsign,'lat':lat,'lng':lon}]}).encode()
        req = Request(ROUTES_URL, data=payload, headers={'Content-Type':'application/json',
                    'Accept':'application/json','User-Agent':'ADSB-TV-Widget/1.1'}, method='POST')
        with urlopen(req, timeout=6) as r:
            rows = json.load(r)
        route = None
        if isinstance(rows,list):
            row = next((x for x in rows if isinstance(x,dict) and
                        str(x.get('callsign','')).strip().upper()==callsign), None)
            if row and row.get('plausible') is True:
                airports = row.get('_airports')
                if isinstance(airports,list) and len(airports)>=2:
                    a,b = airports[0], airports[-1]
                    if isinstance(a,dict) and isinstance(b,dict):
                        origin = a.get('iata') or a.get('icao')
                        destination = b.get('iata') or b.get('icao')
                        if origin and destination:
                            route={'origin':origin,'destination':destination,
                                   'origin_name':a.get('name'),'destination_name':b.get('name'),
                                   'provider':'adsb.im','estimated':True}
        with route_lock:
            route_cache[callsign]=(time.monotonic()+(3600 if route else 300),route)
    except Exception:
        with route_lock:
            route_cache[callsign]=(time.monotonic()+180,None)

def get_route(a):
    global last_route_request
    callsign=str(a.get('flight') or '').strip().upper()
    if not callsign or not isinstance(a.get('lat'),(int,float)) or not isinstance(a.get('lon'),(int,float)):
        return None
    now=time.monotonic()
    with route_lock:
        item=route_cache.get(callsign)
        if item and item[0]>now:
            return item[1]
        if now-last_route_request<15:
            return None
        last_route_request=now
        route_cache[callsign]=(now+45,None)
    threading.Thread(target=load_route,args=(callsign,a['lat'],a['lon']),daemon=True).start()
    return None


def read_json(name):
    with urlopen(URL + name, timeout=2.5) as r:
        return json.load(r)

def distance_nm(a, b, c, d):
    r = 3440.065
    x1, x2 = math.radians(float(a)), math.radians(float(c))
    dy = x2-x1
    dx = math.radians(float(d)-float(b))
    h = math.sin(dy/2)**2 + math.cos(x1)*math.cos(x2)*math.sin(dx/2)**2
    return 2*r*math.asin(min(1.0, math.sqrt(h)))

def live():
    data = read_json('aircraft.json')
    receiver = read_json('receiver.json')
    lat0, lon0 = receiver.get('lat'), receiver.get('lon')
    candidates = []
    for a in data.get('aircraft', []):
        if not isinstance(a.get('lat'), (int,float)) or not isinstance(a.get('lon'),(int,float)):
            continue
        if float(a.get('seen_pos', 9999)) > 15 or float(a.get('seen',9999)) > 15:
            continue
        nm = a.get('r_dst')
        if not isinstance(nm, (int,float)) and isinstance(lat0,(int,float)) and isinstance(lon0,(int,float)):
            nm = distance_nm(lat0, lon0, a['lat'], a['lon'])
        if not isinstance(nm,(int,float)):
            continue
        b = dict(a)
        km = nm * 1.852
        if km > 100:
            continue
        b['distance_km'] = round(km,1)
        candidates.append(b)
    candidates.sort(key=lambda a: a['distance_km'])
    if candidates:
        candidates[0]['route'] = get_route(candidates[0])
    return {'now':data.get('now'),'count':len(data.get('aircraft',[])),
            'positioned':len(candidates),'receiver':{'lat':lat0,'lon':lon0},
            'aircraft':candidates[:10], 'radius_km':100,'source':'local ADS-B readsb'}

class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, mime):
        self.send_response(code)
        self.send_header('Content-Type',mime)
        self.send_header('Cache-Control','no-store, max-age=0')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/index.html'):
            self.send(200, (BASE/'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif path == '/api/live':
            try:
                output = live()
                code = 200
            except Exception as e:
                output = {'error':str(e)}
                code = 503
            self.send(code, json.dumps(output,separators=(',',':')).encode(), 'application/json')
        elif path == '/favicon.ico':
            self.send(204,b'','image/x-icon')
        else:
            self.send(404,b'Not found','text/plain; charset=utf-8')
    def log_message(self, fmt, *args):
        if not self.path.startswith('/api/live'):
            super().log_message(fmt,*args)

if __name__ == '__main__':
    print(f'ADS-B TV listening on {PORT}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
