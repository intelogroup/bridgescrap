import os
import logging
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def send_notification(assignments):
    """Send email notification with retry logic"""
    if not assignments:
        logger.warning("No assignments to notify about")
        return False

    # Get email configuration
    email_user = os.getenv('EMAIL_USER')
    email_password = os.getenv('EMAIL_PASSWORD')
    
    if not email_user or not email_password:
        logger.error("Missing email credentials in environment variables")
        return False

    try:
        subject = f"Bridge Assignments Update - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        body = f"Found {len(assignments)} assignments.\n\n"
        body += "Summary:\n"
        for i, assignment in enumerate(assignments, 1):
            body += (f"\nAssignment #{i}:\n"
                    f"Customer: {assignment.get('customer', 'N/A')}\n"
                    f"Date/Time: {assignment.get('date_time', 'N/A')}\n"
                    f"Language: {assignment.get('language', 'N/A')}\n"
                    f"Service Type: {assignment.get('service_type', 'N/A')}\n"
                    f"Location: {assignment.get('location', 'N/A')}\n"
                    f"Info: {assignment.get('info', 'N/A')}\n"
                    f"Comments: {assignment.get('comments', 'N/A')}\n")

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = email_user
        msg['To'] = email_user

        logger.info("Attempting to connect to SMTP server...")
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            logger.info("Connected to SMTP server, initiating TLS...")
            server.starttls()
            logger.info("Attempting login...")
            server.login(email_user, email_password)
            logger.info("Sending email notification...")
            server.send_message(msg)
            logger.info("Email notification sent successfully")
            return True

    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        if os.getenv('GITHUB_ACTIONS'):
            # Additional error details for GitHub Actions environment
            import traceback
            logger.error(f"Full error traceback:\n{traceback.format_exc()}")
        return False
