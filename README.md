# Xiaomi Bootloader Unlock Slot Script (burst, auditable)

Script to request a Xiaomi bootloader unlock slot at 00:00 Beijing time.
Improved from the gist by 2shrestha22 (sequential loop) with a pre-spawned
parallel burst, connection prewarm and NTP-synced timing.

> No official affiliation with Xiaomi. Use at your own risk.
> Never pay, never run random `.exe` from Telegram/YouTube for this.

## What changed vs the original gist

- 16 parallel workers released at the exact same instant (`threading.Event`),
  pool 32 so no worker waits for a connection.
- NTP-synced Beijing time (`Asia/Shanghai`), configurable offset
  (`FEED_TIME_SHIFT = 1400` ms) to compensate request latency.
- Connection prewarm at -90s / -40s so TLS handshakes happen outside the window.
- Single API host only: `sgp-api.buy.mi.com`. No adb/fastboot, no exfiltration.
- Token read from local `token.txt` (never commit it, never paste it in chats).

## Requirements

- Python 3.10+
- A Xiaomi account eligible for unlocking (aged, same SIM, Find Device ON)
- Fresh `new_bbs_serviceToken` cookie value at 11:45 BOT / 23:45 Beijing

## Audit before running

```bash
python3 -m py_compile bootloader-unlock-req.py
grep -Ei "http|token|cookie|adb|fastboot|password" bootloader-unlock-req.py
# expected: only https://sgp-api.buy.mi.com/... and local token.txt usage
sha256sum bootloader-unlock-req.py
```

## Usage

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp token.txt.example token.txt
# paste ONLY the new_bbs_serviceToken value into token.txt (one line)
python3 bootloader-unlock-req.py 2>&1 | tee unlock_$(date +%Y%m%d_%H%M).log
```

Run ~4 min before 00:00 Beijing (12:00 BOT), leave the window open,
do not close it until `[Done]`.

## Result codes

- `apply_result == 1` = approved. Do the `Add account and device`
  step in Developer options with mobile data immediately.
- `apply_result == 3` = quota, try next day. Do not spam.
- `apply_result == 4` = blocked until the shown date. Stop.
- `code == 100004` = cookie expired, get a fresh token tomorrow.
- `code == 100001` = bad request. `100003` = maybe approved, re-check status.

## After approval

1. Phone with same SIM, mobile data ON, WiFi OFF:
   `Settings > Developer options > Mi Unlock status > Add account and device`.
2. Mi Unlock tool shows the 72/168h wait. Do not re-run, re-bind,
   change SIM/account, factory reset or change password during the wait.
3. Unlocking wipes the phone. Backup first. Never `flash_all_lock`
   or relock a cross-region / custom ROM.

## Credits

- Original idea / base script: gist by 2shrestha22.
- Burst + prewarm + audit hardening: community fork (this repo).

## License

MIT. No warranty. You are responsible for your device and account.
