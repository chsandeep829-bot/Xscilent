import os
import re
import time
import base64
import threading
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")       # Your GitHub Personal Access Token
GITHUB_REPO = os.getenv("GITHUB_REPO")         # e.g., "username/repo-name"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# In-memory storage for active checkout sessions and purchased keys
active_checkout_sessions = {}  
user_purchased_keys = {}

# --- GITHUB KEY MANAGEMENT HELPERS ---
def get_file_path_for_product(product_name):
    mapping = {
        "XSCILENT 5 HOURS - ₹40": "keys/5hours.txt",
        "XSCILENT 1 DAY - ₹100": "keys/1day.txt",
        "XSCILENT 3 DAYS - ₹180": "keys/3days.txt",
        "XSCILENT 7 DAYS - ₹300": "keys/7days.txt",
        "XSCILENT 30 DAYS - ₹800": "keys/30days.txt",
        "XSCILENT FULL SEASON - ₹1200": "keys/fullseason.txt"
    }
    return mapping.get(product_name)

def fetch_keys_from_github(file_path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        content_data = response.json()
        file_content = base64.b64decode(content_data["content"]).decode("utf-8")
        sha = content_data["sha"]
        keys = [line.strip() for line in file_content.splitlines() if line.strip()]
        return keys, sha
    return [], None

def remove_key_from_github(file_path, key_to_remove):
    keys, sha = fetch_keys_from_github(file_path)
    if not sha or key_to_remove not in keys:
        return False
        
    keys.remove(key_to_remove)
    updated_content = "\n".join(keys) + ("\n" if keys else "")
    encoded_content = base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    payload = {
        "message": f"Auto-remove delivered key from {file_path}",
        "content": encoded_content,
        "sha": sha,
        "branch": GITHUB_BRANCH
    }
    
    response = requests.put(url, headers=headers, json=payload)
    return response.status_code in [200, 201]

# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔑 Purchase Key", callback_data="shop_menu"))
    bot.send_message(
        message.chat.id,
        "👋 **Welcome to Xscilent Bot!**\n\nClick below to browse and purchase available keys automatically.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    data = call.data
    
    if data == "shop_menu":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📦 XSCILENT LOADER", callback_data="loader_menu"))
        bot.edit_message_text(
            "📂 **Select a category:**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    elif data == "loader_menu":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("XSCILENT 5 HOURS - ₹40", callback_data="buy_5hours"))
        markup.add(InlineKeyboardButton("XSCILENT 1 DAY - ₹100", callback_data="buy_1day"))
        markup.add(InlineKeyboardButton("XSCILENT 3 DAYS - ₹180", callback_data="buy_3days"))
        markup.add(InlineKeyboardButton("XSCILENT 7 DAYS - ₹300", callback_data="buy_7days"))
        markup.add(InlineKeyboardButton("XSCILENT 30 DAYS - ₹800", callback_data="buy_30days"))
        markup.add(InlineKeyboardButton("XSCILENT FULL SEASON - ₹1200", callback_data="buy_season"))
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="shop_menu"))
        bot.edit_message_text(
            "🛒 **Select your plan:**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    elif data.startswith("buy_"):
        product_map = {
            "buy_5hours": ("XSCILENT 5 HOURS - ₹40", 40.0),
            "buy_1day": ("XSCILENT 1 DAY - ₹100", 100.0),
            "buy_3days": ("XSCILENT 3 DAYS - ₹180", 180.0),
            "buy_7days": ("XSCILENT 7 DAYS - ₹300", 300.0),
            "buy_30days": ("XSCILENT 30 DAYS - ₹800", 800.0),
            "buy_season": ("XSCILENT FULL SEASON - ₹1200", 1200.0)
        }
        
        product_name, price = product_map.get(data, ("XSCILENT 5 HOURS - ₹40", 40.0))
        order_id = str(int(time.time()))
        
        active_checkout_sessions[order_id] = {
            "userId": chat_id,
            "product": product_name,
            "price": price,
            "timestamp": time.time()
        }
        
        qr_text = (
            f"💳 **Checkout Session Created!**\n\n"
            f"📦 Product: `{product_name}`\n"
            f"💰 Amount: **₹{price}**\n\n"
            f"👉 Please pay **₹{price}** via UPI to your designated merchant/number.\n"
            f"⚡ Once paid, your notification forwarder will instantly verify the payment and your key will be delivered here automatically!"
        )
        bot.edit_message_text(
            qr_text,
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

# --- FLASK WEB SERVER & WEBHOOK ROUTE ---
@app.route('/')
def home():
    return "Telegram UPI Bot (Python) is running successfully!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    try:
        body = {}
        if request.is_json:
            body = request.get_json(silent=True) or {}
        elif request.form:
            body = request.form.to_dict()
        else:
            try:
                body = request.get_json(silent=True) or {}
            except Exception:
                pass

        raw_data = request.data.decode('utf-8', errors='ignore')
        print("📥 Webhook Payload Received:", body, "Raw:", raw_data)
        
        raw_input = f"{body} {raw_data} {body.get('title', '')} {body.get('text', '')} {body.get('msg', '')}"
        matched_order_id = None
        amount_match = re.search(r'(?:₹|Rs\.?)\s*(\d+(?:\.\d+)?)', raw_input, re.IGNORECASE)

        if amount_match:
            received_amount = float(amount_match.group(1))
            print(f"🔍 Detected amount from webhook payload: ₹{received_amount}")
            
            latest_time = 0
            for order_id, session in active_checkout_sessions.items():
                if session["price"] == received_amount and session["timestamp"] > latest_time:
                    latest_time = session["timestamp"]
                    matched_order_id = order_id

        print(f"🎯 Matched Order ID: {matched_order_id}")

        session = active_checkout_sessions.get(matched_order_id)
        if not session:
            print("⚠️ Active session not found. Active sessions:", active_checkout_sessions)
            return jsonify({"status": "ignored", "message": "Matching active order session not found"}), 200

        user_id = session["userId"]
        product = session["product"]
        price = session["price"]
        file_path = get_file_path_for_product(product)

        if file_path:
            keys, _ = fetch_keys_from_github(file_path)
            if keys:
                delivered_key = keys[0]
                success = remove_key_from_github(file_path, delivered_key)

                if success:
                    if user_id not in user_purchased_keys:
                        user_purchased_keys[user_id] = []
                    user_purchased_keys[user_id].append({
                        "product": product,
                        "key": delivered_key,
                        "price": price
                    })

                    bot.send_message(
                        user_id,
                        f"✅ **Payment Verified & Key Delivered Automatically!**\n\n📦 Product: `{product}`\n🔑 Your Key:\n`{delivered_key}`",
                        parse_mode="Markdown"
                    )

                    del active_checkout_sessions[matched_order_id]
                    return jsonify({"status": "success", "message": "Key delivered successfully"}), 200
            else:
                bot.send_message(
                    user_id,
                    f"⚠️ Payment received for **{product}**, but keys are currently out of stock! Please contact support.",
                    parse_mode="Markdown"
                )

        return jsonify({"status": "received"}), 200
    except Exception as error:
        print("Webhook processing error:", error)
        return jsonify({"error": "Internal server error"}), 200

# --- RUN BOT & WEB SERVER CONCURRENTLY ---
def run_telegram_bot():
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Telegram polling error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    # Start Telegram Bot Polling in a background thread
    bot_thread = threading.Thread(target=run_telegram_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Run Flask Web Server on Render's required host and port
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
