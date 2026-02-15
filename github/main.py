import asyncio
import json
import os
import re
import shutil
import sys
import time
import fcntl
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import Bot
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv


load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
NAVER_COOKIE = os.environ.get("NAVER_COOKIE", "").strip()

BASE_DIR = Path(__file__).resolve().parent
SENT_POSTS_FILE = BASE_DIR / "sent_posts.json"
LAST_RUN_FILE = BASE_DIR / "last_run.txt"
STATUS_FILE = BASE_DIR / "bot_status.json"
COOKIE_ALERT_FILE = BASE_DIR / "cookie_alert_sent.txt"
_PAGE_SOURCE_LOGGED = False


def _page_source_logged():
    return _PAGE_SOURCE_LOGGED


def _mark_page_source_logged():
    global _PAGE_SOURCE_LOGGED
    _PAGE_SOURCE_LOGGED = True


def _timeout_alarm_handler(signum, frame):
    raise TimeoutError("main runtime timeout reached (120 seconds)")


# ?? ?좏떥由ы떚 ?⑥닔 ??

def _resolve_binary(candidates):
    """?ㅽ뻾 媛?ν븳 諛붿씠?덈━ 寃쎈줈瑜?李얠븘 諛섑솚?쒕떎."""
    for candidate in candidates:
        if not candidate:
            continue
        path = shutil.which(candidate)
        if path and os.path.exists(path) and os.access(path, os.X_OK):
            return path
        if os.path.isabs(candidate) and os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _resolve_health_targets():
    """heartbeat/status ?뚯씪??湲곕줉???꾨낫 ?붾젆?좊━瑜??먯깋?쒕떎."""
    candidate_dirs = [
        BASE_DIR,
        BASE_DIR.parent,
        Path.cwd(),
    ]

    env_health_dir = os.environ.get("NAVER_BOT_HEALTH_DIR", "").strip()
    if env_health_dir:
        candidate_dirs.append(Path(env_health_dir).expanduser())

    env_heartbeat_file = os.environ.get("NAVER_BOT_HEARTBEAT_FILE", "").strip()
    if env_heartbeat_file:
        candidate_dirs.append(Path(env_heartbeat_file).expanduser().resolve().parent)

    # github ?섏쐞 ?붾젆?좊━???꾨낫??異붽?
    candidate_dirs.extend([
        BASE_DIR / "github",
        BASE_DIR.parent / "github",
        Path.cwd() / "github",
    ])

    resolved = []
    seen = set()
    for candidate in candidate_dirs:
        try:
            candidate = candidate.resolve()
        except Exception:
            pass

        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_dir():
            resolved.append(candidate)

    if not resolved:
        resolved = [BASE_DIR]

    heartbeat_files = [path / "last_run.txt" for path in resolved]
    status_files = [path / "bot_status.json" for path in resolved]
    return heartbeat_files, status_files


def update_health_files(run_state, run_detail):
    """遊??곹깭瑜?heartbeat(last_run.txt)? status(bot_status.json)??湲곕줉?쒕떎."""
    now_ts = time.time()
    now_utc = datetime.now(timezone.utc).isoformat()

    payload = {
        "updated_at": now_utc,
        "last_run_ts": now_ts,
        "state": run_state,
        "detail": run_detail,
        "script_path": str(Path(__file__).resolve()),
        "cwd": str(Path.cwd()),
        "pid": os.getpid(),
    }

    heartbeat_files, status_files = _resolve_health_targets()
    wrote = []

    for heartbeat_file in heartbeat_files:
        try:
            heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            with open(heartbeat_file, "w", encoding="utf-8") as f:
                f.write(f"{now_ts}\n")
            wrote.append(str(heartbeat_file))
        except Exception as e:
            print(f"heartbeat ?뚯씪 ????ㅽ뙣 ({heartbeat_file}): {e}")

    for status_file in status_files:
        try:
            status_file.parent.mkdir(parents=True, exist_ok=True)
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"?곹깭 ?뚯씪 ????ㅽ뙣 ({status_file}): {e}")

    if wrote:
        print(f"heartbeat 媛깆떊: {', '.join(wrote)}")
    else:
        print("heartbeat 媛깆떊 ?ㅽ뙣: ??λ맂 寃쎈줈媛 ?놁뒿?덈떎.")


