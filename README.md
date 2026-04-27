# 🚨 Solana Radar Bot

> Built in one night by a Nigerian developer learning Solana.  
> Powered by Birdeye Data API + Claude AI.

**The problem:** African crypto traders get rugged constantly. They see a token trending on Twitter — but by the time they check if it's safe, it's too late. They need real-time safety intelligence, not just price data.

**The solution:** A Telegram bot that monitors trending Solana tokens every 15 minutes, automatically filters dangerous ones, and uses AI to explain WHY a token is trending — not just that it is.

---

## What makes this different

Most alert bots just say "this token is trending." This bot says:

> *"$BONK is trending because volume spiked 340% in 2 hours while price only moved 12% — suggesting accumulation rather than a pump. The contract has no mint authority and top 10 holders control only 31% — relatively safe distribution."*

That's the `/why` command. Powered by Claude AI. No other Solana bot does this.

---

## Commands

| Command | What it does |
|---------|-------------|
| `/start` | Subscribe to live alerts |
| `/stop` | Unsubscribe |
| `/trending` | Top 10 trending tokens RIGHT NOW with safety scores |
| `/new` | Brand new token listings — safety filtered |
| `/why SYMBOL` | AI explains why a token is trending |
| `/stats` | Bot statistics |

---

## Safety Rating System

| Rating | Label | What it means |
|--------|-------|--------------|
| 🟢 | SAFE | Clean contract, healthy distribution |
| 🟡 | CAUTION | Minor flags, proceed carefully |
| 🟠 | RISKY | Multiple red flags |
| 🔴 | AVOID | Dangerous — filtered out automatically, never shown |

Red flags checked: mint authority, freeze authority, top 10 holder concentration, creator percentage.

---

## Birdeye API Endpoints Used

- `GET /defi/token_trending` — fetch top trending tokens every 15 minutes
- `GET /defi/v2/tokens/new_listing` — fetch brand new token listings
- `GET /defi/token_security` — safety analysis per token
- `GET /defi/token_overview` — detailed token data for AI analysis

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Core language |
| python-telegram-bot | Telegram interface |
| httpx | Async API calls to Birdeye |
| anthropic SDK | Claude AI for /why analysis |
| asyncio | Background alert loop (no extra dependencies) |

---

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/solana-radar-bot
cd solana-radar-bot
pip install -r requirements.txt
```

Add your keys in `bot.py`:
```python
BIRDEYE_API_KEY    = "your_birdeye_key"
TELEGRAM_BOT_TOKEN = "your_telegram_token"
ANTHROPIC_API_KEY  = "your_anthropic_key"
```

Then run:
```bash
python bot.py
```

---

## Built for the Birdeye BIP Competition — Sprint 2

April 2026 | by [@kingofgreatness](https://twitter.com/kingofgreatnezz) 🇳🇬

*This is my first Solana project. Built from zero in 48 hours.*  
*Because African crypto traders deserve the same tools as everyone else.*

---

`#BirdeyeAPI` `#Solana` `#BuildInPublic`