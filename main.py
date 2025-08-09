import os
import re
import sys
import time
import random
import threading
import logging
from os import path
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from user_agent import generate_user_agent
import requests

# --------------------------
# تكوين (مضمّن)
# --------------------------
BOT_TOKEN = '8481771881:AAGTGdsf8J1CQORa_vJAe5lpyYHDQQ7aDi0'
CHANNEL_USERNAME = "@CLOVRTOOLS"
YOUTUBE_LINK = "https://www.youtube.com/channel/UCj7TtZr6-7ViVvzVCt0U5SA"

MAX_THREADS = 400
TEST_URL = 'https://httpbin.org/ip'
PROXY_TIMEOUT = 1
CLEAR_CMD = 'cls' if os.name=='nt' else 'clear'
EXPECTED_RESPONSE = '"status_code":0,"status_msg":"Thanks for your feedback"'

# --------------------------
# خريطة أسباب التقرير (نص عربي لكل سبب)
# --------------------------
AR_MENU = {
    1: 'محتوى غير مناسب',
    2: 'بريد مزعج أو تحرش',
    3: 'تحت 13 سنة',
    4: 'معلومات خاطئةوانتحال',
    5: 'خطاب كراهية',
    6: 'محتوى إباحي',
    7: 'منظمات إرهابية',
    8: 'تعريض للنفس للأذى',
    9: 'تحرش أو تنمر',
    10: 'عنف',
    12: 'تقارير عشوائية',
    13: 'تقارير مع بروكسيات',
    14: 'احتيال و عمليات نصب',
    15: 'أفعال خطرة وتحديات',
    16: 'إبلاغ عن سبام'
}

# --------------------------
# إعداد البوت
# --------------------------
bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --------------------------
# حالة المحادثة والبيانات
# --------------------------
user_states = {}  # chat_id -> state
user_data = {}    # chat_id -> dict
running = {}      # chat_id -> threading.Event

# --------------------------
# دوال الاشتراك
# --------------------------

def is_user_subscribed(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "creator", "administrator"]
    except Exception:
        return False


