"""
Email Service for User Verification
⚠️ DISABLED - SMTP functionality has been removed from this project
This module is kept for reference only and should not be imported.

To re-enable email functionality:
1. Uncomment SMTP configuration in .env
2. Configure SMTP provider (Gmail, SendGrid, etc.)
3. Uncomment imports in routes/auth.py
4. Test email sending functionality
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger(__name__)

# ⚠️ Email functionality DISABLED
# SMTP configuration has been removed from this project
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'smtp')  # smtp, sendgrid, mailgun, ses
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', 'noreply@upgrade.local')
SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'UPGRADE Platform')

# Frontend URL for verification links
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')


def send_verification_email(to_email: str, username: str, verification_token: str) -> bool:
    """
    Send email verification link to user
    
    Args:
        to_email: User's email address
        username: User's username
        verification_token: Verification token
        
    Returns:
        True if email sent successfully, False otherwise
    """
    verification_url = f"{FRONTEND_URL}/verify-email?token={verification_token}"
    
    # Create email content
    subject = "Verify Your Email - UPGRADE Platform"
    
    # HTML email body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background-color: #f5f7fa;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #0052ff 0%, #00d4ff 100%);
                padding: 40px 20px;
                text-align: center;
            }}
            .logo {{
                color: white;
                font-size: 32px;
                font-weight: 800;
                margin: 0;
            }}
            .content {{
                padding: 40px 30px;
            }}
            h1 {{
                color: #1e293b;
                font-size: 24px;
                margin: 0 0 20px 0;
            }}
            p {{
                color: #64748b;
                font-size: 16px;
                line-height: 1.6;
                margin: 0 0 20px 0;
            }}
            .button {{
                display: inline-block;
                background: linear-gradient(135deg, #0052ff 0%, #00d4ff 100%);
                color: white;
                text-decoration: none;
                padding: 14px 32px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 16px;
                margin: 20px 0;
            }}
            .button:hover {{
                opacity: 0.9;
            }}
            .code-box {{
                background: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                color: #475569;
                word-break: break-all;
                margin: 20px 0;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e9ecef;
            }}
            .footer p {{
                color: #94a3b8;
                font-size: 14px;
                margin: 5px 0;
            }}
            .warning {{
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 12px;
                margin: 20px 0;
                border-radius: 4px;
            }}
            .warning p {{
                color: #856404;
                margin: 0;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="logo">⚛ UPGRADE</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Urban Pathogen Genomic Surveillance</p>
            </div>
            
            <div class="content">
                <h1>Verify Your Email Address</h1>
                <p>Hello <strong>{username}</strong>,</p>
                <p>Thank you for registering with UPGRADE Platform! Please verify your email address to complete your account setup and access all features.</p>
                
                <p style="text-align: center;">
                    <a href="{verification_url}" class="button">Verify Email Address</a>
                </p>
                
                <p>Or copy and paste this link into your browser:</p>
                <div class="code-box">{verification_url}</div>
                
                <div class="warning">
                    <p><strong>⏰ This link will expire in 24 hours.</strong></p>
                </div>
                
                <p>If you didn't create an account with UPGRADE Platform, you can safely ignore this email.</p>
            </div>
            
            <div class="footer">
                <p>© 2025 UPGRADE Platform</p>
                <p>Powered by Nextflow & React</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Plain text version (fallback)
    text_body = f"""
    UPGRADE Platform - Email Verification
    
    Hello {username},
    
    Thank you for registering with UPGRADE Platform! Please verify your email address by clicking the link below:
    
    {verification_url}
    
    This link will expire in 24 hours.
    
    If you didn't create an account, you can safely ignore this email.
    
    ---
    UPGRADE Platform
    Urban Pathogen Genomic Surveillance
    """
    
    try:
        if EMAIL_PROVIDER == 'smtp':
            return send_smtp_email(to_email, subject, html_body, text_body)
        else:
            logger.error(f"Unsupported email provider: {EMAIL_PROVIDER}")
            return False
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {e}")
        return False


def send_smtp_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """
    Send email using SMTP (Gmail, Office365, etc.)
    
    For Gmail:
    - Enable 2FA on your Google account
    - Generate App Password: https://myaccount.google.com/apppasswords
    - Use App Password in SMTP_PASSWORD
    """
    # Quick check: if no SMTP credentials configured, skip immediately
    if not SMTP_USER or not SMTP_PASSWORD or SMTP_PASSWORD == 'xxxx-xxxx-xxxx-xxxx':
        logger.warning(f"SMTP not configured - skipping email to {to_email}")
        return False
    
    try:
        # Create message
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        message['To'] = to_email
        
        # Attach plain text and HTML versions
        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        message.attach(part1)
        message.attach(part2)
        
        # Connect to SMTP server with 5 second timeout
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as server:
            server.set_debuglevel(0)
            server.ehlo()
            server.starttls()
            server.ehlo()
            
            # Login if credentials provided
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            
            # Send email
            server.send_message(message)
        
        logger.info(f"Verification email sent successfully to {to_email}")
        return True
        
    except smtplib.SMTPAuthenticationError:
        logger.error(f"SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD.")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email to {to_email}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email to {to_email}: {e}")
        return False


def send_welcome_email(to_email: str, username: str) -> bool:
    """
    Send welcome email after successful verification
    """
    subject = "Welcome to UPGRADE Platform! 🎉"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background-color: #f5f7fa;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 16px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #00ff88 0%, #00d4ff 100%);
                padding: 40px 20px;
                text-align: center;
            }}
            .logo {{
                color: white;
                font-size: 32px;
                font-weight: 800;
                margin: 0;
            }}
            .content {{
                padding: 40px 30px;
            }}
            h1 {{
                color: #1e293b;
                font-size: 24px;
                margin: 0 0 20px 0;
            }}
            p {{
                color: #64748b;
                font-size: 16px;
                line-height: 1.6;
                margin: 0 0 20px 0;
            }}
            .features {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .feature {{
                margin: 15px 0;
                padding-left: 30px;
                position: relative;
            }}
            .feature::before {{
                content: "✓";
                position: absolute;
                left: 0;
                color: #00ff88;
                font-weight: bold;
                font-size: 20px;
            }}
            .button {{
                display: inline-block;
                background: linear-gradient(135deg, #0052ff 0%, #00d4ff 100%);
                color: white;
                text-decoration: none;
                padding: 14px 32px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 16px;
                margin: 20px 0;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 20px 30px;
                text-align: center;
                border-top: 1px solid #e9ecef;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="logo">⚛ UPGRADE</h1>
            </div>
            
            <div class="content">
                <h1>🎉 Welcome to UPGRADE Platform!</h1>
                <p>Hello <strong>{username}</strong>,</p>
                <p>Your email has been verified successfully! You now have full access to all platform features.</p>
                
                <div class="features">
                    <h3 style="margin-top: 0;">What you can do now:</h3>
                    <div class="feature">Upload and analyze genomic samples</div>
                    <div class="feature">Monitor pipeline execution in real-time</div>
                    <div class="feature">View comprehensive analysis results</div>
                    <div class="feature">Track geographic pathogen distribution</div>
                    <div class="feature">Access advanced visualization tools</div>
                </div>
                
                <p style="text-align: center;">
                    <a href="{FRONTEND_URL}" class="button">Go to Dashboard</a>
                </p>
                
                <p>If you have any questions or need assistance, don't hesitate to reach out to our support team.</p>
            </div>
            
            <div class="footer">
                <p>© 2025 UPGRADE Platform</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_body = f"""
    Welcome to UPGRADE Platform!
    
    Hello {username},
    
    Your email has been verified successfully! You now have full access to all platform features.
    
    Visit the dashboard: {FRONTEND_URL}
    
    ---
    UPGRADE Platform
    """
    
    try:
        if EMAIL_PROVIDER == 'smtp':
            return send_smtp_email(to_email, subject, html_body, text_body)
        return False
    except Exception as e:
        logger.error(f"Failed to send welcome email to {to_email}: {e}")
        return False
