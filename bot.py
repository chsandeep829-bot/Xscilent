import os
import re
import time
import base64
import io
import qrcode
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")       # Your GitHub Personal Access Token
GITHUB_REPO = os.getenv("GITHUB_REPO")         # e.g., "username/repo-name"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://xscilent.onrender.com")
UPI_VPA = os.getenv("UPI_VPA", "yourname@upi") # Your UPI ID from Render environment
UPI_NAME = os.getenv("UPI_NAME", "Xscilent")   # Display name on UPI apps
SUPPORT_CHAT_ID = "-5409271468"
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")     # Your Telegram Admin ID

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# In-memory storage
active_checkout_sessions = {}  
user_purchased_keys = {}  

# --- GITHUB HELPERS ---
def get_file_path_for_product(product_code):
    mapping = {
        "buy_5hours": "keys_5h.txt",
        "buy_1day": "keys_1d.txt",
        "buy_3days": "keys_3d.txt",
        "buy_7days": "keys_7d.txt",
        "buy_30days": "keys_30d.txt",
        "buy_season": "keys_season.txt"
    }
    return mapping.get(product_code)

def get_product_details(product_code):
    mapping = {
        "buy_5hours": ("XSCILENT 5 HOURS", 40.0),
        "buy_1day": ("XSCILENT 1 DAY", 100.0),
        "buy_3days": ("XSCILENT 3 DAYS", 180.0),
        "buy_7days": ("XSCILENT 7 DAYS", 300.0),
        "buy_30days": ("XSCILENT 30 DAYS", 800.0),
        "buy_season": ("XSCILENT FULL SEASON", 1200.0)
    }
    return mapping.get(product_code, ("Unknown Product", 0.0))

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

def upload_apk_to_github(file_bytes, filename):
    file_path = f"apks/{filename}"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None

    encoded_content = base64.b64encode(file_bytes).decode("utf-8")
    payload = {
        "message": f"Upload APK {filename}",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha

    put_res = requests.put(url, headers=headers, json=payload)
    if put_res.status_code in [200, 201]:
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{file_path}"
    return None

def get_available_apks():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/apks"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        items = res.json()
        apks = []
        for item in items:
            if item["name"].endswith(".apk"):
                apks.append({
                    "name": item["name"],
                    "url": item["download_url"]
                })
        return apks
    return []

# --- KEYBOARDS ---
def get_persistent_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        KeyboardButton("🔑 Purchase Key"),
        KeyboardButton("📋 My Keys"),
        KeyboardButton("📥 Download App"),
        KeyboardButton("💰 Check Fund"),
        KeyboardButton("📚 How to Buy?")
    )
    markup.row(
        KeyboardButton("🆔 My ID"),
        KeyboardButton("🆘 Contact Support")
    )
    return markup

def get_products_inline_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("5 Hours - ₹40", callback_data="buy_5hours"),
        InlineKeyboardButton("1 Day - ₹100", callback_data="buy_1day"),
        InlineKeyboardButton("3 Days - ₹180", callback_data="buy_3days"),
        InlineKeyboardButton("7 Days - ₹300", callback_data="buy_7days"),
        InlineKeyboardButton("30 Days - ₹800", callback_data="buy_30days"),
        InlineKeyboardButton("Full Season - ₹1200", callback_data="buy_season")
    )
    return markup

# --- TELEGRAM HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "👋 **Welcome to Xscilent Bot!**\n\nChoose an option from the keyboard below:",
        reply_markup=get_persistent_keyboard(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "🔑 Purchase Key")
