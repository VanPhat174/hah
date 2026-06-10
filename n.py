"""
Tool tự động cày điểm danh dự quân đoàn Free Fire - Guest Account
Yêu cầu: pip install playwright requests fake-useragent
Và: playwright install chromium
"""

import requests
import random
import string
import time
import json
import re
import sys
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from fake_useragent import UserAgent
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

# ==================== CẤU HÌNH ====================
FF_API_BASE = "https://ff.garena.com/api"
GUEST_LOGIN_ENDPOINT = f"{FF_API_BASE}/guest/login"
JOIN_GUILD_ENDPOINT = f"{FF_API_BASE}/guild/join"
GUILD_INFO_ENDPOINT = f"{FF_API_BASE}/guild/info"
GUILD_HONOR_ENDPOINT = f"{FF_API_BASE}/guild/honor"
LEAVE_GUILD_ENDPOINT = f"{FF_API_BASE}/guild/leave"

# Header mặc định
BASE_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "Keep-Alive",
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; SM-G975F Build/RP1A.200720.012)"
}

# ==================== HÀM TIỆN ÍCH ====================
def generate_device_id() -> str:
    """Tạo device_id dạng IMEI 15 số + MAC ảo"""
    imei = ''.join(random.choices(string.digits, k=15))
    mac = ':'.join(random.choices(string.hexdigits.upper(), k=12)[i:i+2] for i in range(0, 12, 2))
    return f"{imei}_{mac}"

def generate_signature(device_id: str, timestamp: int) -> str:
    """Tạo signature giả lập (Garena dùng HMAC-SHA256, đây là placeholder)"""
    import hashlib
    raw = f"{device_id}{timestamp}SALT_KEY"
    return hashlib.sha256(raw.encode()).hexdigest()

def generate_android_id() -> str:
    """Tạo Android ID 16 ký tự hex"""
    return ''.join(random.choices(string.hexdigits.lower(), k=16))

