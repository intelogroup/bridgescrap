import undetected_chromedriver as uc

class CustomChrome(uc.Chrome):
    """Custom Chrome driver that suppresses the __del__ method and adds additional stealth features"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add additional stealth configurations
        self.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // Pass the Webdriver Test.
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Pass the Chrome Test.
                window.chrome = {
                    runtime: {}
                };
                
                // Pass the Permissions Test.
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """
        })
    
    def __del__(self):
        """Override the destructor to prevent invalid handle errors"""
        try:
            if hasattr(self, 'service') and self.service.process:
                self.quit()
        except Exception:
            pass  # Suppress any errors during cleanup
