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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")       
GITHUB_REPO = os.getenv("GITHUB_REPO", "chsandeep829-bot/Xscilent")         
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://xscilent.onrender.com")
UPI_VPA = os.getenv("UPI_VPA", "yourname@upi") 
UPI_NAME = os.getenv("UPI_NAME", "Xscilent")  
SUPPORT_CHAT_ID = "-5409271468"
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# MacroDroid Webhook URL for loud phone alarm/voice alerts
MACRODROID_URL = os.getenv("MACRODROID_WEBHOOK_URL", "")

# Raw GitHub URL for loader.apk from main branch
LOADER_APK_LINK = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/loader.apk"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# In-memory storage & tracking
active_checkout_sessions = {}  
user_purchased_keys = {}  
user_key_downloads = {}  

# Admin financial & buyer records
total_collection = 0.0
buyer_records = []  

# --- ALERT HELPER FOR OUT OF STOCK ---
def alert_owner_out_of_stock(product_name):
    # 1. Send Telegram message to Admin
    if ADMIN_USER_ID != 0:
        try:
            bot.send_message(
                ADMIN_USER_ID,
                f"🚨 **URGENT: Out of Stock Alert!**\n\n"
                f"Product **{product_name}** has run out of keys! Please refill keys immediately.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print("Error sending admin telegram alert:", e)

    # 2. Trigger MacroDroid Webhook to play alarm/voice alert locally on your phone
    if MACRODROID_URL:
        try:
            response = requests.post(
                MACRODROID_URL, 
                json={"product": product_name, "status": "out_of_stock"}
            )
            print(f"📱 MacroDroid Webhook Triggered Successfully: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ MacroDroid Webhook Error: {str(e)}")
    else:
        print("⚠️ MACRODROID_WEBHOOK_URL environment variable is missing.")

# --- GITHUB HELPERS FOR KEYS ---
def get_file_path_for_product(product_code):
    mapping = {
        "buy_loader_1hour": "loader/keys_1h.txt",
        "buy_loader_5hours": "loader/keys_5h.txt",
        "buy_loader_1day": "loader/keys_1d.txt",
        "buy_loader_3days": "loader/keys_3d.txt",
        "buy_loader_7days": "loader/keys_7d.txt",
        "buy_loader_15days": "loader/keys_15d.txt",
        "buy_loader_30days": "loader/keys_30d.txt",
        "buy_loader_60days": "loader/keys_60d.txt"
    }
    return mapping.get(product_code)

def get_product_details(product_code):
    cat_prefix = "Xscilent Loader"
    if "1hour" in product_code:
        return (f"{cat_prefix} - 1 HOUR", 20.0)
    elif "5hours" in product_code:
        return (f"{cat_prefix} - 5 HOURS", 40.0)
    elif "1day" in product_code:
        return (f"{cat_prefix} - 1 DAY", 100.0)
    elif "3days" in product_code:
        return (f"{cat_prefix} - 3 DAYS", 180.0)
    elif "7days" in product_code:
        return (f"{cat_prefix} - 7 DAYS", 300.0)
    elif "15days" in product_code:
        return (f"{cat_prefix} - 15 DAYS", 500.0)
    elif "30days" in product_code:
        return (f"{cat_prefix} - 30 DAYS", 800.0)
    elif "60days" in product_code:
        return (f"{cat_prefix} - 60 DAYS", 1200.0)
    return ("Unknown Product", 0.0)

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
def get_persistent_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        KeyboardButton("🔑 Purchase Key"),
        KeyboardButton("📋 My Keys"),
        KeyboardButton("💰 Check Fund"),
        KeyboardButton("📚 How to Buy?")
    )
    markup.row(
        KeyboardButton("🆔 My ID"),
        KeyboardButton("🆘 Contact Support")
    )
    return markup

