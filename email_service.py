import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_ADDRESS = os.getenv('GMAIL_ADDRESS')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')

print(f"Email: {GMAIL_ADDRESS}")
print(f"Password length: {len(GMAIL_APP_PASSWORD) if GMAIL_APP_PASSWORD else 0}")

def send_email(to_email, subject, html_content):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        print("Attempting to connect to SMTP...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            print("Connected to SMTP, attempting login...")
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            print("Login successful, sending message...")
            smtp.send_message(msg)
            
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_verification_email(user_email, verification_token):
    subject = "Verify your AetherChat account"
    html_content = f'''
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h1 style="color: #00b4ff;">Welcome to AetherChat!</h1>
            <p>Please verify your email by clicking the link below:</p>
            <a href="https://yourwaifai.uk/verify/{verification_token}" 
               style="display: inline-block; 
                      background-color: #00b4ff; 
                      color: white; 
                      padding: 10px 20px; 
                      text-decoration: none; 
                      border-radius: 5px;">
                Verify Email
            </a>
            <p>If you didn't create an account, you can safely ignore this email.</p>
        </div>
    '''
    return send_email(user_email, subject, html_content)
