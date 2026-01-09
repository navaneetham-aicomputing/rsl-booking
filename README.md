## RSL Booking

### local development setup
clone this repo

```bash
git clone https://github.com/ai/rsl-booking.git
cd rsl-booking
```

install dependencies

```bash
uv sync
```

### configuring scheduler 

```bash
sudo nano /etc/systemd/system/rsl-booking.service
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable rsl-booking.service
sudo systemctl start rsl-booking.service
```

```bash
# Check status
sudo systemctl status rsl-booking

# View live logs
journalctl -u rsl-booking -f
```
