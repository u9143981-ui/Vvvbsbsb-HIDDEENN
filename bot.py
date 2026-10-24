import telebot
from telebot import types
import logging
import re
import urllib.parse
import random
import time
import threading
import os

# Token from environment variable (Render)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8695604407:AAFj49OFbTulux5HTG96j16780xIj5HlCus")
bot = telebot.TeleBot(BOT_TOKEN)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

MAX_CARDS = 25


def escape_markdown(text):
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])


def build_welcome(user):
    return f"""
*{escape_markdown("⌬ @AutoShopifyHitterBot | By @xrucg")}*
```Upgrading...```
━━━━━━━━━━━━━━━━
✅️ *{escape_markdown(f"Hello {user.first_name}!")}*
{escape_markdown("How Are You?")}
👤 *{escape_markdown(f"Your UserID - {user.id}")}*
```BOT Status - Live!!!```
    """


def welcome_keyboard():
    return types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("Auto Checkout", callback_data="auto_checkout")]
    ])


def checkout_keyboard():
    return types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("Back", callback_data="back")]
    ])


def parse_checkout_url(url):
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        shop = parsed.netloc
        if not shop or "." not in shop:
            return None
        path_match = re.match(r'^/cart/(\d+):(\d+)$', parsed.path)
        if not path_match:
            return None
        variant_id = path_match.group(1)
        quantity = path_match.group(2)
        query = urllib.parse.parse_qs(parsed.query)

        def field(name):
            key = f"checkout[shipping_address][{name}]"
            vals = query.get(key)
            return vals[0] if vals else None

        data = {
            "shop": shop, "variant": variant_id, "quantity": quantity,
            "first_name": field("first_name"), "last_name": field("last_name"),
            "address1": field("address1"), "address2": field("address2"),
            "city": field("city"), "province": field("province"),
            "zip": field("zip"), "country": field("country"),
            "phone": field("phone"),
        }
        email_vals = query.get("checkout[email]")
        data["email"] = email_vals[0] if email_vals else None

        required = ["address1", "city", "zip", "country"]
        if not all(data.get(k) for k in required):
            return None
        return data
    except Exception as e:
        logger.error(f"Error parsing checkout URL: {e}")
        return None


def validate_card(card):
    try:
        cc, mm, yy, cvv = card.split('|')
        return (
            len(cc) in (15, 16) and cc.isdigit() and
            len(mm) == 2 and mm.isdigit() and 1 <= int(mm) <= 12 and
            len(yy) in (2, 4) and yy.isdigit() and
            len(cvv) in (3, 4) and cvv.isdigit()
        )
    except ValueError:
        return False


PENDING_CHECKOUTS = {}


def extract_url_and_cards(text):
    lines = text.strip().splitlines()
    url = None
    card_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if url is None and re.match(r'^https?://', line):
            url = line
        else:
            card_lines.append(line)
    return url, card_lines


