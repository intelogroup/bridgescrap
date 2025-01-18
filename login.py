import os
import logging
import time
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from driver_setup import setup_driver, random_delay
from utils import wait_for_element
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

def normalize_url(url: str) -> str:
    """Normalize URL for comparison"""
    parsed = urlparse(url.lower())
    # Remove protocol and www
    domain = parsed.netloc.replace('www.', '')
    path = parsed.path.rstrip('/')
    return f"{domain}{path}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def login(username: str, password: str) -> webdriver.Chrome:
    """Login to the Bridge platform with retry logic"""
    driver = None
    try:
        logger.info("Setting up WebDriver...")
        driver = setup_driver()
        if not driver:
            logger.error("Failed to set up WebDriver")
            return None

        logger.info("Attempting to login...")
        driver.get("https://www.lbridge.com/Login.aspx")
        
        # Add random delay before login
        random_delay()
        
        # Wait for login form elements with random delays between actions
        username_field = wait_for_element(driver, By.NAME, 'ctl00$MainContent$txtUserName', timeout=15, description="username field")
        if not username_field:
            logger.error("Username field not found")
            if driver:
                driver.quit()
            return None
            
        random_delay()
        password_field = wait_for_element(driver, By.NAME, 'ctl00$MainContent$txtPassword', timeout=15, description="password field")
        if not password_field:
            logger.error("Password field not found")
            if driver:
                driver.quit()
            return None
            
        random_delay()
        submit_button = wait_for_element(driver, By.NAME, 'ctl00$MainContent$cmdSubmit', timeout=15, description="submit button")
        if not submit_button:
            logger.error("Submit button not found")
            if driver:
                driver.quit()
            return None
        
        # Fill in login form with random delays
        username_field.clear()
        username_field.send_keys(username)
        random_delay()
        
        password_field.clear()
        password_field.send_keys(password)
        random_delay()
        
        logger.info("Submitting login form...")
        submit_button.click()
        
        # Wait for redirect after login
        try:
            WebDriverWait(driver, 10).until(
                lambda d: normalize_url(d.current_url) != normalize_url("https://www.lbridge.com/Login.aspx")
            )
            
            # Check if login was successful
            current_url = normalize_url(driver.current_url)
            expected_urls = [
                normalize_url("lbridge.com/interpreters/notifications"),
                normalize_url("lbridge.com/Interpreters/notifications"),
                normalize_url("www.lbridge.com/interpreters/notifications")
            ]
            
            if any(current_url == expected for expected in expected_urls):
                logger.info(f"Login successful! Current URL: {driver.current_url}")
                return driver
            else:
                logger.error(f"Login failed. Current URL: {driver.current_url}")
                if os.getenv('GITHUB_ACTIONS'):
                    logger.error(f"Page source:\n{driver.page_source}")
                if driver:
                    driver.quit()
                return None
                
        except TimeoutException:
            logger.error("Timeout waiting for login redirect")
            if os.getenv('GITHUB_ACTIONS'):
                logger.error(f"Page source at timeout:\n{driver.page_source}")
            if driver:
                driver.quit()
            return None
            
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        if driver:
            driver.quit()
        raise  # Re-raise for retry mechanism
