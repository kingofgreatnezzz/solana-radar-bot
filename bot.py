import httpx
import asyncio
import logging
import os
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")

CHECK_INTERVAL = 900   # 15 minutes

# ============================================================
# STORAGE
# =================================
subscribers  = set()
seen_tokens  = set()
alert_count  = 0

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================================
# BIRDEYE — TRENDING
# ============================================================
async def get_trending_tokens():
    url     = "https://public-api.birdeye.so/defi/token_trending"
    headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
    params  = {"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": 20}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=headers, params=params)
            d = r.json()
            if d.get("success") and d.get("data"):
                return d["data"].get("tokens", [])
    except Exception as e:
        logger.error(f"Trending error: {e}")
    return []

# ============================================================
# BIRDEYE — NEW LISTINGS

#==============================
async def get_new_listings():
    url     = "https://public-api.birdeye.so/defi/v2/tokens/new_listing"
    headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
    params  = {"limit": 10}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=headers, params=params)
            d = r.json()
            if d.get("success") and d.get("data"):
                return d["data"].get("items", [])
    except Exception as e:
        logger.error(f"New listings error: {e}")
    return []

# ============================================================
# BIRDEYE — SECURITY
# ===========================================
async def get_token_security(address: str):
    url     = "https://public-api.birdeye.so/defi/token_security"
    headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
    params  = {"address": address}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=headers, params=params)
            d = r.json()
            if d.get("success"):
                return d.get("data", {})
    except Exception as e:
        logger.error(f"Security error: {e}")
    return {}

# ============================================================
# BIRDEYE — TOKEN OVERVIEW (for /why command)
# ===========================================
async def get_token_overview(address: str):
    url     = "https://public-api.birdeye.so/defi/token_overview"
    headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
    params  = {"address": address}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers=headers, params=params)
            d = r.json()
            if d.get("success"):
                return d.get("data", {})
    except Exception as e:
        logger.error(f"Overview error: {e}")
    return {}

# ============================================================
# SAFETY RATINGs 
# ============================================================
def calculate_safety_rating(sec):
    if not sec: return "⚪", "UNKNOWN"
    flags = 0
    if sec.get("mintAuthority")   is not None:      flags += 2
    if sec.get("freezeAuthority") is not None:      flags += 1
    if (sec.get("top10HolderPercent") or 0) > 80:   flags += 2
    if (sec.get("creatorPercentage")  or 0) > 50:   flags += 2
    if flags == 0:    return "🟢", "SAFE"
    elif flags <= 1:  return "🟡", "CAUTION"
    elif flags <= 3:  return "🟠", "RISKY"
    else:             return "🔴", "AVOID"

# ============================================================
# HELPERS
# ============================================================
def fmt_num(n):
    if n is None: return "N/A"
    n = float(n)
    if n >= 1e9:  return f"${n/1e9:.2f}B"
    if n >= 1e6:  return f"${n/1e6:.2f}M"
    if n >= 1e3:  return f"${n/1e3:.2f}K"
    return f"${n:.4f}"

def fmt_price(p):
    if p is None: return "N/A"
    p = float(p)
    if p < 0.000001: return f"${p:.10f}"
    if p < 0.01:     return f"${p:.6f}"
    return f"${p:.4f}"

# ============================================================
# CLAUDE AI — WHY IS THIS TOKEN TRENDING?
# ============================================================
async def ask_claude_why(name, symbol, price, price_change, volume, liquidity,
                          holders, security_label):
    """Use Claude to explain in plain English why a token is trending"""
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""You are a crypto analyst. Analyze this Solana token data and explain in 3-4 sentences 
WHY this token might be trending right now. Be specific, honest, and useful. 
If signals look like a pump-and-dump, say so clearly. Keep it plain English — no jargon.

Token: {name} (${symbol})
Price: {price}
24h Price Change: {price_change}
24h Volume: {volume}
Liquidity: {liquidity}
Holder Count: {holders}
Safety Rating: {security_label}

