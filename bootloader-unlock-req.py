import subprocess
import sys
import os

# Configuration
FEED_TIME_SHIFT = 1400  # Time shift in milliseconds - adjust this value as needed (16/09 measured: 1st response +35ms, 2nd shot +36ms still quota -> timing already optimal, keep 1400)
CONCURRENT_WORKERS = 16  # parallel burst threads at midnight (seq ~2 req/s lost; 16 workers ~= 30-35 req/s at window open)
PREWARM_MARKS = (90, 40)  # seconds before window to pre-warm 16 keep-alive conns (kills ~400-700ms TLS handshake spread at fire time)

# Server lists
ntp_servers = [
    "ntp0.ntp-servers.net", "ntp1.ntp-servers.net", "ntp2.ntp-servers.net",
    "ntp3.ntp-servers.net", "ntp4.ntp-servers.net", "ntp5.ntp-servers.net",
    "ntp6.ntp-servers.net"
]

MI_SERVERS = ['161.117.96.161', '20.157.18.26']

# Installation of dependencies
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

required_packages = ["requests", "ntplib", "pytz", "urllib3", "linecache"]
for package in required_packages:
    try:
        __import__(package)
    except ImportError:
        print(f"Installing package {package}...")
        install_package(package)

os.system('cls' if os.name == 'nt' else 'clear')

import hashlib
import random
import time
from datetime import datetime, timezone, timedelta
import ntplib
import pytz
import urllib3
import json
import threading
from concurrent.futures import ThreadPoolExecutor

def press_enter_to_close():
    # Keeps the console open when run interactively; no-op when stdin is closed (background/nohup run).
    try:
        input(f"Press Enter to close...")
    except EOFError:
        pass

def ask_yes_no(prompt):
    # Yes/No prompt; auto-No when stdin is closed so a background run never spams blindly.
    try:
        ans = input(prompt)
    except EOFError:
        print("no (auto, stdin cerrado)")
        return False
    return ans.strip().lower() in ('y', 'yes')

# Version
os.system('cls' if os.name == 'nt' else 'clear')
scriptversion = "ARU_FHL_v070425"

# Global variables
print(f"{scriptversion}")
print(f"\nChecking account status")
token = open("token.txt").read().strip().split()[0]
cookie_value = token
feed_time_shift = FEED_TIME_SHIFT
feed_time_shift_1 = feed_time_shift / 1000

# Generates a unique device identifier
def generate_device_id():
    random_data = f"{random.random()}-{time.time()}"
    device_id = hashlib.sha1(random_data.encode('utf-8')).hexdigest().upper()
    return device_id

# Get the current Beijing time from NTP
def get_initial_beijing_time():
    client = ntplib.NTPClient()
    beijing_tz = pytz.timezone("Asia/Shanghai")
    for server in ntp_servers:
        try:
            print(f"\nGetting current Beijing time")
            response = client.request(server, version=3)
            ntp_time = datetime.fromtimestamp(response.tx_time, timezone.utc)
            beijing_time = ntp_time.astimezone(beijing_tz)
            print(f"[Beijing time]: {beijing_time.strftime('%Y-%m-%d %H:%M:%S.%f')}")
            return beijing_time
        except Exception as e:
            print(f"Error connecting to {server}: {e}")
    print(f"Could not connect to any NTP server.")
    return None

# Synchronize Beijing time
def get_synchronized_beijing_time(start_beijing_time, start_timestamp):
    elapsed = time.time() - start_timestamp
    current_time = start_beijing_time + timedelta(seconds=elapsed)
    return current_time

