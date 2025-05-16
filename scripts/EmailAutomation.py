"""
-----------------------------------------
Head-less helpers for logging into Gmail once and sending many messages
safely from the *same* browser session, using the exact flow from your
emailtry.py (incognito, JS-click, active_element for To: field).
"""

from __future__ import annotations
import time
from typing import Tuple

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


__all__ = ["setup_email_driver", "send_email"]


def _build_chrome() -> webdriver.Chrome:
    """Return a configured incognito Chrome driver matching emailtry.py."""
    opts = webdriver.ChromeOptions()
    opts.add_argument("--incognito")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-blink-features=AutomationControlled")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )


def setup_email_driver(
    gmail_email: str,
    gmail_password: str,
    *,
    wait_timeout: int = 20,
) -> Tuple[webdriver.Chrome, WebDriverWait]:
    """
    Launch Chrome, log into Gmail, and return (driver, wait).
    Mirrors your working emailtry.py flow.
    """
    driver = _build_chrome()
    wait   = WebDriverWait(driver, wait_timeout)

    # 1) go to Gmail sign-in
    driver.get(
        "https://accounts.google.com/ServiceLogin?service=mail"
    )

    # 2) enter email → Next
    wait.until(EC.visibility_of_element_located((By.ID, "identifierId"))).send_keys(gmail_email)
    wait.until(EC.element_to_be_clickable((By.ID, "identifierNext"))).click()

    # 3) enter password → Next
    # some Gmail pages still use name="Passwd", others name="password"
    try:
        pw = wait.until(EC.visibility_of_element_located((By.NAME, "Passwd")))
    except:
        pw = wait.until(EC.visibility_of_element_located((By.NAME, "password")))
    pw.send_keys(gmail_password)
    wait.until(EC.element_to_be_clickable((By.ID, "passwordNext"))).click()

    # 4) wait for Inbox to load
    wait.until(EC.title_contains("Inbox"))
    time.sleep(2)  # let any UI settle
    return driver, wait


def send_email(
    driver: webdriver.Chrome,
    wait:   WebDriverWait,
    *,
    receiver_email: str,
    subject: str,
    message_body: str,
) -> None:
    """
    Compose & send one e-mail, blocking until Gmail is ready for the next.
    Uses JS-click, active_element for To:, and waits for the compose dialog to
    close so no “element not interactable” errors on the next iteration.
    """
    if not receiver_email:
        raise ValueError("Empty receiver_email – skipping row")

    # 1) click Compose button via JS
    compose_btn = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".T-I.T-I-KE.L3"))
    )
    driver.execute_script("arguments[0].click();", compose_btn)
    time.sleep(3)  # allow compose dialog animation

    # 2) type into the active “To:” field
    active = driver.switch_to.active_element
    active.send_keys(receiver_email)
    time.sleep(1)

    # 3) Subject
    subj_el = wait.until(EC.visibility_of_element_located((By.NAME, "subjectbox")))
    driver.execute_script("arguments[0].scrollIntoView(true);", subj_el)
    driver.execute_script("arguments[0].click();", subj_el)
    subj_el.send_keys(subject)
    time.sleep(1)

    # 4) Body
    body_el = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "div[aria-label='Message Body']"))
    )
    driver.execute_script("arguments[0].scrollIntoView(true);", body_el)
    driver.execute_script("arguments[0].click();", body_el)
    body_el.send_keys(message_body)
    time.sleep(1)

    # 5) Send (Ctrl+Enter)
    body_el.send_keys(Keys.CONTROL, Keys.ENTER)

    # 6) wait for the compose window to close before returning
    #    this matches the “Message sent” toast disappearing
    try:
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "div[aria-label='New Message']")))
    except:
        # fallback sleep if needed
        time.sleep(2)