Give your analysis in this format:
🧠 Why it's trending: [your 3-4 sentence analysis]
⚠️ Watch out for: [one key risk to be aware of]
"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    except anthropic.RateLimitError:
        logger.error("Claude rate limit hit")
        return None, "rate_limit"

    except anthropic.APIStatusError as e:
        # Covers 529 overloaded, 402 out of credits, etc.
        status = e.status_code
        logger.error(f"Claude API status error: {status}")
        if status in (402, 429, 529):
            return None, "quota"
        return None, "error"

    except Exception as e:
        logger.error(f"Claude error: {e}")
        return None, "error"


def get_fallback_message(symbol: str, error_type: str, price, chg_str,
                          vol, liq, emoji, label) -> str:
    """Returns a funny, honest fallback when Claude AI is unavailable"""

    if error_type == "quota":
        ai_section = (
            f"😭 *AI Analysis: Temporarily Unavailable*\n\n"
            f"Sooo... turns out a LOT of you tested this bot 👀\n"
            f"Like, a suspicious amount. An impressive amount.\n"
            f"We ran out of AI tokens faster than ${symbol} ran out of sellers 📈\n\n"
            f"The AI brain is currently on timeout — touched by so many users "
            f"it needed a nap 😴\n\n"
            f"Normal service resumes soon. You lot broke it. I'm proud of you. 🇳🇬"
        )
    elif error_type == "rate_limit":
        ai_section = (
            f"😅 *AI Analysis: Too Popular Right Now*\n\n"
            f"The AI is getting too many questions at once — "
            f"apparently everyone wants to know about ${symbol} simultaneously 😂\n\n"
            f"Take a breath, wait 30 seconds, try `/why {symbol}` again.\n"
            f"The AI isn't gone — just overwhelmed. Like me on a Monday. 😭"
        )
    else:
        ai_section = (
            f"🤖 *AI Analysis: Taking a Quick Break*\n\n"
            f"The AI went for a walk and hasn't come back yet 🚶\n"
            f"Either that or it saw ${symbol}'s chart and got scared.\n\n"
            f"Try `/why {symbol}` again in a minute. It'll be back. Probably. 🤞"
        )

    return ai_section

# ============================================================
# ALERT LOOP — runs every 15 minutes only :000
# ============================================================
async def alert_loop(bot: Bot):
    global alert_count
    logger.info("Alert loop started — checking every 15 minutes")

    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            if not subscribers:
                logger.info("No subscribers yet")
                continue

            logger.info(f"Checking trending ({len(subscribers)} subscribers)...")
            tokens = await get_trending_tokens()
            if not tokens:
                continue

            new_tokens = [t for t in tokens
                          if t.get("address") and t["address"] not in seen_tokens]
            for t in new_tokens:
                seen_tokens.add(t["address"])

            if not new_tokens:
                logger.info("No new tokens this cycle")
                continue

            logger.info(f"{len(new_tokens)} new tokens")

            for token in new_tokens[:5]:
                address = token.get("address", "")
                name    = token.get("name", "Unknown")
                symbol  = token.get("symbol", "???")
                price   = token.get("price")
                vol     = token.get("volume24hUSD")
                chg     = token.get("priceChange24hPercent")
                liq     = token.get("liquidity")

                sec = await get_token_security(address)
                emoji, label = calculate_safety_rating(sec)

                if label == "AVOID":
                    logger.info(f"Skipping {symbol} — AVOID")
                    continue

                chg_str = (f"+{chg:.1f}%" if chg > 0 else f"{chg:.1f}%") if chg else "N/A"
                chg_ico = "📈" if (chg or 0) > 0 else "📉"
                link    = f"https://birdeye.so/token/{address}?chain=solana"

                msg = (
                    f"🚨 *NEW TRENDING TOKEN*\n\n"
                    f"*{name}* (${symbol})\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Price: `{fmt_price(price)}`\n"
                    f"{chg_ico} 24h: `{chg_str}`\n"
                    f"📊 Volume: `{fmt_num(vol)}`\n"
                    f"💧 Liquidity: `{fmt_num(liq)}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Safety: {emoji} *{label}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔗 [View on Birdeye]({link})\n\n"
                    f"💡 Use `/why {symbol}` to get AI analysis\n\n"
                    f"_#BirdeyeAPI | @kingofgreatness 🇳🇬_"
                )

                for cid in subscribers.copy():
                    try:
                        await bot.send_message(cid, msg,
                            parse_mode="Markdown",
                            disable_web_page_preview=True)
                        alert_count += 1
                    except Exception as e:
                        logger.error(f"Send failed {cid}: {e}")
                        subscribers.discard(cid)

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Alert loop error: {e}")

