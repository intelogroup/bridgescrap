import os
import logging
import random
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

def random_wait_time():
    """Generate a random wait time between 1 and 3 seconds"""
    return random.uniform(1, 3)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def wait_for_element(driver, by, value, timeout=10, description="element"):
    """Wait for and find an element with explicit wait and retry logic"""
    try:
        # Add random initial delay
        initial_delay = random_wait_time()
        logger.info(f"Adding initial delay of {initial_delay:.2f} seconds before looking for {description}")
        time.sleep(initial_delay)
        
        # Use dynamic timeout with some randomization
        dynamic_timeout = timeout + random.uniform(0, 2)
        
        # Wait for element with detailed logging
        logger.info(f"Waiting up to {dynamic_timeout:.1f} seconds for {description}")
        element = WebDriverWait(driver, dynamic_timeout).until(
            EC.presence_of_element_located((by, value))
        )
        
        if not element:
            logger.error(f"Element found but returned None: {by}={value}")
            return None
            
        logger.info(f"Successfully found {description}")
        
        # Add small random delay after finding element
        post_delay = random_wait_time()
        logger.info(f"Adding post-delay of {post_delay:.2f} seconds")
        time.sleep(post_delay)
        
        return element
    except TimeoutException as e:
        logger.error(f"Timeout waiting for {description}. Element not found with locator: {by}={value}")
        if os.getenv('GITHUB_ACTIONS'):
            logger.error(f"Page source at time of error: {driver.page_source}")
        raise e  # Re-raise for retry mechanism
    except Exception as e:
        logger.error(f"Error finding {description}: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise e  # Re-raise for retry mechanism