def send_subscription_panel(chat_id, text=None):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔔 اشترك في قناة التيليجرام", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"))
    markup.add(InlineKeyboardButton("▶️ اشترك في اليوتيوب", url=YOUTUBE_LINK))
    markup.add(InlineKeyboardButton("✅ لقد اشتركت", callback_data="check_sub"))
    bot.send_message(chat_id, text or "🔐 للاستخدام: الرجاء الاشتراك في القناة ثم الضغط على (✅ لقد اشتركت)", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub(call):
    bot.answer_callback_query(call.id, "⏳ جارٍ التحقق من الاشتراك...")
    uid = call.from_user.id
    if not is_user_subscribed(uid):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔔 اشترك في قناة التيليجرام", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"))
        markup.add(InlineKeyboardButton("▶️ اشترك في اليوتيوب", url=YOUTUBE_LINK))
        markup.add(InlineKeyboardButton("✅ لقد اشتركت", callback_data="check_sub"))
        try:
            bot.edit_message_text("🚫 لم نتمكن من تأكيد اشتراكك. الرجاء الاشتراك ثم اضغط (✅ لقد اشتركت)", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception:
            send_subscription_panel(call.from_user.id, "🚫 لم نتمكن من تأكيد اشتراكك. الرجاء الاشتراك ثم اضغط (✅ لقد اشتركت)")
        return
    # مشترك
    try:
        bot.edit_message_text("✅ تم التحقق! الآن يمكنك المتابعة.", call.message.chat.id, call.message.message_id)
        # بعد التحقق، عرض قائمة أسباب البلاغ كأزرار عربية
        kb = InlineKeyboardMarkup()
        items = list(AR_MENU.items())
        per_row = 2
        for i in range(0, len(items), per_row):
            buttons = []
            for key, label in items[i:i+per_row]:
                buttons.append(InlineKeyboardButton(f"{key}. {label}", callback_data=f"report_{key}"))
            kb.row(*buttons)
        kb.add(InlineKeyboardButton("إلغاء", callback_data="cancel_all"))
        bot.send_message(uid, "اختر سبب التقرير بالضغط على الزر المناسب:", reply_markup=kb)
    except Exception:
        bot.send_message(uid, "✅ تم التحقق! الآن يمكنك المتابعة.")
        kb = InlineKeyboardMarkup()
        items = list(AR_MENU.items())
        per_row = 2
        for i in range(0, len(items), per_row):
            buttons = []
            for key, label in items[i:i+per_row]:
                buttons.append(InlineKeyboardButton(f"{key}. {label}", callback_data=f"report_{key}"))
            kb.row(*buttons)
        kb.add(InlineKeyboardButton("إلغاء", callback_data="cancel_all"))
        bot.send_message(uid, "اختر سبب التقرير بالضغط على الزر المناسب:", reply_markup=kb)

# --------------------------
# مساعدات البروكسي
# --------------------------

def format_proxy(proxy):
    p = proxy.strip()
    if not any(p.startswith(proto) for proto in ('http://', 'https://', 'socks5://', 'socks4://')):
        return 'http://' + p
    return p


def check_proxy(proxy_url):
    try:
        resp = requests.get(TEST_URL,
                            proxies={'http': format_proxy(proxy_url), 'https': format_proxy(proxy_url)},
                            timeout=PROXY_TIMEOUT)
        return proxy_url, resp.status_code == 200
    except:
        return proxy_url, False


def check_proxies_concurrently(proxy_list):
    working = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
        futures = {ex.submit(check_proxy, p): p for p in proxy_list}
        for f in as_completed(futures):
            p, ok = f.result()
            if ok:
                working.append(format_proxy(p))
    return working

# --------------------------
# إعداد التقرير (كما في النسخة الأصلية)
# --------------------------
REPORT_PARAMS = {
    1: {'reason':'399','reporter_id':'7024230440182809606','device_id':'7008218736944907778'},
    2: {'reason':'310','reporter_id':'27568146','device_id':'7008218736944907778'},
    3: {'reason':'317','reporter_id':'27568146','device_id':'7008218736944907778'},
    4: {'reason':'3142','reporter_id':'6955107540677968897','device_id':'7034110346035136001'},
    5: {'reason':'306','reporter_id':'6955107540677968897','device_id':'7034110346035136001'},
    6: {'reason':'308','reporter_id':'310430566162530304','device_id':'7034110346035136001'},
    7: {'reason':'3011','reporter_id':'310430566162530304','device_id':'7034110346035136001'},
    8: {'reason':'3052','reporter_id':'310430566162530304','device_id':'7034110346035136001'},
    9: {'reason':'3072','reporter_id':'310430566162530304','device_id':'7034110346035136001'},
    10:{'reason':'303','reporter_id':'310430566162530304','device_id':'7034110346035136001'},
    14:{'reason':'9004','reporter_id':'7242379992225940485','device_id':'7449373206865561094'},
    15:{'reason':'90064','reporter_id':'7242379992225940485','device_id':'7449373206865561094'},
    16:{'reason':'9010','reporter_id':'7242379992225940485','device_id':'7449373206865561094'}
}


def get_report(r_type, target_ID, session, proxy_mode=False, proxies=None):
    if r_type in (12, 13):
        r_type = random.choice(list(REPORT_PARAMS.keys()))
    p = REPORT_PARAMS.get(r_type, list(REPORT_PARAMS.values())[0])
    base = 'https://www.tiktok.com/aweme/v1/aweme/feedback/'
    common = (
        '?aid=1233&app_name=tiktok_web&device_platform=web_mobile'
        '&region=SA&priority_region=SA&os=ios&cookie_enabled=true'
        '&screen_width=375&screen_height=667&browser_language=en-US'
        '&browser_platform=iPhone&browser_name=Mozilla'
        '&browser_version=5.0+(iPhone;+CPU+iPhone+OS+15_1+like+Mac+OS+X)'
        '&browser_online=true&app_language=ar&timezone_name=Asia%2FRiyadh'
        '&is_page_visible=true&focus_state=true&is_fullscreen=false'
    )
    url = (
        f"{base}{common}&history_len=14&reason={p['reason']}"
        f"&report_type=user&object_id={target_ID}&owner_id={target_ID}"
        f"&target={target_ID}&reporter_id={p['reporter_id']}"
        "&current_region=SA"
    )
    headers = {
        'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding':'gzip, deflate, br',
        'Accept-Language':'en-US,en;q=0.5',
        'Connection':'keep-alive',
        'Cookie':'sessionid=' + session,
        'Host':'www.tiktok.com',
        'Upgrade-Insecure-Requests':'1',
        'User-Agent': generate_user_agent()
    }
    data = {'object_id':target_ID,'owner_id':target_ID,'report_type':'user','target':target_ID}
    return url, headers, data

# --------------------------
# حلقة التنفيذ للتقارير
# --------------------------

def run_reports(chat_id):
    cfg = user_data[chat_id]
    sessions = cfg['sessions']
    proxies = cfg.get('proxies', [])
    sleep = cfg.get('sleep_time', 1)
    pmode = cfg.get('proxy_mode', False)
    rtype = cfg['report_type']
    tid = cfg['target_id']
    evt = running[chat_id]
    succ = fail = 0
    while not evt.is_set():
        for s in sessions:
            if evt.is_set():
                break
            time.sleep(sleep)
            try:
                url, hd, dt = get_report(rtype, tid, s, pmode, proxies)
                pr = None
                if pmode and proxies:
                    p = random.choice(proxies)
                    pr = {'http': p, 'https': p}
                r = requests.post(url, headers=hd, data=dt, proxies=pr, timeout=5)
                if EXPECTED_RESPONSE in r.text:
                    fail += 1
                else:
                    succ += 1
            except:
                fail += 1
        try:
            bot.send_message(chat_id, f"✔ تم: {succ}  ❌ فشل: {fail}")
        except:
            pass
    try:
        bot.send_message(chat_id, "🛑 تم إيقاف التقرير.")
    except:
        pass

# --------------------------
# تحميل ملفات من المستخدم
# --------------------------

def fetch_file(doc, local_name):
    file_info = bot.get_file(doc.file_id)
    dl = bot.download_file(file_info.file_path)
    with open(local_name, 'wb') as f:
        f.write(dl)
    with open(local_name, 'r', encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip()]

# --------------------------
# واجهات الأوامر (كلها بالعربي وازرار)
# --------------------------

@bot.message_handler(commands=['start'])
def h_start(m):
    send_subscription_panel(m.chat.id)

@bot.message_handler(commands=['report'])
def h_report(m):
    uid = m.from_user.id
    if not is_user_subscribed(uid):
        send_subscription_panel(uid)
        return
    # عرض قائمة الأسباب كأزرار عربية
    kb = InlineKeyboardMarkup()
    row = []
    # نبني أزرار للأسباب (نجمعها بعدد معقول لكل صف)
    items = list(AR_MENU.items())
    per_row = 2
    for i in range(0, len(items), per_row):
        buttons = []
        for key, label in items[i:i+per_row]:
            buttons.append(InlineKeyboardButton(f"{key}. {label}", callback_data=f"report_{key}"))
        kb.row(*buttons)
    kb.add(InlineKeyboardButton("إلغاء", callback_data="cancel_all"))
    bot.send_message(uid, "اختر سبب التقرير بالضغط على الزر المناسب:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith('report_'))
def report_callback(call):
    uid = call.from_user.id
    opt = int(call.data.split('_')[1])
    # تأكد من الاشتراك مرة أخرى
    if not is_user_subscribed(uid):
        send_subscription_panel(uid)
        bot.answer_callback_query(call.id, "🚫 الرجاء الاشتراك أولاً")
        return
    user_data[uid] = user_data.get(uid, {})
    user_data[uid].update({'report_type': opt, 'proxy_mode': opt == 13})
    user_states[uid] = 'sessions'
    bot.answer_callback_query(call.id, f"تم اختيار: {AR_MENU.get(opt, opt)}")
    try:
        bot.edit_message_text(f"✅ تم اختيار: {AR_MENU.get(opt, opt)}\nالآن أرسل الجلسات كملف، نص متعدد الأسطر، أو عدد.", call.message.chat.id, call.message.message_id)
    except Exception:
        bot.send_message(uid, f"✅ تم اختيار: {AR_MENU.get(opt, opt)}\nالآن أرسل الجلسات كملف، نص متعدد الأسطر، أو عدد.")

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_all')
def cancel_cb(call):
    bot.answer_callback_query(call.id, 'تم الإلغاء')
    try:
        bot.edit_message_text('تم إلغاء العملية.', call.message.chat.id, call.message.message_id)
    except:
        bot.send_message(call.from_user.id, 'تم إلغاء العملية.')

# معالجات الحالة (عربية)
@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'sessions')
def h_sessions(m):
    uid = m.from_user.id
    text = m.text or ''
    if m.document:
        sess = fetch_file(m.document, 'sess.txt')
    elif text and '\n' in text:
        sess = [l.strip() for l in text.split('\n') if l.strip()]
    else:
        try:
            cnt = int(text.strip())
            user_data[uid]['sessions'] = []
            user_data[uid]['exp'] = cnt
            user_states[uid] = 'sess_lines'
            return bot.send_message(uid, f'أرسل {cnt} معرف جلسة، رسالة واحدة لكل معرف:')
        except:
            return bot.reply_to(m, 'الرجاء إرسال ملف، نص متعدد الأسطر، أو رقم.')
    user_data[uid]['sessions'] = sess
    user_states[uid] = 'proxies'
    bot.send_message(uid, 'أرسل البروكسيات كملف، نص متعدد الأسطر، أو اكتب "لا"')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'sess_lines')
