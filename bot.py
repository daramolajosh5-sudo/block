import asyncio
import html
import logging
import os
import aiohttp
import feedparser
from duckduckgo_search import DDGS

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fetch environment variables safely
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("CRITICAL ERROR: BOT_TOKEN variable is missing on Railway!")

CRYPTO_RSS_URL = "https://cointelegraph.com/rss"
WELCOME_IMAGE_PATH = "welcome.png"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ------------------ UTILITY & API FUNCTIONS ------------------ #

async def fetch_crypto_prices():
    """Fetches top crypto market data from CoinGecko's public endpoint."""
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=5&page=1&sparkline=false"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                logger.error(f"CoinGecko API returned status: {response.status}")
                return None
    except Exception as e:
        logger.error(f"CoinGecko API Error: {e}")
        return None

def _sync_ddg_chat(prompt: str) -> str:
    """Synchronous execution of DuckDuckGo AI chat."""
    system_instruction = (
        "You are BlockWire AI, an expert cryptocurrency analyst and digital market assistant. "
        "Keep your answers clear, accurate, concise, and easy to read. "
        "Focus on crypto market trends, blockchain technology, trading concepts, and digital assets."
    )
    full_prompt = f"{system_instruction}\n\nUser Question: {prompt}"
    
    with DDGS() as ddgs:
        response = ddgs.chat(full_prompt, model="gpt-4o-mini")
        return response

async def free_ai_chat(user_prompt: str) -> str:
    """Non-blocking async wrapper around DDGS.chat."""
    try:
        response = await asyncio.to_thread(_sync_ddg_chat, user_prompt)
        return response if response else "⚠️ I couldn't generate a response right now. Please try again."
    except Exception as e:
        logger.error(f"Free AI Execution Error: {e}")
        return "⚠️ AI service is busy. Please ask your question again in a moment!"


# ------------------ BOT COMMAND HANDLERS ------------------ #

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Responds to /start command with welcome banner image and interactive menu."""
    welcome_text = (
        "⚡ <b>Welcome to BlockWire Terminal!</b>\n\n"
        "Your interactive portal for live market data, breaking crypto news, and AI insights.\n\n"
        "<b>Commands & Features:</b>\n"
        "• 💰 <code>/prices</code> - Top 5 Coins live market status\n"
        "• 📰 <code>/news</code> - Latest crypto news headlines\n"
        "• 💬 Send any message directly to chat with <b>BlockWire AI</b>!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Live Prices", callback_data="get_prices"),
            InlineKeyboardButton(text="📰 Market News", callback_data="get_news")
        ]
    ])
    
    try:
        photo = FSInputFile(WELCOME_IMAGE_PATH)
        await message.answer_photo(
            photo=photo,
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Failed to send welcome image: {e}")
        # Fallback to text message if welcome.png is missing
        await message.answer(
            text=welcome_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )


@dp.message(Command("prices"))
@dp.callback_query(F.data == "get_prices")
async def prices_handler(event: types.Message | types.CallbackQuery):
    """Fetches and displays live top market cap prices."""
    if isinstance(event, types.CallbackQuery):
        await event.answer("Fetching latest prices...")
        msg = event.message
    else:
        msg = event

    data = await fetch_crypto_prices()
    
    if not data:
        text = "❌ Unable to load market prices right now. Please try again later."
    else:
        text = "📊 <b>BlockWire Market Overview</b>\n\n"
        for coin in data:
            change = coin.get('price_change_percentage_24h', 0)
            indicator = "🟢" if change >= 0 else "🔴"
            price = coin.get('current_price', 0)
            text += f"• <b>{coin['name']} ({coin['symbol'].upper()}):</b> ${price:,} | 24h: {indicator} <code>{change:.2f}%</code>\n"
    
    await msg.answer(text, parse_mode="HTML")


@dp.message(Command("news"))
@dp.callback_query(F.data == "get_news")
async def news_handler(event: types.Message | types.CallbackQuery):
    """Fetches breaking news headlines from CoinTelegraph RSS."""
    if isinstance(event, types.CallbackQuery):
        await event.answer("Fetching news headlines...")
        msg = event.message
    else:
        msg = event

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CRYPTO_RSS_URL, timeout=10) as resp:
                content = await resp.text()
                feed = feedparser.parse(content)
                
        if feed and feed.entries:
            text = "📰 <b>Latest BlockWire News Headlines:</b>\n\n"
            for entry in feed.entries[:3]:
                title = html.escape(entry.title)
                text += f"📌 <b>{title}</b>\n🔗 <a href='{entry.link}'>Read Full Article</a>\n\n"
        else:
            text = "❌ No news entries found at this moment."
    except Exception as e:
        logger.error(f"RSS Fetching Error: {e}")
        text = "❌ Failed to retrieve news updates."

    await msg.answer(text, parse_mode="HTML", disable_web_page_preview=True)


# ------------------ FREE AI CHAT HANDLER ------------------ #

@dp.message(F.text & ~F.text.startswith("/"))
async def chat_handler(message: types.Message):
    """Handles regular text queries for multi-user AI chat."""
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    ai_response = await free_ai_chat(message.text)
    
    try:
        await message.reply(html.escape(ai_response), parse_mode="HTML")
    except Exception:
        await message.reply(ai_response)


# ------------------ MAIN ENGINE RUNNER ------------------ #

async def main():
    logger.info("Starting @BlockWire_bot application...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped successfully.")
