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