def h_sess_lines(m):
    uid = m.from_user.id
    user_data[uid]['sessions'].append(m.text.strip())
    if len(user_data[uid]['sessions']) >= user_data[uid]['exp']:
        user_states[uid] = 'proxies'
        bot.send_message(uid, 'أرسل البروكسيات كملف، نص متعدد الأسطر، أو اكتب "لا"')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'proxies')
def h_proxies(m):
    uid = m.from_user.id
    text = m.text or ''
    if m.document:
        pr = fetch_file(m.document, 'pr.txt')
        user_data[uid]['proxies'] = check_proxies_concurrently(pr)
    elif text and text.strip().lower() != 'لا' and '\n' in text:
        pr = [l.strip() for l in text.split('\n') if l.strip()]
        user_data[uid]['proxies'] = check_proxies_concurrently(pr)
    elif text.strip().lower() in ['لا', 'no']:
        user_data[uid]['proxies'] = []
    else:
        return bot.reply_to(m, 'أرسل ملف، نص متعدد الأسطر، أو اكتب "لا"')
    user_states[uid] = 'username'
    bot.send_message(uid, 'الآن أدخل اسم مستخدم TikTok (مثال: @username)')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'username')
def h_user(m):
    uid = m.from_user.id
    if not is_user_subscribed(uid):
        send_subscription_panel(uid)
        return
    u = m.text.strip().lstrip('@')
    resp = requests.get(f'https://www.tiktok.com/@{u}?lang=en',
                        headers={'User-Agent': generate_user_agent()})
    m2 = re.search(r'"user":\{"id":"(\d+)"', resp.text)
    if not m2:
        return bot.reply_to(m, 'المستخدم غير موجود.')
    user_data[uid]['target_id'] = m2.group(1)
    user_states[uid] = 'sleep'
    bot.send_message(uid, 'أدخل زمن الانتظار بين الطلبات (بالثواني):')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'sleep')