# ============================================================
# COMMANDS
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.add(update.effective_chat.id)
    await update.message.reply_text(
        "👋 *Welcome to Solana Radar Bot!*\n\n"
        "Built by @kingofgreatness 🇳🇬\n"
        "Powered by Birdeye Data API + Claude AI\n\n"
        "I monitor trending Solana tokens every 15 mins, "
        "filter dangerous ones automatically, and use AI to explain "
        "WHY a token is trending — not just that it is.\n\n"
        "🟢 SAFE  🟡 CAUTION  🟠 RISKY  🔴 AVOID (filtered)\n\n"
        "✅ *You are now subscribed!*\n\n"
        "Commands:\n"
        "/trending — Top tokens right now\n"
        "/new — Brand new token listings\n"
        "/why SYMBOL — AI explains why a token is trending\n"
        "/stats — Bot statistics\n"
        "/stop — Unsubscribe",
        parse_mode="Markdown"
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("✅ Unsubscribed. Send /start to resubscribe anytime.")


async def cmd_trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Fetching live trending tokens...")
    tokens = await get_trending_tokens()
    if not tokens:
        await update.message.reply_text("❌ Could not fetch right now. Try again.")
        return

    msg = "🔥 *TOP 10 TRENDING SOLANA TOKENS*\n\n"
    for i, t in enumerate(tokens[:10], 1):
        sym   = t.get("symbol", "???")
        price = t.get("price")
        chg   = t.get("priceChange24hPercent")
        sec   = await get_token_security(t.get("address", ""))
        em, _ = calculate_safety_rating(sec)
        chg_str = (f"+{chg:.1f}%" if chg > 0 else f"{chg:.1f}%") if chg else "N/A"
        msg += f"{i}. *${sym}* {em}\n   `{fmt_price(price)}` | `{chg_str}`\n\n"

    msg += "💡 Use `/why SYMBOL` to get AI analysis on any token\n"
    msg += "_#BirdeyeAPI | @kingofgreatness_"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show brand new token listings that pass safety check"""
    await update.message.reply_text("🆕 Scanning new Solana token listings...")
    listings = await get_new_listings()

    if not listings:
        await update.message.reply_text("❌ Could not fetch new listings right now.")
        return

    msg   = "🆕 *NEW TOKEN RADAR — Safety Filtered*\n\n"
    shown = 0

    for token in listings[:15]:
        address = token.get("address", "")
        symbol  = token.get("symbol", "???")
        name    = token.get("name", "Unknown")
        price   = token.get("price")

        sec = await get_token_security(address)
        emoji, label = calculate_safety_rating(sec)

        if label == "AVOID":
            continue   # filter dangerous ones incase of rug pulls :) lol

        link = f"https://birdeye.so/token/{address}?chain=solana"
        msg += (
            f"• *${symbol}* ({name}) {emoji}\n"
            f"  Price: `{fmt_price(price)}` | Safety: *{label}*\n"
            f"  [View]({link})\n\n"
        )
        shown += 1
        if shown >= 5:
            break

    if shown == 0:
        msg += "No safe new listings found right now. All flagged as risky."

    msg += "_#BirdeyeAPI | @kingofgreatness 🇳🇬_"
    await update.message.reply_text(msg,
        parse_mode="Markdown",
        disable_web_page_preview=True)


async def cmd_why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI-powered explanation of why a token is trending"""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/why SYMBOL`\nExample: `/why BONK`",
            parse_mode="Markdown"
        )
        return

    symbol_query = context.args[0].upper().strip("$")
    await update.message.reply_text(f"🧠 Asking AI to analyse ${symbol_query}...")

    # Find the token in trending list
    tokens = await get_trending_tokens()
    token  = next((t for t in tokens
                   if t.get("symbol","").upper() == symbol_query), None)

    if not token:
        await update.message.reply_text(
            f"❌ `${symbol_query}` not found in current trending list.\n"
            f"Try /trending to see what's trending now.",
            parse_mode="Markdown"
        )
        return

    address  = token.get("address", "")
    name     = token.get("name", "Unknown")
    price    = token.get("price")
    chg      = token.get("priceChange24hPercent")
    vol      = token.get("volume24hUSD")
    liq      = token.get("liquidity")

    sec = await get_token_security(address)
    emoji, label = calculate_safety_rating(sec)
    holders  = sec.get("holderCount", "Unknown")

    chg_str = (f"+{chg:.1f}%" if chg > 0 else f"{chg:.1f}%") if chg else "N/A"

    # Get AI analysis
    result = await ask_claude_why(
        name, symbol_query,
        fmt_price(price), chg_str,
        fmt_num(vol), fmt_num(liq),
        holders, label
    )

    link = f"https://birdeye.so/token/{address}?chain=solana"

    # Handle success vs fallback
    if isinstance(result, tuple):
        # Error occurred — result is (None, error_type)
        _, error_type = result
        ai_section = get_fallback_message(
            symbol_query, error_type,
            fmt_price(price), chg_str,
            fmt_num(vol), fmt_num(liq),
            emoji, label
        )
        msg = (
            f"🔬 *${symbol_query} — Token Data*\n\n"
            f"Safety: {emoji} *{label}*\n"
            f"Price: `{fmt_price(price)}` | 24h: `{chg_str}`\n"
            f"Volume: `{fmt_num(vol)}` | Liquidity: `{fmt_num(liq)}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{ai_section}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 [View on Birdeye]({link})\n\n"
            f"_Data by #BirdeyeAPI | @kingofgreatness 🇳🇬_"
        )
    else:
        # Success — result is the AI text
        msg = (
            f"🔬 *AI Analysis: ${symbol_query}*\n\n"
            f"Safety: {emoji} *{label}*\n"
            f"Price: `{fmt_price(price)}` | 24h: `{chg_str}`\n"
            f"Volume: `{fmt_num(vol)}` | Liquidity: `{fmt_num(liq)}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{result}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 [View on Birdeye]({link})\n\n"
            f"_AI by Claude | Data by #BirdeyeAPI | @kingofgreatness 🇳🇬_"
        )

    await update.message.reply_text(msg,
        parse_mode="Markdown",
        disable_web_page_preview=True)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 *Solana Radar Stats*\n\n"
        f"👥 Subscribers: `{len(subscribers)}`\n"
        f"🚨 Alerts sent: `{alert_count}`\n"
        f"🪙 Tokens tracked: `{len(seen_tokens)}`\n"
        f"⏱️ Check interval: every 15 minutes\n\n"
        f"_@kingofgreatness 🇳🇬 | Birdeye Data API + Claude AI_",
        parse_mode="Markdown"
    )


# ============================================
# MAIN 
# ============================================
async def main():
    logger.info("🚀 Solana Radar Bot starting...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("stop",     cmd_stop))
    app.add_handler(CommandHandler("trending", cmd_trending))
    app.add_handler(CommandHandler("new",      cmd_new))
    app.add_handler(CommandHandler("why",      cmd_why))
    app.add_handler(CommandHandler("stats",    cmd_stats))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    asyncio.create_task(alert_loop(bot))

    logger.info("✅ Bot is LIVE!")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())