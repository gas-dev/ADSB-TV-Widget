#!/usr/bin/env python3
"""Lightweight, dependency-free ADS-B TV companion."""
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from urllib.request import urlopen, Request
from airport_db import lookup as lookup_airport
from photo_db import lookup as lookup_photo
from aircraft_db import lookup as lookup_aircraft_metadata

BASE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8080/data/'
PORT = int(os.environ.get('ADSB_TV_PORT', '8090'))

SETTINGS_FILE = Path('/var/cache/adsb-tv/settings.json')
DEFAULT_SETTINGS = {'radius_km':100,'aircraft_count':1}
settings_lock=threading.Lock()
def validate_settings(data):
    if not isinstance(data,dict): raise ValueError('Expected settings object')
    radius=data.get('radius_km',100)
    count=data.get('aircraft_count',1)
    if type(radius) not in (int,float) or not math.isfinite(radius) or not 1<=radius<=500: raise ValueError('radius_km must be 1 to 500')
    if type(count)!=int or not 1<=count<=20: raise ValueError('aircraft_count must be 1 to 20')
    return {'radius_km':round(radius,1),'aircraft_count':count}
def read_settings():
    try: return validate_settings(json.loads(SETTINGS_FILE.read_text()))
    except (OSError,ValueError,TypeError): return dict(DEFAULT_SETTINGS)
def write_settings(data):
    with settings_lock:
        settings=validate_settings(data)
        temp=SETTINGS_FILE.with_suffix('.tmp')
        temp.write_text(json.dumps(settings))
        os.replace(temp,SETTINGS_FILE)
    return settings

ROUTES_URL = 'https://adsb.im/api/0/routeset'
route_cache = {}
route_lock = threading.Lock()
last_route_request = 0.0
ROUTE_RETRY_SECONDS = 45
ROUTE_REFRESH_SECONDS = 600
ROUTE_MIN_SPACING_SECONDS = 10

def airport_coords(a):
    """Accept documented coordinate shapes only; never guess from airport code."""
    if not isinstance(a, dict):
        return None
    loc = a.get('location')
    if isinstance(loc, dict):
        a = {**loc, **a}
    lat = a.get('lat', a.get('latitude'))
    lon = a.get('lon', a.get('lng', a.get('longitude')))
    if isinstance(lat,(float,int)) and isinstance(lon,(float,int)) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return (lat,lon)
    return None

