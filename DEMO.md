# Public demo deployment

The live example is available at **https://adsbtv.gasdev.eu/**. Its receiving antenna is near **Comiso Airport, Sicily, Italy**. Geographic reference: **IATA CIY**, airport reference coordinates **36.995833° N, 14.608889° E**. These are airport coordinates, **not** the antenna's precise location.

This guide describes how to publish the TV dashboard without enabling browser-based administration. The normal private/LAN installation remains configurable using `/setup`.

## Modes

- **Trusted LAN (default, `ADSB_TV_READ_ONLY=0`):** `/setup` and `GET/POST /api/settings` are available without authentication. Do not expose this mode to the Internet.
- **Public demo (`ADSB_TV_READ_ONLY=1`):** setup is hidden; both settings methods return HTTP 403; the TV and its essential data endpoints remain available. The service has no authentication or per-client privilege distinction.

| Request | Private / trusted LAN | Public read-only |
| --- | --- | --- |
| `GET /` | 200 | 200 |
| `GET /setup` or `/setup.html` | 200 | 404 |
| `GET /api/settings` | 200 | 403 |
| `POST /api/settings` | 200 for valid input | 403 |
| `GET /api/live` | 200 when feeder is healthy | 200 when feeder is healthy, minimized payload |
| `GET /api/photo/{icao24}` | available | available |
| Unknown routes | 404 | 404 |

`/api/live` supplies the on-screen aircraft positions relative to the receiver and the display settings needed to render the TV. Disabling it would disable the dashboard's live functionality. The photo endpoint remains enabled for optional aircraft imagery.

In public mode, `/api/live` omits the receiver's explicit latitude/longitude, individual aircraft latitude/longitude, feeder host/port and additional fields not needed by the TV. This **does not guarantee privacy of the receiver location**: relative distance and bearing, aircraft identity, and public ADS-B observations can permit approximate location inference. If your station's exact or approximate location is sensitive, do not publish a live receiver feed without additional controls.

## Install and configure locally first

Follow the [README](README.md) to install the receiver companion, then configure the feeder via `http://DEVICE-IP:8090/setup` **before** enabling read-only mode.

Settings are stored in `/var/cache/adsb-tv/settings.json`. The application does not need access to the public Internet to receive local telemetry, although external enrichment features may then be unavailable.

## Enable public read-only mode

Create a systemd drop-in without an interactive editor:

```bash
sudo mkdir -p /etc/systemd/system/adsb-tv.service.d
printf '[Service]\nEnvironment=ADSB_TV_READ_ONLY=1\n' | \
  sudo tee /etc/systemd/system/adsb-tv.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart adsb-tv
```

Confirm that systemd loaded the flag:

```bash
systemctl show adsb-tv -p Environment
systemctl is-active adsb-tv
```

Do not enable `ADSB_TV_READ_ONLY=0` on an Internet-accessible instance just to change settings. Edit the local configuration file while read-only stays active, validate JSON, and restart:

```bash
sudo cp -a /var/cache/adsb-tv/settings.json \
  /var/cache/adsb-tv/settings.json.backup
sudo nano /var/cache/adsb-tv/settings.json
python3 -m json.tool /var/cache/adsb-tv/settings.json >/dev/null && \
  sudo systemctl restart adsb-tv
```

The settings file must retain correct permissions for the service account.

## Verification

Run these checks against the local service:

```bash
curl -s -o /dev/null -w 'Dashboard: %{http_code}\n' http://127.0.0.1:8090/
curl -s -o /dev/null -w 'Setup: %{http_code}\n' http://127.0.0.1:8090/setup
curl -s -o /dev/null -w 'GET settings: %{http_code}\n' http://127.0.0.1:8090/api/settings
curl -s -o /dev/null -w 'POST settings: %{http_code}\n' \
  -X POST http://127.0.0.1:8090/api/settings \
  -H 'Content-Type: application/json' -d '{}'
curl -s -o /dev/null -w 'Live: %{http_code}\n' http://127.0.0.1:8090/api/live
```

Expected codes: **200, 404, 403, 403, 200** when the feeder is working. A 503 for live means the application could not obtain the feeder data. HTTP 200 on setup or settings means read-only is not enforced by the running code or configuration.

Verify that explicit receiver and aircraft coordinates are not sent in the public payload:

```bash
curl -fsS http://127.0.0.1:8090/api/live | python3 -c '
import json,sys
data=json.load(sys.stdin)
assert data.get("receiver")=={}, "Receiver location exposed"
assert all("lat" not in a and "lon" not in a for a in data.get("aircraft",[])), "Aircraft coordinates exposed"
assert "feeder_host" not in data.get("settings",{}), "Feeder host exposed"
assert "feeder_port" not in data.get("settings",{}), "Feeder port exposed"
print("Explicit receiver/aircraft coordinates and feeder address not present")
'
```

After publishing behind HTTPS, run the same HTTP status checks using the **public domain** instead of `http://127.0.0.1:8090`. This distinguishes a properly protected public service from one protected only on localhost.

## Network deployment

- Use a properly configured HTTPS reverse proxy or tunnel. Do **not** forward TCP 8090 directly from the router.
- Where a reverse proxy runs on the same host, bind the service to loopback using `Environment=ADSB_TV_HOST=127.0.0.1` in the systemd drop-in. Do not use this setting if the proxy or tunnel needs to access the service from another host or container network.
- Protect the service from excessive request volumes at the proxy. The browser requests live updates approximately once per second; the backend fetches fresh feeder data for those requests.
- External metadata/photo providers may impose access limits or terms of use.
- This mode is read-only, **not** a complete security boundary. The data endpoints remain publicly accessible to API clients and not merely to the dashboard UI.

## Updating an existing installation

After a normal compatible Git history update:

```bash
cd ~/ADSB-TV-Widget
git pull --ff-only
sudo sh install.sh
```

**Special case for installations cloned before the project's initial public history reset (November 2026):** the local branch has a different history and `git pull --ff-only` cannot reconcile it. Back up your local changes and `/var/cache/adsb-tv/settings.json` first. If the local Git working tree has no changes you need, use:

```bash
cd ~/ADSB-TV-Widget
git fetch origin main
git status --short
git reset --hard origin/main
sudo install -m 644 server.py index.html setup.html \
  airport_db.py photo_db.py aircraft_db.py /opt/adsb-tv/
sudo systemctl restart adsb-tv
```

`git reset --hard` discards local changes to tracked repository files; it does not touch settings stored in `/var/cache/adsb-tv/`.

## Licensing

Source availability does not grant commercial rights. Review [LICENSE.md](LICENSE.md) and contact **iu0ves@ipaddress.email** to request a commercial license.