# Wait until the target time taking into account the ping
def wait_until_target_time(start_beijing_time, start_timestamp, session=None, cookie_value=None, device_id=None):
    next_day = start_beijing_time + timedelta(days=1)
    print(f"\nBootloader unlock request")
    print(f"[Set offset]: {feed_time_shift:.2f} ms.")
    target_time = next_day.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=feed_time_shift_1)
    print(f"[Waiting until]: {target_time.strftime('%Y-%m-%d %H:%M:%S.%f')}")
    print(f"\nDo not close this window...")
    prewarm_done = set()
    
    while True:
        current_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
        time_diff = target_time - current_time
        
        if time_diff.total_seconds() > 1:
            if session is not None:
                for mark in PREWARM_MARKS:
                    if time_diff.total_seconds() <= mark and mark not in prewarm_done:
                        prewarm_done.add(mark)
                        threading.Thread(target=prewarm_connections, args=(session, cookie_value, device_id), daemon=True).start()
                        print(f"[Prewarm]: warming {CONCURRENT_WORKERS} connections ({mark}s to window, background)...")
            time.sleep(min(1.0, time_diff.total_seconds() - 1))
        elif current_time >= target_time:
            print(f"Target time reached: {current_time.strftime('%Y-%m-%d %H:%M:%S.%f')}. Starting to send requests...")
            break
        else:
            time.sleep(0.0001)

# Pre-warm N keep-alive connections so the midnight burst skips the TCP+TLS handshake (~400-700ms each)
def prewarm_connections(session, cookie_value, device_id, n=CONCURRENT_WORKERS):
    url = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
    headers = {
        "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
    }
    ok = [0]
    lock = threading.Lock()
    def one_warm():
        try:
            r = session.make_request('GET', url, headers=headers)
            if r is not None:
                _ = r.data  # drain fully so the connection returns to the pool reusable
                r.release_conn()
                with lock:
                    ok[0] += 1
        except Exception:
            pass
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(lambda _: one_warm(), range(n)))
    print(f"[Prewarm]: {ok[0]}/{n} connections warm in {(time.time()-t0)*1000:.0f} ms.")

# Check if account unlocking is possible via API
def check_unlock_status(session, cookie_value, device_id):
    try:
        url = "https://sgp-api.buy.mi.com/bbs/api/global/user/bl-switch/state"
        headers = {
            "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
        }
        
        response = session.make_request('GET', url, headers=headers)
        if response is None:
            print(f"[Error] Could not get unlock status.")
            return False

        response_data = json.loads(response.data.decode('utf-8'))
        response.release_conn()

        if response_data.get("code") == 100004:
            print(f"[Error] Cookie has expired, needs to be updated.")
            press_enter_to_close()
            exit()

        data = response_data.get("data", {})
        is_pass = data.get("is_pass")
        button_state = data.get("button_state")
        deadline_format = data.get("deadline_format", "")

        if is_pass == 4:
            if button_state == 1:
                    print(f"[Account status]: request can be sent.")
                    return True

            elif button_state == 2:
                print(f"[Account status]: request block until {deadline_format} (Month/Day).")
                if ask_yes_no(f"Continue (Yes/No)?: "):
                    return True
                else:
                    press_enter_to_close()
                    exit()
            elif button_state == 3:
                print(f"[Account status]: account was created less than 30 days ago.")
                if ask_yes_no(f"Continue (Yes/No)?: "):
                    return True
                else:
                    press_enter_to_close()
                    exit()
        elif is_pass == 1:
            print(f"[Account status]: request was approved, unlock is possible until {deadline_format}.")
            press_enter_to_close()
            exit()
        else:
            print(f"[Account status]: unknown status.")
            press_enter_to_close()
            exit()
    except Exception as e:
        print(f"[Status check error] {e}")
        return False

# Container for working with HTTP requests
class HTTP11Session:
    def __init__(self):
        self.http = urllib3.PoolManager(
            maxsize=32,  # >= CONCURRENT_WORKERS: no worker ever waits for a pooled connection (that wait WOULD add ms)
            retries=True,
            timeout=urllib3.Timeout(connect=2.0, read=15.0),
            headers={}
        )

    def make_request(self, method, url, headers=None, body=None):
        try:
            request_headers = {}
            if headers:
                request_headers.update(headers)
                request_headers['Content-Type'] = 'application/json; charset=utf-8'
            
            if method == 'POST':
                if body is None:
                    body = '{"is_retry":true}'.encode('utf-8')
                request_headers['Content-Length'] = str(len(body))
                request_headers['Accept-Encoding'] = 'gzip, deflate, br'
                request_headers['User-Agent'] = 'okhttp/4.12.0'
                request_headers['Connection'] = 'keep-alive'
            
            response = self.http.request(
                method,
                url,
                headers=request_headers,
                body=body,
                preload_content=False
            )
            
            return response
        except Exception as e:
            print(f"[Network error] {e}")
            return None
 