def handle_purchase_text(message):
    bot.send_message(
        message.chat.id,
        "📦 **Select a plan to purchase:**",
        reply_markup=get_products_inline_menu(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "📋 My Keys")
def handle_my_keys_text(message):
    user_id = message.from_user.id
    keys = user_purchased_keys.get(user_id, [])
    if keys:
        keys_text = "\n".join([f"`{k}`" for k in keys])
        bot.send_message(message.chat.id, f"📋 **Your Purchased Keys:**\n\n{keys_text}", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "📋 You haven't purchased any keys yet.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📥 Download App")
def handle_download_app_text(message):
    apks = get_available_apks()
    if apks:
        apk_list_text = "📥 **Available Applications for Download:**\n\n"
        for apk in apks:
            apk_list_text += f"🔹 [{apk['name']}]({apk['url']})\n"
        bot.send_message(message.chat.id, apk_list_text, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ No APK files are currently uploaded. Please check back later.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💰 Check Fund")
def handle_check_fund_text(message):
    bot.send_message(message.chat.id, "💰 **Your Account Balance:**\n\n₹0.0 (Direct UPI QR payment mode active)", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📚 How to Buy?")
def handle_how_to_buy_text(message):
    bot.send_message(
        message.chat.id,
        "📚 **How to Buy:**\n\n1. Click **Purchase Key** and select your desired duration.\n2. Scan the generated QR code using GPay, PhonePe, or Paytm.\n3. Complete the payment.\n4. Your key will be delivered instantly upon payment verification!",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "🆔 My ID")
def handle_my_id_text(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, f"🆔 **Your Telegram Info:**\n\nUser ID: `{user_id}`\nUsername: @{message.from_user.username or 'None'}", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🆘 Contact Support")
def handle_support_text(message):
    group_clean_id = SUPPORT_CHAT_ID.replace('-100', '').replace('-', '')
    bot.send_message(
        message.chat.id,
        f"🆘 **Contact Support:**\n\nClick the link below to open our support group:\n👉 [Open Support Group](https://t.me/c/{group_clean_id}/1)",
        parse_mode="Markdown"
    )

@bot.message_handler(content_types=['document'])
def handle_apk_upload(message):
    user_id = message.from_user.id
    if ADMIN_USER_ID and str(user_id) != str(ADMIN_USER_ID):
        bot.send_message(user_id, "⚠️ Only the admin is authorized to upload APK files.")
        return
        
    file_name = message.document.file_name or "app.apk"
    if not file_name.endswith('.apk'):
        bot.send_message(user_id, "⚠️ Please upload a valid .apk file.")
        return
        
    bot.send_message(user_id, "⏳ Downloading and uploading APK to GitHub storage...")
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        raw_url = upload_apk_to_github(downloaded_file, file_name)
        if raw_url:
            bot.send_message(
                user_id,
                f"✅ **APK Uploaded Successfully!**\n\n📁 Filename: `{file_name}`\n🔗 Download Link:\n{raw_url}\n\nUsers can now download it via the 'Download App' button!",
                parse_mode="Markdown"
            )
        else:
            bot.send_message(user_id, "❌ Failed to upload APK to GitHub.")
    except Exception as e:
        bot.send_message(user_id, f"❌ Error uploading file: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data

    if data.startswith("buy_"):
        product_name, price = get_product_details(data)
        order_id = str(int(time.time()))
        
        upi_url = f"upi://pay?pa={UPI_VPA}&pn={UPI_NAME}&am={price}&cu=INR"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        bio = io.BytesIO()
        bio.name = 'upi_qr.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
            
        sent_msg = bot.send_photo(
            chat_id,
            photo=bio,
            caption=f"💳 **Checkout Session Created!**\n\n"
                    f"📦 Product: `{product_name}`\n"
                    f"💰 Amount: **₹{price}**\n\n"
                    f"📱 **Scan the QR code above** using GPay, PhonePe, or Paytm to pay instantly.\n\n"
                    f"⚡ Once paid, MacroDroid will instantly notify this bot and your key will be delivered automatically!",
            parse_mode="Markdown"
        )
        
        active_checkout_sessions[order_id] = {
            "userId": chat_id,
            "product_code": data,
            "product_name": product_name,
            "price": price,
            "timestamp": time.time(),
            "message_id": sent_msg.message_id
        }

# --- FLASK WEB SERVER & WEBHOOK ROUTES ---
@app.route('/')
def home():
    return "Telegram UPI Bot with Persistent Keyboard is running successfully!"

@app.route(f'/bot/{TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST', 'GET'])
def macro_webhook():
    try:
        body = {}
        if request.is_json:
            body = request.get_json(silent=True) or {}
        elif request.form:
            body = request.form.to_dict()

        text = str(body.get('text', '')) or request.data.decode('utf-8', errors='ignore')
        print("📥 MacroDroid Webhook Payload Received:", text)

        amount_match = re.search(r'(?:₹|Rs\.?)\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if amount_match:
            received_amount = float(amount_match.group(1))
            print(f"🔍 Detected amount from MacroDroid webhook: ₹{received_amount}")
            
            matched_order_id = None
            latest_time = 0
            for order_id, session in active_checkout_sessions.items():
                if session["price"] == received_amount and session["timestamp"] > latest_time:
                    latest_time = session["timestamp"]
                    matched_order_id = order_id
                    
            session = active_checkout_sessions.get(matched_order_id)
            if session:
                user_id = session["userId"]
                product_name = session["product_name"]
                file_path = get_file_path_for_product(session["product_code"])
                
                if file_path:
                    keys, _ = fetch_keys_from_github(file_path)
                    if keys:
                        delivered_key = keys[0]
                        success = remove_key_from_github(file_path, delivered_key)
                        
                        if success:
                            if user_id not in user_purchased_keys:
                                user_purchased_keys[user_id] = []
                            user_purchased_keys[user_id].append(delivered_key)

                            try:
                                bot.delete_message(chat_id=user_id, message_id=session["message_id"])
                            except Exception as del_err:
                                print("Could not delete QR message:", del_err)
                            
                            bot.send_message(
                                user_id,
                                f"✅ **Payment Verified & Key Delivered!**\n\n📦 Product: `{product_name}`\n🔑 Your Key:\n`{delivered_key}`\n\n(You can view your keys anytime using 'My Keys' in the menu)",
                                parse_mode="Markdown"
                            )
                            del active_checkout_sessions[matched_order_id]
                            return jsonify({"status": "success", "message": "Key delivered and QR deleted"}), 200
                    else:
                        bot.send_message(
                            user_id,
                            f"⚠️ Payment received for **{product_name}**, but keys are currently out of stock on GitHub!",
                            parse_mode="Markdown"
                        )
                        
        return jsonify({"status": "received"}), 200
    except Exception as error:
        print("Webhook error:", error)
        return jsonify({"error": str(error)}), 200

if __name__ == '__main__':
    webhook_url = f"{RENDER_URL}/bot/{TOKEN}"
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url)
    print(f"🔗 Telegram Webhook set to: {webhook_url}")

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
