#!/usr/bin/env python3
"""Lightweight, dependency-free ADS-B TV companion."""
import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

BASE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8080/data/'
PORT = int(os.environ.get('ADSB_TV_PORT', '8090'))

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
        b['distance_km'] = round(nm*1.852,1)
        candidates.append(b)
    candidates.sort(key=lambda a: a['distance_km'])
    return {'now':data.get('now'),'count':len(data.get('aircraft',[])),
            'positioned':len(candidates),'receiver':{'lat':lat0,'lon':lon0},
            'aircraft':candidates[:10], 'source':'local ADS-B readsb'}

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
        if self.path in ('/', '/index.html'):
            self.send(200, (BASE/'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/api/live':
            try:
                output = live()
                code = 200
            except Exception as e:
                output = {'error':str(e)}
                code = 503
            self.send(code, json.dumps(output,separators=(',',':')).encode(), 'application/json')
        else:
            self.send(404,b'Not found','text/plain; charset=utf-8')
    def log_message(self, fmt, *args):
        if not self.path.startswith('/api/live'):
            super().log_message(fmt,*args)

if __name__ == '__main__':
    print(f'ADS-B TV listening on {PORT}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
