import logging
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import time
import random
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from utils import wait_for_element
from driver_setup import random_delay
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Custom exceptions for better error handling
class SessionExpiredException(Exception):
    """Raised when the session has expired"""
    pass

class WebsiteErrorException(Exception):
    """Raised when the website returns an error"""
    pass

class MaintenanceModeException(Exception):
    """Raised when the site is in maintenance mode"""
    pass

class NavigationException(Exception):
    """Raised when navigation fails"""
    pass

@retry(
    stop=stop_after_attempt(5),  # Increase retry attempts
    wait=wait_exponential(multiplier=1, min=4, max=30),  # Longer max wait time
    retry=retry_if_exception_type((
        TimeoutException,
        NoSuchElementException,
        Exception  # Catch all for network issues
    )),
    before_sleep=lambda retry_state: logger.warning(
        f"Retry attempt {retry_state.attempt_number} after error: {retry_state.outcome.exception()}"
    )
)
def get_assignments(driver) -> list:
    """
    Retrieve available assignments from the platform with enhanced retry logic
    
    Returns:
        list: List of assignment dictionaries
        
    Raises:
        Exception: If unable to retrieve assignments after all retries
    """
    try:
        logger.info("Navigating to assignments page...")
        driver.get("https://www.lbridge.com/Interpreters/open_assignments.aspx")
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        # Enhanced session validation
        try:
            # Check for multiple indicators of session state
            login_elements = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"], #login, .login-form')
            error_elements = driver.find_elements(By.CSS_SELECTOR, '.error-message, .alert-error')
            session_timeout_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'session') and contains(text(), 'expired')]")
            
            if login_elements:
                logger.error("Found login elements - session expired")
                raise SessionExpiredException("Session expired - login elements found")
            elif error_elements:
                error_text = error_elements[0].text if error_elements else "Unknown error"
                logger.error(f"Found error message: {error_text}")
                raise WebsiteErrorException(f"Website error: {error_text}")
            elif session_timeout_elements:
                logger.error("Session timeout detected")
                raise SessionExpiredException("Session timeout message found")
                
        except (SessionExpiredException, WebsiteErrorException) as e:
            logger.error(f"Session validation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during session validation: {str(e)}")
            raise
        
        # Enhanced URL validation with health check
        current_url = driver.current_url
        logger.info(f"Current URL after navigation: {current_url}")
        
        # Define valid URLs and redirects
        VALID_URLS = [
            "lbridge.com/Interpreters/open_assignments",
            "www.lbridge.com/Interpreters/open_assignments"
        ]
        ERROR_INDICATORS = ["error", "maintenance", "unavailable", "login"]
        
        # Check if we're on a valid page
        if any(valid_url in current_url.lower() for valid_url in VALID_URLS):
            logger.info("Successfully validated current URL")
        else:
            # Check for known error states
            if any(indicator in current_url.lower() for indicator in ERROR_INDICATORS):
                if "login" in current_url.lower():
                    logger.error("Redirected to login page")
                    raise SessionExpiredException("Session expired - redirected to login")
                elif "maintenance" in current_url.lower():
                    logger.error("Site is in maintenance mode")
                    raise MaintenanceModeException("Site is under maintenance")
                elif "error" in current_url.lower() or "unavailable" in current_url.lower():
                    logger.error("Site error page detected")
                    raise WebsiteErrorException("Site error page encountered")
            
            # If not on a valid page or known error page, try to recover
            logger.warning(f"Not on assignments page. Current URL: {current_url}")
            recovery_attempts = 3
            for attempt in range(recovery_attempts):
                try:
                    logger.info(f"Recovery attempt {attempt + 1}/{recovery_attempts}")
                    driver.get("https://www.lbridge.com/Interpreters/open_assignments.aspx")
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script('return document.readyState') == 'complete'
                    )
                    current_url = driver.current_url
                    if any(valid_url in current_url.lower() for valid_url in VALID_URLS):
                        logger.info("Successfully recovered navigation")
                        break
                except Exception as e:
                    if attempt == recovery_attempts - 1:
                        raise NavigationException(f"Failed to recover navigation after {recovery_attempts} attempts")
                    logger.warning(f"Recovery attempt {attempt + 1} failed: {str(e)}")
        
        # Add intelligent delay based on page load time
        start_time = time.time()
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script('return document.readyState') == 'complete' and
                     len(d.find_elements(By.TAG_NAME, 'table')) > 0
        )
        load_time = time.time() - start_time
        
        # Adjust delay based on load time to avoid overwhelming the server
        if load_time < 2:
            delay = random.uniform(2, 4)
        else:
            delay = random.uniform(1, 2)
        logger.info(f"Page loaded in {load_time:.2f}s, adding {delay:.2f}s delay")
        time.sleep(delay)
        
        # Try to find the table directly with a more flexible approach
        table = None
        try:
            # First try: Wait for any table to be present
            table = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, 'table'))
            )
            logger.info("Found table using generic table tag")
            logger.info(f"Table HTML: {table.get_attribute('outerHTML')[:500]}")
        except TimeoutException:
            logger.info("Could not find table using generic tag, trying specific locators")
            
            # Try different possible locators for the assignments table
            table_locators = [
                (By.ID, 'gvOrders'),
                (By.CSS_SELECTOR, '[id*="gvOrders"]'),
                (By.CSS_SELECTOR, 'table[role="grid"]'),
                (By.XPATH, "//table[contains(@id, 'gvOrders')]"),
                (By.XPATH, "//table[contains(@class, 'grid')]"),
                (By.XPATH, "//div[contains(@class, 'gridview')]//table")
            ]
            
            for selector_type, selector_value in table_locators:
                try:
                    logger.info(f"Attempting to find table with locator: {selector_type}={selector_value}")
                    table = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    if table:
                        logger.info(f"Found table with {selector_value}")
                        logger.info(f"Table HTML: {table.get_attribute('outerHTML')[:500]}")
                        random_delay()  # Add delay after finding table
                        break
                except TimeoutException:
                    continue
        
        if not table:
            logger.error("Could not find assignments table with any of the locators")
            return []
            
        # Check for "no assignments" or empty table indicators
        try:
            no_data_messages = driver.find_elements(By.XPATH, 
                "//*[contains(text(), 'No assignments') or contains(text(), 'No records') or contains(text(), 'No data')]")
            if no_data_messages:
                logger.info("Found 'no assignments' message: " + no_data_messages[0].text)
                return []
                
            # Also check if the table is empty or only contains headers
            table_text = table.text.strip()
            if not table_text:
                logger.info("Table is empty")
                return []
            logger.info(f"Table text preview: {table_text[:200]}")
        except Exception as e:
            logger.error(f"Error checking for empty table: {str(e)}")
        
        assignments = []
        try:
            # Wait for table to be fully loaded
            WebDriverWait(driver, 10).until(
                lambda d: len(table.find_elements(By.TAG_NAME, 'tr')) > 0
            )
            
            # Get all rows including their HTML for debugging
            all_rows = table.find_elements(By.TAG_NAME, 'tr')
            logger.info(f"Found {len(all_rows)} total rows")
            for i, row in enumerate(all_rows[:2]):  # Log first two rows for debugging
                logger.info(f"Row {i} HTML: {row.get_attribute('outerHTML')}")
            
            # Filter out header rows by checking cell type (th vs td)
            rows = []
            for row in all_rows:
                th_cells = row.find_elements(By.TAG_NAME, 'th')
                td_cells = row.find_elements(By.TAG_NAME, 'td')
                if len(td_cells) > 0 and len(th_cells) == 0:  # Only include rows with td cells
                    rows.append(row)
            
            logger.info(f"Found {len(rows)} data rows after filtering headers")
            
            for row in rows:
                try:
                    # No need for delay between rows as we're just reading data
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 6:
                        # Clean and format date_time
                        date_time = ' '.join(cells[1].text.strip().split())  # Replace newlines with space
                        
                        assignment = {
                            'customer': cells[0].text.strip(),
                            'date_time': date_time,
                            'language': cells[2].text.strip(),
                            'service_type': cells[3].text.strip(),
                            'info': cells[4].text.strip(),
                            'comments': cells[5].text.strip(),
                        }
                        assignments.append(assignment)
                except Exception as e:
                    logger.error(f"Error processing row: {str(e)}. Skipping to next row.")
                    continue
            
            logger.info(f"Found {len(assignments)} assignments")
            return assignments
            
        except NoSuchElementException:
            logger.error("Could not find table rows in the assignments table")
            logger.error(f"Current URL: {driver.current_url}")
            logger.error(f"Page source preview: {driver.page_source[:500]}")
            return []
            
    except Exception as e:
        logger.error(f"Error in get_assignments: {str(e)}. Exiting function.")
        raise  # Re-raise for retry mechanism
