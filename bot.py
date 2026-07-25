import os
import base64
import time
import re
import threading
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import telebot
from telebot import types

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
UPI_VPA = os.getenv("UPI_VPA", "c.sandeep@superyes")
UPI_NAME = os.getenv("UPI_NAME", "My Business")

if not TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN is missing in environment variables.")
    exit(1)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

active_checkout_sessions = {}
user_purchased_keys = {}

def get_file_path_for_product(product_name):
    name = product_name.upper()
    if "5 HOURS" in name: return "keys_5h.txt"
    if "1 DAY" in name: return "keys_1d.txt"
    if "3 DAYS" in name: return "keys_3d.txt"
    if "7 DAYS" in name: return "keys_7d.txt"
    if "30 DAYS" in name: return "keys_30d.txt"
    if "FULL SEASON" in name: return "keys_season.txt"
    return None

def fetch_keys_from_github(file_path):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            keys = [line.strip() for line in content.split("\n") if line.strip()]
            return keys, data["sha"]
    except Exception as error:
        print(f"Error fetching keys from GitHub ({file_path}):", error)
    return [], None

def remove_key_from_github(file_path, key_to_remove):
    keys, sha = fetch_keys_from_github(file_path)
    if not sha or key_to_remove not in keys:
        return False
    keys.remove(key_to_remove)
    updated_content = "\n".join(keys) + ("\n" if keys else "")
    encoded_content = base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    }
    body = {
        "message": f"Auto-remove sold key: {key_to_remove}",
        "content": encoded_content,
        "sha": sha
    }
    try:
        res = requests.put(url, headers=headers, json=body)
        if res.status_code in [200, 201]:
            print(f"Successfully removed key {key_to_remove} from {file_path}")
            return True
    except Exception as error:
        print(f"Error updating GitHub keys file ({file_path}):", error)
    return False

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔑 Purchase Key", "📋 My Keys")
    markup.row("🎁 Redeem Code", "📖 How to Buy")
    markup.row("🆔 My ID", "🆘 Contact Support")
    return markup

def get_brands_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("XSCILENT LOADER")
    markup.row("⬅️ Back")
    return markup

def get_xscilent_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("XSCILENT 5 HOURS - ₹40", "XSCILENT 1 DAY - ₹100")
    markup.row("XSCILENT 3 DAYS - ₹180", "XSCILENT 7 DAYS - ₹300")
    markup.row("XSCILENT 30 DAYS - ₹800", "XSCILENT FULL SEASON - ₹1200")
    markup.row("⬅️ Back to Brands")
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "👋 Welcome to Key Store", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "🔑 Purchase Key")
def purchase_key(message):
    bot.send_message(message.chat.id, "🎮 Select a brand:", reply_markup=get_brands_menu())

@bot.message_handler(func=lambda msg: msg.text == "⬅️ Back to Brands")
def back_to_brands(message):
    bot.send_message(message.chat.id, "🎮 Select a brand:", reply_markup=get_brands_menu())

@bot.message_handler(func=lambda msg: msg.text == "⬅️ Back")
def back_main(message):
    bot.send_message(message.chat.id, "👋 Main Menu", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "XSCILENT LOADER")
def xscilent_loader(message):
    bot.send_message(message.chat.id, "⏳ Select duration:", reply_markup=get_xscilent_menu())

@bot.message_handler(func=lambda msg: msg.text == "📋 My Keys")
def my_keys(message):
    user_id = message.from_user.id
    purchased = user_purchased_keys.get(user_id, [])
    if not purchased:
        bot.send_message(message.chat.id, "📋 You haven't purchased any keys yet.", reply_markup=get_main_menu())
    else:
        msg = "📋 **Your Purchased Keys:**\n\n"
        for idx, item in enumerate(purchased):
            msg += f"{idx + 1}. **{item['product']}**\n🔑 Key: `{item['key']}`\n💵 Price: ₹{item['price']}\n\n"
        bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "📖 How to Buy")
def how_to_buy(message):
    guide_text = (
        "📖 **How to Buy License Keys:**\n\n"
        "1️⃣ Tap **🔑 Purchase Key** from the main menu.\n"
        "2️⃣ Select your desired loader brand and duration.\n"
        "3️⃣ Scan the UPI QR code and complete payment.\n"
        "4️⃣ Your license key will be delivered **instantly and automatically** upon successful payment! 🚀"
    )
    bot.send_message(message.chat.id, guide_text, parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "🆘 Contact Support")