def main():
        
    device_id = generate_device_id()
    session = HTTP11Session()

    if check_unlock_status(session, cookie_value, device_id):
        start_beijing_time = get_initial_beijing_time()
        if start_beijing_time is None:
            print(f"Could not establish initial time. Press Enter to close...")
            press_enter_to_close()
            exit()

        start_timestamp = time.time()

        url = "https://sgp-api.buy.mi.com/bbs/api/global/apply/bl-auth"
        headers = {
            "Cookie": f"new_bbs_serviceToken={cookie_value};versionCode=500411;versionName=5.4.11;deviceId={device_id};"
        }

        print(f"[Burst]: {CONCURRENT_WORKERS} parallel workers, pre-spawned before the window.")
        stop_event = threading.Event()
        start_event = threading.Event()

        def burst_worker(worker_id):
            start_event.wait()  # all workers released at the exact same instant: zero spawn stagger in the hot path
            while not stop_event.is_set():  # ~50ns check, negligible vs ~440ms RTT
                request_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
                print(f"[W{worker_id}][Request]: Sending request at {request_time.strftime('%Y-%m-%d %H:%M:%S.%f')} (UTC+8)")

                response = session.make_request('POST', url, headers=headers)
                if response is None:
                    continue

                response_time = get_synchronized_beijing_time(start_beijing_time, start_timestamp)
                print(f"[W{worker_id}][Response]: Response received at {response_time.strftime('%Y-%m-%d %H:%M:%S.%f')} (UTC+8)")

                try:
                    response_data = response.data
                    response.release_conn()
                    json_response = json.loads(response_data.decode('utf-8'))
                    code = json_response.get("code")
                    data = json_response.get("data", {})

                    if code == 0:
                        apply_result = data.get("apply_result")
                        if apply_result == 1:
                            print(f"[W{worker_id}][Status]: Request was approved, checking status...")
                            stop_event.set()
                            check_unlock_status(session, cookie_value, device_id)
                            return
                        elif apply_result == 3:
                            deadline_format = data.get("deadline_format", "Not specified")
                            print(f"[W{worker_id}][Status]: Request was not sent, limit reached. Try again on {deadline_format} (Month/Day).")
                            stop_event.set()
                            return
                        elif apply_result == 4:
                            deadline_format = data.get("deadline_format", "Not specified")
                            print(f"[W{worker_id}][Status]: Request was not sent, block imposed until {deadline_format} (Month/Day).")
                            stop_event.set()
                            return
                    elif code == 100001:
                        print(f"[W{worker_id}][Status]: Request was rejected, error in the request.")
                        print(f"[W{worker_id}][FULL RESPONSE]: {json_response}")
                    elif code == 100003:
                        print(f"[W{worker_id}][Status]: Request may have been approved, checking status...")
                        print(f"[W{worker_id}][Full response]: {json_response}")
                    elif code is not None:
                        print(f"[W{worker_id}][Status]: Unknown request status: {code}")
                        print(f"[W{worker_id}][Full response]: {json_response}")
                    else:
                        print(f"[W{worker_id}][Error]: Response does not contain required code.")
                        print(f"[W{worker_id}][Full response]: {json_response}")

                except json.JSONDecodeError:
                    print(f"[W{worker_id}][Error]: Could not decode JSON response.")
                    print(f"[W{worker_id}][Server response]: {response_data}")
                except Exception as e:
                    print(f"[W{worker_id}][Response processing error]: {e}")
                    continue

        try:
            with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
                futures = [executor.submit(burst_worker, i + 1) for i in range(CONCURRENT_WORKERS)]
                wait_until_target_time(start_beijing_time, start_timestamp, session, cookie_value, device_id)
                start_event.set()  # window open: all workers fire at once
                print(f"[Burst]: released {CONCURRENT_WORKERS} workers.")
                for fut in futures:
                    try:
                        fut.result()
                    except SystemExit:
                        raise
                    except Exception as e:
                        print(f"[Worker error]: {e}")
            print(f"[Done]: burst stopped, all workers finished.")
            press_enter_to_close()
        except Exception as e:
            print(f"[Request error]: {e}")
            press_enter_to_close()
            exit()

if __name__ == "__main__":
    main()