# ?? 寃뚯떆湲 ???濡쒕뱶 ??

def load_sent_posts():
    """?댁쟾???꾩넚??寃뚯떆湲 紐⑸줉??濡쒕뱶?쒕떎."""
    if not SENT_POSTS_FILE.exists():
        return []
    try:
        with open(SENT_POSTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"sent_posts 濡쒕뱶 ?ㅽ뙣: {e}")
        return []


def save_sent_posts(posts):
    """?꾩넚??寃뚯떆湲 紐⑸줉????ν븳?? 理쒕? 500媛쒓퉴吏 ?좎?."""
    try:
        if len(posts) > 500:
            posts = posts[-500:]
        with open(SENT_POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"sent_posts ????ㅽ뙣: {e}")


# ?? 荑좏궎 ?뚯떛 ??

def _parse_cookie_pairs(raw_cookie):
    """?몃?肄쒕줎?쇰줈 援щ텇??荑좏궎 臾몄옄?댁쓣 (key, value) ?쒗뵆 由ъ뒪?몃줈 蹂?섑븳??"""
    pairs = []
    for pair in raw_cookie.split(";"):
        if "=" not in pair:
            continue
        key, value = pair.strip().split("=", 1)
        if key and value:
            pairs.append((key, value))
    return pairs


def _is_chromedriver_connection_issue(message):
    lowered = (message or "").lower()
    return "connection refused" in lowered or "no such session" in lowered


# ?? ?쒓컙 ?뚯떛 ??

