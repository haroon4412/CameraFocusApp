# Camera Calibration Web App

A Flask web application for camera calibration with email authentication restricted to @tatweermea.com domain.

## Features

- **Email Authentication**: Sign up and sign in with @tatweermea.com email addresses only
- **Email Verification**: 4-digit verification code sent to email for account creation
- **Camera Calibration**: Execute Calib.py script through web interface
- **Data Collection**: Collect vehicle ID and calibration date after completion
- **Session Management**: Secure user sessions and data storage

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Email Settings

Set up email credentials for verification codes:

```bash
# Windows (PowerShell)
$env:MAIL_USERNAME="your-email@gmail.com"
$env:MAIL_PASSWORD="your-app-password"

# Linux/Mac
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="your-app-password"
```

See `EMAIL_SETUP.md` for detailed email configuration instructions.

### 3. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

### 4. Database

The application uses SQLite database (`calibration_app.db`) which will be created automatically on first run.

## Usage

1. **Sign Up**: Create an account with a @tatweermea.com email address
2. **Verify Email**: Enter the 4-digit code sent to your email
3. **Sign In**: Access your dashboard
4. **Start Calibration**: Click "Start Calibration" to run Calib.py
5. **Complete Session**: After calibration, provide vehicle ID and date
6. **View Results**: All calibration sessions are stored in the database

## File Structure

```
├── app.py                 # Main Flask application
├── Calib.py              # Original calibration script
├── requirements.txt      # Python dependencies
├── templates/            # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   └── calibration_complete.html
└── calibration_app.db    # SQLite database (created automatically)
```

## Security Notes

- Change the `SECRET_KEY` in production
- Use environment variables for sensitive configuration
- Consider using HTTPS in production
- Implement proper password policies

## Requirements

- Python 3.7+
- Basler camera with pypylon drivers
- OpenCV compatible camera
