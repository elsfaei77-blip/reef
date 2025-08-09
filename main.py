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
from user_agent import generate_user_agent
import requests

# --------------------------
# CONFIGURATION (Hard-coded)
# --------------------------
BOT_TOKEN = '8481771881:AAGTGdsf8J1CQORa_vJAe5lpyYHDQQ7aDi0'
MAX_THREADS = 400
TEST_URL = 'https://httpbin.org/ip'
PROXY_TIMEOUT = 1
CLEAR_CMD = 'cls' if os.name=='nt' else 'clear'
EXPECTED_RESPONSE = '"status_code":0,"status_msg":"Thanks for your feedback"'

# --------------------------
# Report Menu
# --------------------------
REPORT_MENU = '''
CHYO
-----------------------------------------------------------
 TikTok Reporter Bot
 
1 - Report Content
-----------------------------------------------------------
2 - Spam or Harassment
-----------------------------------------------------------
3 - Under 13
-----------------------------------------------------------
4 - Fake Information - Alias
-----------------------------------------------------------
5 - Hate Speech
-----------------------------------------------------------
6 - Pornographic
-----------------------------------------------------------
7 - Terrorism Organizations
-----------------------------------------------------------
8 - Self Harm
-----------------------------------------------------------
9 - Harassment or Bullying - Someone I Know
-----------------------------------------------------------
10 - Violence
-----------------------------------------------------------
12 - Random Reports
-----------------------------------------------------------
13 - Random Reports with Proxies
-----------------------------------------------------------
14 - Frauds And Scams
-----------------------------------------------------------
15 - Dangerous and Challenges Acts
-----------------------------------------------------------
16 - Report Spam

'''

# --------------------------
# Color Codes (unused but kept)
# --------------------------
RED = '\033[1;31m'; YELLOW = '\033[1;33m'; GREEN = '\033[2;32m'; CYAN = '\033[2;36m'

# --------------------------
# Telegram Bot Setup
# --------------------------
bot = telebot.TeleBot(BOT_TOKEN)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --------------------------
# Conversational State
# --------------------------
user_states = {}  # chat_id -> state string
user_data = {}    # chat_id -> data dict
running = {}      # chat_id -> threading.Event

# --------------------------
# Proxy Helpers
# --------------------------
def format_proxy(proxy):
    p = proxy.strip()
    if not any(p.startswith(proto) for proto in ('http://','https://','socks5://','socks4://')):
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
# Report Params Mapping
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

# --------------------------
# Build report URL, headers, data
# --------------------------
def get_report(r_type, target_ID, session, proxy_mode=False, proxies=None):
    if r_type in (12, 13):
        r_type = random.choice(list(REPORT_PARAMS.keys()))
    p = REPORT_PARAMS[r_type]
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
# Reporting Loop thread
# --------------------------
def run_reports(chat_id):
    cfg = user_data[chat_id]
    sessions = cfg['sessions']
    proxies = cfg['proxies']
    sleep = cfg['sleep_time']
    pmode = cfg['proxy_mode']
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
        bot.send_message(chat_id, f"Doneâ: {succ}  Badâ: {fail}")
    bot.send_message(chat_id, "ð Reporting stopped.")

# --------------------------
# File Download Helper
# --------------------------
def fetch_file(doc, local_name):
    file_info = bot.get_file(doc.file_id)
    dl = bot.download_file(file_info.file_path)
    with open(local_name, 'wb') as f:
        f.write(dl)
    with open(local_name, 'r', encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip()]

# --------------------------
# Handlers
# --------------------------
@bot.message_handler(commands=['start'])
def h_start(m):
    bot.reply_to(m, "Welcome to TikTok Reporter! Use /report to begin.")

@bot.message_handler(commands=['report'])
def h_report(m):
    uid = m.from_user.id
    user_states[uid] = 'type'
    user_data[uid] = {}
    bot.send_message(uid, REPORT_MENU)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'type')
