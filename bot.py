# -*- coding: utf-8 -*-
import telebot
import requests
import time
import json
import io
import html
import re
import sqlite3
import os
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== CONFIG ====================
BOT_TOKEN = "8867059811:AAFh4UYL1ZjxWiMiYoIdQGRkaEig6Jsioh4"
ADMIN_ID = 8248049273

# Global Variable for Bot Status
is_bot_active = True

# ==================== DATABASE SETUP ====================
conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# Config table
cursor.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('gbs_api_url', 'https://admin.gbssystems.com/public/api/v1/api.php')")
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('gbs_api_key', 'CKHB7')")

# Default Buttons ke API Commands
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cmd_number', 'number')")
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cmd_family', 'family')")
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cmd_rc', 'rc')")
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cmd_v2n', 'v2n')")
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cmd_vehiclechallan', 'vehiclechallan')")
cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('cmd_numtoupi', 'numtoupi')")

# Custom Buttons table
cursor.execute('''CREATE TABLE IF NOT EXISTS custom_buttons (
    label TEXT PRIMARY KEY,
    cmd TEXT,
    prompt TEXT,
    regex TEXT
)''')

# Users table
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    daily_searches INTEGER DEFAULT 0,
    last_reset_date TEXT DEFAULT ''
)''')
conn.commit()

def get_config(key):
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = c.fetchone()
    c.close()
    return row[0] if row else ""

def set_config(key, value):
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    c.close()

def get_custom_buttons():
    c = conn.cursor()
    c.execute("SELECT label, cmd, prompt, regex FROM custom_buttons")
    rows = c.fetchall()
    c.close()
    return rows

def add_custom_button(label, cmd, prompt, regex=""):
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO custom_buttons (label, cmd, prompt, regex) VALUES (?, ?, ?, ?)", (label, cmd, prompt, regex))
    conn.commit()
    c.close()

def get_all_users():
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    c.close()
    return [r[0] for r in rows]

# ==================== AUTO RESTART FUNCTION ====================
def restart_bot():
    bot.send_message(ADMIN_ID, "🔄 <b>Bot Restarting...</b>\nNaya button add ho gaya hai. 2 second mein bot wapas online hoga.", parse_mode='HTML')
    time.sleep(2)
    print("🔄 Restarting Bot...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

# ==================== LIMIT CHECKER ====================
def check_and_increment_limit(user_id):
    if user_id == ADMIN_ID:
        return True, "Admin Unlimited"

    today = datetime.now().date().isoformat()
    c = conn.cursor()
    c.execute("SELECT daily_searches, last_reset_date FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        c.execute("INSERT INTO users (user_id, daily_searches, last_reset_date) VALUES (?, 1, ?)", (user_id, today))
        conn.commit()
        c.close()
        return True, "1/5"
        
    daily, last_date = row
    
    if last_date != today:
        c.execute("UPDATE users SET daily_searches = 1, last_reset_date = ? WHERE user_id = ?", (today, user_id))
        conn.commit()
        c.close()
        return True, "1/5"
        
    if daily >= 5:
        c.close()
        return False, "Limit Exceeded"
        
    c.execute("UPDATE users SET daily_searches = daily_searches + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    c.close()
    return True, f"{daily + 1}/5"

# ==================== BOT INIT ====================
bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}
temp_data = {}
admin_add_data = {}

# ==================== FORMATTERS ====================
def format_number_info(data):
    lines = ["📱 <b>NUMBER LOOKUP RESULT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not isinstance(data, dict) or ('result' not in data and 'status' not in data):
        return "❌ API Error: Server se sahi response nahi mila."
    results = data.get('result', [])
    if not results: return "❌ No data found for this number."
    lines.append(f"📊 <b>SUMMARY:</b> {len(results)} RECORD(S) FOUND\n")
    for idx, rec in enumerate(results, 1):
        lines.append(f"━━━ <b>RECORD {idx}</b> ━━━")
        fields = [('aadhar', '🆔 Aadhar'), ('name', '👤 Name'), ('mobile', '📱 Mobile'),
                  ('alternate_mobile', '📞 Alt Mobile'), ('father_name', "👨‍👦 Father's Name"),
                  ('circle', '🌐 Circle'), ('address', '📍 Address'), ('email', '📧 Email')]
        for key, label in fields:
            val = rec.get(key)
            if val and str(val).strip() not in ['NA', 'N/A', 'null', '', 'None']:
                lines.append(f"{label}: <b>{html.escape(str(val))}</b>")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_family_info(data):
    lines = ["👨‍👩‍👧‍👦 <b>FAMILY LOOKUP RESULT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not data.get('success') and not data.get('details'): return "❌ No family data found."
    aadhar, rc = data.get('aadhaar', 'N/A'), data.get('rationCardNumber', 'N/A')
    pd = data.get('details', {}).get('pd', {})
    lines.append(f"🆔 <b>Aadhar:</b> {html.escape(str(aadhar))}")
    lines.append(f"💳 <b>Ration Card:</b> {html.escape(str(rc))}")
    if pd.get('homeStateName'): lines.append(f"🏛️ <b>State:</b> {html.escape(str(pd.get('homeStateName')))}")
    if pd.get('homeDistName'): lines.append(f"🏙️ <b>District:</b> {html.escape(str(pd.get('homeDistName')))}")
    if pd.get('address'): lines.append(f"📍 <b>Address:</b> {html.escape(str(pd.get('address')))}")
    if pd.get('fpsId'): lines.append(f"🏪 <b>FPS ID:</b> {html.escape(str(pd.get('fpsId')))}")
    if pd.get('schemeName'): lines.append(f"📋 <b>Scheme:</b> {html.escape(str(pd.get('schemeName')))}")
    members = pd.get('memberDetailsList', [])
    if members:
        lines.append(f"\n👥 <b>FAMILY MEMBERS ({len(members)})</b>")
        for idx, mem in enumerate(members, 1):
            lines.append(f"━━━ <b>MEMBER {idx}</b> ━━━")
            if mem.get('memberName'): lines.append(f"👤 <b>Name:</b> {html.escape(str(mem.get('memberName')))}")
            if mem.get('releationship_name'): lines.append(f"🔗 <b>Relation:</b> {html.escape(str(mem.get('releationship_name')))}")
            if mem.get('uid'): lines.append(f"✅ <b>Aadhar Linked:</b> {html.escape(str(mem.get('uid')))}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_vehicle_rc(data):
    lines = ["🚗 <b>VEHICLE RC DETAILS</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not data.get('status'): return "❌ No vehicle data found."
    d = data.get('data', {})
    fields = [('reg_no', '🔢 Registration No'), ('status', '📌 Status'), ('owner_name', '👤 Owner Name'),
              ('father_name', "👨‍👦 Father's Name"), ('owner_sr_no', '📋 Owner Serial'), ('rto', '🏛️ RTO'),
              ('regn_dt', '📅 Reg Date'), ('vehicle_age', '⏳ Vehicle Age'), ('maker', '🏭 Maker'),
              ('maker_modal', '🚘 Model'), ('vh_class', '🚙 Vehicle Class'), ('fuel_type', '⛽ Fuel Type'),
              ('fuel_norms', '📊 Fuel Norms'), ('vehicle_color', '🎨 Color'), ('chasi_no', '🔧 Chassis No'),
              ('engine_no', '⚙️ Engine No'), ('cubic_cap', '📏 Cubic Cap'), ('number_of_seat', '💺 Seating Capacity'),
              ('fitness_upto', '📋 Fitness Upto'), ('tax_upto', '💰 Tax Upto'), ('insurance_company', '🏢 Insurance Co'),
              ('insurance_upto', '📅 Insurance Upto'), ('insurance_no', '📄 Policy No'), ('puc_upto', '🔬 PUC Upto'),
              ('financer_name', '🏦 Financier Name'), ('noc_details', '📝 NOC Details'), ('blacklist_details', '🚫 Blacklist Details')]
    for key, label in fields:
        val = d.get(key)
        if val and str(val).strip() not in ['NA', 'N/A', 'null', '']:
            lines.append(f"{label}: <b>{html.escape(str(val))}</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_v2n(data):
    lines = ["🚗 <b>VEHICLE TO NUMBER RESULT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not data.get('success') or not data.get('data'): return "❌ No data found for this vehicle."
    d = data.get('data', {})
    reg_no = d.get('registration') or data.get('registration')
    fields = [('Registration No', reg_no, '🔢'), ('Owner Name', d.get('owner'), '👤'), ('Mobile Number', d.get('mobile'), '📱'),
              ('Father Name', d.get('owner_father_name'), '👨‍👦'), ('RTO Name', d.get('rto_name'), '🏛️'), ('RTO Code', d.get('rto_code'), '📌'),
              ('Registration Date', d.get('reg_date'), '📅'), ('Vehicle Class', d.get('vehicle_class'), '🚙'),
              ('Manufacturer', d.get('manufacturer'), '🏭'), ('Model', d.get('model'), '🚘'), ('Variant', d.get('variant'), '⚙️'),
              ('Fuel Type', d.get('fuel_type'), '⛽'), ('Cubic Capacity', d.get('cubic_capacity'), '📏'),
              ('Seat Capacity', d.get('seat_capacity'), '💺'), ('Color', d.get('color'), '🎨'), ('Chassis No', d.get('chassis'), '🔧'),
              ('Engine No', d.get('engine'), '⚙️'), ('Financer Name', d.get('financer_name'), '🏦'),
              ('Insurance Company', d.get('insurance_company'), '🏢'), ('Insurance Upto', d.get('insurance_upto'), '📅'),
              ('PUCC Number', d.get('pucc_number'), '🔬'), ('PUCC Upto', d.get('pucc_valid_upto'), '📅'),
              ('Present Address', d.get('present_address'), '📍'), ('Permanent Address', d.get('permanent_address'), '🏠'), ('Source', d.get('source'), '🌐')]
    for label, val, emoji in fields:
        if val and str(val).strip() not in ['NA', 'N/A', 'null', '', 'None', '0']:
            lines.append(f"{emoji} <b>{label}:</b> {html.escape(str(val))}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_challan(data):
    lines = ["🚦 <b>VEHICLE CHALLAN RESULT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if not data.get('ok'): return "❌ No data found."
    rc = data.get('rc', 'N/A')
    challans = data.get('data', [])
    lines.append(f"🔢 <b>Vehicle No:</b> {html.escape(str(rc))}")
    lines.append(f"📋 <b>Total Challans:</b> {len(challans)}")
    if not challans:
        lines.append("\n✅ <b>No challans found for this vehicle!</b>")
        return "\n".join(lines)
    for idx, ch in enumerate(challans[:10], 1):
        lines.append(f"\n━━━ <b>CHALLAN {idx}</b> ━━━")
        if ch.get('challan_number'): lines.append(f"🔢 <b>Challan No:</b> {html.escape(str(ch.get('challan_number')))}")
        if ch.get('challan_date'): lines.append(f"📅 <b>Date:</b> {str(ch.get('challan_date'))[:10]}")
        if ch.get('offense_details'): lines.append(f"⚖️ <b>Offense:</b> {html.escape(str(ch.get('offense_details'))[:100])}")
        if ch.get('challan_place'): lines.append(f"📍 <b>Place:</b> {html.escape(str(ch.get('challan_place'))[:80])}")
        if ch.get('state'): lines.append(f"🏛️ <b>State:</b> {html.escape(str(ch.get('state')))}")
        if ch.get('amount'): lines.append(f"💰 <b>Amount:</b> ₹{ch.get('amount')}")
        if ch.get('challan_status'): lines.append(f"📌 <b>Status:</b> {html.escape(str(ch.get('challan_status')))}")
        if ch.get('challan_category'): lines.append(f"📂 <b>Category:</b> {html.escape(str(ch.get('challan_category')))}")
    if len(challans) > 10: lines.append(f"\n<i>... and {len(challans) - 10} more challans</i>")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_num_to_upi(data):
    lines = ["📲 <b>NUMBER TO UPI RESULT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    if data.get('status') != 'success': return "❌ No UPI data found for this number."
    d = data.get('data', {})
    bank_name = d.get('bankNameStringId', '').replace('payselect_netBanking_', '').replace('payselect_', '')
    is_merchant = d.get('isMerchant') or d.get('merchant')
    fields = [('Phone Number', data.get('phone'), '📱'), ('Holder Name', data.get('holder_name'), '👤'),
              ('UPI ID (VPA)', data.get('vpa'), '💳'), ('Valid VPA', "✅ Yes" if d.get('validVpa') else "❌ No", '✔️'),
              ('Bank Name', bank_name or 'N/A', '🏦'), ('Is Merchant', "✅ Yes" if is_merchant else "❌ No", '🏪')]
    for label, val, emoji in fields:
        if val and str(val).strip() not in ['NA', 'N/A', 'null', '', 'None']:
            lines.append(f"{emoji} <b>{label}:</b> {html.escape(str(val))}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

# 🔥 SMART FORMATTER (Automatically handles any JSON response)
def format_generic_json(data):
    lines = ["🔍 <b>API RESPONSE RESULT</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    def process_dict(d, indent=0):
        prefix = "  " * indent
        for k, v in d.items():
            clean_key = html.escape(str(k).replace('_', ' ').title())
            if isinstance(v, dict):
                lines.append(f"{prefix}📁 <b>{clean_key}:</b>")
                process_dict(v, indent + 1)
            elif isinstance(v, list):
                lines.append(f"{prefix}📋 <b>{clean_key}:</b> ({len(v)} items)")
                for i, item in enumerate(v[:5], 1): # Max 5 items
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  ─ Item {i} ─")
                        process_dict(item, indent + 2)
                    else:
                        lines.append(f"{prefix}  • {html.escape(str(item))}")
                if len(v) > 5: lines.append(f"{prefix}  <i>...and {len(v)-5} more</i>")
            else:
                if v and str(v).strip() not in ['NA', 'N/A', 'null', '', 'None']:
                    lines.append(f"{prefix}🔹 <b>{clean_key}:</b> {html.escape(str(v))}")
    if isinstance(data, dict): process_dict(data)
    elif isinstance(data, list):
        lines.append(f"📋 <b>Total Records:</b> {len(data)}")
        for i, item in enumerate(data[:5], 1):
            lines.append(f"\n━━━ <b>RECORD {i}</b> ━━━")
            if isinstance(item, dict): process_dict(item)
            else: lines.append(html.escape(str(item)))
    else: lines.append(html.escape(str(data)))
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

# ==================== KEYBOARDS ====================
def get_main_keyboard(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("📱 NUMBER LOOKUP"), KeyboardButton("👨‍👩‍👧‍👦 FAMILY LOOKUP"))
    kb.add(KeyboardButton("🚗 VEHICLE INFO"), KeyboardButton("🚗 VEH TO NUM"))
    kb.add(KeyboardButton("🚦 VEH CHALLAN"), KeyboardButton("📲 NUM TO UPI"))
    
    custom_btns = get_custom_buttons()
    for btn in custom_btns:
        kb.add(KeyboardButton(btn[0]))
        
    if user_id == ADMIN_ID:
        kb.add(KeyboardButton("⚙️ Admin Panel"))
    return kb

def get_cancel_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(KeyboardButton("↩️ CANCEL"))
    return kb

def get_admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("➕ Add New Button"), KeyboardButton("🔄 Edit Button API"))
    kb.add(KeyboardButton("🔗 Change Main API"), KeyboardButton("🔑 Change API Key"))
    kb.add(KeyboardButton("📢 Broadcast"), KeyboardButton("▶️ Start Bot"))
    kb.add(KeyboardButton("🛑 Stop Bot"), KeyboardButton("🔙 Back to Menu"))
    return kb

def get_footer():
    return "\n🛡️ <b>ID:</b> SAIF ALI"

# ==================== START & ADMIN ====================
@bot.message_handler(commands=['start'])
def start_cmd(m):
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,))
    conn.commit()
    c.close()

    text = (
        "🔥 <b>WELCOME TO OSINT BOT</b> 🔥\n\n"
        "💎 <i>Free Users: 5 Searches/Day</i>\n"
        "⚡ <i>Fast & Secure API</i>\n\n"
        "🃏 <b>Menu Options</b>\n"
        "😋 Choose an option from the keyboard below:\n\n"
        "🛡️ <b>Admin:</b> SAIF ALI"
    )
    bot.send_message(m.chat.id, text, parse_mode='HTML')
    bot.send_message(m.chat.id, "👇 <b>Tap a button below to start:</b>", reply_markup=get_main_keyboard(m.from_user.id), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel" and m.from_user.id == ADMIN_ID)
def admin_panel(m):
    user_states[m.from_user.id] = None
    text = "⚙️ <b>ADMIN PANEL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSelect an option below:"
    bot.send_message(m.chat.id, text, reply_markup=get_admin_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🔙 Back to Menu" and m.from_user.id == ADMIN_ID)
def back_menu_admin(m):
    user_states[m.from_user.id] = None
    bot.send_message(m.chat.id, "👇 Main Menu:", reply_markup=get_main_keyboard(m.from_user.id))

# ==================== ADMIN: START / STOP BOT ====================
@bot.message_handler(func=lambda m: m.text == "🛑 Stop Bot" and m.from_user.id == ADMIN_ID)
def stop_bot(m):
    global is_bot_active
    is_bot_active = False
    bot.send_message(m.chat.id, "🛑 <b>Bot is now STOPPED.</b>\nNormal users cannot search now.", reply_markup=get_admin_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "▶️ Start Bot" and m.from_user.id == ADMIN_ID)
def start_bot(m):
    global is_bot_active
    is_bot_active = True
    bot.send_message(m.chat.id, "▶️ <b>Bot is now STARTED.</b>\nAll users can search again.", reply_markup=get_admin_keyboard(), parse_mode='HTML')

# ==================== ADMIN: EDIT API FLOW ====================
@bot.message_handler(func=lambda m: m.text == "🔄 Edit Button API" and m.from_user.id == ADMIN_ID)
def edit_api_start(m):
    default_btns = [
        ("📱 NUMBER LOOKUP", "cmd_number"),
        ("👨‍👩‍👧‍👦 FAMILY LOOKUP", "cmd_family"),
        ("🚗 VEHICLE INFO", "cmd_rc"),
        ("🚗 VEH TO NUM", "cmd_v2n"),
        ("🚦 VEH CHALLAN", "cmd_vehiclechallan"),
        ("📲 NUM TO UPI", "cmd_numtoupi")
    ]
    custom_btns = get_custom_buttons()
    
    kb = InlineKeyboardMarkup(row_width=2)
    for label, key in default_btns:
        kb.add(InlineKeyboardButton(label, callback_data=f"editdef_{key}"))
    
    for btn in custom_btns:
        kb.add(InlineKeyboardButton(btn[0], callback_data=f"editcus_{btn[0]}"))
    
    bot.send_message(m.chat.id, "🔄 <b>Select the button whose API you want to change:</b>", reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('editdef_') and call.from_user.id == ADMIN_ID)
def edit_def_api_callback(call):
    key = call.data.split('_', 1)[1]
    user_states[call.from_user.id] = f"edit_def_api_{key}"
    bot.edit_message_text(f"📝 <b>Send new API Command (cmd) or Full URL for this feature:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='HTML')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('editcus_') and call.from_user.id == ADMIN_ID)
def edit_cus_api_callback(call):
    label = call.data.split('_', 1)[1]
    user_states[call.from_user.id] = f"edit_cus_api_{label}"
    bot.edit_message_text(f"📝 <b>Send new API Command (cmd) or Full URL for '{label}':</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='HTML')
    bot.answer_callback_query(call.id)

# ==================== ADMIN: BROADCAST FLOW ====================
@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and m.from_user.id == ADMIN_ID)
def broadcast_start(m):
    user_states[m.from_user.id] = "admin_broadcast"
    bot.send_message(m.chat.id, "📢 <b>Send the message you want to broadcast:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "admin_broadcast" and m.from_user.id == ADMIN_ID, content_types=['text', 'photo', 'video', 'document', 'animation'])
def process_broadcast(m):
    if m.text and m.text.strip() == "↩️ CANCEL":
        user_states[m.from_user.id] = None
        return bot.send_message(m.chat.id, "❌ Broadcast Cancelled.", reply_markup=get_admin_keyboard())
        
    user_states[m.from_user.id] = None
    status_msg = bot.send_message(m.chat.id, "⏳ <b>Broadcasting started...</b>", parse_mode='HTML')
    
    users = get_all_users()
    success, failed = 0, 0
    
    for uid in users:
        try:
            bot.copy_message(chat_id=uid, from_chat_id=m.chat.id, message_id=m.message_id)
            success += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
            
    bot.edit_message_text(f"✅ <b>Broadcast Completed!</b>\n\n👥 Total Users: {len(users)}\n✅ Sent: {success}\n❌ Failed: {failed}", chat_id=m.chat.id, message_id=status_msg.message_id, parse_mode='HTML')
    bot.send_message(m.chat.id, "⚙️ <b>Admin Panel</b>", reply_markup=get_admin_keyboard(), parse_mode='HTML')

# ==================== ADMIN: ADD NEW BUTTON FLOW (Auto Restart) ====================
@bot.message_handler(func=lambda m: m.text == "➕ Add New Button" and m.from_user.id == ADMIN_ID)
def add_btn_step1(m):
    user_states[m.from_user.id] = "admin_add_btn_name"
    bot.send_message(m.chat.id, "📝 <b>Step 1/3: Send Button Name</b>\n\n<i>(Example: 🆔 PAN LOOKUP)</i>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) in ["admin_add_btn_name", "admin_add_btn_api", "admin_add_btn_prompt"] and m.from_user.id == ADMIN_ID)
def process_add_btn(m):
    uid = m.from_user.id
    state = user_states.get(uid)
    text = m.text.strip()
    
    if text == "↩️ CANCEL":
        user_states[uid] = None
        return bot.send_message(m.chat.id, "❌ Cancelled.", reply_markup=get_admin_keyboard())
        
    if state == "admin_add_btn_name":
        admin_add_data[uid] = {'label': text}
        user_states[uid] = "admin_add_btn_api"
        bot.send_message(m.chat.id, "📝 <b>Step 2/3: Send API URL or CMD</b>\n\n<i>(Example: https://.../api.php?query=... ya sirf 'pan2')</i>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')
        
    elif state == "admin_add_btn_api":
        admin_add_data[uid]['api'] = text
        user_states[uid] = "admin_add_btn_prompt"
        bot.send_message(m.chat.id, "📝 <b>Step 3/3: Send Input Prompt</b>\n\n<i>(Example: Send PAN number:)</i>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')
        
    elif state == "admin_add_btn_prompt":
        prompt = text
        data = admin_add_data.get(uid, {})
        
        if data.get('label') and data.get('api'):
            add_custom_button(data['label'], data['api'], prompt)
            user_states[uid] = None
            admin_add_data.pop(uid, None)
            
            # 🔥 AUTO RESTART
            restart_bot()
        else:
            bot.send_message(m.chat.id, "❌ Error adding button.", reply_markup=get_admin_keyboard())

# ==================== ADMIN: CHANGE API URL/KEY ====================
@bot.message_handler(func=lambda m: m.text == "🔗 Change Main API" and m.from_user.id == ADMIN_ID)
def change_api_url(m):
    user_states[m.from_user.id] = "waiting_new_api_url"
    bot.send_message(m.chat.id, "🔗 <b>Send new API Base URL:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🔑 Change API Key" and m.from_user.id == ADMIN_ID)
def change_api_key(m):
    user_states[m.from_user.id] = "waiting_new_api_key"
    bot.send_message(m.chat.id, "🔑 <b>Send new API Key:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) in ["waiting_new_api_url", "waiting_new_api_key"] and m.from_user.id == ADMIN_ID)
def process_api_change(m):
    uid = m.from_user.id
    state = user_states.get(uid)
    text = m.text.strip()
    
    if text == "↩️ CANCEL":
        user_states[uid] = None
        return bot.send_message(m.chat.id, "❌ Cancelled.", reply_markup=get_admin_keyboard())
        
    if state == "waiting_new_api_url":
        set_config('gbs_api_url', text)
        user_states[uid] = None
        bot.send_message(m.chat.id, "✅ <b>API URL Updated!</b>", reply_markup=get_admin_keyboard(), parse_mode='HTML')
        
    elif state == "waiting_new_api_key":
        set_config('gbs_api_key', text)
        user_states[uid] = None
        bot.send_message(m.chat.id, "✅ <b>API Key Updated!</b>", reply_markup=get_admin_keyboard(), parse_mode='HTML')

# ==================== BUTTON HANDLERS (Default) ====================
@bot.message_handler(func=lambda m: m.text == "📱 NUMBER LOOKUP")
def number_lookup_btn(m):
    user_states[m.from_user.id] = "waiting_number"
    bot.send_message(m.chat.id, "📱 <b>NUMBER LOOKUP</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>Send a 10-digit phone number:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "👨‍👩‍👧‍👦 FAMILY LOOKUP")
def family_lookup_btn(m):
    user_states[m.from_user.id] = "waiting_family"
    bot.send_message(m.chat.id, "👨‍👩‍👧‍👦 <b>FAMILY LOOKUP</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>Send a 12-digit Aadhar number:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🚗 VEHICLE INFO")
def vehicle_lookup_btn(m):
    user_states[m.from_user.id] = "waiting_vehicle"
    bot.send_message(m.chat.id, "🚗 <b>VEHICLE INFO</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>Send a vehicle number:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🚗 VEH TO NUM")
def v2n_lookup_btn(m):
    user_states[m.from_user.id] = "waiting_v2n"
    bot.send_message(m.chat.id, "🚗 <b>VEHICLE TO NUMBER</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>Send a vehicle number:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "🚦 VEH CHALLAN")
def challan_lookup_btn(m):
    user_states[m.from_user.id] = "waiting_challan"
    bot.send_message(m.chat.id, "🚦 <b>VEHICLE CHALLAN</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>Send a vehicle number:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "📲 NUM TO UPI")
def numtoupi_lookup_btn(m):
    user_states[m.from_user.id] = "waiting_numtoupi"
    bot.send_message(m.chat.id, "📲 <b>NUMBER TO UPI</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⚠️ <b>Send a 10-digit phone number:</b>", reply_markup=get_cancel_keyboard(), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "↩️ CANCEL")
def cancel_btn(m):
    user_states[m.from_user.id] = None
    bot.send_message(m.chat.id, "❌ <b>Search Cancelled.</b>", reply_markup=get_main_keyboard(m.from_user.id), parse_mode='HTML')

# ==================== DYNAMIC INPUT HANDLERS ====================
@bot.message_handler(func=lambda m: True)
def dynamic_input_router(m):
    uid = m.from_user.id
    text = m.text.strip() if m.text else ""
    state = user_states.get(uid)

    if not is_bot_active and uid != ADMIN_ID:
        if text in ["📱 NUMBER LOOKUP", "👨‍👩‍👧‍👦 FAMILY LOOKUP", "🚗 VEHICLE INFO", "🚗 VEH TO NUM", "🚦 VEH CHALLAN", "📲 NUM TO UPI"]:
            return bot.send_message(m.chat.id, "⚠️ <b>Bot is currently under maintenance.</b>\nPlease try again later.", parse_mode='HTML')
        custom_btns = get_custom_buttons()
        is_custom_btn = any(text == btn[0] for btn in custom_btns)
        if is_custom_btn:
            return bot.send_message(m.chat.id, "⚠️ <b>Bot is currently under maintenance.</b>\nPlease try again later.", parse_mode='HTML')

    if state and state.startswith("edit_def_api_"):
        key = state.split("edit_def_api_")[1]
        new_cmd = text
        if new_cmd == "↩️ CANCEL":
            user_states[uid] = None
            return bot.send_message(m.chat.id, "❌ Cancelled.", reply_markup=get_admin_keyboard())
        
        set_config(key, new_cmd)
        user_states[uid] = None
        return bot.send_message(m.chat.id, f"✅ <b>API Command updated successfully to '{new_cmd}'!</b>", reply_markup=get_admin_keyboard(), parse_mode='HTML')

    if state and state.startswith("edit_cus_api_"):
        label = state.split("edit_cus_api_")[1]
        new_cmd = text
        if new_cmd == "↩️ CANCEL":
            user_states[uid] = None
            return bot.send_message(m.chat.id, "❌ Cancelled.", reply_markup=get_admin_keyboard())

        c = conn.cursor()
        c.execute("UPDATE custom_buttons SET cmd = ? WHERE label = ?", (new_cmd, label))
        conn.commit()
        c.close()

        user_states[uid] = None
        return bot.send_message(m.chat.id, f"✅ <b>API Command for '{label}' successfully changed to '{new_cmd}'!</b>", reply_markup=get_admin_keyboard(), parse_mode='HTML')

    if state and state.startswith("custom_"):
        cmd = state.split("custom_")[1]
        c = conn.cursor()
        c.execute("SELECT label, regex FROM custom_buttons WHERE cmd = ?", (cmd,))
        row = c.fetchone()
        c.close()
        
        if not row: return bot.send_message(m.chat.id, "❌ Button error.")
        label, regex = row
        
        if text == "↩️ CANCEL":
            user_states[uid] = None
            return bot.send_message(m.chat.id, "❌ Cancelled.", reply_markup=get_main_keyboard(uid))
            
        if regex and not re.match(regex, text.upper() if "^[A-Z]" in regex else text):
            return bot.send_message(m.chat.id, "❌ <b>Invalid Format!</b> Try again ya Cancel karein.", reply_markup=get_cancel_keyboard(), parse_mode='HTML')
            
        do_search(m, text, cmd, label, format_generic_json)
        user_states[uid] = None
        return

    if state == "waiting_number":
        if not text.isdigit() or len(text) != 10:
            return bot.send_message(m.chat.id, "❌ Invalid number! 10 digits only.", reply_markup=get_cancel_keyboard())
        do_search(m, text, get_config('cmd_number'), 'Number Lookup', format_number_info)
        
    elif state == "waiting_family":
        if not text.isdigit() or len(text) != 12:
            return bot.send_message(m.chat.id, "❌ Invalid Aadhar! 12 digits only.", reply_markup=get_cancel_keyboard())
        do_search(m, text, get_config('cmd_family'), 'Family Lookup', format_family_info)
        
    elif state == "waiting_vehicle":
        text_up = text.upper().replace(" ", "")
        if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$', text_up):
            return bot.send_message(m.chat.id, "❌ Invalid Vehicle Number!", reply_markup=get_cancel_keyboard())
        do_search(m, text_up, get_config('cmd_rc'), 'Vehicle Info', format_vehicle_rc)
        
    elif state == "waiting_v2n":
        text_up = text.upper().replace(" ", "")
        if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$', text_up):
            return bot.send_message(m.chat.id, "❌ Invalid Vehicle Number!", reply_markup=get_cancel_keyboard())
        do_search(m, text_up, get_config('cmd_v2n'), 'Vehicle to Number', format_v2n)
        
    elif state == "waiting_challan":
        text_up = text.upper().replace(" ", "")
        if not re.match(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$', text_up):
            return bot.send_message(m.chat.id, "❌ Invalid Vehicle Number!", reply_markup=get_cancel_keyboard())
        do_search(m, text_up, get_config('cmd_vehiclechallan'), 'Vehicle Challan', format_challan)
        
    elif state == "waiting_numtoupi":
        if not text.isdigit() or len(text) != 10:
            return bot.send_message(m.chat.id, "❌ Invalid number! 10 digits only.", reply_markup=get_cancel_keyboard())
        do_search(m, text, get_config('cmd_numtoupi'), 'UPI Lookup', format_num_to_upi)
        
    elif state is None:
        custom_btns = get_custom_buttons()
        for btn in custom_btns:
            if text == btn[0]:
                user_states[uid] = f"custom_{btn[1]}"
                return bot.send_message(m.chat.id, btn[2], reply_markup=get_cancel_keyboard(), parse_mode='HTML')
                
        bot.send_message(m.chat.id, "❌ Unknown command.", reply_markup=get_main_keyboard(uid))

# ==================== SEARCH FUNCTION (Smart URL Handler) ====================
def do_search(m, query, cmd, title, formatter):
    uid = m.from_user.id
    chat = m.chat.id
    
    allowed, limit_status = check_and_increment_limit(uid)
    if not allowed:
        return bot.send_message(chat, "❌ <b>Daily Limit Reached!</b>\n\nAap ek din mein sirf <b>5 searches</b> kar sakte hain. Kal dobara try karein.\n\n💎 <i>Admin is unlimited.</i>", reply_markup=get_main_keyboard(uid), parse_mode='HTML')

    start = time.time()
    loading = bot.send_message(chat, f"⏳ <b>Processing {title}...</b>", parse_mode='HTML')
    
    api_url = get_config('gbs_api_url')
    api_key = get_config('gbs_api_key')
    
    try:
        # Smart URL Handling
        if cmd.startswith("http"):
            parsed = urlparse(cmd)
            qs = parse_qs(parsed.query)
            qs['query'] = [query]
            if 'key' not in qs:
                qs['key'] = [api_key]
                
            new_query = urlencode(qs, doseq=True)
            final_url = urlunparse(parsed._replace(query=new_query))
            
            resp = requests.get(final_url, timeout=90)
        else:
            params = {'key': api_key, 'cmd': cmd, 'query': query}
            resp = requests.get(api_url, params=params, timeout=90)
            
        end = time.time()
        
        if resp.status_code == 200:
            try: data = resp.json()
            except: data = {'response': resp.text[:4000]}
            
            formatted = formatter(data)
            response_time = end - start
            
            try: bot.delete_message(chat, loading.message_id)
            except: pass
            
            emoji = "🔥"
            caption = f"{emoji} <b>SAIF OSINT RESULT</b> {emoji}"
            try:
                bot.send_video(chat, video="https://www.image2url.com/r2/default/videos/1786259979579-39550222-56a8-4114-b7b5-ea6e8d2790c4.mp4", caption=caption, parse_mode='HTML', supports_streaming=True)
            except: pass
            
            limit_info = f"\n📊 <b>Search {limit_status}</b>" if uid != ADMIN_ID else ""
            
            final = formatted + f"\n⏱ <b>Response Time:</b> {response_time:.2f} sec" + limit_info + get_footer()
            
            if len(final) > 4096:
                for i in range(0, len(final), 4000): bot.send_message(chat, final[i:i+4000], parse_mode='HTML')
            else:
                bot.send_message(chat, final, parse_mode='HTML')
            
            token = str(time.time())
            temp_data[token] = data
            json_kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📄 VIEW RAW JSON", callback_data=f"json_{token}"))
            bot.send_message(chat, "⚙️ <b>Result Options:</b>", reply_markup=json_kb, parse_mode='HTML')
            
        else:
            try: bot.delete_message(chat, loading.message_id)
            except: pass
            bot.send_message(chat, f"❌ <b>API Error:</b> {resp.status_code}", reply_markup=get_main_keyboard(uid), parse_mode='HTML')
            
    except Exception as e:
        try: bot.delete_message(chat, loading.message_id)
        except: pass
        bot.send_message(chat, f"❌ <b>Error:</b> {str(e)}", reply_markup=get_main_keyboard(uid), parse_mode='HTML')
        
    user_states[uid] = None

# ==================== CALLBACKS ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('json_'))
def json_callback(call):
    token = call.data.split('_', 1)[1]
    data = temp_data.get(token)
    if not data: return bot.answer_callback_query(call.id, "❌ Expired", True)
    
    js = json.dumps(data, indent=2, ensure_ascii=False)
    if len(js) > 4096:
        f = io.BytesIO(js.encode()); f.name = 'result.json'
        bot.send_document(call.message.chat.id, f, caption="📄 Raw JSON Data")
    else:
        bot.send_message(call.message.chat.id, f"```json\n{js}\n```", parse_mode='Markdown')
    
    bot.answer_callback_query(call.id, "✅ JSON Sent!")
    temp_data.pop(token, None)

# ==================== MAIN ====================
if __name__ == '__main__':
    print("🔥 OSINT BOT STARTED (Auto Restart Added)!")
    try: bot.remove_webhook()
    except: pass
    while True:
        try:
            bot.infinity_polling(timeout=30)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(5)
