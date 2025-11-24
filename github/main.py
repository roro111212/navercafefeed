import os
import asyncio
import time
import json
import re
from datetime import datetime, timedelta
from telegram import Bot
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# GitHub Secrets에서 환경 변수 로드
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
NAVER_COOKIE = os.environ.get('NAVER_COOKIE', '').strip() # NID_AUT=...; NID_SES=...

# 보낸 게시글 목록 파일 경로
SENT_POSTS_FILE = 'sent_posts.json'

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
    now = datetime.now()
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
        # NAVER_COOKIE 예시: "NID_AUT=...; NID_SES=..."
        if not NAVER_COOKIE:
            print("오류: NAVER_COOKIE 환경 변수가 비어있습니다.")
        
        cookie_pairs = NAVER_COOKIE.split(';')
        print(f"설정할 쿠키 개수: {len(cookie_pairs)}")
        
        for pair in cookie_pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                if key and value:
                    driver.add_cookie({
                        'name': key,
                        'value': value,
                        'domain': '.naver.com'
                    })
                    print(f"쿠키 추가됨: {key}")
        
        # 3. 피드 페이지로 이동
        print("피드 페이지로 이동 중...")
        driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
        
        # 4. 로딩 대기 (스켈레톤 UI가 아닌 실제 텍스트가 뜰 때까지)
        try:
            # 1차 대기: 컨테이너
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_item"))
            )
            # 2차 대기: 실제 제목 요소 (스켈레톤에는 strong.title에 텍스트가 없거나 클래스가 다를 수 있음)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_item strong.title"))
            )
            time.sleep(3) # 렌더링 안정화
        except Exception as e:
            print(f"로딩 대기 중 타임아웃: {e}")

        print(f"이동 후 URL: {driver.current_url}")
        
        # 5. 데이터 추출
        elements = driver.find_elements(By.CSS_SELECTOR, "div.feed_item")
        print(f"발견된 게시글 수: {len(elements)}")
        
        if len(elements) == 0:
            print("게시글을 찾지 못했습니다. 페이지 소스 일부:")
            print(driver.page_source[:2000])
        
        # 최신 20개 검사
        for i, el in enumerate(elements[:20]): 
            try:
                title_el = el.find_element(By.CSS_SELECTOR, "strong.title")
                link_el = el.find_element(By.CSS_SELECTOR, "div.feed_content > a")
                date_el = el.find_element(By.CSS_SELECTOR, "span.date")
                
                # 좋아요/댓글 수 추출 (선택자는 네이버 카페 피드 구조에 맞춰 추정)
                # 보통 div.feed_like > span.num, div.feed_comment > span.num 형태임
                like_count = "0"
                comment_count = "0"
                
                try:
                    like_el = el.find_element(By.CSS_SELECTOR, "div.feed_like span.num")
                    like_count = like_el.text.strip()
                except:
                    pass # 없으면 0
                    
                try:
                    comment_el = el.find_element(By.CSS_SELECTOR, "div.feed_comment span.num")
                    comment_count = comment_el.text.strip()
                except:
                    pass # 없으면 0

                title = title_el.text.strip()
                link = link_el.get_attribute('href').strip()
                date_text = date_el.text.strip()
                
                # 절대 시간으로 변환
                absolute_time = parse_time_string(date_text)
                
                # print(f"게시글 {i+1} 추출 성공: {title} / {date_text} -> {absolute_time}")
                
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

async def main():
    print("네이버 카페 피드 확인 중... (Selenium Headless + Anti-Detect)")
    
    # 1. 기존에 보낸 게시글 목록 로드
    sent_posts = load_sent_posts()
    print(f"기존에 보낸 게시글 수: {len(sent_posts)}")
    
    # 2. 새 게시글 가져오기
    posts = get_feed_posts()
    
    if not posts:
        print("새로운 게시글이 없거나 가져오는데 실패했습니다.")
        return

    new_posts_count = 0
    
    # 3. 중복 확인 및 전송
    for post in posts:
        link = post['link']
        
        # 이미 보낸 링크라면 건너뜀
        if link in sent_posts:
            continue
            
        # 전송 메시지 포맷 변경
        # 오후 12:12
        # 제목
        # 링크
        # 좋아요 99 댓글 99
        msg = f"{post['absolute_time']}\n{post['title']}\n{post['link']}\n좋아요 {post['like']} 댓글 {post['comment']}"
        
        await send_telegram_message(msg)
        
        # 보낸 목록에 추가
        sent_posts.append(link)
        new_posts_count += 1
        
        # 텔레그램 전송 딜레이 (안전장치)
        time.sleep(1)
            
    if new_posts_count == 0:
        print("새로운 게시글이 없습니다.")
    else:
        print(f"{new_posts_count}개의 새 글 알림을 전송했습니다.")
        # 4. 업데이트된 목록 저장
        save_sent_posts(sent_posts)

if __name__ == "__main__":
    asyncio.run(main())
