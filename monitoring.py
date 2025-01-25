import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class MetricsData:
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_assignments_processed: int = 0
    total_notifications_sent: int = 0
    average_processing_time: float = 0.0
    last_successful_run: Optional[str] = None
    last_failed_run: Optional[str] = None
    error_counts: Dict[str, int] = None
    validation_error_counts: Dict[str, int] = None

    def __post_init__(self):
        if self.error_counts is None:
            self.error_counts = {}
        if self.validation_error_counts is None:
            self.validation_error_counts = {}

class Metrics:
    """Tracks application metrics and health data"""
    
    def __init__(self, metrics_file: str = "data/metrics.json"):
        self.metrics_file = metrics_file
        self.metrics = self._load_metrics()
        self._ensure_data_dir()
        
    def _ensure_data_dir(self):
        """Ensure the data directory exists"""
        os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
        
    def _load_metrics(self) -> MetricsData:
        """Load metrics from file or create new metrics"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                return MetricsData(**data)
        except Exception as e:
            logger.error(f"Error loading metrics: {str(e)}")
        return MetricsData()
        
    def _save_metrics(self):
        """Save metrics to file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(asdict(self.metrics), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving metrics: {str(e)}")
            
    def start_run(self):
        """Start tracking a new run"""
        self.run_start_time = time.time()
        self.metrics.total_runs += 1
        self._save_metrics()
        
    def end_run(self, success: bool, assignments_count: int = 0, notifications_sent: int = 0):
        """Record the end of a run"""
        run_time = time.time() - self.run_start_time
        
        # Update run counts
        if success:
            self.metrics.successful_runs += 1
            self.metrics.last_successful_run = datetime.now().isoformat()
        else:
            self.metrics.failed_runs += 1
            self.metrics.last_failed_run = datetime.now().isoformat()
            
        # Update processing metrics
        self.metrics.total_assignments_processed += assignments_count
        self.metrics.total_notifications_sent += notifications_sent
        
        # Update average processing time
        if self.metrics.average_processing_time == 0:
            self.metrics.average_processing_time = run_time
        else:
            self.metrics.average_processing_time = (
                self.metrics.average_processing_time * 0.9 + run_time * 0.1
            )
            
        self._save_metrics()
        
    def record_error(self, error_type: str):
        """Record an error occurrence"""
        self.metrics.error_counts[error_type] = self.metrics.error_counts.get(error_type, 0) + 1
        self._save_metrics()
        
    def record_validation_error(self, error_type: str):
        """Record a validation error occurrence"""
        self.metrics.validation_error_counts[error_type] = self.metrics.validation_error_counts.get(error_type, 0) + 1
        self._save_metrics()
        
    def get_health_status(self) -> Dict:
        """Get current health status of the application"""
        now = datetime.now()
        
        # Parse timestamps
        last_success = datetime.fromisoformat(self.metrics.last_successful_run) if self.metrics.last_successful_run else None
        last_failure = datetime.fromisoformat(self.metrics.last_failed_run) if self.metrics.last_failed_run else None
        
        # Calculate health indicators
        status = {
            'healthy': True,
            'warnings': [],
            'errors': []
        }
        
        # Check for recent successful runs
        if last_success and (now - last_success) > timedelta(hours=2):
            status['warnings'].append("No successful runs in the last 2 hours")
            
        # Check error rate
        if self.metrics.total_runs > 0:
            error_rate = self.metrics.failed_runs / self.metrics.total_runs
            if error_rate > 0.2:  # More than 20% failure rate
                status['errors'].append(f"High error rate: {error_rate:.1%}")
                status['healthy'] = False
                
        # Check processing time
        if self.metrics.average_processing_time > 300:  # Over 5 minutes
            status['warnings'].append(f"High average processing time: {self.metrics.average_processing_time:.1f}s")
            
        # Check validation errors
        total_validation_errors = sum(self.metrics.validation_error_counts.values())
        if total_validation_errors > 100:
            status['warnings'].append(f"High number of validation errors: {total_validation_errors}")
            
        return status
        
    def get_metrics_report(self) -> str:
        """Generate a human-readable metrics report"""
        status = self.get_health_status()
        
        report = [
            "=== Bridge Assignments Monitor Health Report ===",
            f"Status: {'🟢 Healthy' if status['healthy'] else '🔴 Unhealthy'}",
            "",
            "Run Statistics:",
            f"- Total Runs: {self.metrics.total_runs}",
            f"- Success Rate: {(self.metrics.successful_runs / self.metrics.total_runs * 100):.1f}% ({self.metrics.successful_runs}/{self.metrics.total_runs})",
            f"- Average Processing Time: {self.metrics.average_processing_time:.1f}s",
            f"- Last Successful Run: {self.metrics.last_successful_run or 'Never'}",
            "",
            "Processing Statistics:",
            f"- Total Assignments Processed: {self.metrics.total_assignments_processed}",
            f"- Total Notifications Sent: {self.metrics.total_notifications_sent}",
            "",
            "Error Statistics:",
            "- Error Types:",
        ]
        
        # Add error counts
        for error_type, count in self.metrics.error_counts.items():
            report.append(f"  • {error_type}: {count}")
            
        report.extend([
            "",
            "Validation Statistics:",
            "- Validation Error Types:",
        ])
        
        # Add validation error counts
        for error_type, count in self.metrics.validation_error_counts.items():
            report.append(f"  • {error_type}: {count}")
            
        # Add warnings and errors
        if status['warnings']:
            report.extend([
                "",
                "⚠️ Warnings:",
            ])
            for warning in status['warnings']:
                report.append(f"- {warning}")
                
        if status['errors']:
            report.extend([
                "",
                "❌ Errors:",
            ])
            for error in status['errors']:
                report.append(f"- {error}")
                
        return "\n".join(report)

# Global metrics instance
metrics = Metrics()
