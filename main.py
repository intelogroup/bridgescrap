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
    """Save assignments to a file with consistent formatting"""
    try:
        # Extract location and other details from info field
        formatted_assignments = []
        for assignment in assignments:
            formatted = {}
            # Copy basic fields
            formatted['customer'] = assignment.get('customer', '')
            formatted['date_time'] = assignment.get('date_time', '')
            formatted['language'] = assignment.get('language', '')
            formatted['service_type'] = assignment.get('service_type', '')
            
            # Parse info field
            info = assignment.get('info', '')
            for line in info.split('\n'):
                line = line.strip()
                if 'Contact person\'s name and phone number:' in line:
                    formatted['contact_person_name_and_phone'] = line.split(':', 1)[1].strip()
                elif 'Contact person\'s email address:' in line:
                    formatted['contact_person\'s_email_address'] = line.split(':', 1)[1].strip()
                elif 'Address:' in line:
                    formatted['address'] = line.split(':', 1)[1].strip()
                elif 'Location:' in line:
                    formatted['location'] = line.split(':', 1)[1].strip()
                elif 'Client name and phone:' in line:
                    formatted['client_name_and_phone'] = line.split(':', 1)[1].strip()
            
            formatted['comments'] = assignment.get('comments', '')
            formatted_assignments.append(formatted)
        
        # Write formatted assignments to file
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Bridge Assignments Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            for i, assignment in enumerate(formatted_assignments, 1):
                f.write(f"Assignment #{i}:\n")
                f.write("-" * 30 + "\n")
                for key, value in sorted(assignment.items()):  # Sort keys for consistent order
                    if value:  # Only write non-empty values
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
    # Skip header lines and empty lines
    lines = [line.strip() for line in content.split('\n') 
            if line.strip() and not line.startswith('Bridge Assignments Report')]
    
    for line in lines:
        if line.startswith('Assignment #'):
            if current_assignment:
                assignments_list.append(current_assignment)
            current_assignment = {}
        elif line.startswith('-'): # Skip separator lines
            continue
        elif ':' in line:
            key, value = [part.strip() for part in line.split(':', 1)]
            # Normalize keys to make comparison more reliable
            key = key.lower().replace(' ', '_')
            # Normalize empty or n/a values
            value = '' if value.lower() in ['n/a', 'none', ''] else value
            current_assignment[key] = value
    
    if current_assignment:
        assignments_list.append(current_assignment)
    return assignments_list

def compare_assignments(prev_assignments, curr_assignments):
    """Compare assignments with detailed change tracking"""
    changes = []
    
    # Create sets of assignment identifiers (using customer, date_time, and language as unique identifiers)
    def get_assignment_key(assignment):
        return (
            assignment.get('customer', ''),
            assignment.get('date_time', ''),
            assignment.get('language', '')
        )
    
    prev_keys = {get_assignment_key(a) for a in prev_assignments}
    curr_keys = {get_assignment_key(a) for a in curr_assignments}
    
    # Find new and removed assignments
    new_keys = curr_keys - prev_keys
    removed_keys = prev_keys - curr_keys
    
    # Log new assignments
    for key in new_keys:
        changes.append(f"New assignment added: {key[0]} - {key[1]} - {key[2]}")
    
    # Log removed assignments
    for key in removed_keys:
        changes.append(f"Assignment removed: {key[0]} - {key[1]} - {key[2]}")
    
    # Compare assignments that exist in both lists
    common_keys = prev_keys & curr_keys
    important_fields = ['customer', 'date_time', 'language', 'service_type', 'location', 
                       'client_name_and_phone', 'contact_person\'s_email_address']
    
    for key in common_keys:
        prev = next(a for a in prev_assignments if get_assignment_key(a) == key)
        curr = next(a for a in curr_assignments if get_assignment_key(a) == key)
        assignment_changes = []
        
        for field in important_fields:
            prev_value = prev.get(field, '')
            curr_value = curr.get(field, '')
            if prev_value != curr_value:
                assignment_changes.append(f"{field}: '{prev_value}' → '{curr_value}'")
        
        if assignment_changes:
            changes.append(f"Changes in Assignment ({key[0]}, {key[1]}):")
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
