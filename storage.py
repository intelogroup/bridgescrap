import os
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AssignmentStorage:
    """Handles persistent storage of assignments using JSON"""
    
    def __init__(self, storage_file: str = "data/assignments.json"):
        self.storage_file = storage_file
        self._ensure_data_dir()
        
    def _ensure_data_dir(self):
        """Ensure the data directory exists"""
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        
    def _read_storage(self) -> Dict:
        """Read the storage file"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {
                'last_updated': None,
                'assignments': [],
                'history': []
            }
        except Exception as e:
            logger.error(f"Error reading storage: {str(e)}")
            return {
                'last_updated': None,
                'assignments': [],
                'history': []
            }
            
    def _write_storage(self, data: Dict) -> bool:
        """Write to the storage file"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error writing storage: {str(e)}")
            return False
            
    def _clean_old_history(self, history: List[Dict]) -> List[Dict]:
        """
        Clean history entries older than 7 days
        
        Args:
            history: List of history entries
            
        Returns:
            List of filtered history entries
        """
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        return [
            entry for entry in history 
            if entry.get('timestamp') and entry['timestamp'] > seven_days_ago
        ]
            
    def save_assignments(self, assignments: List[Dict]) -> bool:
        """
        Save assignments to storage
        
        Args:
            assignments: List of assignment dictionaries
            
        Returns:
            bool: True if successful
        """
        try:
            data = self._read_storage()
            
            # Update history
            if data['assignments']:
                history_entry = {
                    'timestamp': data['last_updated'],
                    'assignments': data['assignments']
                }
                data['history'].append(history_entry)
            
            # Clean old history entries
            data['history'] = self._clean_old_history(data['history'])
            
            # Update current assignments
            data['last_updated'] = datetime.now().isoformat()
            data['assignments'] = assignments
            
            return self._write_storage(data)
            
        except Exception as e:
            logger.error(f"Error saving assignments: {str(e)}")
            return False
            
    def get_assignments(self) -> List[Dict]:
        """
        Get current assignments from storage
        
        Returns:
            List of assignment dictionaries
        """
        try:
            data = self._read_storage()
            return data['assignments']
        except Exception as e:
            logger.error(f"Error getting assignments: {str(e)}")
            return []
            
    def get_assignment_history(self) -> List[Dict]:
        """
        Get assignment history
        
        Returns:
            List of history entries with timestamp and assignments
        """
        try:
            data = self._read_storage()
            return self._clean_old_history(data['history'])
        except Exception as e:
            logger.error(f"Error getting assignment history: {str(e)}")
            return []
            
    def _normalize_value(self, value: str) -> str:
        """Normalize a value for comparison"""
        if not isinstance(value, str):
            return str(value)
        
        # Replace multiple spaces with single space, strip, and convert to lowercase
        return ' '.join(value.split()).lower()
    
    def _get_assignment_key(self, assignment: Dict) -> tuple:
        """Get unique identifier for assignment using all main fields"""
        # Only use core identifying fields for the key
        # This prevents minor changes in info/comments from causing false duplicates
        return (
            self._normalize_value(assignment.get('customer', '')),
            self._normalize_value(assignment.get('date_time', '')),
            self._normalize_value(assignment.get('language', '')),
            self._normalize_value(assignment.get('service_type', ''))
        )
        
    def _clean_assignment(self, assignment: Dict) -> Dict:
        """Clean assignment for comparison"""
        # List of fields to ignore in comparison
        ignore_fields = {'timestamp', 'last_updated', 'created_at', 'updated_at'}
        
        cleaned = {}
        for key, value in assignment.items():
            key = key.lower()  # Normalize key to lowercase
            
            # Skip timestamp-related fields
            if key in ignore_fields:
                continue
            
            # Handle missing or empty values
            if value is None or (isinstance(value, str) and not value.strip()):
                cleaned[key] = 'n/a'
                continue
            
            # Normalize all values to lowercase
            cleaned[key] = self._normalize_value(value)
            
        return cleaned
    
    def _assignments_equal(self, a1: Dict, a2: Dict) -> bool:
        """Compare two assignments, ignoring case and space differences"""
        # Get all unique keys
        all_keys = set(a1.keys()) | set(a2.keys())
        
        for key in all_keys:
            # Get values, defaulting to 'n/a' for missing values
            v1 = self._normalize_value(a1.get(key, 'n/a'))
            v2 = self._normalize_value(a2.get(key, 'n/a'))
            
            if v1 != v2:
                return False
        return True
    
    def compare_assignments(self, new_assignments: List[Dict]) -> tuple[bool, List[str], List[Dict]]:
        """
        Compare new assignments with stored assignments
        
        Args:
            new_assignments: List of new assignment dictionaries
            
        Returns:
            Tuple of (has_changes: bool, changes: List[str], new_assignments_list: List[Dict])
        """
        changes = []
        current_assignments = self.get_assignments()
        
        # Fields where case matters
        case_sensitive_fields = {'info', 'comments'}
        
        # Clean assignments for comparison
        current_cleaned = [self._clean_assignment(a) for a in current_assignments]
        new_cleaned = [self._clean_assignment(a) for a in new_assignments]
        
        # Get assignment keys
        current_keys = {self._get_assignment_key(a): (a, orig_a) 
                       for a, orig_a in zip(current_cleaned, current_assignments)}
        new_keys = {self._get_assignment_key(a): (a, orig_a) 
                   for a, orig_a in zip(new_cleaned, new_assignments)}
        
        # Find added and removed assignments
        added_keys = set(new_keys.keys()) - set(current_keys.keys())
        removed_keys = set(current_keys.keys()) - set(new_keys.keys())
        common_keys = set(current_keys.keys()) & set(new_keys.keys())
        
        # Collect truly new assignments (use original assignments, not cleaned)
        new_assignments_list = []
        for key in added_keys:
            # Find the original assignment that matches this key
            cleaned_assignment, original_assignment = new_keys[key]
            new_assignments_list.append(original_assignment)
            changes.append(f"New assignment added: Customer: {key[0]}, Language: {key[2]}, Date/Time: {key[1]}")
            
        # Log removed assignments
        for key in removed_keys:
            changes.append(f"Assignment removed: Customer: {key[0]}, Language: {key[2]}, Date/Time: {key[1]}")
            
        # Compare common assignments
        for key in common_keys:
            current_cleaned, current_orig = current_keys[key]
            new_cleaned, new_orig = new_keys[key]
            
            # Only compare if assignments are actually different
            if not self._assignments_equal(current_cleaned, new_cleaned):
                # Compare all fields
                field_changes = []
                all_fields = set(current_cleaned.keys()) | set(new_cleaned.keys())
                
                for field in sorted(all_fields):
                    current_value = current_cleaned.get(field, 'n/a')
                    new_value = new_cleaned.get(field, 'n/a')
                    
                    if current_value != new_value:
                        # Use original values for display
                        orig_current = current_orig.get(field, 'N/A')
                        orig_new = new_orig.get(field, 'N/A')
                        if self._normalize_value(orig_current) != self._normalize_value(orig_new):  # Only show if values truly differ
                            field_changes.append(f"{field}: '{orig_current}' → '{orig_new}'")
                
                if field_changes:  # Only add changes if there are actual differences
                    changes.append(f"Changes in Assignment (Customer: {key[0]}, Language: {key[2]}, Date/Time: {key[1]}):")
                    changes.extend([f"  - {change}" for change in field_changes])
                
        return bool(changes), changes, new_assignments_list
