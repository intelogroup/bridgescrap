import os
import sys
import logging
import atexit
import traceback
from datetime import datetime
from dotenv import load_dotenv
from login import login
from assignments import get_assignments
from email_handler import send_notification

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

def save_assignments(assignments, filename="assignments.txt"):
    """Save assignments to a file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Bridge Assignments Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            for i, assignment in enumerate(assignments, 1):
                f.write(f"Assignment #{i}:\n")
                f.write("-" * 30 + "\n")
                for key, value in assignment.items():
                    f.write(f"{key.title()}: {value}\n")
                f.write("\n")
        logger.info(f"Assignments saved to {filename}")
        return True
    except Exception as e:
        logger.error(f"Error saving assignments: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def parse_assignments(content):
    """Parse assignments from file content"""
    assignments_list = []
    current_assignment = {}
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    
    for line in lines:
        if line.startswith('Assignment #'):
            if current_assignment:
                assignments_list.append(current_assignment)
            current_assignment = {}
        elif ':' in line:
            key, value = [part.strip() for part in line.split(':', 1)]
            # Normalize keys to make comparison more reliable
            key = key.lower().replace(' ', '_')
            current_assignment[key] = value
    
    if current_assignment:
        assignments_list.append(current_assignment)
    return assignments_list

def compare_assignments(prev_assignments, curr_assignments):
    """Compare assignments with detailed change tracking"""
    changes = []
    
    # Handle case where number of assignments changed
    if len(prev_assignments) != len(curr_assignments):
        prev_count = len(prev_assignments)
        curr_count = len(curr_assignments)
        changes.append(f"Assignment count changed from {prev_count} to {curr_count}")
        
        # If assignments were added
        if curr_count > prev_count:
            for i in range(prev_count, curr_count):
                changes.append(f"New assignment added: {curr_assignments[i].get('customer', 'Unknown')} - "
                             f"{curr_assignments[i].get('date_time', 'No date')} - "
                             f"{curr_assignments[i].get('language', 'No language')}")
        
        # If assignments were removed
        elif prev_count > curr_count:
            for i in range(curr_count, prev_count):
                changes.append(f"Assignment removed: {prev_assignments[i].get('customer', 'Unknown')} - "
                             f"{prev_assignments[i].get('date_time', 'No date')} - "
                             f"{prev_assignments[i].get('language', 'No language')}")
    
    # Compare common assignments
    common_count = min(len(prev_assignments), len(curr_assignments))
    important_fields = ['customer', 'date_time', 'language', 'service_type', 'location', 
                       'client_name_and_phone', 'contact_person\'s_email_address']
    
    for i in range(common_count):
        prev = prev_assignments[i]
        curr = curr_assignments[i]
        assignment_changes = []
        
        for field in important_fields:
            prev_value = prev.get(field, '')
            curr_value = curr.get(field, '')
            if prev_value != curr_value:
                assignment_changes.append(f"{field}: '{prev_value}' → '{curr_value}'")
        
        if assignment_changes:
            changes.append(f"Changes in Assignment #{i+1}:")
            changes.extend([f"  - {change}" for change in assignment_changes])
    
    return bool(changes), changes

def main():
    try:
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
                
                # First save the new assignments
                save_assignments(assignments)
                logger.info("New assignments saved to assignments.txt")

                # Load previous assignments
                previous_assignments_content = ""
                if os.path.exists("Previous_assignments.txt"):
                    try:
                        with open("Previous_assignments.txt", 'r', encoding='utf-8') as f:
                            previous_assignments_content = f.read()
                    except Exception as e:
                        logger.error(f"Error reading Previous_assignments.txt: {str(e)}")
                        logger.error(traceback.format_exc())

                # Load current assignments
                current_assignments_content = ""
                try:
                    with open("assignments.txt", 'r', encoding='utf-8') as f:
                        current_assignments_content = f.read()
                except Exception as e:
                    logger.error(f"Error reading assignments.txt: {str(e)}")
                    logger.error(traceback.format_exc())

                prev_assignments = parse_assignments(previous_assignments_content)
                curr_assignments = parse_assignments(current_assignments_content)
                
                has_changes, changes = compare_assignments(prev_assignments, curr_assignments)
                
                if has_changes:
                    logger.info("\nChanges detected:")
                    for change in changes:
                        logger.info(change)
                    logger.info("\nSending email notification...")
                    
                    if send_notification(assignments):
                        logger.info("Email notification sent successfully")
                        # Update Previous_assignments.txt with new content
                        try:
                            with open("Previous_assignments.txt", 'w', encoding='utf-8') as f:
                                f.write(current_assignments_content)
                            logger.info("Previous_assignments.txt updated with new content")
                        except Exception as e:
                            logger.error(f"Error updating Previous_assignments.txt: {str(e)}")
                            logger.error(traceback.format_exc())
                    else:
                        logger.error("Failed to send email notification")
                else:
                    logger.info("No changes detected in assignments")
                    logger.info("No email notification needed.")
            else:
                logger.warning("No assignments found")
        except Exception as e:
            logger.error(f"An error occurred during execution: {str(e)}")
            logger.error(traceback.format_exc())
            sys.exit(1)
        finally:
            if driver:
                atexit.unregister(cleanup_driver)  # Deregister the cleanup handler
                cleanup_driver(driver)  # Call cleanup once
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
