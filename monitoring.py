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
    success_counts: Dict[str, int] = None
    recent_processing_times: List[float] = None
    recent_error_rates: List[float] = None
    max_history_size: int = 100

    def __post_init__(self):
        if self.error_counts is None:
            self.error_counts = {}
        if self.validation_error_counts is None:
            self.validation_error_counts = {}
        if self.success_counts is None:
            self.success_counts = {}
        if self.recent_processing_times is None:
            self.recent_processing_times = []
        if self.recent_error_rates is None:
            self.recent_error_rates = []

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
        
    def _get_trend_indicator(self, trend: str) -> str:
        """Convert trend string to visual indicator"""
        indicators = {
            'increasing': '📈 Increasing',
            'decreasing': '📉 Decreasing',
            'stable': '📊 Stable'
        }
        return indicators.get(trend, '❓ Unknown')

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
        
        # Update recent metrics history
        self.metrics.recent_processing_times.append(run_time)
        if len(self.metrics.recent_processing_times) > self.metrics.max_history_size:
            self.metrics.recent_processing_times.pop(0)
            
        if self.metrics.total_runs > 0:
            error_rate = self.metrics.failed_runs / self.metrics.total_runs
            self.metrics.recent_error_rates.append(error_rate)
            if len(self.metrics.recent_error_rates) > self.metrics.max_history_size:
                self.metrics.recent_error_rates.pop(0)
        
        # Update average processing time with weighted moving average
        if self.metrics.average_processing_time == 0:
            self.metrics.average_processing_time = run_time
        else:
            self.metrics.average_processing_time = (
                self.metrics.average_processing_time * 0.9 + run_time * 0.1
            )
            
        self._save_metrics()
        
    def record_success(self, success_type: str):
        """Record a successful operation"""
        self.metrics.success_counts[success_type] = self.metrics.success_counts.get(success_type, 0) + 1
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
            'errors': [],
            'trends': {
                'error_rate_trend': 'stable',
                'processing_time_trend': 'stable'
            }
        }
        
        # Environment-specific thresholds
        is_production = os.getenv('PRODUCTION', 'false').lower() == 'true'
        thresholds = {
            'error_rate': 0.2 if is_production else 0.3,
            'processing_time': 300 if is_production else 600,  # 5 min prod, 10 min dev
            'validation_errors': 50 if is_production else 100,
            'success_gap_hours': 2 if is_production else 4
        }
        
        # Check for recent successful runs
        if last_success:
            hours_since_success = (now - last_success).total_seconds() / 3600
            if hours_since_success > thresholds['success_gap_hours']:
                status['warnings'].append(
                    f"No successful runs in the last {thresholds['success_gap_hours']} hours"
                )
            
        # Check error rate
        if self.metrics.total_runs > 0:
            error_rate = self.metrics.failed_runs / self.metrics.total_runs
            if error_rate > thresholds['error_rate']:
                status['errors'].append(f"High error rate: {error_rate:.1%}")
                status['healthy'] = False
            
            # Analyze error rate trend
            if self.metrics.total_runs > 10:
                recent_error_rate = error_rate
                if recent_error_rate > error_rate * 1.2:
                    status['trends']['error_rate_trend'] = 'increasing'
                elif recent_error_rate < error_rate * 0.8:
                    status['trends']['error_rate_trend'] = 'decreasing'
                
        # Check processing time
        if self.metrics.average_processing_time > thresholds['processing_time']:
            status['warnings'].append(
                f"High average processing time: {self.metrics.average_processing_time:.1f}s"
            )
            
        # Check validation errors with categorization
        validation_errors = self.metrics.validation_error_counts
        total_validation_errors = sum(validation_errors.values())
        
        if total_validation_errors > thresholds['validation_errors']:
            # Categorize validation errors
            error_categories = {
                'service_type': sum(count for type_, count in validation_errors.items() 
                                  if 'service_type' in type_.lower()),
                'date_time': sum(count for type_, count in validation_errors.items() 
                                if 'date' in type_.lower() or 'time' in type_.lower()),
                'other': sum(count for type_, count in validation_errors.items() 
                           if 'service_type' not in type_.lower() 
                           and 'date' not in type_.lower() 
                           and 'time' not in type_.lower())
            }
            
            # Add specific warnings for high-count categories
            for category, count in error_categories.items():
                if count > thresholds['validation_errors'] * 0.5:  # If category makes up >50% of threshold
                    status['warnings'].append(
                        f"High number of {category} validation errors: {count}"
                    )
            
        return status
        
    def get_metrics_report(self) -> str:
        """Generate a human-readable metrics report"""
        status = self.get_health_status()
        is_production = os.getenv('PRODUCTION', 'false').lower() == 'true'
        
        # Environment indicator
        env_indicator = "🏭 Production" if is_production else "🔧 Development"
        
        report = [
            "=== Bridge Assignments Monitor Health Report ===",
            f"Environment: {env_indicator}",
            f"Status: {'🟢 Healthy' if status['healthy'] else '🔴 Unhealthy'}",
            "",
            "Run Statistics:",
            f"- Total Runs: {self.metrics.total_runs}",
            f"- Success Rate: {(self.metrics.successful_runs / self.metrics.total_runs * 100):.1f}% ({self.metrics.successful_runs}/{self.metrics.total_runs})",
            f"- Average Processing Time: {self.metrics.average_processing_time:.1f}s",
            f"- Last Successful Run: {self.metrics.last_successful_run or 'Never'}"
        ]
        
        # Add trend analysis
        if 'trends' in status:
            report.extend([
                "",
                "Trend Analysis:",
                f"- Error Rate: {self._get_trend_indicator(status['trends']['error_rate_trend'])}",
                f"- Processing Time: {self._get_trend_indicator(status['trends']['processing_time_trend'])}"
            ])
            
            # Add recent metrics if available
            if self.metrics.recent_processing_times:
                recent_avg = sum(self.metrics.recent_processing_times[-10:]) / min(10, len(self.metrics.recent_processing_times))
                report.append(f"- Recent Average Processing Time: {recent_avg:.1f}s")
            
            if self.metrics.recent_error_rates:
                recent_error_rate = self.metrics.recent_error_rates[-1]
                report.append(f"- Recent Error Rate: {recent_error_rate:.1%}")
        
        report.extend([
            "",
            "Processing Statistics:",
            f"- Total Assignments Processed: {self.metrics.total_assignments_processed}",
            f"- Total Notifications Sent: {self.metrics.total_notifications_sent}",
            "",
            "Success Statistics:",
            "- Success Types (sorted by frequency):"
        ])
        
        # Add success counts sorted by frequency
        success_items = sorted(self.metrics.success_counts.items(), 
                             key=lambda x: x[1], reverse=True)
        for success_type, count in success_items:
            report.append(f"  • {success_type}: {count}")
            
        report.extend([
            "",
            "Error Statistics:",
            "- Error Types (sorted by frequency):"
        ])
        
        # Add error counts sorted by frequency
        error_items = sorted(self.metrics.error_counts.items(), 
                           key=lambda x: x[1], reverse=True)
        for error_type, count in error_items:
            report.append(f"  • {error_type}: {count}")
            
        report.extend([
            "",
            "Validation Statistics:",
            "- Validation Error Types (sorted by frequency):"
        ])
        
        # Add validation error counts sorted by frequency
        validation_items = sorted(self.metrics.validation_error_counts.items(), 
                                key=lambda x: x[1], reverse=True)
        for error_type, count in validation_items:
            report.append(f"  • {error_type}: {count}")
            
        # Add warnings and errors
        if status['warnings']:
            report.extend([
                "",
                "⚠️ Warnings:"
            ])
            for warning in sorted(status['warnings']):  # Sort warnings alphabetically
                report.append(f"- {warning}")
                
        if status['errors']:
            report.extend([
                "",
                "❌ Errors:"
            ])
            for error in sorted(status['errors']):  # Sort errors alphabetically
                report.append(f"- {error}")
                
        return "\n".join(report)

# Global metrics instance
metrics = Metrics()