# ==================== API GUEST ACCOUNT ====================
def create_guest_account(proxy: Optional[Dict] = None) -> Optional[Dict]:
    """
    Tạo guest account thông qua API giả lập
    Trả về: {"uid": str, "guest_token": str, "refresh_token": str, "device_id": str}
    """
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    device_id = generate_device_id()
    android_id = generate_android_id()
    timestamp = int(time.time())
    
    headers = BASE_HEADERS.copy()
    ua = UserAgent()
    headers["User-Agent"] = ua.random
    
    payload = {
        "device_id": device_id,
        "android_id": android_id,
        "app_version": "1.112.0",
        "os_version": "Android 11",
        "manufacturer": random.choice(["Samsung", "Xiaomi", "Oppo", "Vivo", "Realme"]),
        "model": random.choice(["SM-G975F", "M2012K11AG", "CPH2219", "RMX3370"]),
        "timestamp": timestamp,
        "signature": generate_signature(device_id, timestamp)
    }
    
    try:
        response = session.post(GUEST_LOGIN_ENDPOINT, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 0 or data.get('success'):
                return {
                    "uid": data.get('uid'),
                    "guest_token": data.get('access_token') or data.get('token'),
                    "refresh_token": data.get('refresh_token'),
                    "device_id": device_id,
                    "android_id": android_id
                }
            else:
                # Thử endpoint thay thế
                alt_payload = {"device_id": device_id, "platform": "android"}
                alt_response = session.post(f"{FF_API_BASE}/guest/register", json=alt_payload, headers=headers, timeout=30)
                if alt_response.status_code == 200:
                    alt_data = alt_response.json()
                    return {
                        "uid": alt_data.get('uid'),
                        "guest_token": alt_data.get('token'),
                        "refresh_token": alt_data.get('refresh_token'),
                        "device_id": device_id,
                        "android_id": android_id
                    }
        return None
    except Exception as e:
        print(f"[!] Lỗi tạo guest account: {e}")
        return None

def refresh_guest_token(refresh_token: str, device_id: str, proxy: Optional[Dict] = None) -> Optional[str]:
    """Làm mới token khi hết hạn"""
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    headers = BASE_HEADERS.copy()
    headers["Authorization"] = f"Bearer {refresh_token}"
    
    payload = {
        "device_id": device_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    try:
        response = session.post(f"{FF_API_BASE}/token/refresh", json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data.get('access_token')
        return None
    except:
        return None

# ==================== API QUÂN ĐOÀN ====================
def get_guild_info(uid: str, token: str, proxy: Optional[Dict] = None) -> Optional[Dict]:
    """Lấy thông tin quân đoàn hiện tại của tài khoản"""
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
    
    try:
        response = session.get(f"{GUILD_INFO_ENDPOINT}?uid={uid}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def join_guild(uid: str, token: str, guild_id: str, proxy: Optional[Dict] = None) -> bool:
    """Gia nhập quân đoàn theo ID"""
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
    payload = {
        "guild_id": guild_id,
        "uid": uid,
        "join_type": "public"
    }
    
    try:
        response = session.post(JOIN_GUILD_ENDPOINT, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data.get('code') == 0 or data.get('success')
        
        # Nếu đã ở guild khác, rời đi rồi join lại
        guild_info = get_guild_info(uid, token, proxy)
        if guild_info and guild_info.get('guild_id'):
            leave_response = session.post(LEAVE_GUILD_ENDPOINT, json={"uid": uid}, headers=headers, timeout=30)
            if leave_response.status_code == 200:
                time.sleep(2)
                return join_guild(uid, token, guild_id, proxy)
        return False
    except:
        return False

def get_honor_points(uid: str, token: str, proxy: Optional[Dict] = None) -> int:
    """Lấy điểm danh dự hiện tại"""
    session = requests.Session()
    if proxy:
        session.proxies = proxy
    
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
    
    try:
        response = session.get(f"{GUILD_HONOR_ENDPOINT}?uid={uid}", headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data.get('honor_points', 0) or data.get('points', 0)
        return 0
    except:
        return 0

# ==================== PLAYWRIGHT AUTOMATION ====================
class FreeFireBot:
    """Bot điều khiển trình duyệt để vào trận sinh tồn"""
    
    def __init__(self, account: Dict, guild_id: str, proxy: Optional[str] = None, headless: bool = True):
        self.uid = account['uid']
        self.token = account['guest_token']
        self.refresh_token = account.get('refresh_token')
        self.device_id = account.get('device_id')
        self.guild_id = guild_id
        self.proxy = proxy
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.match_count = 0
        self.total_honor = 0
        self.running = True
        
    def _setup_proxy(self) -> Optional[Dict]:
        """Chuyển đổi proxy string sang dict cho playwright"""
        if not self.proxy:
            return None
        # Định dạng: http://user:pass@ip:port hoặc socks5://ip:port
        return {"server": self.proxy}
    
    def start_browser(self):
        """Khởi tạo trình duyệt"""
        playwright = sync_playwright().start()
        proxy_config = self._setup_proxy()
        
        launch_options = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
        }
        
        if proxy_config:
            launch_options["proxy"] = proxy_config
        
        self.browser = playwright.chromium.launch(**launch_options)
        self.context = self.browser.new_context(
            viewport={"width": 360, "height": 640},
            user_agent="Mozilla/5.0 (Linux; Android 11; SM-G975F) AppleWebKit/537.36"
        )
        self.page = self.context.new_page()
        
        # Thêm script để ẩn webdriver
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = {runtime: {}};
        """)
        
    def login_to_web(self) -> bool:
        """Đăng nhập vào web Garena bằng token (nếu cần)"""
        # Một số phiên bản web hỗ trợ đăng nhập qua token
        try:
            self.page.goto("https://ff.garena.com/", timeout=30000)
            time.sleep(3)
            # Thực hiện set localStorage token nếu có endpoint
            self.page.evaluate(f"""
                localStorage.setItem('access_token', '{self.token}');
                localStorage.setItem('uid', '{self.uid}');
            """)
            self.page.reload()
            time.sleep(5)
            return True
        except Exception as e:
            print(f"[Bot {self.uid}] Lỗi đăng nhập web: {e}")
            return False
    
    def find_and_click(self, selectors: List[str], timeout: int = 10) -> bool:
        """Tìm và click vào element với nhiều selector khác nhau"""
        for selector in selectors:
            try:
                self.page.wait_for_selector(selector, timeout=timeout * 1000)
                self.page.click(selector)
                return True
            except:
                continue
        return False
    
    def start_classic_match(self) -> bool:
        """Vào chế độ Classic Battle Royale - Solo"""
        try:
            # Đợi màn hình chính load
            time.sleep(random.uniform(2, 4))
            
            # Click nút Battle Royale (các selector khả dĩ)
            br_selectors = [
                "button:has-text('Battle Royale')",
                "div:has-text('Battle Royale')",
                ".mode-br",
                "[data-mode='battleroyale']"
            ]
            if not self.find_and_click(br_selectors, timeout=10):
                print(f"[Bot {self.uid}] Không tìm thấy nút Battle Royale")
                return False
            
            time.sleep(random.uniform(1, 2))
            
            # Click Classic mode
            classic_selectors = [
                "button:has-text('Classic')",
                "div:has-text('Classic')",
                ".mode-classic"
            ]
            if not self.find_and_click(classic_selectors, timeout=5):
                print(f"[Bot {self.uid}] Không tìm thấy Classic mode")
                return False
            
            time.sleep(random.uniform(1, 2))
            
            # Chọn Solo
            solo_selectors = [
                "button:has-text('Solo')",
                "div:has-text('Solo')",
                ".solo-mode"
            ]
            self.find_and_click(solo_selectors, timeout=3)
            
            time.sleep(random.uniform(1, 2))
            
            # Click nút Start
            start_selectors = [
                "button:has-text('Start')",
                "button:has-text('Bắt đầu')",
                ".btn-start"
            ]
            if not self.find_and_click(start_selectors, timeout=10):
                return False
            
            print(f"[Bot {self.uid}] Đã vào trận đấu Classic Solo")
            return True
            
        except Exception as e:
            print(f"[Bot {self.uid}] Lỗi khi vào trận: {e}")
            return False
    
    def random_move(self):
        """Thực hiện random di chuyển bằng phím WASD hoặc click chuột"""
        try:
            move_type = random.choice(['wasd', 'click'])
            
            if move_type == 'wasd':
                key = random.choice(['w', 'a', 's', 'd'])
                self.page.keyboard.down(key)
                time.sleep(random.uniform(0.3, 0.8))
                self.page.keyboard.up(key)
            else:
                # Click random vị trí trên màn hình game
                x = random.randint(100, 260)
                y = random.randint(300, 580)
                self.page.mouse.click(x, y)
            
            # Đôi khi nhảy
            if random.random() < 0.3:
                self.page.keyboard.press('Space')
                
        except Exception as e:
            print(f"[Bot {self.uid}] Lỗi random move: {e}")
    
    def idle_in_match(self, max_duration: int = 1200):
        """Treo máy trong trận với random di chuyển"""
        start_time = time.time()
        last_move_time = start_time
        
        print(f"[Bot {self.uid}] Bắt đầu treo máy trong {max_duration//60} phút")
        
        while time.time() - start_time < max_duration and self.running:
            # Random di chuyển mỗi 30-60 giây
            if time.time() - last_move_time > random.uniform(30, 60):
                self.random_move()
                last_move_time = time.time()
            
            # Kiểm tra xem trận đã kết thúc chưa
            try:
                # Nếu có nút "Tiếp tục" hoặc "Continue" thì trận đã kết thúc
                next_btn = self.page.query_selector("button:has-text('Tiếp tục'), button:has-text('Continue'), button:has-text('Next')")
                if next_btn and next_btn.is_visible():
                    print(f"[Bot {self.uid}] Trận đã kết thúc")
                    break
            except:
                pass
            
            time.sleep(5)
        
        print(f"[Bot {self.uid}] Kết thúc treo máy sau {int(time.time() - start_time)} giây")
    
    def handle_match_end(self) -> bool:
        """Xử lý sau khi trận kết thúc, nhận thưởng"""
        try:
            time.sleep(3)
            
            # Click nút Tiếp tục
            next_selectors = [
                "button:has-text('Tiếp tục')",
                "button:has-text('Continue')",
                "button:has-text('Next')",
                ".btn-continue"
            ]
            if self.find_and_click(next_selectors, timeout=15):
                print(f"[Bot {self.uid}] Đã nhận thưởng sau trận")
                time.sleep(random.uniform(3, 5))
                
                # Click qua màn hình kết quả
                ok_selectors = [
                    "button:has-text('OK')",
                    "button:has-text('Đồng ý')",
                    ".btn-ok"
                ]
                self.find_and_click(ok_selectors, timeout=5)
                return True
            
            return False
        except Exception as e:
            print(f"[Bot {self.uid}] Lỗi xử lý kết thúc trận: {e}")
            return False
    
    def get_current_honor(self) -> int:
        """Lấy điểm danh dự hiện tại qua API"""
        return get_honor_points(self.uid, self.token, self._proxy_dict())
    
    def _proxy_dict(self) -> Optional[Dict]:
        if self.proxy:
            return {"http": self.proxy, "https": self.proxy}
        return None
    
    def check_token_alive(self) -> bool:
        """Kiểm tra token còn sống không"""
        info = get_guild_info(self.uid, self.token, self._proxy_dict())
        return info is not None
    
    def refresh_token_if_needed(self) -> bool:
        """Làm mới token nếu cần"""
        if not self.check_token_alive():
            print(f"[Bot {self.uid}] Token hết hạn, đang refresh...")
            new_token = refresh_guest_token(self.refresh_token, self.device_id, self._proxy_dict())
            if new_token:
                self.token = new_token
                print(f"[Bot {self.uid}] Đã refresh token thành công")
                return True
            else:
                print(f"[Bot {self.uid}] Refresh thất bại, tạo guest mới...")
                new_account = create_guest_account(self._proxy_dict())
                if new_account:
                    self.uid = new_account['uid']
                    self.token = new_account['guest_token']
                    self.refresh_token = new_account.get('refresh_token')
                    self.device_id = new_account.get('device_id')
                    # Join lại guild
                    join_guild(self.uid, self.token, self.guild_id, self._proxy_dict())
                    return True
        return False
    
    def ensure_in_guild(self) -> bool:
        """Đảm bảo tài khoản đã ở trong guild mục tiêu"""
        info = get_guild_info(self.uid, self.token, self._proxy_dict())
        
        if info and info.get('guild_id') == self.guild_id:
            return True
        
        print(f"[Bot {self.uid}] Chưa ở guild {self.guild_id}, đang join...")
        return join_guild(self.uid, self.token, self.guild_id, self._proxy_dict())
    
    def farm_loop(self, target_matches: int = 10):
        """Vòng lặp cày điểm chính"""
        self.start_browser()
        
        try:
            # Đăng nhập web
            if not self.login_to_web():
                print(f"[Bot {self.uid}] Không thể đăng nhập web, thoát")
                return
            
            # Đảm bảo đã join guild
            if not self.ensure_in_guild():
                print(f"[Bot {self.uid}] Không thể join guild {self.guild_id}")
                return
            
            # Lấy điểm ban đầu
            initial_honor = self.get_current_honor()
            print(f"[Bot {self.uid}] Điểm danh dự ban đầu: {initial_honor}")
            
            for match in range(target_matches):
                if not self.running:
                    break
                
                # Kiểm tra token
                self.refresh_token_if_needed()
                
                match_start = datetime.now()
                print(f"[Bot {self.uid}] === Bắt đầu trận {match + 1}/{target_matches} ===")
                
                # Vào trận
                if not self.start_classic_match():
                    print(f"[Bot {self.uid}] Không thể vào trận, thử lại...")
                    time.sleep(10)
                    continue
                
                # Treo máy trong trận (15-20 phút)
                match_duration = random.randint(15, 20) * 60
                self.idle_in_match(max_duration=match_duration)
                
                # Xử lý kết thúc trận
                self.handle_match_end()
                
                # Cập nhật điểm
                time.sleep(5)
                current_honor = self.get_current_honor()
                honor_gained = current_honor - initial_honor
                self.match_count += 1
                self.total_honor += honor_gained
                initial_honor = current_honor
                
                match_end = datetime.now()
                self._log_match(match + 1, match_start, match_end, honor_gained, current_honor)
                
                # Chờ giữa các trận
                wait_time = random.uniform(10, 20)
                print(f"[Bot {self.uid}] Chờ {wait_time:.1f} giây trước trận tiếp theo")
                time.sleep(wait_time)
                
        except Exception as e:
            print(f"[Bot {self.uid}] Lỗi trong farm loop: {e}")
        finally:
            self.cleanup()
    
    def _log_match(self, match_num: int, start_time, end_time, honor_gained: int, total_honor: int):
        """Ghi log trận đấu"""
        log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Bot {self.uid} | Trận {match_num} | Bắt đầu: {start_time.strftime('%H:%M:%S')} | Kết thúc: {end_time.strftime('%H:%M:%S')} | Điểm nhận: {honor_gained} | Tổng: {total_honor}\n"
        
        with open(f"log_{self.uid}.txt", "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        print(f"[Bot {self.uid}] Trận {match_num}: +{honor_gained} điểm danh dự (Tổng: {total_honor})")
    
    def cleanup(self):
        """Dọn dẹp trình duyệt"""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()

# ==================== QUẢN LÝ ĐA LUỒNG ====================
class MultiBotManager:
    def __init__(self, guild_id: str, num_bots: int = 5, proxy_list: List[str] = None):
        self.guild_id = guild_id
        self.num_bots = num_bots
        self.proxy_list = proxy_list or []
        self.bots = []
        
    def create_bots(self):
        """Tạo các guest account và khởi tạo bot"""
        print(f"[*] Đang tạo {self.num_bots} guest account...")
        
        for i in range(self.num_bots):
            proxy = self.proxy_list[i % len(self.proxy_list)] if self.proxy_list else None
            
            # Tạo guest account
            proxy_dict = {"http": proxy, "https": proxy} if proxy else None
            account = create_guest_account(proxy_dict)
            
            if not account:
                print(f"[!] Không thể tạo guest account cho bot {i+1}")
                continue
            
            # Join guild
            join_guild(account['uid'], account['guest_token'], self.guild_id, proxy_dict)
            
            bot = FreeFireBot(account, self.guild_id, proxy, headless=True)
            self.bots.append(bot)
            print(f"[+] Bot {i+1}: UID={account['uid'][:8]}... | Proxy={proxy if proxy else 'None'}")
            
            time.sleep(2)
        
        print(f"[*] Đã tạo thành công {len(self.bots)} bot")
    
    def run_all(self, matches_per_bot: int = 10):
        """Chạy tất cả bot cùng lúc"""
        if not self.bots:
            print("[!] Không có bot nào để chạy")
            return
        
        print(f"[*] Bắt đầu chạy {len(self.bots)} bot, mỗi bot {matches_per_bot} trận")
        
        def run_bot(bot):
            bot.farm_loop(target_matches=matches_per_bot)
        
        with ThreadPoolExecutor(max_workers=min(len(self.bots), 10)) as executor:
            futures = [executor.submit(run_bot, bot) for bot in self.bots]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"[!] Lỗi bot: {e}")
        
        # Tổng kết
        print("\n[*] ========== TỔNG KẾT ==========")
        total_matches = sum(b.match_count for b in self.bots)
        total_honor = sum(b.total_honor for b in self.bots)
        print(f"[*] Tổng số trận đã chạy: {total_matches}")
        print(f"[*] Tổng điểm danh dự nhận được: {total_honor}")
        print(f"[*] Trung bình mỗi bot: {total_honor//len(self.bots) if self.bots else 0} điểm")
        
        # Lưu tổng kết
        with open("farming_summary.txt", "w", encoding="utf-8") as f:
            f.write(f"Guild ID: {self.guild_id}\n")
            f.write(f"Số bot: {len(self.bots)}\n")
            f.write(f"Tổng trận: {total_matches}\n")
            f.write(f"Tổng điểm danh dự: {total_honor}\n")
            f.write(f"Thời gian kết thúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# ==================== MAIN ====================
def main():
    print("=" * 60)
    print("TOOL CÀY ĐIỂM DANH DỰ QUÂN ĐOÀN FREE FIRE")
    print("=" * 60)
    
    guild_id = input("Nhập ID quân đoàn: ").strip()
    if not guild_id:
        print("[!] ID quân đoàn không hợp lệ")
        return
    
    try:
        num_bots = int(input("Số lượng guest bot cần chạy (1-20): ") or "5")
        num_bots = max(1, min(20, num_bots))
    except:
        num_bots = 5
    
    try:
        matches_per_bot = int(input("Số trận mỗi bot (1-50): ") or "10")
        matches_per_bot = max(1, min(50, matches_per_bot))
    except:
        matches_per_bot = 10
    
    use_proxy = input("Sử dụng proxy? (y/n): ").lower() == 'y'
    proxy_list = []
    
    if use_proxy:
        proxy_file = input("Nhập đường dẫn file proxy (mỗi dòng một proxy, định dạng http://ip:port hoặc socks5://ip:port): ")
        try:
            with open(proxy_file, 'r') as f:
                proxy_list = [line.strip() for line in f if line.strip()]
            print(f"[+] Đã tải {len(proxy_list)} proxy")
        except:
            print("[!] Không thể đọc file proxy, chạy không proxy")
            proxy_list = []
    
    print("\n[*] Đang khởi tạo...")
    manager = MultiBotManager(guild_id, num_bots, proxy_list)
    manager.create_bots()
    
    if not manager.bots:
        print("[!] Không thể tạo bot nào, thoát")
        return
    
    print(f"\n[*] Bắt đầu cày điểm danh dự...")
    manager.run_all(matches_per_bot=matches_per_bot)
    
    print("\n[*] HOÀN THÀNH!")

if __name__ == "__main__":
    main()
