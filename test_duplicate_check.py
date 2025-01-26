import os
import json
import logging
from unittest.mock import patch
from main import storage, process_assignments, send_notification

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_email_notification():
    """Test email notification behavior with various assignment scenarios"""
    
    def run_test(name, assignment, expected_email=False):
        """Helper function to run a test case"""
        print(f"\n=== {name} ===")
        
        # Mock the send_notification function
        with patch('main.send_notification') as mock_send:
            # Set up mock return value
            mock_send.return_value = True
            
            # Process the assignment
            result = process_assignments([assignment])
            formatted_assignments, has_changes, changes, new_assignments = result
            
            print(f"Has changes: {has_changes}")
            print(f"Number of new assignments: {len(new_assignments)}")
            if changes:
                print("Changes detected:")
                for change in changes:
                    print(f"  {change}")
            
            # Check if email would be sent based on new assignments
            would_send_email = bool(new_assignments)
            
            print(f"Would send email: {would_send_email}")
            print(f"Number of new assignments: {len(new_assignments)}")
            if new_assignments:
                print("New assignments:")
                for assignment in new_assignments:
                    print(f"  - Customer: {assignment.get('customer')}, Language: {assignment.get('language')}")
            print(f"Expected to send email: {expected_email}")
            print(f"Test result: {'✓ PASS' if would_send_email == expected_email else '✗ FAIL'}")
            
            return result, would_send_email

    # Clean up any existing test data
    if os.path.exists('data/assignments.json'):
        os.remove('data/assignments.json')

    # Test data - original assignment
    test_assignment = {
        'customer': 'Test School',
        'date_time': '2/6/2025 10:15 AM',
        'language': 'French',
        'service_type': 'In-person Interpretation',
        'info': 'Test info',
        'comments': 'Test comments'
    }
    
    # Test 1: First Assignment (should send email)
    run_test("Test 1: First Assignment (New)", test_assignment, expected_email=True)
    
    # Test 2: Same content with different case (should not send email)
    case_different = {
        'customer': 'TEST SCHOOL',
        'date_time': '2/6/2025 10:15 AM',
        'language': 'FRENCH',
        'service_type': 'IN-PERSON INTERPRETATION',
        'info': 'TEST INFO',
        'comments': 'TEST COMMENTS'
    }
    run_test("Test 2: Case Different Assignment (Duplicate)", case_different, expected_email=False)
    
    # Test 3: Mixed case but same content (should not send email)
    mixed_case = {
        'customer': 'Test SCHOOL',
        'date_time': '2/6/2025 10:15 AM',
        'language': 'French',
        'service_type': 'In-Person INTERPRETATION',
        'info': 'Test Info',
        'comments': 'Test Comments'
    }
    run_test("Test 3: Mixed Case Assignment (Duplicate)", mixed_case, expected_email=False)
    
    # Test 4: Modified content (should not send email for changes)
    different_content = test_assignment.copy()
    different_content['info'] = 'Different test info'
    run_test("Test 4: Modified Content (Change)", different_content, expected_email=False)
    
    # Test 5: Completely new assignment (should send email)
    new_assignment = {
        'customer': 'Another School',
        'date_time': '2/7/2025 2:30 PM',
        'language': 'Spanish',
        'service_type': 'In-person Interpretation',
        'info': 'New test info',
        'comments': 'New test comments'
    }
    run_test("Test 5: Different Assignment (New)", new_assignment, expected_email=True)

if __name__ == "__main__":
    # Clean up any existing test data
    if os.path.exists('data/assignments.json'):
        os.remove('data/assignments.json')
    
    # Run tests
    test_email_notification()
    
    # Clean up after tests
    if os.path.exists('data/assignments.json'):
        os.remove('data/assignments.json')
