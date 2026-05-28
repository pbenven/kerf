# Installing Kerf

## Requirements

| Method | Requirements |
|---|---|
| Docker (recommended) | Docker 24+, Docker Compose v2 |
| Python direct | Python 3.8+, pip |

---

## Option 1 — Docker (recommended)

Docker isolates Kerf completely from your system and handles all
dependencies automatically.

### Install

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/kerf.git
sudo mv kerf /opt/kerf
```

### Run

```bash
docker compose -f /opt/kerf/compose.yaml -p kerf up --build -d
```

Open your browser at **http://localhost:5000**

### Stop

```bash
docker compose -f /opt/kerf/compose.yaml -p kerf down
```

### Update

```bash
cd /opt/kerf
git pull
docker compose -f /opt/kerf/compose.yaml -p kerf down
docker compose -f /opt/kerf/compose.yaml -p kerf build --no-cache
docker compose -f /opt/kerf/compose.yaml -p kerf up -d
```

---

## Option 2 — Start on boot (systemd)

To have Kerf start automatically when your machine boots:

```bash
sudo tee /etc/systemd/system/kerf.service > /dev/null << 'EOF'
[Unit]
Description=Kerf Sheet Goods Optimizer
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/opt/kerf
ExecStart=/usr/bin/docker compose -f /opt/kerf/compose.yaml -p kerf up
ExecStop=/usr/bin/docker compose -f /opt/kerf/compose.yaml -p kerf down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now kerf
```

Check status:

```bash
sudo systemctl status kerf
```

View logs:

```bash
docker compose -f /opt/kerf/compose.yaml -p kerf logs -f
```

---

## Option 3 — Python direct (no Docker)

Useful for development or on systems where Docker is not available.

```bash
git clone https://github.com/YOUR_USERNAME/kerf.git
cd kerf
pip install flask gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
```

For development with auto-reload:

```bash
FLASK_ENV=development python app.py
```

---

## Changing the port

Edit `compose.yaml` and change the left side of the port mapping:

```yaml
ports:
  - "8080:5000"   # now accessible at http://localhost:8080
```

Then rebuild:

```bash
docker compose -f /opt/kerf/compose.yaml -p kerf up --build -d
```

---

## Uninstall

```bash
docker compose -f /opt/kerf/compose.yaml -p kerf down
docker image rm kerf-cutlist 2>/dev/null || true
sudo rm -rf /opt/kerf
sudo systemctl disable kerf 2>/dev/null || true
sudo rm -f /etc/systemd/system/kerf.service
```
