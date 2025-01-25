import os
import sys
import logging
import atexit
import traceback
from datetime import datetime
from typing import List, Dict, Tuple
from dotenv import load_dotenv
from login import login
from assignments import get_assignments
from email_handler import send_notification
from validation import validate_and_sanitize_assignments
from monitoring import metrics

# Set up logging first, before any other operations
if os.getenv('GITHUB_ACTIONS'):
    # Ensure logs directory exists
    os.makedirs('bridge_logs', exist_ok=True)
    
    # Configure logging for GitHub Actions
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join('bridge_logs', 'app.log')),
            logging.StreamHandler()
        ]
    )
else:
    # Local development logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def cleanup_driver(driver):
    """Safely cleanup the Chrome driver"""
    try:
        if driver and hasattr(driver, 'quit') and driver.service.process:
            driver.quit()
            logger.info("Chrome driver cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during driver cleanup: {str(e)}")
        logger.error(traceback.format_exc())

def format_assignment(assignment):
    """Format a single assignment for consistent structure"""
    formatted = {}
    
    # Fields that should be case-sensitive
    case_sensitive_fields = {'info', 'comments'}
    
    def normalize_value(value: str, preserve_case: bool = False) -> str:
        """Normalize a value by cleaning spaces and handling case"""
        if not isinstance(value, str):
            return str(value)
        
        # Replace multiple spaces with single space and strip
        value = ' '.join(value.split())
        
        if not value:
            return 'N/A'
            
        if not preserve_case:
            value = value.lower()
            
        return value
    
    # Copy and normalize direct fields
    direct_fields = {
        'customer': assignment.get('customer', ''),
        'language': assignment.get('language', ''),
        'service_type': assignment.get('service_type', ''),
        'comments': assignment.get('comments', '')
    }
    
    for field, value in direct_fields.items():
        preserve_case = field in case_sensitive_fields
        formatted[field] = normalize_value(value, preserve_case)
    
    # Extract fields from info
    info = assignment.get('info', '')
    info_lines = [line.strip() for line in info.split('\n') if line.strip()]
    
    # Initialize fields that should be extracted from info
    info_fields = {
        'contact_person_name_and_phone': 'N/A',
        'contact_person\'s_email_address': 'N/A',
        'address': 'N/A',
        'location': 'N/A',
        'client_name_and_phone': 'N/A'
    }
    formatted.update(info_fields)
    
    # Process each line of info
    current_field = None
    current_value = []
    
    for line in info_lines:
        # Check for field markers
        if 'Contact person\'s name and phone number:' in line:
            if current_field and current_value:
                formatted[current_field] = normalize_value(' '.join(current_value), True)
            current_field = 'contact_person_name_and_phone'
            current_value = [line.split(':', 1)[1].strip()]
        elif 'Contact person\'s email address:' in line:
            if current_field and current_value:
                formatted[current_field] = normalize_value(' '.join(current_value), True)
            current_field = 'contact_person\'s_email_address'
            current_value = [line.split(':', 1)[1].strip()]
        elif 'Address:' in line:
            if current_field and current_value:
                formatted[current_field] = normalize_value(' '.join(current_value), True)
            current_field = 'address'
            current_value = [line.split(':', 1)[1].strip()]
        elif 'Location:' in line:
            if current_field and current_value:
                formatted[current_field] = normalize_value(' '.join(current_value), True)
            current_field = 'location'
            current_value = [line.split(':', 1)[1].strip()]
        elif 'Client name and phone:' in line:
            if current_field and current_value:
                formatted[current_field] = normalize_value(' '.join(current_value), True)
            current_field = 'client_name_and_phone'
            current_value = [line.split(':', 1)[1].strip()]
        elif current_field:  # Continue previous field if no new field marker
            current_value.append(line)
    
    # Save the last field being processed
    if current_field and current_value:
        formatted[current_field] = normalize_value(' '.join(current_value), True)
    
    return formatted

from storage import AssignmentStorage

# Initialize storage
storage = AssignmentStorage()