def contact_support(message):
    bot.send_message(message.chat.id, "🆘 **Customer Support**\n\nIf you are facing any issues, reach out:\n\n💬 Support Admin: @c_sandeep", parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "🎁 Redeem Code")
def redeem_code(message):
    bot.send_message(message.chat.id, "🎁 **Redeem Code**\n\nSend voucher code directly in chat to redeem.", parse_mode="Markdown", reply_markup=get_main_menu())

@bot.message_handler(func=lambda msg: msg.text == "🆔 My ID")
def my_id(message):
    bot.send_message(message.chat.id, f"Your User ID is: `{message.from_user.id}`", parse_mode="Markdown")

@bot.message_handler(func=lambda msg: bool(re.search(r'₹(\d+)', msg.text)))
def handle_price_selection(message):
    try:
        text = message.text
        user_id = message.from_user.id
        match = re.search(r'₹(\d+)', text)
        if not match:
            return

        base_price = float(match.group(1))
        order_id = f"ord_{int(time.time() * 1000)}"
        note = f"Payment for {text}"

        upi_uri = f"upi://pay?pa={requests.utils.quote(UPI_VPA)}&pn={requests.utils.quote(UPI_NAME)}&am={base_price}&tr={order_id}&tn={requests.utils.quote(note)}&cu=INR"
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={requests.utils.quote(upi_uri)}"

        links = {
            "phonepe": f"phonepe://pay?pa={requests.utils.quote(UPI_VPA)}&pn={requests.utils.quote(UPI_NAME)}&am={base_price}&tr={order_id}&tn={requests.utils.quote(note)}&cu=INR",
            "gpay": f"tez://upi/pay?pa={requests.utils.quote(UPI_VPA)}&pn={requests.utils.quote(UPI_NAME)}&am={base_price}&tr={order_id}&tn={requests.utils.quote(note)}&cu=INR",
            "paytm": f"paytmmp://pay?pa={requests.utils.quote(UPI_VPA)}&pn={requests.utils.quote(UPI_NAME)}&am={base_price}&tr={order_id}&tn={requests.utils.quote(note)}&cu=INR",
            "bhim": f"upi://pay?pa={requests.utils.quote(UPI_VPA)}&pn={requests.utils.quote(UPI_NAME)}&am={base_price}&tr={order_id}&tn={requests.utils.quote(note)}&cu=INR"
        }

        active_checkout_sessions[order_id] = {
            "userId": user_id,
            "product": text,
            "price": base_price,
            "timestamp": time.time() * 1000
        }

        print(f"📝 Created checkout session: Order ID {order_id} for Price ₹{base_price} (User: {user_id})")

        caption = f"""
💳 **Payment Checkout**

💵 Amount: **₹{base_price}**
📦 Item: `{text}`
🆔 Order ID: `{order_id}`

📱 **Pay Instantly via Apps:**
• [PhonePe]({links['phonepe']})
• [Google Pay]({links['gpay']})
• [Paytm]({links['paytm']})
• [Any UPI App]({links['bhim']})

*Scan the QR code or click an app to pay. Your key will be sent **automatically** as soon as payment is confirmed!*
        """.strip()

        bot.send_photo(message.chat.id, qr_image_url, caption=caption, parse_mode="Markdown")
    except Exception as error:
        print("Error generating UPI QR:", error)
        bot.send_message(message.chat.id, "❌ Failed to generate payment QR code. Please try again later.")

@app.route('/')
def index():
    return "Telegram UPI Bot (Python) is running successfully!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        body = request.get_json(silent=True) or {}
        print("📥 Webhook Payload Received:", body)
        
        # Aggregate properties to capture payload details from SMS/Notification forwarder
        raw_input = f"{body} {body.get('title', '')} {body.get('text', '')} {body.get('msg', '')}"
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
            return jsonify({"error": "Matching active order session not found", "received": raw_input}), 404

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
                    f"⚠️ Payment received for **{product}**, but keys are currently out of stock! Please contact support @c_sandeep.",
                    parse_mode="Markdown"
                )

        return jsonify({"status": "received"}), 200
    except Exception as error:
        print("Webhook processing error:", error)
        return jsonify({"error": "Internal server error"}), 500

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("🌐 Web server thread started...")

    print("🤖 Telegram UPI Bot (Python) is running...")
    bot.infinity_polling()