def parse_time_string(time_str):
    """?ㅼ씠踰?移댄럹???곷? ?쒓컙 臾몄옄?댁쓣 ?덈? ?쒓컙 ?뺤떇?쇰줈 蹂?섑븳??"""
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    time_str = (time_str or "").strip()

    try:
        if "諛⑷툑" in time_str:
            dt = now
        elif "遺??? in time_str:
            minutes = int(re.search(r"(\d+)遺?, time_str).group(1))
            dt = now - timedelta(minutes=minutes)
        elif "?쒓컙 ?? in time_str:
            hours = int(re.search(r"(\d+)?쒓컙", time_str).group(1))
            dt = now - timedelta(hours=hours)
        elif "???? in time_str:
            days = int(re.search(r"(\d+)??, time_str).group(1))
            dt = now - timedelta(days=days)
        else:
            dt = now

        ampm = "?ㅼ쟾" if dt.hour < 12 else "?ㅽ썑"
        hour = dt.hour if dt.hour <= 12 else dt.hour - 12
        hour = 12 if hour == 0 else hour
        return f"{ampm} {hour}:{dt.minute:02d}"
    except Exception as e:
        print(f"?쒓컙 ?뚯떛 ?ㅽ뙣 ({time_str}): {e}")
        ampm = "?ㅼ쟾" if now.hour < 12 else "?ㅽ썑"
        hour = now.hour if now.hour <= 12 else now.hour - 12
        hour = 12 if hour == 0 else hour
        return f"{ampm} {hour}:{now.minute:02d}"


# ?? ?붾젅洹몃옩 ?꾩넚 ??

async def send_telegram_message(message):
    """?붾젅洹몃옩?쇰줈 硫붿떆吏瑜??꾩넚?쒕떎. 20珥???꾩븘???곸슜."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("?붾젅洹몃옩 ?ㅼ젙???꾨씫?섏뼱 ?덉뒿?덈떎.")
        return
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await asyncio.wait_for(
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message),
            timeout=20,
        )
        print(f"?붾젅洹몃옩 ?꾩넚: {message[:20]}...")
    except asyncio.TimeoutError:
        print("?붾젅洹몃옩 ?꾩넚 ??꾩븘??20珥?")
    except Exception as e:
        print(f"?붾젅洹몃옩 ?꾩넚 ?ㅽ뙣: {e}")


# ?? Chrome ?쒕씪?대쾭 ?앹꽦 ??

def _build_driver():
    """?ㅻ뱶由ъ뒪 Chrome ?쒕씪?대쾭瑜??앹꽦?섍퀬 諛섑솚?쒕떎."""
    chrome_binary = _resolve_binary([
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium",
        "chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/chrome",
    ])
    if not chrome_binary:
        raise FileNotFoundError("Chrome 釉뚮씪?곗? ?ㅽ뻾 ?뚯씪??李얠? 紐삵뻽?듬땲??")

    chromedriver_path = _resolve_binary([
        "chromedriver",
        "/usr/bin/chromedriver",
        "/usr/bin/chromium-chromedriver",
        "/usr/local/bin/chromedriver",
    ])
    if not chromedriver_path:
        raise FileNotFoundError("chromedriver ?ㅽ뻾 ?뚯씪??李얠? 紐삵뻽?듬땲??")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    # 硫붾え由??덉빟 ?듭뀡 (1GB ?쒕쾭 ?섍꼍 理쒖쟻??
    options.add_argument("--disable-background-networking")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--log-level=3")
    options.binary_location = chrome_binary
    options.page_load_strategy = "eager"

    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    # ?섏씠吏 濡쒕뵫/?ㅽ겕由쏀듃 ?ㅽ뻾 ??꾩븘??(臾댄븳 ?湲?諛⑹?)
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(45)

    # navigator.webdriver ?띿꽦???④꺼 ?먮룞???먯? ?고쉶
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


# ?? ?λ룞???湲? URL 蹂寃??먮뒗 ?쇰뱶 ?붿냼 媛먯? ??

def _wait_url_or_feed(driver, timeout=25):
    """
    timeout ?숈븞 ?대쭅?섎ŉ URL 蹂寃?濡쒓렇??由щ떎?대젆?? ?먮뒗 ?쇰뱶 ?붿냼 異쒗쁽??媛먯??쒕떎.
    """
    poll_interval = 0.5
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            current = driver.current_url
            if "nid.naver.com" in current or "nidlogin" in current:
                return "login"
            if driver.find_elements(By.CSS_SELECTOR, "div.feed_item"):
                return "ready"
        except Exception:
            pass
        time.sleep(poll_interval)
    return "timeout"


# ?? 荑좏궎 ?곸슜 ??

def _apply_cookies(driver, cookie_pairs):
    """?쒕씪?대쾭??荑좏궎瑜??쇨큵 ?곸슜?쒕떎."""
    for key, value in cookie_pairs:
        try:
            driver.add_cookie({"name": key, "value": value, "domain": ".naver.com"})
        except Exception as e:
            print(f"荑좏궎 ?깅줉 ?ㅽ뙣 ({key}): {e}")


# ?? ?쇰뱶 寃뚯떆湲 ?섏쭛 ??

def get_feed_posts():
    """
    ?ㅼ씠踰?移댄럹 ?쇰뱶?먯꽌 寃뚯떆湲???섏쭛?쒕떎.
    諛섑솚媛? (posts, cookie_expired, fetch_ok)
    """
    if not NAVER_COOKIE:
        print("NAVER_COOKIE媛 ?ㅼ젙?섏? ?딆븯?듬땲??")
        return [], False, False

    cookie_pairs = _parse_cookie_pairs(NAVER_COOKIE)
    if not cookie_pairs:
        print("NAVER_COOKIE ?뺤떇???좏슚?섏? ?딆뒿?덈떎.")
        return [], False, False

    driver = None
    posts = []
    cookie_expired = False
    fetch_ok = False

    try:
        driver = _build_driver()
    except Exception as e:
        print(f"?쒕씪?대쾭 珥덇린???ㅽ뙣: {e}")
        return posts, cookie_expired, False

    try:
        print(f"荑좏궎 媛쒖닔: {len(cookie_pairs)}")

        # ?? 1?④퀎: ?ㅼ씠踰??꾨찓???뺣낫 + 荑좏궎 ?곸슜 ??
        driver.get("https://www.naver.com")
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )
        except Exception:
            pass

        _apply_cookies(driver, cookie_pairs)

        # ?? 2?④퀎: 荑좏궎 ?쒖꽦??(naver.com ?щ갑臾? ??
        driver.get("https://www.naver.com")
        time.sleep(1)

        # ?? 3?④퀎: 移댄럹 ?쇰뱶濡??대룞 + ?λ룞???湲???
        driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
        result = _wait_url_or_feed(driver, timeout=15)
        print(f"珥덇린 吏꾩엯 寃곌낵: {result}, URL={driver.current_url}")

        # ?? 濡쒓렇??由щ떎?대젆????1???ъ떆????
        if result == "login":
            print("濡쒓렇???섏씠吏濡?由щ떎?대젆?몃맖: 荑좏궎 ?ъ쟻????1???ъ떆??)
            _apply_cookies(driver, cookie_pairs)
            driver.get("https://www.naver.com")
            time.sleep(1)
            _apply_cookies(driver, cookie_pairs)
            driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
            result = _wait_url_or_feed(driver, timeout=20)
            print(f"?ъ떆??吏꾩엯 寃곌낵: {result}, URL={driver.current_url}")

        # ?? 理쒖쥌 寃곌낵 ?먯젙 ??
        if result == "login":
            cookie_expired = True
            return [], cookie_expired, True
        if result == "timeout":
            print("?쇰뱶 而⑦뀒?대꼫 ?먯깋 ?ㅽ뙣: ?붿냼/由щ떎?대젆???먯젙 紐⑤몢 ?놁쓬")
            return [], cookie_expired, False

        fetch_ok = True
        elements = driver.find_elements(By.CSS_SELECTOR, "div.feed_item")
        print(f"寃뚯떆湲 議고쉶 ?? {len(elements)}")

        if len(elements) == 0:
            if not _page_source_logged():
                print("No feed items found. Page source snippet:")
                print(driver.page_source[:1000])
                _mark_page_source_logged()
            else:
                print(f"[skip] page source log skipped (URL={driver.current_url})")

        # ?? 寃뚯떆湲 ?뚯떛 ??
        for el in elements[:20]:
            try:
                title_el = el.find_element(By.CSS_SELECTOR, "strong.title")
                link_el = el.find_element(By.CSS_SELECTOR, "div.feed_content > a")
                date_el = el.find_element(By.CSS_SELECTOR, "span.date")

                like_count = "0"
                comment_count = "0"

                try:
                    like_el = el.find_element(By.CSS_SELECTOR, "span.count.like")
                    like_match = re.search(r"(\d+)", (like_el.text or "").strip())
                    if like_match:
                        like_count = like_match.group(1)
                except Exception:
                    pass

                try:
                    comment_el = el.find_element(By.CSS_SELECTOR, "a.comment")
                    comment_match = re.search(r"(\d+)", (comment_el.text or "").strip())
                    if comment_match:
                        comment_count = comment_match.group(1)
                except Exception:
                    pass

                title = (title_el.text or "").strip()
                link = (link_el.get_attribute("href") or "").strip()
                date_text = (date_el.text or "").strip()

                if title and link:
                    posts.append({
                        "title": title,
                        "link": link,
                        "date": date_text,
                        "absolute_time": parse_time_string(date_text),
                        "like": like_count,
                        "comment": comment_count,
                    })
            except Exception as e:
                print(f"寃뚯떆湲 異붿텧 ?ㅽ뙣: {e}")

    except Exception as e:
        if _is_chromedriver_connection_issue(str(e)):
            print(f"ChromeDriver connection issue (possible OOM): {e}")
        else:
            print(f"피드 조회 실패: {e}")
        fetch_ok = False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    return posts, cookie_expired, fetch_ok


# ?? 硫붿씤 ?ㅽ뻾 ??

async def main():
    if sys.platform == "win32":
        print("Windows ?섍꼍?먯꽌??蹂??ㅽ겕由쏀듃 ?ㅽ뻾???쒗븳?⑸땲??")
        update_health_files("skipped", "windows_not_supported")
        return

    run_state = "running"
    run_detail = "?쒖옉"
    timeout_scheduled = False

    lock_file = None
    try:
        lock_path = BASE_DIR / "bot.lock"
        lock_file = open(str(lock_path), "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("?대? ?ㅽ뻾 以묒엯?덈떎. 以묐났 ?ㅽ뻾??李⑤떒?⑸땲??")
        if lock_file is not None:
            lock_file.close()
        return
    except Exception as e:
        print(f"???뚯씪 ?ㅼ젙 ?ㅽ뙣: {e}")

    try:
        signal.signal(signal.SIGALRM, _timeout_alarm_handler)
        signal.alarm(120)
        timeout_scheduled = True

        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        print("\n" + "=" * 50)
        print(f"?ㅽ뻾 ?쒖옉: {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
        print("=" * 50)
        print("?ㅼ씠踰?移댄럹 ?쇰뱶 議고쉶 ?쒖옉 (Selenium Headless)")

        update_health_files("running", "?쇰뱶 ?섏쭛 ?쒖옉")

        sent_posts = load_sent_posts()
        print(f"湲곗〈 sent_posts: {len(sent_posts)}")

        posts, cookie_expired, fetch_ok = get_feed_posts()

        if not fetch_ok:
            run_state = "error"
            run_detail = "?쇰뱶 議고쉶 ?ㅽ뙣"
            print("?쇰뱶 議고쉶 ?ㅽ뙣濡?醫낅즺?⑸땲??")
            return

        if cookie_expired:
            run_state = "cookie_expired"
            run_detail = "荑좏궎 留뚮즺"
            send_alert = True
            today = datetime.now(KST).strftime("%Y-%m-%d")
            if COOKIE_ALERT_FILE.exists():
                try:
                    with open(COOKIE_ALERT_FILE, "r", encoding="utf-8") as f:
                        if f.read().strip() == today:
                            send_alert = False
                except Exception:
                    pass

            if send_alert:
                alert_msg = (
                    "?좑툘 [湲닿툒] ?ㅼ씠踰?荑좏궎媛 留뚮즺?섏뿀?듬땲??\n\n"
                    "遊뉗씠 ???댁긽 ?뺤긽 ?섏쭛?????놁뒿?덈떎.\n"
                    "PC?먯꽌 ?ㅼ씠踰?移댄럹 濡쒓렇??????荑좏궎瑜?蹂듭궗?섏뿬 .env??媛깆떊?댁＜?몄슂."
                )
                await send_telegram_message(alert_msg)
                try:
                    with open(COOKIE_ALERT_FILE, "w", encoding="utf-8") as f:
                        f.write(today)
                except Exception as e:
                    print(f"荑좏궎 ?뚮┝ 湲곕줉 ?ㅽ뙣: {e}")
            return

        if not posts:
            run_state = "ok"
            run_detail = "?좉퇋 寃뚯떆湲 0嫄?
            print("?덈줈??寃뚯떆湲???녾굅???섏쭛?섏? ?딆븯?듬땲??")
            return

        new_posts_count = 0
        for post in reversed(posts):
            link = post["link"]
            if link in sent_posts:
                continue

            msg = f"{post['absolute_time']}\n{post['title']}\n{post['link']}\n醫뗭븘??{post['like']} ?볤? {post['comment']}"
            await send_telegram_message(msg)
            sent_posts.append(link)
            new_posts_count += 1
            time.sleep(1)

        if new_posts_count > 0:
            save_sent_posts(sent_posts)
            run_state = "ok"
            run_detail = f"??湲 {new_posts_count}嫄?
            print(f"--> {new_posts_count}嫄??꾩넚 ?꾨즺.")
        else:
            run_state = "ok"
            run_detail = "?좉퇋 寃뚯떆湲 ?놁쓬"
            print("--> ?좉퇋 寃뚯떆湲???놁뒿?덈떎.")

    except TimeoutError as e:
        run_state = "error"
        run_detail = str(e)
        print(f"실행 시간 초과: {e}")
    except asyncio.CancelledError:
        run_state = "interrupted"
        run_detail = "??꾩븘??以묐떒"
        print("?ㅽ뻾??以묐떒?⑸땲??")
    except KeyboardInterrupt:
        run_state = "interrupted"
        run_detail = "?ъ슜??以묐떒"
        print("?ъ슜???먮뒗 ?몃? ?쒓렇?먯뿉 ?섑빐 以묐떒?섏뿀?듬땲??")
    except Exception as e:
        run_state = "error"
        run_detail = f"?덇린移?紐삵븳 ?덉쇅: {e}"
        print(f"移섎챸???ㅻ쪟: {e}")
    finally:
        if timeout_scheduled:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
        if lock_file is not None:
            try:
                lock_file.close()
            except Exception:
                pass
        update_health_files(run_state, run_detail)


if __name__ == "__main__":
    asyncio.run(main())