def process_assignments(assignments: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], bool, List[str], List[Dict]]:
    """
    Process and validate assignments
    
    Args:
        assignments: Raw assignments from scraper
        
    Returns:
        Tuple of (processed assignments, has changes, change messages, new assignments)
    """
    # Validate and sanitize assignments
    sanitized_assignments, validation_errors = validate_and_sanitize_assignments(assignments)
    
    # Record any validation errors
    for assignment_errors in validation_errors.values():
        for error in assignment_errors:
            metrics.record_validation_error(f"{error.field}: {error.error}")
    
    # Compare with stored assignments
    has_changes, changes, new_assignments = storage.compare_assignments(sanitized_assignments)
    
    # If changes detected, save new assignments
    if has_changes:
        if not storage.save_assignments(sanitized_assignments):
            logger.error("Failed to save assignments")
            metrics.record_error("storage_write_error")
    
    return sanitized_assignments, has_changes, changes, new_assignments

def main():
    try:
        # Start metrics tracking
        metrics.start_run()
        
        # Ensure required directories exist
        os.makedirs('bridge_logs', exist_ok=True)
        os.makedirs('data', exist_ok=True)

        # Log start of execution
        logger.info("Starting Bridge Assignment Checker")
        if os.getenv('GITHUB_ACTIONS'):
            logger.info("Running in GitHub Actions environment")

        # Retrieve username and password from environment variables
        username = os.getenv('BRIDGE_USERNAME')
        password = os.getenv('BRIDGE_PASSWORD')
        
        if not username or not password:
            logger.error("Missing required environment variables BRIDGE_USERNAME and/or BRIDGE_PASSWORD")
            sys.exit(1)
        
        driver = None
        try:
            driver = login(username, password)
            if not driver:
                logger.error("Login failed")
                sys.exit(1)

            atexit.register(cleanup_driver, driver)
            
            assignments = get_assignments(driver)
            if assignments:
                logger.info(f"\nFound {len(assignments)} assignments")
                for i, assignment in enumerate(assignments, 1):
                    logger.info(f"\nAssignment #{i}:")
                    for key, value in assignment.items():
                        logger.info(f"{key.title()}: {value}")
                
                # Process and validate assignments
                formatted_assignments, has_changes, changes, new_assignments = process_assignments(assignments)
                
                if has_changes and new_assignments:  # Only notify if there are new assignments
                    logger.info("\nNew assignments detected:")
                    for change in changes:
                        if change.startswith("New assignment added:"):
                            logger.info(change)
                    
                    logger.info("\nSending email notification for new assignments...")
                    
                    # Get health status for notification
                    health_status = metrics.get_health_status()
                    
                    # Filter changes to only include new assignments
                    new_assignment_changes = [
                        change for change in changes 
                        if change.startswith("New assignment added:")
                    ]
                    
                    if not health_status['healthy']:
                        new_assignment_changes.append("\n⚠️ System Health Warnings:")
                        for warning in health_status['warnings']:
                            new_assignment_changes.append(f"- {warning}")
                        for error in health_status['errors']:
                            new_assignment_changes.append(f"- {error}")
                    
                    if send_notification(new_assignment_changes, new_assignments):
                        logger.info("Email notification sent successfully")
                        metrics.record_error("notification_success")
                        
                        # Save all assignments to storage
                        if storage.save_assignments(formatted_assignments):
                            logger.info("Assignments saved successfully")
                        else:
                            logger.error("Failed to save assignments")
                            metrics.record_error("storage_write_error")
                    else:
                        logger.error("Failed to send email notification")
                        metrics.record_error("notification_failure")
                else:
                    if has_changes:
                        logger.info("Changes detected but no new assignments")
                    else:
                        logger.info("No changes detected in assignments")
                    logger.info("No email notification needed.")
            else:
                logger.warning("No assignments found")
                metrics.record_error("no_assignments")
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"An error occurred during execution: {str(e)}")
            logger.error(traceback.format_exc())
            metrics.record_error(error_type)
            sys.exit(1)
        finally:
            if driver:
                atexit.unregister(cleanup_driver)  # Deregister the cleanup handler
                cleanup_driver(driver)  # Call cleanup once
    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"Critical error in main: {str(e)}")
        logger.error(traceback.format_exc())
        metrics.record_error(error_type)
        sys.exit(1)
    finally:
        # Record run completion
        success = sys.exc_info()[0] is None
        metrics.end_run(
            success=success,
            assignments_count=len(assignments) if 'assignments' in locals() else 0,
            notifications_sent=1 if success and 'has_changes' in locals() and has_changes else 0
        )

if __name__ == "__main__":
    main()