@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    welcome_message = build_welcome(user)
    reply_markup = welcome_keyboard()
    try:
        bot.reply_to(message, welcome_message, reply_markup=reply_markup, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        bot.reply_to(
            message,
            f"Hello {user.first_name}! Welcome to @AutoShopifyHitterBot.\nYour UserID - {user.id}",
            reply_markup=reply_markup
        )


@bot.message_handler(commands=['sco'])
def sco_command(message):
    parts = message.text.split(maxsplit=1)
    content = parts[1].strip() if len(parts) > 1 else ""
    url, card_lines = (None, [])
    if content:
        url, card_lines = extract_url_and_cards(content)

    if not url:
        usage = (
            "*Usage* \\: `/sco <checkout_url>`\n"
            "or\n"
            "`/sco <checkout_url>` then cards on next lines\\:\n"
            "`CC|MM|YY|CVV` (one per line, max 25)\n\n"
            "Or send URL alone and reply to the bot's message with cards."
        )
        try:
            bot.reply_to(message, usage, parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Error sending sco usage: {e}")
            bot.reply_to(message, "Usage : /sco <checkout_url>\nThen cards CC|MM|YY|CVV (one per line, max 25)")
        return

    data = parse_checkout_url(url)
    if not data:
        bot.reply_to(
            message,
            "⚠️ Invalid checkout URL.\n\nAccepted format:\n"
            "<code>https://shop.com/cart/&lt;variant&gt;:&lt;qty&gt;?checkout[shipping_address][address1]=...&checkout[shipping_address][city]=...&checkout[shipping_address][zip]=...&checkout[shipping_address][country]=...</code>",
            parse_mode='HTML'
        )
        return

    if card_lines:
        start_check_session(message, data, card_lines)
        return

    full_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")])) or "N/A"
    address_lines = [data.get("address1")]
    if data.get("address2"):
        address_lines.append(data["address2"])
    address_lines.append(f"{data.get('city') or ''}, {data.get('province') or ''} - {data.get('zip') or ''}")
    address_lines.append(data.get("country") or "")
    full_address = "\n".join([l for l in address_lines if l.strip()])

    response = (
        f"✅ <b>Checkout Detected</b>\n━━━━━━━━━━━━━━━━\n"
        f"<b>Shop:</b> <code>{data['shop']}</code>\n"
        f"<b>Variant:</b> <code>{data['variant']}</code> (x{data['quantity']})\n\n"
        f"<b>👤 Name:</b> {full_name}\n"
        f"<b>🏠 Address:</b>\n<code>{full_address}</code>\n\n"
        f"<b>📞 Phone:</b> <code>{data.get('phone') or 'N/A'}</code>\n"
        f"<b>📧 Email:</b> <code>{data.get('email') or 'N/A'}</code>\n\n"
        f"➡️ Reply to this message with cards (<code>CC|MM|YY|CVV</code>), one per line, max 25."
    )
    try:
        sent = bot.reply_to(message, response, parse_mode='HTML')
        PENDING_CHECKOUTS[sent.message_id] = data
    except Exception as e:
        logger.error(f"Error sending checkout details: {e}")
        bot.reply_to(message, "⚠️ Failed to display checkout details.")


def start_check_session(message, checkout_data, raw_lines):
    cards = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if len(cards) >= MAX_CARDS:
            break
        if validate_card(line):
            cards.append(line)

    if not cards:
        bot.reply_to(message, "⚠️ No valid cards found.\n\nFormat: <code>CC|MM|YY|CVV</code> one per line.", parse_mode='HTML')
        return

    total_to_check = len(cards)
    total_lines = len([l for l in raw_lines if l.strip()])
    limit_note = ""
    if total_lines > MAX_CARDS:
        limit_note = f"\n\n⚠️ Max {MAX_CARDS} cards accepted, using first {MAX_CARDS}."

    initial_text = (
        f"*{escape_markdown('⌬ @AutoShopifyHitterBot | Auto Checkout')}*\n"
        f"```Starting checks...```\n━━━━━━━━━━━━━━━━\n"
        f"*Cards Loaded* \\: `{total_to_check}`\n"
        f"*Shop* \\: `{escape_markdown(checkout_data['shop'])}`"
        f"{escape_markdown(limit_note) if limit_note else ''}"
    )
    try:
        status_msg = bot.reply_to(message, initial_text, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error sending initial status: {e}")
        return

    threading.Thread(
        target=run_checks,
        args=(message.chat.id, status_msg.message_id, cards, checkout_data),
        daemon=True,
    ).start()


@bot.message_handler(func=lambda m: m.reply_to_message is not None and m.reply_to_message.message_id in PENDING_CHECKOUTS)
def handle_cards_reply(message):
    checkout_data = PENDING_CHECKOUTS.pop(message.reply_to_message.message_id, None)
    if not checkout_data:
        return
    raw_lines = message.text.strip().splitlines()
    start_check_session(message, checkout_data, raw_lines)


def run_checks(chat_id, message_id, cards, checkout_data):
    checked = 0
    total = len(cards)
    declines = 0
    three_ds = 0

    for card in cards:
        processing_text = (
            f"*{escape_markdown('⌬ @AutoShopifyHitterBot | Auto Checkout')}*\n"
            f"```Processing...```\n━━━━━━━━━━━━━━━━\n"
            f"*Count* \\: `Checked {checked}/{total}`\n\n"
            f"*𝗖𝗮𝗿𝗱* \\: `{escape_markdown(card)}`\n"
            f"*𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞* \\: `Checking...`\n\n"
            f"*Checkout Status* \\: `Incomplete`"
        )
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=processing_text, parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Error editing (processing): {e}")

        time.sleep(random.uniform(3.0, 4.0))

        roll = random.random()
        if roll < 0.70:
            response_text = "3DS_Required"
            three_ds += 1
        else:
            response_text = "Card_Declined"
            declines += 1

        checked += 1
        checked_text = (
            f"*{escape_markdown('⌬ @AutoShopifyHitterBot | Auto Checkout')}*\n"
            f"```Completed```\n━━━━━━━━━━━━━━━━\n"
            f"*Count* \\: `Checked {checked}/{total}`\n\n"
            f"*𝗖𝗮𝗿𝗱* \\: `{escape_markdown(card)}`\n"
            f"*𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞* \\: `{escape_markdown(response_text)}`\n\n"
            f"*Checkout Status* \\: `Incomplete`"
        )
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=checked_text, parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Error editing (checked): {e}")

    final_text = (
        f"*{escape_markdown('⌬ @AutoShopifyHitterBot | Auto Checkout Done')}*\n"
        f"```Payment attempts finished```\n━━━━━━━━━━━━━━━━\n"
        f"*Total* \\: `{total}`\n"
        f"*Shop* \\: `{escape_markdown(checkout_data['shop'])}`\n\n"
        f"❌ *Declined* \\: `{declines}`\n"
        f"🔐 *3DS* \\: `{three_ds}`\n\n"
        f"*Checkout Status* \\: `Incomplete`"
    )
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_text, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error editing (final): {e}")


@bot.callback_query_handler(func=lambda call: call.data == "auto_checkout")
def auto_checkout_callback(call):
    info_message = (
        f"【✘】*Status* \\: \\| `Live`\n\n"
        f"【✘】*Command* \\: `/sco`\n\n"
        f"【✘】*Gateway* \\: `Auto Shopify Hitter`"
    )
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=info_message,
            reply_markup=checkout_keyboard(),
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"Error sending checkout info: {e}")


@bot.callback_query_handler(func=lambda call: call.data == "back")
def back_callback(call):
    user = call.from_user
    welcome_message = build_welcome(user)
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=welcome_message,
            reply_markup=welcome_keyboard(),
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"Error going back: {e}")


def start_bot():
    logger.info("Bot is starting...")
    try:
        bot.delete_webhook()
        bot.infinity_polling(timeout=30, long_polling_timeout=25)
    except Exception as e:
        logger.error(f"Bot error: {e}")


if __name__ == "__main__":
    start_bot()
