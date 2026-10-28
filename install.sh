#!/bin/sh
set -eu
if [ "$(id -u)" -ne 0 ]; then echo 'Esegui: sudo sh install.sh'; exit 1; fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -f "$SCRIPT_DIR/server.py" ] || [ ! -f "$SCRIPT_DIR/index.html" ]; then echo 'File mancanti'; exit 1; fi
if ! /usr/bin/python3 -m py_compile "$SCRIPT_DIR/server.py"; then exit 1; fi
if ss -ltn | grep -Eq ':8090[[:space:]]'; then echo 'La porta 8090 è già in uso. Nessuna modifica effettuata.'; exit 1; fi
install -d -m 755 /opt/adsb-tv
install -d -m 755 -o pi -g pi /var/cache/adsb-tv
install -m 644 "$SCRIPT_DIR/server.py" "$SCRIPT_DIR/index.html" "$SCRIPT_DIR/airport_db.py" /opt/adsb-tv/
cat > /etc/systemd/system/adsb-tv.service <<'UNIT'
[Unit]
Description=Lightweight ADS-B TV widget
After=network-online.target docker.service
Wants=network-online.target
[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/opt/adsb-tv
ExecStart=/usr/bin/python3 /opt/adsb-tv/server.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/cache/adsb-tv
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now adsb-tv.service
sleep 1
systemctl --no-pager --full status adsb-tv.service || true
echo 'Dashboard: http://192.168.1.125:8090'