def h_sleep(m):
    uid = m.from_user.id
    try:
        user_data[uid]['sleep_time'] = int(m.text.strip())
    except:
        return bot.reply_to(m, 'الرجاء إدخال عدد صحيح.')
    user_states[uid] = 'cont'
    bot.send_message(uid, 'هل التشغيل مستمر؟ اكتب نعم أو لا')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'cont')
def h_cont(m):
    uid = m.from_user.id
    user_data[uid]['continuous'] = m.text.strip().lower().startswith('ن')
    user_states[uid] = 'start'
    bot.send_message(uid, 'اكتب "ابدأ" للبدء أو "إلغاء" للإلغاء')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'start')
def h_start_cmd(m):
    uid = m.from_user.id
    cmd = m.text.strip().lower()
    if cmd in ['إلغاء', 'الغاء', 'cancel']:
        user_states.pop(uid, None)
        user_data.pop(uid, None)
        return bot.reply_to(m, 'تم إلغاء العملية.')
    if cmd not in ['ابدأ', 'ابدأ', 'start', 'start']:
        return bot.reply_to(m, 'الرجاء كتابة "ابدأ" أو "إلغاء"')
    evt = threading.Event()
    running[uid] = evt
    user_states.pop(uid, None)
    thread = threading.Thread(target=run_reports, args=(uid,), daemon=True)
    thread.start()
    bot.reply_to(m, 'تم بدء الإبلاغ. اكتب /stop لإيقاف العملية.')

@bot.message_handler(commands=['stop'])
def h_stop(m):
    uid = m.from_user.id
    if uid in running:
        running[uid].set()
        running.pop(uid, None)
        bot.reply_to(m, 'تم إيقاف التقرير.')
    else:
        bot.reply_to(m, 'لا يوجد شيء يعمل حالياً.')

# --------------------------
# شغّل البوت
# --------------------------
if __name__ == '__main__':
    bot.infinity_polling()
