import os
import asyncio
import time
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from telegram import Bot
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

# .env 파일 로드 (같은 디렉토리 또는 상위 디렉토리 확인)
load_dotenv()

# 환경 변수 로드
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NAVER_COOKIE = os.environ.get('NAVER_COOKIE', '').strip()

# PC 버전은 별도의 로그 파일 사용
SENT_POSTS_FILE = 'local_log.json'

def load_sent_posts():
    if os.path.exists(SENT_POSTS_FILE):
        try:
            with open(SENT_POSTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"기존 로그 파일 로드 실패: {e}")
            return []
    return []

def save_sent_posts(posts):
    try:
        # 너무 많이 쌓이지 않도록 최신 100개만 유지
        if len(posts) > 100:
            posts = posts[-100:]
        with open(SENT_POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"로그 파일 저장 실패: {e}")

def parse_time_string(time_str):
    """
    '방금 전', '1분 전', '1시간 전' 등의 문자열을 파싱하여 
    '오후 12:12' 형식의 절대 시간 문자열로 반환
    """
    # KST (UTC+9) 설정
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    
    time_str = time_str.strip()
    
    try:
        if '방금' in time_str:
            dt = now
        elif '분 전' in time_str:
            minutes = int(re.search(r'(\d+)분', time_str).group(1))
            dt = now - timedelta(minutes=minutes)
        elif '시간 전' in time_str:
            hours = int(re.search(r'(\d+)시간', time_str).group(1))
            dt = now - timedelta(hours=hours)
        elif '일 전' in time_str: # 혹시 모를 경우 대비
            days = int(re.search(r'(\d+)일', time_str).group(1))
            dt = now - timedelta(days=days)
        else:
            # 날짜 형식 (2024.01.01 등)이거나 알 수 없는 형식이면 현재 시간으로 대체하거나 그대로 둠
            # 여기서는 현재 시간으로 처리
            dt = now
            
        # 오전/오후 포맷팅
        ampm = "오전" if dt.hour < 12 else "오후"
        hour = dt.hour if dt.hour <= 12 else dt.hour - 12
        hour = 12 if hour == 0 else hour
        minute = dt.minute
        
        return f"{ampm} {hour}:{minute:02d}"
        
    except Exception as e:
        print(f"시간 파싱 오류 ({time_str}): {e}")
        # 오류 발생 시 현재 시간 반환
        ampm = "오전" if now.hour < 12 else "오후"
        hour = now.hour if now.hour <= 12 else now.hour - 12
        hour = 12 if hour == 0 else hour
        return f"{ampm} {hour}:{now.minute:02d}"

async def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정이 누락되었습니다.")
        return
    try:
        # Bot 초기화 시 토큰 다시 한 번 확인
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"텔레그램 전송 성공: {message[:20]}...")
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def get_feed_posts():
    if not NAVER_COOKIE:
        print("네이버 쿠키(NAVER_COOKIE)가 설정되지 않았습니다.")
        return []

    # Selenium Headless 설정
    chrome_options = Options()
    chrome_options.add_argument("--headless") # 화면 없이 실행
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # 봇 탐지 방지 옵션 추가
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # 로그 레벨 조정 (불필요한 로그 숨김)
    chrome_options.add_argument("--log-level=3")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    # 봇 탐지 방지 스크립트 실행
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })
    
    posts = []
    try:
        # 1. 네이버 도메인으로 이동 (쿠키 설정을 위해)
        driver.get("https://www.naver.com")
        
        # 2. 쿠키 파싱 및 설정
        if not NAVER_COOKIE:
            print("오류: NAVER_COOKIE 환경 변수가 비어있습니다.")
        
        cookie_pairs = NAVER_COOKIE.split(';')
        
        for pair in cookie_pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                if key and value:
                    driver.add_cookie({
                        'name': key,
                        'value': value,
                        'domain': '.naver.com'
                    })
        
        # 3. 피드 페이지로 이동
        driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
        
        # 4. 로딩 대기
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_item"))
            )
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_item strong.title"))
            )
            time.sleep(3) # 렌더링 안정화
        except Exception as e:
            print(f"로딩 대기 중 타임아웃: {e}")

        # 5. 데이터 추출
        elements = driver.find_elements(By.CSS_SELECTOR, "div.feed_item")
        print(f"발견된 게시글 수: {len(elements)}")
        
        # 최신 20개 검사
        for i, el in enumerate(elements[:20]): 
            try:
                title_el = el.find_element(By.CSS_SELECTOR, "strong.title")
                link_el = el.find_element(By.CSS_SELECTOR, "div.feed_content > a")
                date_el = el.find_element(By.CSS_SELECTOR, "span.date")
                
                # 좋아요/댓글 수 추출
                like_count = "0"
                comment_count = "0"
                
                try:
                    like_el = el.find_element(By.CSS_SELECTOR, "span.count.like")
                    like_text = like_el.text.strip()
                    match = re.search(r'\d+', like_text)
                    if match:
                        like_count = match.group()
                except:
                    pass 
                    
                try:
                    comment_el = el.find_element(By.CSS_SELECTOR, "a.comment")
                    comment_text = comment_el.text.strip()
                    match = re.search(r'\d+', comment_text)
                    if match:
                        comment_count = match.group()
                except:
                    pass

                title = title_el.text.strip()
                link = link_el.get_attribute('href').strip()
                date_text = date_el.text.strip()
                
                # 절대 시간으로 변환
                absolute_time = parse_time_string(date_text)
                
                if title and link:
                    posts.append({
                        'title': title, 
                        'link': link,
                        'date': date_text,
                        'absolute_time': absolute_time,
                        'like': like_count,
                        'comment': comment_count
                    })
            except Exception as e:
                print(f"게시글 {i+1} 추출 실패: {e}")
                continue
                
    except Exception as e:
        print(f"피드 가져오기 실패: {e}")
    finally:
        driver.quit()
        
    return posts

async def main_loop():
    print("="*50)
    print("PC 버전 네이버 카페 알림 봇 시작")
    print("1분 간격으로 피드를 확인합니다.")
    print("종료하려면 Ctrl+C를 누르세요.")
    print("="*50)
    
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 피드 확인 중...")
            
            # 1. 기존 로그 로드
            sent_posts = load_sent_posts()
            
            # 2. 새 글 가져오기
            posts = get_feed_posts()
            
            if posts:
                new_posts_count = 0
                for post in posts:
                    link = post['link']
                    if link in sent_posts:
                        continue
                        
                    msg = f"{post['absolute_time']}\n{post['title']}\n{post['link']}\n좋아요 {post['like']} 댓글 {post['comment']}"
                    await send_telegram_message(msg)
                    
                    sent_posts.append(link)
                    new_posts_count += 1
                    time.sleep(1)
                
                if new_posts_count > 0:
                    print(f"--> {new_posts_count}개의 새 글 알림 전송 완료.")
                    save_sent_posts(sent_posts)
                else:
                    print("--> 새로운 게시글이 없습니다.")
            else:
                print("--> 게시글을 가져오지 못했습니다.")
                
        except Exception as e:
            print(f"오류 발생: {e}")
            
        # 1분 대기
        print("1분 뒤 다시 확인합니다...")
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
