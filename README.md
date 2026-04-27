# 🚨 Solana Radar Bot

A Telegram bot that monitors Solana's trending tokens every 15 minutes and alerts subscribers — with automatic safety scoring to filter out dangerous tokens.

Built by [@kingofgreatness](https://twitter.com/kingofgreatnezz) 🇳🇬  
Powered by [Birdeye Data API](https://bds.birdeye.so) #BirdeyeAPI

---

## What it does

- Monitors `/defi/token_trending` every 15 minutes via Birdeye API
- For each new trending token, checks `/defi/token_security` for safety
- Automatically **filters out AVOID-rated tokens** to protect users
- Sends Telegram alerts with: price, 24h change, volume, liquidity, safety rating
- Users can subscribe/unsubscribe via Telegram commands

## Safety Rating System

| Rating | Label | Meaning |
|--------|-------|---------|
| 🟢 | SAFE | Clean contract, no red flags |
| 🟡 | CAUTION | Minor flags, proceed with care |
| 🟠 | RISKY | Multiple red flags |
| 🔴 | AVOID | Dangerous — filtered out automatically |

## Birdeye API Endpoints Used

- `GET /defi/token_trending` — fetch trending tokens
- `GET /defi/token_security` — fetch safety data per token

## Commands

| Command | Action |
|---------|--------|
| `/start` | Subscribe to alerts |
| `/stop` | Unsubscribe |
| `/trending` | View top 10 trending tokens now |
| `/stats` | Bot statistics |

## Tech Stack

- Python 3.11+
- `python-telegram-bot` — Telegram interface
- `httpx` — async API calls to Birdeye
- `apscheduler` — 15-minute interval scheduling
- Deployed on Railway (free tier)

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/solana-radar-bot
cd solana-radar-bot
pip install -r requirements.txt
python bot.py
```

## Environment Variables (for production)

Replace the keys in `bot.py` with environment variables:
```
BIRDEYE_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_token_here
```

---

*Built for the Birdeye Data BIP Competition — Sprint 2*  
*April 2026*
"# solana-radar-bot" 
