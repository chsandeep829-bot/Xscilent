import os
import re
import time
import base64
import requests
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")       # Your GitHub Personal Access Token
GITHUB_REPO = os.getenv("GITHUB_REPO")         # e.g., "username/repo-name"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://xscilent.onrender.com")
SMS_CHAT_ID = os.getenv("SMS_CHAT_ID")         # Optional: Restrict SMS parsing to this specific Chat ID

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# In-memory storage for active checkout sessions
active_checkout_sessions = {}  

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
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("XSCILENT 5 HOURS - ₹40"),
        KeyboardButton("XSCILENT 1 DAY - ₹100"),
        KeyboardButton("XSCILENT 3 DAYS - ₹180"),
        KeyboardButton("XSCILENT 7 DAYS - ₹300"),
        KeyboardButton("XSCILENT 30 DAYS - ₹800"),
        KeyboardButton("XSCILENT FULL SEASON - ₹1200")
    )
    bot.send_message(
        message.chat.id,
        "👋 **Welcome to Xscilent Bot!**\n\nSelect a plan below to create your checkout session:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: True)
def handle_incoming_message(message):
    text = message.text or ""
    chat_id = message.chat.id
    
    product_map = {
        "XSCILENT 5 HOURS - ₹40": 40.0,
        "XSCILENT 1 DAY - ₹100": 100.0,
        "XSCILENT 3 DAYS - ₹180": 180.0,
        "XSCILENT 7 DAYS - ₹300": 300.0,
        "XSCILENT 30 DAYS - ₹800": 800.0,
        "XSCILENT FULL SEASON - ₹1200": 1200.0
    }
    
    # 1. Handle user clicking a buy button in private chat
    if text in product_map:
        price = product_map[text]
        order_id = str(int(time.time()))
        
        active_checkout_sessions[order_id] = {
            "userId": chat_id,
            "product": text,
            "price": price,
            "timestamp": time.time()
        }
        
        bot.send_message(
            chat_id,
            f"💳 **Checkout Session Created!**\n\n"
            f"📦 Product: `{text}`\n"
            f"💰 Amount: **₹{price}**\n\n"
            f"👉 Please pay **₹{price}** via UPI.\n"
            f"⚡ Once paid, your SMS forwarder app will send the notification here, and your key will be delivered instantly!",
            parse_mode="Markdown"
        )
        return

    # 2. Handle forwarded SMS payment notifications from the authorized group
    if SMS_CHAT_ID and str(chat_id) != str(SMS_CHAT_ID):
        return  # Ignore messages from other chats for security

    amount_match = re.search(r'(?:₹|Rs\.?)\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if amount_match:
        received_amount = float(amount_match.group(1))
        print(f"🔍 Detected amount from authorized SMS stream: ₹{received_amount}")
        
        matched_order_id = None
        latest_time = 0
        for order_id, session in active_checkout_sessions.items():
            if session["price"] == received_amount and session["timestamp"] > latest_time:
                latest_time = session["timestamp"]
                matched_order_id = order_id
                
        session = active_checkout_sessions.get(matched_order_id)
        if session:
            user_id = session["userId"]
            product = session["product"]
            file_path = get_file_path_for_product(product)
            
            if file_path:
                keys, _ = fetch_keys_from_github(file_path)
                if keys:
                    delivered_key = keys[0]
                    success = remove_key_from_github(file_path, delivered_key)
                    
                    if success:
                        bot.send_message(
                            user_id,
                            f"✅ **Payment Verified via SMS & Key Delivered!**\n\n📦 Product: `{product}`\n🔑 Your Key:\n`{delivered_key}`",
                            parse_mode="Markdown"
                        )
                        del active_checkout_sessions[matched_order_id]
                        return
                else:
                    bot.send_message(
                        user_id,
                        f"⚠️ Payment received for **{product}**, but keys are currently out of stock!",
                        parse_mode="Markdown"
                    )

# --- FLASK WEB SERVER & WEBHOOK ROUTES ---
@app.route('/')
def home():
    return "Telegram UPI Bot (SMS Forwarder Mode) is running successfully!"

@app.route(f'/bot/{TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

if __name__ == '__main__':
    webhook_url = f"{RENDER_URL}/bot/{TOKEN}"
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url)
    print(f"🔗 Telegram Webhook set to: {webhook_url}")

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
