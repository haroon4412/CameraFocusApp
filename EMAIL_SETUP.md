# Email Configuration Guide

## Setting Up Email Verification

The app requires email configuration to send verification codes. Here's how to set it up:

### 1. Gmail Setup (Recommended)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"
3. **Set Environment Variables**:

```bash
# Windows (PowerShell)
$env:MAIL_USERNAME="your-email@gmail.com"
$env:MAIL_PASSWORD="your-16-character-app-password"
$env:MAIL_SERVER="smtp.gmail.com"
$env:MAIL_PORT="587"

# Linux/Mac
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="your-16-character-app-password"
export MAIL_SERVER="smtp.gmail.com"
export MAIL_PORT="587"
```

### 2. Alternative Email Providers

#### Outlook/Hotmail
```bash
MAIL_SERVER=smtp-mail.outlook.com
MAIL_PORT=587
MAIL_USERNAME=your-email@outlook.com
MAIL_PASSWORD=your-password
```

#### Yahoo Mail
```bash
MAIL_SERVER=smtp.mail.yahoo.com
MAIL_PORT=587
MAIL_USERNAME=your-email@yahoo.com
MAIL_PASSWORD=your-app-password
```

### 3. Testing Email Configuration

Run this test script to verify your email setup:

```python
python -c "
from app import send_verification_email, generate_verification_code
code = generate_verification_code()
result = send_verification_email('test@tatweermea.com', code)
print('Email sent successfully!' if result else 'Email failed to send')
"
```

### 4. Security Notes

- Never commit email credentials to version control
- Use environment variables for all sensitive data
- Consider using a dedicated email service for production
- Regularly rotate app passwords

### 5. Troubleshooting

**Common Issues:**
- "Authentication failed": Check username/password
- "Connection refused": Check SMTP server/port
- "TLS error": Ensure TLS is enabled
- "App password required": Use app password, not regular password

**Debug Mode:**
Set `app.config['MAIL_DEBUG'] = True` in app.py to see detailed SMTP logs.
