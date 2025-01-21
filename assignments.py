import logging
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from utils import wait_for_element
from driver_setup import random_delay
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_assignments(driver) -> list:
    """Retrieve available assignments from the platform with retry logic"""
    try:
        logger.info("Navigating to assignments page...")
        driver.get("https://www.lbridge.com/Interpreters/open_assignments.aspx")
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        # Check if we're logged in by looking for login-related elements
        try:
            login_elements = driver.find_elements(By.CSS_SELECTOR, 'input[type="password"], #login, .login-form')
            if login_elements:
                logger.error("Found login elements - session may have expired")
                raise Exception("Session expired or not logged in")
        except Exception as e:
            logger.error(f"Error checking login state: {str(e)}")
            raise
        
        # Verify we're on the correct page
        current_url = driver.current_url
        logger.info(f"Current URL after navigation: {current_url}")
        
        # Handle potential redirects
        if "login" in current_url.lower():
            logger.error("Redirected to login page")
            raise Exception("Session expired - redirected to login")
        elif "open_assignments" not in current_url.lower():
            logger.error(f"Not on assignments page. Current URL: {current_url}")
            # Try to navigate again
            driver.get("https://www.lbridge.com/Interpreters/open_assignments.aspx")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            current_url = driver.current_url
            if "open_assignments" not in current_url.lower():
                raise Exception(f"Failed to navigate to assignments page. Current URL: {current_url}")
        
        # Add random delay after navigation
        random_delay()
        
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
            
            # Skip header row if present
            rows = rows[1:] if rows else []
            
            for row in rows:
                try:
                    # No need for delay between rows as we're just reading data
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if len(cells) >= 6:
                        assignment = {
                            'customer': cells[0].text.strip(),
                            'date_time': cells[1].text.strip(),
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
