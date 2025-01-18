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
                        random_delay()  # Add delay after finding table
                        break
                except TimeoutException:
                    continue
        
        if not table:
            logger.error("Could not find assignments table with any of the locators")
            return []
        
        assignments = []
        try:
            # Wait for rows to be present
            rows = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'tr:not(:first-child)'))
            )
            
            for row in rows:
                try:
                    random_delay()  # Add delay between processing rows
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
            logger.error("Could not find table rows")
            return []
            
    except Exception as e:
        logger.error(f"Error in get_assignments: {str(e)}. Exiting function.")
        raise  # Re-raise for retry mechanism