def h_type(m):
    uid = m.from_user.id
    txt = m.text.strip()
    try:
        opt = int(txt)
        assert opt in [1,2,3,4,5,6,7,8,9,10,12,13,14,15,16]
    except:
        return bot.reply_to(m, 'Invalid option. Please select a number from the menu.')
    user_data[uid].update({'report_type': opt, 'proxy_mode': opt == 13})
    user_states[uid] = 'sessions'
    bot.send_message(uid, 'Send sessions as a file, multiline text, or a single count:')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'sessions')
def h_sessions(m):
    uid = m.from_user.id
    text = m.text
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
            return bot.send_message(uid, f'Send {cnt} session IDs, one per message:')
        except:
            return bot.reply_to(m, 'Please send a file, multiline text, or an integer count.')
    user_data[uid]['sessions'] = sess
    user_states[uid] = 'proxies'
    bot.send_message(uid, 'Send proxies as a file, multiline text, or "no":')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'sess_lines')
def h_sess_lines(m):
    uid = m.from_user.id
    user_data[uid]['sessions'].append(m.text.strip())
    if len(user_data[uid]['sessions']) >= user_data[uid]['exp']:
        user_states[uid] = 'proxies'
        bot.send_message(uid, 'Send proxies as a file, multiline text, or "no":')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'proxies')
def h_proxies(m):
    uid = m.from_user.id
    text = m.text
    if m.document:
        pr = fetch_file(m.document, 'pr.txt')
        user_data[uid]['proxies'] = check_proxies_concurrently(pr)
    elif text and text.lower() != 'no' and '\n' in text:
        pr = [l.strip() for l in text.split('\n') if l.strip()]
        user_data[uid]['proxies'] = check_proxies_concurrently(pr)
    elif text.strip().lower() == 'no':
        user_data[uid]['proxies'] = []
    else:
        return bot.reply_to(m, 'Send a file, multiline text, or "no".')
    user_states[uid] = 'username'
    bot.send_message(uid, 'Enter TikTok username:')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'username')
def h_user(m):
    uid = m.from_user.id
    u = m.text.strip().lstrip('@')
    resp = requests.get(f'https://www.tiktok.com/@{u}?lang=en',
                        headers={'User-Agent': generate_user_agent()})
    m2 = re.search(r'"user":\{"id":"(\d+)"', resp.text)
    if not m2:
        return bot.reply_to(m, 'User not found.')
    user_data[uid]['target_id'] = m2.group(1)
    user_states[uid] = 'sleep'
    bot.send_message(uid, 'Enter sleep time between requests (in seconds):')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'sleep')
def h_sleep(m):
    uid = m.from_user.id
    try:
        user_data[uid]['sleep_time'] = int(m.text.strip())
    except:
        return bot.reply_to(m, 'Please enter an integer.')
    user_states[uid] = 'cont'
    bot.send_message(uid, 'Continuous mode? yes/no')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'cont')
def h_cont(m):
    uid = m.from_user.id
    user_data[uid]['continuous'] = m.text.strip().lower().startswith('y')
    user_states[uid] = 'start'
    bot.send_message(uid, 'Type "start" to begin or "cancel" to abort')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'start')
def h_start_cmd(m):
    uid = m.from_user.id
    cmd = m.text.strip().lower()
    if cmd == 'cancel':
        user_states.pop(uid, None)
        user_data.pop(uid, None)
        return bot.reply_to(m, 'Operation aborted.')
    if cmd != 'start':
        return bot.reply_to(m, 'Please send "start" or "cancel".')
    evt = threading.Event()
    running[uid] = evt
    user_states.pop(uid, None)
    thread = threading.Thread(target=run_reports, args=(uid,), daemon=True)
    thread.start()
    bot.reply_to(m, 'ð¢ Reporting started. Use /stop to end.')

@bot.message_handler(commands=['stop'])
def h_stop(m):
    uid = m.from_user.id
    if uid in running:
        running[uid].set()
        running.pop(uid, None)
        bot.reply_to(m, 'ð Reporting stopped.')
    else:
        bot.reply_to(m, 'Nothing is running.')

# --------------------------
# Run Bot
# --------------------------
if __name__ == '__main__':
    bot.infinity_polling()

