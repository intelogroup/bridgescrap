import os
import logging
import random
import platform
import subprocess
import time
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from custom_chrome import CustomChrome
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# List of common user agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]

def get_chrome_version():
    """Get the installed Chrome version based on the platform"""
    try:
        system = platform.system().lower()
        version = None
        
        if system == "linux":
            # For Ubuntu/Linux, try multiple commands
            commands = [
                ['chromium-browser', '--version'],
                ['google-chrome', '--version'],
                ['google-chrome-stable', '--version']
            ]
            
            for cmd in commands:
                try:
                    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                    version_str = output.decode().strip().split()[-1]
                    logger.info(f"Detected Chrome version string: {version_str}")
                    
                    # Extract major version
                    major_version = version_str.split('.')[0]
                    try:
                        version = int(major_version)
                        logger.info(f"Successfully parsed major version: {version}")
                        break
                    except ValueError:
                        logger.warning(f"Could not parse major version from: {major_version}")
                        continue
                except (subprocess.CalledProcessError, IndexError) as e:
                    logger.warning(f"Failed to get version using {cmd}: {str(e)}")
                    continue
                    
        elif system == "darwin":
            try:
                output = subprocess.check_output(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'])
                version = int(output.decode().strip().split()[-1].split('.')[0])
            except Exception as e:
                logger.warning(f"Failed to get Chrome version on MacOS: {str(e)}")
                
        elif system == "windows":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Google\Chrome\BLBeacon')
                version_str = winreg.QueryValueEx(key, 'version')[0]
                version = int(version_str.split('.')[0])
            except Exception as e:
                logger.warning(f"Failed to get Chrome version on Windows: {str(e)}")
                
        # If version detection failed, use a safe default
        if not version:
            version = 108
            logger.info(f"Using default Chrome version: {version}")
        else:
            logger.info(f"Using detected Chrome version: {version}")
            
        return version
            
    except Exception as e:
        logger.error(f"Error in get_chrome_version: {str(e)}")
        logger.info("Falling back to default Chrome version: 108")
        return 108

def random_delay():
    """Add a random delay between operations"""
    delay = random.uniform(2, 5)
    logger.info(f"Adding random delay of {delay:.2f} seconds")
    time.sleep(delay)
    return delay

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def setup_driver():
    """Set up and configure the Chrome WebDriver with anti-detection measures"""
    try:
        # Random window size
        width = random.randint(1800, 1920)
        height = random.randint(1000, 1080)
        
        # Random user agent
        user_agent = random.choice(USER_AGENTS)
        logger.info(f"Using user agent: {user_agent}")
        logger.info(f"Using window size: {width}x{height}")
        
        # Get Chrome version
        chrome_version = get_chrome_version()
        logger.info(f"Using Chrome version: {chrome_version}")
        
        # Set up Chrome options
        options = Options()
        options.add_argument(f'--window-size={width},{height}')
        options.add_argument(f'user-agent={user_agent}')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        if os.getenv('GITHUB_ACTIONS'):
            options.add_argument('--headless=new')
            logger.info("Running in GitHub Actions environment with headless mode")
        
        # Initialize the driver with detected version
        driver = CustomChrome(
            driver_executable_path=ChromeDriverManager().install(),
            options=options,
            version_main=chrome_version,
            headless=True if os.getenv('GITHUB_ACTIONS') else False,
            use_subprocess=True
        )
        
        driver.implicitly_wait(10)
        
        # Execute CDP commands to prevent detection
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Pass the Chrome Test
                window.chrome = {
                    runtime: {}
                };
                
                // Pass the Permissions Test
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """
        })
        
        logger.info("WebDriver setup completed successfully")
        return driver
    except Exception as e:
        logger.error(f"Error setting up driver: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise  # Re-raise for retry mechanism
