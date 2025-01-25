import re
from datetime import datetime
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class AssignmentValidationError:
    field: str
    error: str
    value: str

class AssignmentValidator:
    """Validates assignment data structure and content"""
    
    # Required fields and their types
    REQUIRED_FIELDS = {
        'customer': str,
        'date_time': str,
        'language': str,
        'service_type': str,
        'info': str,
        'comments': str
    }
    
    # Known valid values for certain fields (case-insensitive)
    VALID_SERVICE_TYPES = {
        'in-person interpretation',
        'video interpretation',
        'phone interpretation',
        'document translation'
    }
    
    # Common languages to check for typos
    COMMON_LANGUAGES = {
        'Spanish', 'French', 'Portuguese', 'Mandarin', 'Cantonese',
        'Vietnamese', 'Russian', 'Arabic', 'Korean', 'Japanese'
    }
    
    @classmethod
    def validate_assignment(cls, assignment: Dict[str, str]) -> List[AssignmentValidationError]:
        """
        Validate a single assignment dictionary
        
        Args:
            assignment: Dictionary containing assignment data
            
        Returns:
            List of validation errors, empty if valid
        """
        errors = []
        
        # Check required fields
        for field, expected_type in cls.REQUIRED_FIELDS.items():
            if field not in assignment:
                errors.append(AssignmentValidationError(
                    field=field,
                    error="Missing required field",
                    value="N/A"
                ))
                continue
                
            value = assignment[field]
            if not isinstance(value, expected_type):
                errors.append(AssignmentValidationError(
                    field=field,
                    error=f"Invalid type. Expected {expected_type.__name__}, got {type(value).__name__}",
                    value=str(value)
                ))
        
        # Validate date_time format
        if 'date_time' in assignment:
            date_str = assignment['date_time']
            try:
                # Try multiple common date formats and standardize
                for fmt in ['%m/%d/%Y %I:%M %p', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y\n%I:%M %p']:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        # Convert to standard format
                        assignment['date_time'] = dt.strftime('%m/%d/%Y %I:%M %p')
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError("Invalid date format. Expected MM/DD/YYYY HH:MM AM/PM")
            except ValueError as e:
                errors.append(AssignmentValidationError(
                    field='date_time',
                    error=f"Invalid date format: {str(e)}",
                    value=date_str
                ))
        
        # Validate service type
        if 'service_type' in assignment:
            service_type = assignment['service_type'].lower().strip()
            if service_type not in cls.VALID_SERVICE_TYPES:
                errors.append(AssignmentValidationError(
                    field='service_type',
                    error=f"Unknown service type. Valid types: {', '.join(cls.VALID_SERVICE_TYPES)}",
                    value=service_type
                ))
        
        # Check for empty or whitespace-only values
        for field, value in assignment.items():
            if isinstance(value, str) and not value.strip():
                errors.append(AssignmentValidationError(
                    field=field,
                    error="Empty or whitespace-only value",
                    value=value
                ))
        
        # Validate language field for common typos
        if 'language' in assignment:
            language = assignment['language']
            if language not in cls.COMMON_LANGUAGES:
                # Check for close matches to detect potential typos
                close_matches = [l for l in cls.COMMON_LANGUAGES if cls._similar_strings(language, l)]
                if close_matches:
                    errors.append(AssignmentValidationError(
                        field='language',
                        error=f"Possible typo. Did you mean: {', '.join(close_matches)}?",
                        value=language
                    ))
        
        # Validate customer field format
        if 'customer' in assignment:
            customer = assignment['customer']
            if not cls._is_valid_customer_name(customer):
                errors.append(AssignmentValidationError(
                    field='customer',
                    error="Invalid customer name format",
                    value=customer
                ))
        
        return errors
    
    @classmethod
    def validate_assignments(cls, assignments: List[Dict[str, str]]) -> Dict[int, List[AssignmentValidationError]]:
        """
        Validate a list of assignments
        
        Args:
            assignments: List of assignment dictionaries
            
        Returns:
            Dictionary mapping assignment index to list of validation errors
        """
        validation_errors = {}
        
        for i, assignment in enumerate(assignments):
            errors = cls.validate_assignment(assignment)
            if errors:
                validation_errors[i] = errors
                
                # Log validation errors
                logger.warning(f"Validation errors in assignment #{i + 1}:")
                for error in errors:
                    logger.warning(f"  - {error.field}: {error.error} (value: {error.value})")
        
        return validation_errors
    
    @staticmethod
    def _similar_strings(s1: str, s2: str) -> bool:
        """Check if two strings are similar (for typo detection)"""
        s1 = s1.lower()
        s2 = s2.lower()
        
        # Exact match
        if s1 == s2:
            return True
            
        # Levenshtein distance for similar strings
        if len(s1) > len(s2):
            s1, s2 = s2, s1
            
        distances = range(len(s1) + 1)
        for i2, c2 in enumerate(s2):
            distances_ = [i2+1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
            
        # Return True if the strings are similar enough (distance <= 2)
        return distances[-1] <= 2
    
    @staticmethod
    def _is_valid_customer_name(name: str) -> bool:
        """Validate customer name format"""
        # Check for common invalid patterns
        invalid_patterns = [
            r'^\s*$',  # Empty or whitespace only
            r'^[0-9]+$',  # Numbers only
            r'^test.*$',  # Test entries
            r'^unknown$',  # Unknown entries
            r'^n/?a$',  # N/A entries
        ]
        
        name = name.lower().strip()
        return not any(re.match(pattern, name) for pattern in invalid_patterns)

def sanitize_assignment(assignment: Dict[str, str]) -> Dict[str, str]:
    """
    Sanitize assignment data by cleaning and normalizing values
    
    Args:
        assignment: Raw assignment dictionary
        
    Returns:
        Sanitized assignment dictionary
    """
    sanitized = {}
    
    # Fields that should be case-sensitive
    case_sensitive_fields = {'info', 'comments'}
    
    # Known empty value indicators
    empty_values = {'n/a', 'none', 'null', '-', 'unknown', 'not specified', 'not available'}
    
    for key, value in assignment.items():
        if not isinstance(value, str):
            sanitized[key] = value
            continue
            
        # Strip whitespace
        value = value.strip()
        
        # Normalize empty values
        if not value or value.lower() in empty_values:
            value = 'N/A'
            
        # Handle date_time field
        if key == 'date_time':
            try:
                # Try multiple common date formats and standardize
                for fmt in ['%m/%d/%Y %I:%M %p', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y\n%I:%M %p']:
                    try:
                        dt = datetime.strptime(value, fmt)
                        value = dt.strftime('%m/%d/%Y %I:%M %p')  # Standardize format
                        break
                    except ValueError:
                        continue
            except Exception as e:
                logger.warning(f"Failed to normalize date format: {str(e)}")
                value = 'N/A'
            
        # Normalize case based on field type
        if key not in case_sensitive_fields:
            value = value.lower()  # Default to lowercase for non-case-sensitive fields
            
        # Normalize service type
        if key == 'service_type':
            value = value.strip().lower()
            # Map similar service types to standard values
            service_type_mapping = {
                'in person': 'in-person interpretation',
                'in-person': 'in-person interpretation',
                'video': 'video interpretation',
                'phone': 'phone interpretation',
                'document': 'document translation'
            }
            for pattern, standard in service_type_mapping.items():
                if pattern in value:
                    value = standard
                    break
            
        # Normalize language
        if key == 'language':
            value = value.strip().title()  # Languages should be Title Case
            
        sanitized[key] = value
        
    return sanitized

def validate_and_sanitize_assignments(assignments: List[Dict[str, str]]) -> tuple[List[Dict[str, str]], Dict[int, List[AssignmentValidationError]]]:
    """
    Validate and sanitize a list of assignments
    
    Args:
        assignments: List of raw assignment dictionaries
        
    Returns:
        Tuple of (sanitized assignments, validation errors)
    """
    # First sanitize the assignments
    sanitized_assignments = [sanitize_assignment(assignment) for assignment in assignments]
    
    # Then validate them
    validation_errors = AssignmentValidator.validate_assignments(sanitized_assignments)
    
    # Log summary
    total_errors = sum(len(errors) for errors in validation_errors.values())
    if total_errors > 0:
        logger.warning(f"Found {total_errors} validation errors in {len(validation_errors)} assignments")
    else:
        logger.info("All assignments passed validation")
        
    return sanitized_assignments, validation_errors
