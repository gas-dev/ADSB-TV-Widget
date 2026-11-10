#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run: sudo sh install.sh" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for file in server.py index.html setup.html airport_db.py photo_db.py aircraft_db.py; do
    if [ ! -f "$SCRIPT_DIR/$file" ]; then
        echo "Missing application file: $file" >&2
        exit 1
    fi
done

USER_NAME=${ADSB_TV_USER:-${SUDO_USER:-}}
if [ -z "$USER_NAME" ] || [ "$USER_NAME" = root ]; then
    echo "Specify an existing non-root user: sudo ADSB_TV_USER=youruser sh install.sh" >&2
    exit 1
fi
case "$USER_NAME" in
    *[!a-zA-Z0-9_.-]*)
        echo "Invalid service username" >&2
        exit 1
        ;;
esac
if ! id "$USER_NAME" >/dev/null 2>&1; then
    echo "User does not exist: $USER_NAME" >&2
    exit 1
fi
GROUP_NAME=$(id -gn "$USER_NAME")
case "$GROUP_NAME" in
    *[!a-zA-Z0-9_.-]*)
        echo "Invalid service group" >&2
        exit 1
        ;;
esac

for file in server.py airport_db.py photo_db.py aircraft_db.py; do
    /usr/bin/python3 -m py_compile "$SCRIPT_DIR/$file"
done
if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd is required" >&2
    exit 1
fi

if ! systemctl is-active --quiet adsb-tv.service; then
    if ss -ltn 2>/dev/null | grep -Eq ':8090[[:space:]]'; then
        echo "TCP port 8090 is already in use. No changes made." >&2
        exit 1
    fi
fi

install -d -m 755 /opt/adsb-tv
install -d -m 755 -o "$USER_NAME" -g "$GROUP_NAME" /var/cache/adsb-tv
install -m 644 "$SCRIPT_DIR/server.py" "$SCRIPT_DIR/index.html" "$SCRIPT_DIR/setup.html" \
    "$SCRIPT_DIR/airport_db.py" "$SCRIPT_DIR/photo_db.py" "$SCRIPT_DIR/aircraft_db.py" /opt/adsb-tv/

cat > /etc/systemd/system/adsb-tv.service <<UNIT
[Unit]
Description=ADS-B TV aircraft dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$GROUP_NAME
WorkingDirectory=/opt/adsb-tv
Environment=PYTHONDONTWRITEBYTECODE=1
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
systemctl enable adsb-tv.service
systemctl restart adsb-tv.service
systemctl --no-pager --full status adsb-tv.service || true
echo "ADS-B TV installed. Open http://DEVICE-IP:8090/setup on your trusted LAN."
