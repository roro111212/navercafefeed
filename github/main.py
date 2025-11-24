import os
import asyncio
import time
from datetime import datetime
from telegram import Bot
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# GitHub Secrets에서 환경 변수 로드
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
NAVER_COOKIE = os.environ.get('NAVER_COOKIE') # NID_AUT=...; NID_SES=...

async def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정이 누락되었습니다.")
        return
    try:
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
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    posts = []
    try:
        # 1. 네이버 도메인으로 이동 (쿠키 설정을 위해)
        driver.get("https://www.naver.com")
        
        # 2. 쿠키 파싱 및 설정
        # NAVER_COOKIE 예시: "NID_AUT=...; NID_SES=..."
        cookie_pairs = NAVER_COOKIE.split(';')
        for pair in cookie_pairs:
            if '=' in pair:
                key, value = pair.strip().split('=', 1)
                driver.add_cookie({
                    'name': key,
                    'value': value,
                    'domain': '.naver.com'
                })
        
        # 3. 피드 페이지로 이동
        driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
        
        # 4. 로딩 대기 (게시글 요소가 나타날 때까지)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_item"))
            )
        except:
            print("게시글 로딩 시간 초과 또는 게시글 없음")
            # 디버깅용 소스 출력 (너무 길면 자름)
            # print(driver.page_source[:1000])
        
        # 5. 데이터 추출
        elements = driver.find_elements(By.CSS_SELECTOR, "div.feed_item")
        
        for el in elements[:5]: # 최신 5개
            try:
                title_el = el.find_element(By.CSS_SELECTOR, "strong.title")
                link_el = el.find_element(By.CSS_SELECTOR, "div.feed_content > a")
                date_el = el.find_element(By.CSS_SELECTOR, "span.date")
                
                title = title_el.text
                link = link_el.get_attribute('href')
                date_text = date_el.text
                
                if title and link:
                    posts.append({
                        'title': title, 
                        'link': link,
                        'date': date_text
                    })
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"피드 가져오기 실패: {e}")
    finally:
        driver.quit()
        
    return posts

async def main():
    print("네이버 카페 피드 확인 중... (Selenium Headless)")
    posts = get_feed_posts()
    
    if not posts:
        print("새로운 게시글이 없거나 가져오는데 실패했습니다.")
        return

    target_times = ["방금 전", "1분 전", "2분 전", "3분 전", "4분 전", "5분 전"]
    
    new_posts_count = 0
    for post in posts:
        if any(t in post['date'] for t in target_times):
            msg = f"[새 글 알림]\n{post['title']}\n{post['link']}\n({post['date']})"
            await send_telegram_message(msg)
            new_posts_count += 1
            
    if new_posts_count == 0:
        print("최근 5분 내 작성된 새 글이 없습니다.")
    else:
        print(f"{new_posts_count}개의 새 글 알림을 전송했습니다.")

if __name__ == "__main__":
    asyncio.run(main())
