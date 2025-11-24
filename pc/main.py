import os
import time
import asyncio
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot

# 환경 변수 로드
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 전역 변수
last_feed_content = []

async def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram 설정이 누락되었습니다. .env 파일을 확인해주세요.")
        return

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"텔레그램 전송 성공: {message[:20]}...")
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def setup_driver():
    """Selenium WebDriver 설정"""
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # 로그인 필요하므로 헤드리스 모드 끔
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # 사용자 데이터 디렉토리를 지정하여 로그인 세션 유지 (선택 사항)
    # options.add_argument(f"user-data-dir={os.getcwd()}/chrome_profile")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def check_login(driver):
    """로그인 여부 확인 및 대기"""
    driver.get("https://section.cafe.naver.com/ca-fe/home/feed")
    
    print("페이지 로딩 중...")
    time.sleep(3)
    
    # 로그인 페이지로 리다이렉트 되었는지 확인 (URL 또는 특정 요소로 확인)
    if "nid.naver.com" in driver.current_url:
        print("로그인이 필요합니다. 브라우저에서 로그인을 진행해주세요.")
        print("로그인이 완료되면 자동으로 피드 감지를 시작합니다.")
        
        # 로그인이 완료될 때까지 대기 (URL이 피드 페이지로 바뀔 때까지)
        while "nid.naver.com" in driver.current_url:
            time.sleep(1)
        
        print("로그인 감지됨! 피드 모니터링을 시작합니다.")
        # 로그인 후 페이지가 완전히 로드될 때까지 잠시 대기
        time.sleep(5)

def get_feed_items(driver):
    """피드 아이템 추출"""
    posts = []
    try:
        # 피드 리스트 요소 찾기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed_list_wrap"))
        )
        
        # 게시글 요소들 가져오기
        elements = driver.find_elements(By.CSS_SELECTOR, "div.feed_item")
        
        for el in elements[:5]: # 최신 5개만 확인
            try:
                title_el = el.find_element(By.CSS_SELECTOR, "strong.title")
                link_el = el.find_element(By.CSS_SELECTOR, "div.feed_content > a")
                
                title = title_el.text
                link = link_el.get_attribute('href')
                
                if title and link:
                    posts.append({'title': title, 'link': link})
            except Exception as e:
                # print(f"요소 추출 실패: {e}")
                continue
                
    except Exception as e:
        # print(f"피드 가져오기 오류 (아직 로딩 중일 수 있음): {e}")
        pass
        
    return posts

async def main():
    driver = setup_driver()
    
    try:
        check_login(driver)
        
        print("피드 모니터링 시작... (Ctrl+C로 종료)")
        
        global last_feed_content
        
        # 디버깅: 페이지 소스 저장
        try:
            with open("debug_feed.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            print("디버깅용 HTML 파일(debug_feed.html)을 저장했습니다.")
        except Exception as e:
            print(f"디버깅 파일 저장 실패: {e}")

        while True:
            current_posts = get_feed_items(driver)
            
            if not current_posts:
                print("게시글을 찾을 수 없습니다. debug_feed.html 파일을 확인해보세요.")
            else:
                print(f"현재 감지된 게시글 수: {len(current_posts)}")
            
            # 첫 실행 시에는 알림을 보내지 않고 기준점만 잡음
            if not last_feed_content and current_posts:
                last_feed_content = current_posts
                print(f"초기 피드 데이터 로드 완료: {len(current_posts)}개")
                # 초기 로드 후 바로 다음 루프로 넘어가지 않고, 현재 상태를 출력해봄
                for p in current_posts:
                    print(f" - {p['title']}")
                continue
            
            # 새로운 게시글 확인
            new_posts = []
            if current_posts:
                last_titles = [p['title'] for p in last_feed_content]
                
                for post in current_posts:
                    if post['title'] not in last_titles:
                        new_posts.append(post)
            
            # 알림 전송 및 상태 업데이트
            if new_posts:
                print(f"새로운 게시글 {len(new_posts)}개 발견!")
                for post in new_posts:
                    msg = f"[새 글 알림]\n{post['title']}\n{post['link']}"
                    await send_telegram_message(msg)
                
                # 상태 업데이트 (단순하게 최신 리스트로 교체)
                last_feed_content = current_posts
            
            # 폴링 주기 (예: 60초)
            time.sleep(60)
            driver.refresh()
            
    except KeyboardInterrupt:
        print("프로그램을 종료합니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    asyncio.run(main())
