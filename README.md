# ADSB TV Widget

Dashboard TV per ADSB.im, sul Raspberry IU0VESADSBKAS01.

- Sorgente live: http://127.0.0.1:8080/data/aircraft.json
- Ricevitore: http://127.0.0.1:8080/data/receiver.json
- Porta dashboard: 8090
- Nessun container, pacchetto Python o database aggiuntivo.
- Mostra l'aeromobile più vicino con posizione recente, aggiornamento 1 s.
- Distanza orizzontale in km dal ricevitore; velocità ADS-B al suolo.
- Partenza/destinazione non disponibili nel feed locale, richiedono arricchimento verificato.

## Installazione Raspberry

```bash
git clone https://github.com/gas-dev/ADSB-TV-Widget.git
cd ADSB-TV-Widget
sudo sh install.sh
```

Aprire http://192.168.1.125:8090 sulla rete locale.

## Verifica

```bash
sudo systemctl status adsb-tv --no-pager
curl -s http://127.0.0.1:8090/api/live | python3 -m json.tool | head -40
```

## Aggiornamenti

```bash
cd ~/ADSB-TV-Widget
git pull --ff-only
sudo systemctl stop adsb-tv
sudo install -m 644 server.py index.html /opt/adsb-tv/
sudo systemctl start adsb-tv
```

Non esporre la porta 8090 direttamente su Internet.

## Airport countries and coordinates

The airport_db.py module downloads the public-domain OurAirports airports.csv and countries.csv in a background thread, caches matching IATA/ICAO codes in /var/cache/adsb-tv/airports.json, and provides country names and coordinates without per-second web requests. A first lookup can take some seconds. If the download fails, country remains unavailable. Source: https://ourairports.com/data/

For manual updates, copy airport_db.py alongside server.py and index.html into /opt/adsb-tv before restarting the service.

## TV setup and multi-aircraft rotation

Open `http://RASPBERRY-IP:8090/setup` and configure the maximum radius (1-500 km) and number of closest aircraft (1-20). Settings are persisted in `/var/cache/adsb-tv/settings.json`; defaults are 100 km and 1 aircraft. The TV rotates through the available closest aircraft every 10 seconds while updating telemetry and all radar positions every second. The current card is highlighted in yellow on the north-up radar, while the other selected aircraft are shown in blue. The radar's outer range is the configured maximum.

To upgrade an existing installation:

```bash
cd ~/ADSB-TV-Widget
git pull --ff-only
sudo install -m 644 server.py index.html setup.html airport_db.py photo_db.py /opt/adsb-tv/
sudo systemctl restart adsb-tv
```

To test: `curl -s http://127.0.0.1:8090/api/settings`. The setup page writes settings through `POST /api/settings`. Only expose this service on a trusted LAN because setup currently has no authentication.

## Free aircraft metadata enrichment

For aircraft actually received by the local antenna, the server asynchronously looks up HexDB (with ADSBdb as fallback) using the ICAO24 hex. It caches successful lookups for 24 hours and missing lookups for one hour, throttles new requests, and never substitutes external positions for local ADS-B. When supplied by the external database, the TV shows manufacturer, registered owner, owner country and a more detailed type as fallback. Owner is a registered owner, **not necessarily the airline or operator of the current flight**. Empty values are omitted, not guessed. The service is optional: the TV continues to work offline.

Upgrade existing devices with `sudo install -m 644 server.py index.html setup.html airport_db.py photo_db.py aircraft_db.py /opt/adsb-tv/` and restart `adsb-tv`.