def get_duration_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("1 Hour - ₹20", callback_data="buy_loader_1hour"),
        InlineKeyboardButton("5 Hours - ₹40", callback_data="buy_loader_5hours"),
        InlineKeyboardButton("1 Day - ₹100", callback_data="buy_loader_1day"),
        InlineKeyboardButton("3 Days - ₹180", callback_data="buy_loader_3days"),
        InlineKeyboardButton("7 Days - ₹300", callback_data="buy_loader_7days"),
        InlineKeyboardButton("15 Days - ₹500", callback_data="buy_loader_15days"),
        InlineKeyboardButton("30 Days - ₹800", callback_data="buy_loader_30days"),
        InlineKeyboardButton("60 Days - ₹1200", callback_data="buy_loader_60days")
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

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    user_id = message.from_user.id
    if ADMIN_USER_ID != 0 and user_id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "❌ You are not authorized to use this command.")
        return

    buyers_summary = ""
    if buyer_records:
        buyers_list_formatted = []
        for idx, b in enumerate(buyer_records, 1):
            buyers_list_formatted.append(
                f"{idx}. User: `{b['username']}` (ID: `{b['user_id']}`)\n"
                f"   📦 Product: {b['product']} (₹{b['price']})\n"
                f"   🔑 Key: `{b['key']}`\n"
                f"   🕒 Time: {b['time']}"
            )
        buyers_summary = "\n\n".join(buyers_list_formatted)
    else:
        buyers_summary = "No purchases made yet."

    stats_text = (
        f"📊 **Admin Panel - Statistics**\n\n"
        f"💰 **Total Collection:** ₹{total_collection}\n"
        f"👥 **Total Buyers Count:** {len(buyer_records)}\n\n"
        f"📜 **Buyer Details:**\n{buyers_summary}"
    )
    
    if len(stats_text) > 4000:
        for x in range(0, len(stats_text), 4000):
            bot.send_message(message.chat.id, stats_text[x:x+4000], parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🔑 Purchase Key")
def handle_purchase_text(message):
    bot.send_message(
        message.chat.id,
        "🚀 **Select a plan for Xscilent Loader:**",
        reply_markup=get_duration_menu(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "📋 My Keys")
def handle_my_keys_text(message):
    user_id = message.from_user.id
    keys = user_purchased_keys.get(user_id, [])
    if not keys:
        bot.send_message(message.chat.id, "📋 You haven't purchased any keys yet.", parse_mode="Markdown")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for k in keys:
        rem = user_key_downloads.get((user_id, k), 2)
        markup.add(InlineKeyboardButton(f"📥 Download APK for {k[:8]}... ({rem}/2 left)", callback_data=f"dl_key_{k}"))
    
    keys_text = "\n".join([f"`{k}` (Downloads left: {user_key_downloads.get((user_id, k), 2)}/2)" for k in keys])
    bot.send_message(
        message.chat.id,
        f"📋 **Your Purchased Keys & Downloads:**\n\n{keys_text}\n\nClick below to download your APK (Limit: 2 times per key):",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "💰 Check Fund")
def handle_check_fund_text(message):
    bot.send_message(message.chat.id, "💰 **Your Account Balance:**\n\n₹0.0 (Direct UPI QR payment mode active)", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📚 How to Buy?")
def handle_how_to_buy_text(message):
    bot.send_message(
        message.chat.id,
        "📚 **How to Buy:**\n\n1. Click **Purchase Key** and select your duration.\n2. Scan the generated QR code using GPay, PhonePe, or Paytm.\n3. Complete the payment.\n4. Your key and loader download link will be delivered instantly upon payment verification!",
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

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("cancel_"):
        order_id = data.replace("cancel_", "")
        if order_id in active_checkout_sessions:
            del active_checkout_sessions[order_id]
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception as e:
            print("Error deleting cancelled QR message:", e)
        bot.answer_callback_query(call.id, "❌ Payment cancelled and QR removed.")
        return

    if data.startswith("dl_key_"):
        key_str = data.replace("dl_key_", "")
        user_id = call.from_user.id
        
        if key_str not in user_purchased_keys.get(user_id, []):
            bot.answer_callback_query(call.id, "❌ Key not found in your account!", show_alert=True)
            return
            
        rem = user_key_downloads.get((user_id, key_str), 2)
        if rem <= 0:
            bot.answer_callback_query(call.id, "❌ Download limit reached (0/2) for this key!", show_alert=True)
            return
            
        user_key_downloads[(user_id, key_str)] = rem - 1
        new_rem = rem - 1
        
        bot.answer_callback_query(call.id, f"✅ Download authorized! ({new_rem}/2 left)")
        
        link_markup = InlineKeyboardMarkup()
        link_markup.add(InlineKeyboardButton("📥 Click Here to Download APK", url=LOADER_APK_LINK))
        
        bot.send_message(
            chat_id,
            f"🚀 **Xscilent Loader APK Download**\n\n"
            f"🔑 Key: `{key_str}`\n"
            f"📊 Remaining Downloads for this key: **{new_rem}/2**\n\n"
            f"Click the button below to download your file:",
            reply_markup=link_markup,
            parse_mode="Markdown"
        )
        return

    if data.startswith("buy_"):
        product_name, price = get_product_details(data)
        file_path = get_file_path_for_product(data)
        
        if file_path:
            keys, _ = fetch_keys_from_github(file_path)
            if not keys:
                alert_owner_out_of_stock(product_name)
                
                bot.answer_callback_query(call.id, "❌ Out of Stock!", show_alert=True)
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                bot.send_message(
                    chat_id,
                    f"❌ **Out of Stock!**\n\nSorry, **{product_name}** is currently out of stock on GitHub. The owner has been alerted with an alarm. Please check back later!",
                    parse_mode="Markdown"
                )
                return

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
            
        cancel_markup = InlineKeyboardMarkup()
        cancel_markup.add(InlineKeyboardButton("❌ Cancel Payment", callback_data=f"cancel_{order_id}"))

        sent_msg = bot.send_photo(
            chat_id,
            photo=bio,
            caption=f"💳 **Checkout Session Created!**\n\n"
                    f"📦 Product: `{product_name}`\n"
                    f"💰 Amount: **₹{price}**\n\n"
                    f"📱 **Scan the QR code above** using GPay, PhonePe, or Paytm to pay instantly.\n\n"
                    f"⚡ Once paid, MacroDroid will instantly notify this bot and your key & download link will be delivered automatically!",
            reply_markup=cancel_markup,
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
    return "Xscilent Loader Bot is running successfully!"

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
    global total_collection
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
                product_code = session["product_code"]
                price = session["price"]
                file_path = get_file_path_for_product(product_code)
                
                if file_path:
                    keys, _ = fetch_keys_from_github(file_path)
                    if keys:
                        delivered_key = keys[0]
                        success = remove_key_from_github(file_path, delivered_key)
                        
                        if success:
                            if user_id not in user_purchased_keys:
                                user_purchased_keys[user_id] = []
                            user_purchased_keys[user_id].append(delivered_key)
                            
                            user_key_downloads[(user_id, delivered_key)] = 2

                            total_collection += price
                            
                            username_str = f"ID:{user_id}"
                            try:
                                chat_info = bot.get_chat(user_id)
                                if chat_info.username:
                                    username_str = f"@{chat_info.username}"
                            except Exception:
                                pass

                            buyer_records.append({
                                "user_id": user_id,
                                "username": username_str,
                                "product": product_name,
                                "price": price,
                                "key": delivered_key,
                                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                            })

                            try:
                                bot.delete_message(chat_id=user_id, message_id=session["message_id"])
                            except Exception as del_err:
                                print("Could not delete QR message:", del_err)
                            
                            bot.send_message(
                                user_id,
                                f"✅ **Payment Verified & Key Delivered!**\n\n"
                                f"📦 Product: `{product_name}`\n"
                                f"🔑 Your Key:\n`{delivered_key}`\n\n"
                                f"(You can view your keys and download links anytime using 'My Keys' in the menu)",
                                parse_mode="Markdown"
                            )
                            
                            try:
                                link_markup = InlineKeyboardMarkup()
                                link_markup.add(InlineKeyboardButton("📥 Download Xscilent Loader APK (2/2 left)", callback_data=f"dl_key_{delivered_key}"))
                                bot.send_message(
                                    user_id,
                                    "🚀 **Loader App Download:**\n\n"
                                    "Click the button below to download your loader application (Allowed: 2 times):",
                                    reply_markup=link_markup,
                                    parse_mode="Markdown"
                                )
                            except Exception as msg_err:
                                print("Error sending download link messages:", msg_err)

                            del active_checkout_sessions[matched_order_id]
                            return jsonify({"status": "success", "message": "Key and link delivered"}), 200
                    else:
                        alert_owner_out_of_stock(product_name)
                        bot.send_message(
                            user_id,
                            f"⚠️ Payment received for **{product_name}**, but keys are currently out of stock on GitHub! The owner has been alerted with an alarm.",
                            parse_mode="Markdown"
                        )
                        
        return jsonify({"status": "received"}), 200
    except Exception as error:
        print("Webhook error:", error)
        return jsonify({"error": str(error)}), 200

if __name__ == '__main__':
    try:
        bot.set_my_short_description("Get instant keys & files for Xscilent Loader!")
        bot.set_my_description("Welcome to Xscilent Bot! Purchase instant keys and download the loader securely.")
    except Exception as e:
        print("Could not update bot descriptions:", e)

    webhook_url = f"{RENDER_URL}/bot/{TOKEN}"
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url)
    print(f"🔗 Telegram Webhook set to: {webhook_url}")

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
