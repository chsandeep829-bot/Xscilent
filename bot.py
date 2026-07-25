import os
import re
import time
import base64
import io
import qrcode
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")       # Your GitHub Personal Access Token
GITHUB_REPO = os.getenv("GITHUB_REPO")         # e.g., "username/repo-name"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://xscilent.onrender.com")
UPI_VPA = os.getenv("UPI_VPA", "yourname@upi") # Your UPI ID from Render environment
UPI_NAME = os.getenv("UPI_NAME", "Xscilent")   # Display name on UPI apps
SUPPORT_CHAT_ID = "-5409271468"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# In-memory storage
active_checkout_sessions = {}  
user_purchased_keys = {}  # Stores keys bought by users: {user_id: [key1, key2]}

# --- GITHUB KEY MANAGEMENT HELPERS ---
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

# --- KEYBOARDS ---
def get_main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🔑 Purchase Key", callback_data="menu_purchase"),
        InlineKeyboardButton("📋 My Keys", callback_data="menu_my_keys"),
        InlineKeyboardButton("💰 Check Fund", callback_data="menu_check_fund"),
        InlineKeyboardButton("📚 How to Buy?", callback_data="menu_how_to_buy")
    )
    markup.row(
        InlineKeyboardButton("🆔 My ID", callback_data="menu_my_id"),
        InlineKeyboardButton("🆘 Contact Support", callback_data="menu_support")
    )
    return markup

def get_products_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("5 Hours - ₹40", callback_data="buy_5hours"),
        InlineKeyboardButton("1 Day - ₹100", callback_data="buy_1day"),
        InlineKeyboardButton("3 Days - ₹180", callback_data="buy_3days"),
        InlineKeyboardButton("7 Days - ₹300", callback_data="buy_7days"),
        InlineKeyboardButton("30 Days - ₹800", callback_data="buy_30days"),
        InlineKeyboardButton("Full Season - ₹1200", callback_data="buy_season")
    )
    markup.add(InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_main"))
    return markup

# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Clear old bottom reply keyboard first
    temp_msg = bot.send_message(message.chat.id, "🧹", reply_markup=ReplyKeyboardRemove())
    try:
        bot.delete_message(message.chat.id, temp_msg.message_id)
    except Exception:
        pass

    bot.send_message(
        message.chat.id,
        "👋 **Welcome to Xscilent Bot!**\n\nChoose an option from the menu below:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data

    if data == "menu_main":
        try:
            bot.edit_message_text(
                "👋 **Main Menu:**\n\nChoose an option below:",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=get_main_menu(),
                parse_mode="Markdown"
            )
        except Exception:
            bot.send_message(chat_id, "👋 **Main Menu:**", reply_markup=get_main_menu(), parse_mode="Markdown")

    elif data == "menu_purchase":
        bot.edit_message_text(
            "📦 **Select a plan to purchase:**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=get_products_menu(),
            parse_mode="Markdown"
        )

    elif data == "menu_my_keys":
        keys = user_purchased_keys.get(user_id, [])
        if keys:
            keys_text = "\n".join([f"`{k}`" for k in keys])
            bot.answer_callback_query(call.id, "Here are your keys!")
            bot.send_message(chat_id, f"📋 **Your Purchased Keys:**\n\n{keys_text}", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "No keys found!", show_alert=True)
            bot.send_message(chat_id, "📋 You haven't purchased any keys yet.", parse_mode="Markdown")

    elif data == "menu_check_fund":
        bot.answer_callback_query(call.id, "Balance checked")
        bot.send_message(chat_id, "💰 **Your Account Balance:**\n\n₹0.0 (Direct UPI QR payment mode active)", parse_mode="Markdown")

    elif data == "menu_how_to_buy":
        bot.answer_callback_query(call.id)
        bot.send_message(
            chat_id,
            "📚 **How to Buy:**\n\n1. Click **Purchase Key** and select your desired duration.\n2. Scan the generated QR code using GPay, PhonePe, or Paytm.\n3. Complete the payment.\n4. Your key will be delivered instantly upon payment verification!",
            parse_mode="Markdown"
        )

    elif data == "menu_my_id":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"🆔 **Your Telegram Info:**\n\nUser ID: `{user_id}`\nUsername: @{call.from_user.username or 'None'}", parse_mode="Markdown")

    elif data == "menu_support":
        bot.answer_callback_query(call.id, "Opening Support Group...")
        bot.send_message(
            chat_id,
            f"🆘 **Contact Support:**\n\nClick the link below to open our support group:\n👉 [Open Support Group](https://t.me/c/{SUPPORT_CHAT_ID.replace('-100', '').replace('-', '')}/1)",
            parse_mode="Markdown"
        )

    elif data.startswith("buy_"):
        product_name, price = get_product_details(data)
        order_id = str(int(time.time()))
        
        # Construct UPI Payment Link
        upi_url = f"upi://pay?pa={UPI_VPA}&pn={UPI_NAME}&am={price}&cu=INR"
        
        # Generate QR Code image in memory
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        bio = io.BytesIO()
        bio.name = 'upi_qr.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.delete_message(chat_id, call.message.message_id)
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
    return "Telegram UPI Bot (Menu Cleaned) is running successfully!"

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
                                f"✅ **Payment Verified & Key Delivered!**\n\n📦 Product: `{product_name}`\n🔑 Your Key:\n`{delivered_key}`\n\n(You can also view your keys anytime using 'My Keys' in the menu)",
                                reply_markup=get_main_menu(),
                                parse_mode="Markdown"
                            )
                            del active_checkout_sessions[matched_order_id]
                            return jsonify({"status": "success", "message": "Key delivered and QR deleted"}), 200
                    else:
                        bot.send_message(
                            user_id,
                            f"⚠️ Payment received for **{product_name}**, but keys are currently out of stock on GitHub!",
                            reply_markup=get_main_menu(),
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
