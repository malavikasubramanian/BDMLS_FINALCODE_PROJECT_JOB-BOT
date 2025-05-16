# ────────────────────────────────────────────────────────────────────
# Bulk LinkedIn DM sender
# • Opens profile
# • Clicks Message
# • Types + sends
# • **NEW → JS click** on the overlay’s ✕ close button so the drawer
#   is gone before the loop proceeds to the next profile.
# --------------------------------------------------------------------

from __future__ import annotations

import time
import urllib.parse
from typing import Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    NoSuchElementException,
)
from webdriver_manager.chrome import ChromeDriverManager


# ───────────────────────── driver setup ────────────────────────────
def setup_driver(headless: bool = False) -> webdriver.Chrome:
    """Incognito Chrome with optional headless flag."""
    opts = webdriver.ChromeOptions()
    opts.add_argument("--incognito")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if headless:
        opts.add_argument("--headless=new")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )


# ───────────────────────── authentication ──────────────────────────
def login_to_linkedin(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    email: str,
    password: str,
) -> None:
    """Logs in and pauses if LinkedIn throws a checkpoint screen."""
    driver.get("https://www.linkedin.com/login")

    wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(email)
    wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys(password)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    time.sleep(5)  # Let the page settle / possible 2-FA prompt

    if "checkpoint" in driver.current_url:
        print("🔒 Verification required! Please complete it manually.")
        while "checkpoint" in driver.current_url:
            time.sleep(5)
        print("✅ Verification completed. Continuing…")


# ───────────────────────── search helpers ──────────────────────────
def construct_search_url(name: str, organization: str, position: str) -> str | None:
    """Build a LinkedIn search URL for the given keywords."""
    keywords = [k.strip() for k in (name, organization, position) if k.strip()]
    if not keywords:
        print("⚠️ Provide at least one search term.")
        return None
    query = urllib.parse.quote(" ".join(keywords))
    return f"https://www.linkedin.com/search/results/all/?keywords={query}&origin=GLOBAL_SEARCH_HEADER"


def select_people_tab(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    """Ensure the ‘People’ filter is active on the search results page."""
    try:
        people_tab = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//li[contains(@class,'search-reusables__primary-filter')]/button")
            )
        )
        if people_tab.get_attribute("aria-pressed") != "true":
            people_tab.click()
            print("✅ Clicked on the 'People' tab.")
            time.sleep(3)
        else:
            print("✅ 'People' tab already selected.")
    except Exception as e:
        print("❌ Error clicking 'People' tab:", e)


def open_first_profile(driver: webdriver.Chrome, wait: WebDriverWait) -> str | None:
    """Click the first result in the list and return the profile URL."""
    try:
        first_div = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div.linked-area.flex-1.cursor-pointer"))
        )
        print("✅ Clicking the first profile result…")
        driver.execute_script("arguments[0].scrollIntoView();", first_div)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", first_div)
        time.sleep(5)
        url = driver.current_url
        print(f"✅ Opened first profile: {url}")
        return url
    except Exception as e:
        print("❌ Error opening profile:", e)
        return None


# ───────────────────────── message helpers ─────────────────────────
MESSAGE_BUTTON_XPATHS = [
    "//button[contains(@aria-label,'Message')]",
    "//button[span[text()='Message']]",
    "//button[contains(.,'Message')]",
    "//button[contains(@aria-label,'InMail')]",
    "//a[contains(@aria-label,'Message')]",
]


def click_message_button(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
    """Find the Message/InMail button via several XPath variants."""
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    for xp in MESSAGE_BUTTON_XPATHS:
        try:
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
            driver.execute_script("arguments[0].scrollIntoView(true);", btn)
            time.sleep(1)
            try:
                btn.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", btn)
            print(f"✅ Clicked the 'Message' button via {xp}")
            return True
        except Exception:
            continue

    print("❌ No visible 'Message' button found.")
    return False


def _js_close_overlay(driver: webdriver.Chrome, wait: WebDriverWait) -> bool:
    OVERLAY = "div.msg-overlay-conversation-bubble"
    # (1) wait up to 5s for the overlay to appear
    try:
        WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, OVERLAY))
        )
    except TimeoutException:
        return False

    # (2) run the JS to click the ✕
    driver.execute_script(
        "const btn = document.querySelector('button.msg-overlay-bubble-header__control');"
        "if (btn) btn.click();"
    )

    # (3) wait until it’s gone
    try:
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, OVERLAY)))
    except TimeoutException:
        pass

    return True

    

    # 4. Wait for the overlay to fully disappear
    try:
        wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, OVERLAY))
        )
    except TimeoutException:
        # if it’s stubborn, we at least clicked
        pass

    return True


def send_message_on_profile(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    message_text: str,
) -> None:
    """Click Message → type → send → **close overlay via JS**."""
    if not click_message_button(driver, wait):
        print("⚠️ Message button missing; skipping.")
        return

    try:
        box = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[@aria-label='Write a message…']"))
        )
        box.send_keys(message_text)

        send_btn = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[@type='submit' and contains(@class,'msg-form__send-button')]")
            )
        )
        send_btn.click()
        print("✅ Message sent!")

        # ——— NEW BIT ———
        # closed = _js_close_overlay(driver, wait)
        # if not closed:
        #     print("⚠️ Close button not found—overlay may still be open.")
        # ————————————

    except Exception as e:
        print("❌ Error while sending:", e)


# ───────────────────────── example runner ──────────────────────────
def main() -> None:
    linkedin_email    = "your_linkedin_email"
    linkedin_password = "your_linkedin_password"
    recipient_name    = "John Doe"
    organization      = "Example Corp"
    position          = "Software Engineer"
    msg_text          = "Hi John! 👋 Would love to connect."

    driver = setup_driver()
    wait   = WebDriverWait(driver, 20)

    try:
        login_to_linkedin(driver, wait, linkedin_email, linkedin_password)

        url = construct_search_url(recipient_name, organization, position)
        if not url:
            return

        driver.get(url)
        select_people_tab(driver, wait)

        profile = open_first_profile(driver, wait)
        if not profile:
            return

        send_message_on_profile(driver, wait, msg_text)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
