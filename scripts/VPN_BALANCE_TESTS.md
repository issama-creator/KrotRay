# VPN Balance Tests

Run from project root (preferably inside venv):

```bash
python scripts/run_vpn_balance_tests.py --help
```

## 1) Smooth ramp (50 -> 100 -> 300 -> 500)

```bash
python scripts/run_vpn_balance_tests.py ramp \
  --base-url https://krotray.ru \
  --workers 120 \
  --stage-seconds 300 \
  --pause-seconds 5 \
  --do-ping
```

What to check:
- `latency_ms p95` ideally < 200ms
- `distribution_skew=max/avg` close to 1 (lower is better)
- no single server dominates heavily

## 2) Spike test (0 -> 1000 quickly)

```bash
python scripts/run_vpn_balance_tests.py spike \
  --base-url https://krotray.ru \
  --users 1000 \
  --workers 250 \
  --do-ping
```

What to check:
- initial skew may jump, then should recover after worker ticks
- no permanent concentration on one server

## 3) Failover test

Auto mark top server as dead (requires DB URL):

```bash
python scripts/run_vpn_balance_tests.py failover \
  --base-url https://krotray.ru \
  --users 400 \
  --workers 120 \
  --do-ping \
  --database-url "$DATABASE_URL" \
  --wait-after-fail-s 10
```

Manual mode (no DB URL):

```bash
python scripts/run_vpn_balance_tests.py failover \
  --base-url https://krotray.ru \
  --users 400 \
  --workers 120 \
  --do-ping
```

In manual mode script pauses, then you mark one server dead in DB and press Enter.

