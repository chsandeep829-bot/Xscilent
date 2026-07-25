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
GITHUB_REPO = os.getenv("GITHUB_REPO")         
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://xscilent.onrender.com")
UPI_VPA = os.getenv("UPI_VPA", "yourname@upi") 
UPI_NAME = os.getenv("UPI_NAME", "Xscilent")  
SUPPORT_CHAT_ID = "-5409271468"
OBB_GROUP_LINK = "https://t.me/c/5409271468/1"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# In-memory storage
active_checkout_sessions = {}  
user_purchased_keys = {}  

# --- GITHUB HELPERS FOR KEYS ---
def get_file_path_for_product(product_code):
    mapping = {
        "buy_loader_5hours": "loader/keys_5h.txt",
        "buy_loader_1day": "loader/keys_1d.txt",
        "buy_loader_3days": "loader/keys_3d.txt",
        "buy_loader_7days": "loader/keys_7d.txt",
        "buy_loader_30days": "loader/keys_30d.txt",
        "buy_loader_season": "loader/keys_season.txt",
        
        "buy_bgmi_5hours": "bgmi/keys_5h.txt",
        "buy_bgmi_1day": "bgmi/keys_1d.txt",
        "buy_bgmi_3days": "bgmi/keys_3d.txt",
        "buy_bgmi_7days": "bgmi/keys_7d.txt",
        "buy_bgmi_30days": "bgmi/keys_30d.txt",
        "buy_bgmi_season": "bgmi/keys_season.txt"
    }
    return mapping.get(product_code)

def get_product_details(product_code):
    cat_prefix = "Xscilent Loader" if "loader" in product_code else "Xscilent Mod BGMI"
    
    if "5hours" in product_code:
        return (f"{cat_prefix} - 5 HOURS", 40.0)
    elif "1day" in product_code:
        return (f"{cat_prefix} - 1 DAY", 100.0)
    elif "3days" in product_code:
        return (f"{cat_prefix} - 3 DAYS", 180.0)
    elif "7days" in product_code:
        return (f"{cat_prefix} - 7 DAYS", 300.0)
    elif "30days" in product_code:
        return (f"{cat_prefix} - 30 DAYS", 800.0)
    elif "season" in product_code:
        return (f"{cat_prefix} - FULL SEASON", 1200.0)
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

def get_products_category_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚀 Xscilent Loader", callback_data="cat_loader"),
        InlineKeyboardButton("🎮 Xscilent Mod BGMI", callback_data="cat_bgmi")
    )
    return markup

def get_duration_menu(category):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("5 Hours - ₹40", callback_data=f"buy_{category}_5hours"),
        InlineKeyboardButton("1 Day - ₹100", callback_data=f"buy_{category}_1day"),
        InlineKeyboardButton("3 Days - ₹180", callback_data=f"buy_{category}_3days"),
        InlineKeyboardButton("7 Days - ₹300", callback_data=f"buy_{category}_7days"),
        InlineKeyboardButton("30 Days - ₹800", callback_data=f"buy_{category}_30days"),
        InlineKeyboardButton("Full Season - ₹1200", callback_data=f"buy_{category}_season")
    )
    markup.add(InlineKeyboardButton("⬅️ Back to Categories", callback_data="back_to_categories"))
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
        "📦 **Select a product category:**",
        reply_markup=get_products_category_menu(),
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

