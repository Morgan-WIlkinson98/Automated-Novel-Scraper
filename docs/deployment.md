# Deployment Guide

This guide covers deploying the AI Novel Web Scraper in various environments, from local development to production servers.

## Table of Contents

- [Local Deployment](#local-deployment)
- [Server Deployment](#server-deployment)
- [Docker Deployment](#docker-deployment)
- [Systemd Service](#systemd-service)
- [Monitoring and Logging](#monitoring-and-logging)
- [Backup and Recovery](#backup-and-recovery)
- [Security Considerations](#security-considerations)

## Local Deployment

### Quick Start

1. **Clone and setup:**
```bash
git clone https://github.com/Morgan-Wilkinson/AI-Web-Scrapper.git
cd AI-Web-Scrapper
git checkout v2
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Run the scraper:**
```bash
python main.py
```

3. **Verify operation:**
- Check for `chapters.db` and `seen_entries.db` files
- Monitor console output for "saved:" messages
- Verify chapters are being stored

### Running in Background

**Using nohup:**
```bash
nohup python main.py > scraper.log 2>&1 &
```

**Using screen:**
```bash
screen -S scraper
python main.py
# Press Ctrl+A, then D to detach
```

**Using tmux:**
```bash
tmux new -s scraper
python main.py
# Press Ctrl+B, then D to detach
```

## Server Deployment

### Prerequisites

- Ubuntu/Debian or CentOS/RHEL server
- Python 3.8+
- Git
- (Optional) Docker

### Step-by-Step Deployment

#### 1. Server Setup

**Update system:**
```bash
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
# or
sudo yum update -y  # CentOS/RHEL
```

**Install Python:**
```bash
sudo apt install python3 python3-pip python3-venv -y  # Ubuntu/Debian
# or
sudo yum install python3 python3-pip -y  # CentOS/RHEL
```

**Install Git:**
```bash
sudo apt install git -y  # Ubuntu/Debian
# or
sudo yum install git -y  # CentOS/RHEL
```

#### 2. Deploy Application

**Clone repository:**
```bash
cd /opt
sudo git clone https://github.com/Morgan-Wilkinson/AI-Web-Scrapper.git
cd AI-Web-Scrapper
sudo git checkout v2
```

**Create deployment user (recommended):**
```bash
sudo useradd -r -s /bin/false scraper
sudo chown -R scraper:scraper /opt/AI-Web-Scrapper
```

**Setup virtual environment:**
```bash
sudo -u scraper python3 -_m venv venv
sudo -u scraper venv/bin/pip install -r requirements.txt
```

#### 3. Configure Application

**Create configuration file:**
```bash
sudo -u scraper nano config.py
```

```python
# config.py
RSS_FEED_URL = "https://www.novelupdates.com/rss/"
POLL_INTERVAL_SECONDS = 15 * 60
MIN_DELAY_SECONDS = 5
USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://yourdomain.com/bot-info)"
```

**Update imports in modules to use config:**
```python
# In rss_watcher.py, politeness.py, etc.
try:
    from config import RSS_FEED_URL, POLL_INTERVAL_SECONDS, MIN_DELAY_SECONDS, USER_AGENT
except ImportError:
    # Fallback defaults
    RSS_FEED_URL = "https://www.novelupdates.com/rss/"
    POLL_INTERVAL_SECONDS = 15 * 60
    MIN_DELAY_SECONDS = 5
    USER_AGENT = "Mozilla/5.0 (compatible; ChapterFetcher/1.0; +https://example.invalid/bot-info)"
```

#### 4. Setup Directories

**Create data directory:**
```bash
sudo mkdir -p /var/lib/scraper
sudo chown scraper:scraper /var/lib/scraper
```

**Update storage paths in code:**
```python
# In rss_watcher.py
def init_db(path="/var/lib/scraper/seen_entries.db"):
    # ...

# In storage.py
def init_storage(path="/var/lib/scraper/chapters.db"):
    # ...
```

## Docker Deployment

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./

# Create data directory
RUN mkdir -p /data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV RSS_FEED_URL="https://www.novelupdates.com/rss/"
ENV POLL_INTERVAL_SECONDS=900
ENV MIN_DELAY_SECONDS=5

# Run the application
CMD ["python", "main.py"]
```

### docker-compose.yml

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  scraper:
    build: .
    container_name: novel-scraper
    restart: unless-stopped
    volumes:
      - ./data:/data
      - ./config.py:/app/config.py:ro
    environment:
      - RSS_FEED_URL=${RSS_FEED_URL:-https://www.novelupdates.com/rss/}
      - POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-900}
      - MIN_DELAY_SECONDS=${MIN_DELAY_SECONDS:-5}
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### .env file

Create `.env`:

```env
RSS_FEED_URL=https://www.novelupdates.com/rss/
POLL_INTERVAL_SECONDS=900
MIN_DELAY_SECONDS=5
```

### Build and Run

**Build:**
```bash
docker-compose build
```

**Run:**
```bash
docker-compose up -d
```

**View logs:**
```bash
docker-compose logs -f
```

**Stop:**
```bash
docker-compose down
```

## Systemd Service

### Create Service File

**Create systemd service:**
```bash
sudo nano /etc/systemd/system/novel-scraper.service
```

```ini
[Unit]
Description=AI Novel Web Scraper
After=network.target

[Service]
Type=simple
User=scraper
Group=scraper
WorkingDirectory=/opt/AI-Web-Scrapper
Environment="PATH=/opt/AI-Web-Scrapper/venv/bin"
ExecStart=/opt/AI-Web-Scrapper/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/scraper/output.log
StandardError=append:/var/log/scraper/error.log

[Install]
WantedBy=multi-user.target
```

### Setup Logging

**Create log directory:**
```bash
sudo mkdir -p /var/log/scraper
sudo chown scraper:scraper /var/log/scraper
```

**Configure log rotation:**
```bash
sudo nano /etc/logrotate.d/novel-scraper
```

```
/var/log/scraper/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 scraper scraper
}
```

### Enable and Start Service

**Enable service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable novel-scraper
```

**Start service:**
```bash
sudo systemctl start novel-scraper
```

**Check status:**
```bash
sudo systemctl status novel-scraper
```

**View logs:**
```bash
sudo journalctl -u novel-scraper -f
# or
sudo tail -f /var/log/scraper/output.log
```

**Restart service:**
```bash
sudo systemctl restart novel-scraper
```

**Stop service:**
```bash
sudo systemctl stop novel-scraper
```

## Monitoring and Logging

### Application Logging

**Add structured logging:**

Create `logger_config.py`:

```python
import logging
import logging.handlers
import os

def setup_logger(name, log_file, level=logging.INFO):
    """Setup logger with file and console handlers."""
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

# Usage in modules
# logger = setup_logger(__name__, '/var/log/scraper/app.log')
# logger.info("Application started")
```

### Health Checks

**Create health check endpoint (optional):**

Add to `main.py`:

```python
import http.server
import socketserver
import threading

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server(port=8080):
    with socketserver.TCPServer(("", port), HealthHandler) as httpd:
        httpd.serve_forever()

# In main, start in background thread
health_thread = threading.Thread(target=start_health_server, daemon=True)
health_thread.start()
```

### Monitoring Tools

**Using Prometheus (advanced):**

Install prometheus client:
```bash
pip install prometheus-client
```

Add metrics to `main.py`:

```python
from prometheus_client import start_http_server, Counter, Histogram

# Define metrics
chapters_scraped = Counter('chapters_scraped_total', 'Total chapters scraped')
extraction_duration = Histogram('extraction_duration_seconds', 'Extraction duration')

# Use in code
@extraction_duration.time()
def handle_new_entry(entry):
    # ... existing code ...
    chapters_scraped.inc()

# Start metrics server
start_http_server(8000)
```

## Backup and Recovery

### Database Backups

**Automated backup script:**

Create `/opt/backup-scraper.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/scraper"
DATA_DIR="/var/lib/scraper"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup databases
cp "$DATA_DIR/chapters.db" "$BACKUP_DIR/chapters_$DATE.db"
cp "$DATA_DIR/seen_entries.db" "$BACKUP_DIR/seen_entries_$DATE.db"

# Compress old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete

echo "Backup completed: $DATE"
```

**Make executable:**
```bash
sudo chmod +x /opt/backup-scraper.sh
```

**Add to crontab:**
```bash
sudo crontab -e
```

Add line for daily backup at 2 AM:
```
0 2 * * * /opt/backup-scraper.sh >> /var/log/scraper/backup.log 2>&1
```

### Restore from Backup

```bash
# Stop service
sudo systemctl stop novel-scraper

# Restore databases
sudo cp /var/backups/scraper/chapters_YYYYMMDD_HHMMSS.db /var/lib/scraper/chapters.db
sudo cp /var/backups/scraper/seen_entries_YYYYMMDD_HHMMSS.db /var/lib/scraper/seen_entries.db

# Fix permissions
sudo chown scraper:scraper /var/lib/scraper/*.db

# Start service
sudo systemctl start novel-scraper
```

### Application Code Backup

**Git-based backup:**

```bash
# In /opt/AI-Web-Scrapper
sudo -u scraper git add -A
sudo -u scraper git commit -m "Backup before deployment"
sudo -u scraper git push origin backup-branch
```

## Security Considerations

### User Permissions

**Run as non-root user:**
```bash
sudo useradd -r -s /bin/false scraper
```

**File permissions:**
```bash
sudo chown -R scraper:scraper /opt/AI-Web-Scrapper
sudo chmod 750 /opt/AI-Web-Scrapper
sudo chmod 640 /opt/AI-Web-Scrapper/*.py
```

### Firewall Configuration

**UFW (Ubuntu):**
```bash
sudo ufw allow ssh
sudo ufw enable
```

**firewalld (CentOS):**
```bash
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --reload
```

### SSL/TLS (if adding web interface)

**Use certbot for Let's Encrypt:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

### Secrets Management

**Never commit secrets to git:**

Use environment variables:
```python
import os

API_KEY = os.getenv('API_KEY')
if not API_KEY:
    raise ValueError("API_KEY environment variable not set")
```

**Use .env file (add to .gitignore):**
```
.env
*.db
*.log
__pycache__/
venv/
```

### Rate Limiting

**Configure politeness settings:**

In `politeness.py`:
```python
MIN_DELAY_SECONDS = 10  # More conservative for production
```

### robots.txt Compliance

The politeness layer automatically respects robots.txt. Monitor logs for:
```
[politeness] robots.txt disallows {url}, skipping
```

## Troubleshooting Deployment

### Service Won't Start

**Check logs:**
```bash
sudo journalctl -u novel-scraper -n 50
```

**Common issues:**
- Missing dependencies: Reinstall with `pip install -r requirements.txt`
- Permission errors: Check file ownership with `ls -la /opt/AI-Web-Scrapper`
- Python path issues: Verify venv is properly configured

### High Memory Usage

**Monitor memory:**
```bash
ps aux | grep python
```

**Solutions:**
- Reduce RSS polling frequency
- Limit database size with periodic cleanup
- Add memory limits to systemd service

### Network Issues

**Test connectivity:**
```bash
curl -I https://www.novelupdates.com/rss/
```

**Check DNS:**
```bash
nslookup novelupdates.com
```

**Verify firewall:**
```bash
sudo ufw status
```

## Scaling Considerations

### Multiple Instances

**For high-volume scraping:**

1. Deploy multiple instances
2. Use shared database (PostgreSQL instead of SQLite)
3. Implement distributed locking for RSS polling
4. Use message queue (Redis/RabbitMQ) for work distribution

### Database Migration

**From SQLite to PostgreSQL:**

1. Install PostgreSQL
2. Create database and user
3. Migrate schema
4. Update storage.py to use psycopg2
5. Migrate existing data

```python
# Example PostgreSQL connection
import psycopg2

def init_storage(path="postgresql://user:pass@localhost/scraper"):
    conn = psycopg2.connect(path)
    # ... rest of function
```

## Maintenance

### Regular Updates

**Update dependencies:**
```bash
sudo -u scraper venv/bin/pip install --upgrade -r requirements.txt
```

**Update application code:**
```bash
cd /opt/AI-Web-Scrapper
sudo -u scraper git pull origin v2
sudo systemctl restart novel-scraper
```

### Log Rotation

Already configured via logrotate. Verify:
```bash
sudo logrotate -d /etc/logrotate.d/novel-scraper
```

### Database Maintenance

**Vacuum SQLite databases:**
```bash
sqlite3 /var/lib/scraper/chapters.db "VACUUM;"
sqlite3 /var/lib/scraper/seen_entries.db "VACUUM;"
```

**Analyze database size:**
```bash
ls -lh /var/lib/scraper/
```

## Production Checklist

Before deploying to production:

- [ ] Run as non-root user
- [ ] Configure systemd service
- [ ] Setup log rotation
- [ ] Configure automated backups
- [ ] Set up monitoring
- [ ] Configure firewall
- [ ] Test robots.txt compliance
- [ ] Verify rate limiting
- [ ] Set up alerts for failures
- [ ] Document deployment process
- [ ] Test restore procedure
- [ ] Review and update User-Agent
- [ ] Configure appropriate polling intervals