def route_from_adsbdb(callsign):
    req = Request('https://api.adsbdb.com/v0/callsign/' + quote(callsign, safe=''),
                  headers={'User-Agent':'ADSB-TV-Widget/1.4','Accept':'application/json'})
    with urlopen(req, timeout=5) as response:
        payload = json.load(response)
    flight = (payload.get('response') or {}).get('flightroute') or {}
    origin = flight.get('origin') or {}
    destination = flight.get('destination') or {}
    oc = origin.get('iata_code') or origin.get('icao_code')
    dc = destination.get('iata_code') or destination.get('icao_code')
    if not oc or not dc:
        return None
    coords = None
    if isinstance(destination.get('latitude'),(float,int)) and isinstance(destination.get('longitude'),(float,int)):
        coords = (destination['latitude'], destination['longitude'])
    return {'origin':oc,'destination':dc,
            'origin_name':origin.get('name'),'destination_name':destination.get('name'),
            'origin_country':origin.get('country_name'),'destination_country':destination.get('country_name'),
            'destination_coords':coords,'provider':'ADSBdb','estimated':True}

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
            if row:
                airports = row.get('_airports') or row.get('airports')
                if isinstance(airports,list) and len(airports)>=2:
                    a,b = airports[0], airports[-1]
                    if isinstance(a,dict) and isinstance(b,dict):
                        origin = a.get('iata') or a.get('icao')
                        destination = b.get('iata') or b.get('icao')
                        if origin and destination:
                            route={'origin':origin,'destination':destination,
                                   'origin_name':a.get('name'),'destination_name':b.get('name'),
                                   'origin_country':a.get('country_name') or a.get('country'),
                                   'destination_country':b.get('country_name') or b.get('country'),
                                   'provider':'adsb.im','estimated':True,
                                   'plausible':row.get('plausible'),
                                   'destination_coords':airport_coords(b)}
        if not route:
            try:
                route = route_from_adsbdb(callsign)
            except Exception as exc:
                print('ADSBdb lookup failed:',callsign,str(exc),flush=True)
        if not route:
            print('Route unavailable:',callsign,flush=True)
        with route_lock:
            route_cache[callsign]=(time.monotonic()+(ROUTE_REFRESH_SECONDS if route else ROUTE_RETRY_SECONDS),route)
    except Exception as exc:
        print('Primary route lookup failed:',callsign,str(exc),flush=True)
        try:
            route = route_from_adsbdb(callsign)
        except Exception as fallback_error:
            print('Fallback route lookup failed:',callsign,str(fallback_error),flush=True)
            route = None
        with route_lock:
            route_cache[callsign]=(time.monotonic()+(ROUTE_REFRESH_SECONDS if route else ROUTE_RETRY_SECONDS),route)

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
        if now-last_route_request<ROUTE_MIN_SPACING_SECONDS:
            return None
        last_route_request=now
        route_cache[callsign]=(now+ROUTE_RETRY_SECONDS,None)
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
    settings=read_settings()
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
        if km > settings['radius_km']:
            continue
        b['distance_km'] = round(km,1)
        candidates.append(b)
    candidates.sort(key=lambda a: a['distance_km'])
    candidates=candidates[:settings['aircraft_count']]
    for aircraft in candidates:
        aircraft['metadata'] = lookup_aircraft_metadata(aircraft.get('hex'), aircraft.get('r'))
        route = get_route(aircraft)
        if route:
            route = dict(route)
            origin_airport = lookup_airport(route.get('origin'))
            dest_airport = lookup_airport(route.get('destination'))
            if origin_airport and origin_airport.get('country'):
                route['origin_country'] = origin_airport['country']
            if dest_airport and dest_airport.get('country'):
                route['destination_country'] = dest_airport['country']
            coords = route.pop('destination_coords', None)
            if not coords and dest_airport and 'lat' in dest_airport and 'lon' in dest_airport:
                coords = (dest_airport['lat'], dest_airport['lon'])
            if coords:
                route['distance_to_destination_km'] = round(
                    distance_nm(aircraft['lat'], aircraft['lon'], coords[0], coords[1])*1.852,1)
        aircraft['route'] = route
    return {'now':data.get('now'),'count':len(data.get('aircraft',[])),
            'positioned':len(candidates),'receiver':{'lat':lat0,'lon':lon0},
            'aircraft':candidates, 'radius_km':settings['radius_km'], 'aircraft_count':settings['aircraft_count'], 'source':'local ADS-B readsb'}

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
        elif path in ('/setup','/setup.html'):
            self.send(200,(BASE/'setup.html').read_bytes(),'text/html; charset=utf-8')
        elif path == '/api/settings':
            self.send(200,json.dumps(read_settings()).encode(),'application/json')
        elif path == '/api/live':
            try:
                output = live()
                code = 200
            except Exception as e:
                output = {'error':str(e)}
                code = 503
            self.send(code, json.dumps(output,separators=(',',':')).encode(), 'application/json')
        elif path.startswith('/api/photo/'):
            code = path[len('/api/photo/'):].lower()
            if len(code) != 6 or any(ch not in '0123456789abcdef' for ch in code):
                self.send(400,b'{"error":"invalid hex"}','application/json')
            else:
                self.send(200,json.dumps({'photo':lookup_photo(code, parse_qs(urlsplit(self.path).query).get('reg',[''])[0])}).encode(),'application/json')
        elif path == '/favicon.ico':
            self.send(204,b'','image/x-icon')
        else:
            self.send(404,b'Not found','text/plain; charset=utf-8')
    def do_POST(self):
        if urlsplit(self.path).path!='/api/settings':
            self.send(404,b'Not found','text/plain; charset=utf-8')
            return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096: raise ValueError('Invalid request size')
            settings=write_settings(json.loads(self.rfile.read(length)))
            self.send(200,json.dumps(settings).encode(),'application/json')
        except (ValueError,TypeError) as exc:
            self.send(400,json.dumps({'error':str(exc)}).encode(),'application/json')
        except OSError as exc:
            print('Settings write failed:',exc,flush=True)
            self.send(500,b'{"error":"Unable to save settings"}','application/json')
    def log_message(self, fmt, *args):
        if not self.path.startswith('/api/live'):
            super().log_message(fmt,*args)

if __name__ == '__main__':
    print(f'ADS-B TV listening on {PORT}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