@bot.message_handler(func=lambda message: message.text == "💰 Check Fund")
def handle_check_fund_text(message):
    bot.send_message(message.chat.id, "💰 **Your Account Balance:**\n\n₹0.0 (Direct UPI QR payment mode active)", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📚 How to Buy?")
def handle_how_to_buy_text(message):
    bot.send_message(
        message.chat.id,
        "📚 **How to Buy:**\n\n1. Click **Purchase Key** and select your product & duration.\n2. Scan the generated QR code using GPay, PhonePe, or Paytm.\n3. Complete the payment.\n4. Your key and app files will be delivered instantly upon payment verification!",
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

    if data == "cat_loader":
        bot.edit_message_text(
            "🚀 **Select a plan for Xscilent Loader:**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=get_duration_menu("loader"),
            parse_mode="Markdown"
        )
        return

    elif data == "cat_bgmi":
        bot.edit_message_text(
            "🎮 **Select a plan for Xscilent Mod BGMI:**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=get_duration_menu("bgmi"),
            parse_mode="Markdown"
        )
        return

    elif data == "back_to_categories":
        bot.edit_message_text(
            "📦 **Select a product category:**",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=get_products_category_menu(),
            parse_mode="Markdown"
        )
        return

    elif data.startswith("buy_"):
        product_name, price = get_product_details(data)
        file_path = get_file_path_for_product(data)
        
        if file_path:
            keys, _ = fetch_keys_from_github(file_path)
            if not keys:
                bot.answer_callback_query(call.id, "❌ Out of Stock!", show_alert=True)
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception:
                    pass
                bot.send_message(
                    chat_id,
                    f"❌ **Out of Stock!**\n\nSorry, **{product_name}** is currently out of stock on GitHub. No QR code has been generated. Please check back later!",
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
            
        sent_msg = bot.send_photo(
            chat_id,
            photo=bio,
            caption=f"💳 **Checkout Session Created!**\n\n"
                    f"📦 Product: `{product_name}`\n"
                    f"💰 Amount: **₹{price}**\n\n"
                    f"📱 **Scan the QR code above** using GPay, PhonePe, or Paytm to pay instantly.\n\n"
                    f"⚡ Once paid, MacroDroid will instantly notify this bot and your key & files will be delivered automatically!",
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
    return "Xscilent Bot is running successfully!"

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
                product_code = session["product_code"]
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

                            try:
                                bot.delete_message(chat_id=user_id, message_id=session["message_id"])
                            except Exception as del_err:
                                print("Could not delete QR message:", del_err)
                            
                            # Send Key First
                            bot.send_message(
                                user_id,
                                f"✅ **Payment Verified & Key Delivered!**\n\n"
                                f"📦 Product: `{product_name}`\n"
                                f"🔑 Your Key:\n`{delivered_key}`\n\n"
                                f"(You can view your keys anytime using 'My Keys' in the menu)",
                                parse_mode="Markdown"
                            )
                            
                            # Deliver Files / Group Link based on product type
                            is_loader = "loader" in product_code
                            try:
                                if is_loader:
                                    loader_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/loader.apk"
                                    bot.send_document(user_id, document=loader_url, caption="📥 Here is your Xscilent Loader APK file!")
                                else:
                                    # Send BGMI APK from root repository path
                                    bgmi_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/bgmi.apk"
                                    bot.send_document(user_id, document=bgmi_url, caption="📥 Here is your Xscilent Mod BGMI APK file!")
                                    
                                    # Send OBB Group Link Button using your group ID
                                    obb_markup = InlineKeyboardMarkup()
                                    obb_markup.add(InlineKeyboardButton("📥 Download OBB File in Group", url=OBB_GROUP_LINK))
                                    
                                    bot.send_message(
                                        user_id,
                                        "📦 **BGMI OBB File Download:**\n\n"
                                        "Due to its large size (1.24 GB), the OBB file (`main.21325.com.pubg.imobile.obb`) is available in our official download group.\n\n"
                                        "👉 Click the button below to join the group and download the OBB file:",
                                        reply_markup=obb_markup,
                                        parse_mode="Markdown"
                                    )
                            except Exception as doc_err:
                                print("Error sending document/message:", doc_err)

                            del active_checkout_sessions[matched_order_id]
                            return jsonify({"status": "success", "message": "Key and files delivered"}), 200
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
    try:
        bot.set_my_short_description("Get instant keys & files for Xscilent Loader & BGMI Mod!")
        bot.set_my_description("Welcome to Xscilent Bot! Purchase instant keys and download files securely.")
    except Exception as e:
        print("Could not update bot descriptions:", e)

    webhook_url = f"{RENDER_URL}/bot/{TOKEN}"
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=webhook_url)
    print(f"🔗 Telegram Webhook set to: {webhook_url}")

    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
