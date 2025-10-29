#!/usr/bin/env python3
"""
Flask webapp for camera calibration with email authentication
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
import re
import random
import smtplib
import json
from io import BytesIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from PIL import Image as PILImage
from PyPDF2 import PdfMerger

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calibration_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration (you should set these as environment variables in production)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'm.haroon4479@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'aduwzhwntbiunzxa')
app.config['MAIL_USE_TLS'] = True

db = SQLAlchemy(app)

# Global variable to track calibration status
calibration_status = {
    'running': False,
    'completed': False,
    'error': None,
    'start_time': None,
    'end_time': None
}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class EmailVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    verification_code = db.Column(db.String(4), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

class CalibrationSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    camera_id = db.Column(db.String(100), nullable=True)
    lens_id = db.Column(db.String(100), nullable=True)
    calibration_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='pending')
    pdf_filename = db.Column(db.String(200), nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)
    sharpness_10m = db.Column(db.Float, nullable=True)
    sharpness_20m = db.Column(db.Float, nullable=True)
    sharpness_40m = db.Column(db.Float, nullable=True)
    tested_on_field = db.Column(db.Boolean, default=False)
    tested_by = db.Column(db.String(120), nullable=True)
    tested_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to User model
    user = db.relationship('User', backref='calibration_sessions')

def validate_email_domain(email):
    """Validate that email is from @tatweermea.com domain"""
    pattern = r'^[a-zA-Z0-9._%+-]+@tatweermea\.com$'
    return re.match(pattern, email) is not None

def generate_verification_code():
    """Generate a random 4-digit verification code"""
    return str(random.randint(1000, 9999))

def send_verification_email(email, verification_code):
    """Send verification email with 4-digit code"""
    try:
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = email
        msg['Subject'] = "Camera Calibration App - Email Verification"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 28px;">🔐 Email Verification</h1>
            </div>
            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <h2 style="color: #333; margin-top: 0;">Welcome to Camera Calibration App!</h2>
                <p style="color: #666; font-size: 16px; line-height: 1.6;">
                    Thank you for signing up! To complete your registration, please use the verification code below:
                </p>
                <div style="background: white; border: 2px dashed #667eea; border-radius: 10px; padding: 20px; text-align: center; margin: 20px 0;">
                    <h1 style="color: #667eea; font-size: 36px; margin: 0; letter-spacing: 5px; font-family: 'Courier New', monospace;">
                        {verification_code}
                    </h1>
                </div>
                <p style="color: #666; font-size: 14px;">
                    This code will expire in 10 minutes. If you didn't request this verification, please ignore this email.
                </p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    This is an automated message from Camera Calibration App
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        text = msg.as_string()
        server.sendmail(app.config['MAIL_USERNAME'], email, text)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def generate_calibration_pdf(camera_id, lens_id, username, calibration_date, calibrated_image_path, sharpness_data=None):
    """Generate a PDF report with calibration data and image"""
    try:
        # Create PDF filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"calibration_report_{camera_id}_{lens_id}_{timestamp}.pdf"
        
        # Create PDF document
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1,  # Center alignment
            textColor=colors.darkblue
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            textColor=colors.darkblue
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=6
        )
        
        # Build PDF content
        story = []
        
        # Title
        story.append(Paragraph("Camera Calibration Report", title_style))
        story.append(Spacer(1, 20))
        
        # Calibration Information
        story.append(Paragraph("Calibration Information", heading_style))
        story.append(Paragraph(f"<b>Vehicle ID:</b> {camera_id}", normal_style))
        story.append(Paragraph(f"<b>Lens ID:</b> {lens_id}", normal_style))
        story.append(Paragraph(f"<b>User:</b> {username}", normal_style))
        story.append(Paragraph(f"<b>Calibration Date:</b> {calibration_date.strftime('%Y-%m-%d')}", normal_style))
        story.append(Paragraph(f"<b>Report Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
        
        # Sharpness Measurements
        if sharpness_data:
            story.append(Spacer(1, 20))
            story.append(Paragraph("Sharpness Measurements", heading_style))
            
            # Lens information
            if 'lens_mm' in sharpness_data:
                story.append(Paragraph(f"<b>Detected Lens:</b> {sharpness_data['lens_mm']}mm", normal_style))
            
            # Sharpness scores
            story.append(Paragraph(f"<b>Sharpness at 10m:</b> {sharpness_data.get('sharpness_10m', 'N/A')}", normal_style))
            story.append(Paragraph(f"<b>Sharpness at 20m:</b> {sharpness_data.get('sharpness_20m', 'N/A')}", normal_style))
            story.append(Paragraph(f"<b>Sharpness at 40m:</b> {sharpness_data.get('sharpness_40m', 'N/A')}", normal_style))
            
            # ROIs detected
            if 'rois_detected' in sharpness_data:
                rois_str = ', '.join([f"{roi}m" for roi in sharpness_data['rois_detected']])
                story.append(Paragraph(f"<b>ROIs Detected:</b> {rois_str}", normal_style))
        
        # Field Test Status
        story.append(Spacer(1, 20))
        story.append(Paragraph("Field Testing", heading_style))
        if sharpness_data and 'tested_on_field' in sharpness_data:
            if sharpness_data['tested_on_field']:
                story.append(Paragraph("<b>Status:</b> ✅ Tested on Field", normal_style))
                if 'tested_by' in sharpness_data and sharpness_data['tested_by']:
                    story.append(Paragraph(f"<b>Tested by:</b> {sharpness_data['tested_by']}", normal_style))
                if 'tested_at' in sharpness_data and sharpness_data['tested_at']:
                    story.append(Paragraph(f"<b>Tested on:</b> {sharpness_data['tested_at']}", normal_style))
            else:
                story.append(Paragraph("<b>Status:</b> ❌ Not Tested on Field", normal_style))
        else:
            story.append(Paragraph("<b>Status:</b> ❌ Not Tested on Field", normal_style))
        
        story.append(Spacer(1, 20))
        
        # Page break before image
        story.append(PageBreak())
        
        # Calibrated Image
        story.append(Paragraph("Calibrated Image", heading_style))
        story.append(Spacer(1, 12))
        
        # Add image if it exists
        if os.path.exists(calibrated_image_path):
            # Resize image to fit page width while maintaining aspect ratio
            img = PILImage.open(calibrated_image_path)
            img_width, img_height = img.size
            
            # Calculate new dimensions to fit page width (A4 width is about 8.27 inches)
            max_width = 7.5 * inch  # Leave some margin
            if img_width > max_width:
                ratio = max_width / img_width
                new_width = max_width
                new_height = img_height * ratio
            else:
                new_width = img_width
                new_height = img_height
            
            # Ensure image doesn't exceed page height
            max_height = 9 * inch  # Leave margin for page
            if new_height > max_height:
                ratio = max_height / new_height
                new_height = max_height
                new_width = new_width * ratio
            
            pdf_image = Image(calibrated_image_path, width=new_width, height=new_height)
            story.append(pdf_image)
        else:
            story.append(Paragraph("Calibrated image not found.", normal_style))
        
        # Build PDF
        doc.build(story)
        
        return pdf_filename
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return None

def run_calibration():
    """Run the Calib.py script in a separate thread"""
    global calibration_status
    
    try:
        calibration_status['running'] = True
        calibration_status['start_time'] = datetime.now()
        calibration_status['error'] = None
        
        # Generate a random filename for this calibration session
        random_filename = f"{random.randint(10000, 99999)}.jpg"
        calibration_status['output_filename'] = random_filename
        
        # Run the calibration script with the random filename
        result = subprocess.run(['python', 'Calib.py', random_filename], 
                              capture_output=True, 
                              text=True, 
                              timeout=3000)  # 50 minute timeout
        print(result.stdout)
        print(result.stderr)
        # Check if the output file was created (indicating successful calibration)
        if os.path.exists(random_filename):
            calibration_status['completed'] = True
            calibration_status['status'] = 'completed'
            # Clean up the temporary file
            # try:
            #     os.remove(random_filename)
            # except:
            #     pass
        else:
            calibration_status['error'] = 'Calibration failed - no output file created'
            calibration_status['status'] = 'error'
            
    except subprocess.TimeoutExpired:
        calibration_status['error'] = 'Calibration timed out after 5 minutes'
        calibration_status['status'] = 'error'
    except Exception as e:
        calibration_status['error'] = str(e)
        calibration_status['status'] = 'error'
    finally:
        calibration_status['running'] = False
        calibration_status['end_time'] = datetime.now()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].lower().strip()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validation
        if not validate_email_domain(email):
            flash('Only @tatweermea.com email addresses are allowed', 'error')
            return render_template('signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('signup.html')
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('signup.html')
        
        # Generate verification code
        verification_code = generate_verification_code()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        # Store verification code
        verification = EmailVerification(
            email=email,
            verification_code=verification_code,
            expires_at=expires_at
        )
        db.session.add(verification)
        db.session.commit()
        
        # Send verification email
        if send_verification_email(email, verification_code):
            flash('Verification code sent to your email! Please check your inbox.', 'success')
            return redirect(url_for('verify_email', email=email))
        else:
            flash('Failed to send verification email. Please try again.', 'error')
            return render_template('signup.html')
    
    return render_template('signup.html')

@app.route('/verify_email/<email>', methods=['GET', 'POST'])
def verify_email(email):
    if request.method == 'POST':
        verification_code = request.form['verification_code'].strip()
        password = request.form['password']
        
        # Find the verification record
        verification = EmailVerification.query.filter_by(
            email=email, 
            verification_code=verification_code,
            is_used=False
        ).first()
        
        if not verification:
            flash('Invalid verification code', 'error')
            return render_template('verify_email.html', email=email)
        
        # Check if code is expired
        if datetime.utcnow() > verification.expires_at:
            flash('Verification code has expired. Please sign up again.', 'error')
            return redirect(url_for('signup'))
        
        # Create user account
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        
        # Mark verification as used
        verification.is_used = True
        db.session.commit()
        
        flash('Account created successfully! Please sign in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('verify_email.html', email=email)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower().strip()
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_email'] = user.email
            flash('Successfully signed in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been signed out', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get all calibration sessions from all users with user information
    calibration_sessions = CalibrationSession.query.join(User).order_by(
        CalibrationSession.created_at.desc()
    ).all()
    
    return render_template('dashboard.html', calibration_sessions=calibration_sessions)

@app.route('/start_calibration', methods=['POST'])
def start_calibration():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if calibration_status['running']:
        return jsonify({'error': 'Calibration already running'}), 400
    
    # Start calibration in a separate thread
    thread = threading.Thread(target=run_calibration)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Calibration started'})

@app.route('/calibration_status')
def get_calibration_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    return jsonify(calibration_status)

@app.route('/calibration_complete', methods=['GET', 'POST'])
def calibration_complete():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if not calibration_status['completed']:
        flash('Calibration not completed yet', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        camera_id = request.form['camera_id']
        lens_id = request.form['lens_id']
        calibration_date = request.form['calibration_date']
        
        if not camera_id or not lens_id or not calibration_date:
            flash('Please fill in all fields', 'error')
            return render_template('calibration_complete.html')
        
        # Get user information
        user = User.query.get(session['user_id'])
        username = user.email if user else 'Unknown User'
        
        # Parse calibration date
        calibration_date_obj = datetime.strptime(calibration_date, '%Y-%m-%d')
        
        # Load sharpness data if available
        sharpness_data = None
        calibrated_image_path = calibration_status.get('output_filename', 'Output.jpg')
        sharpness_file = calibrated_image_path.replace('.jpg', '_sharpness.json')
        
        if os.path.exists(sharpness_file):
            try:
                with open(sharpness_file, 'r') as f:
                    sharpness_data = json.load(f)
            except Exception as e:
                print(f"Error loading sharpness data: {e}")
        
        # Generate PDF report
        # Add field test data to sharpness_data for PDF generation
        if sharpness_data is None:
            sharpness_data = {}
        sharpness_data['tested_on_field'] = False
        sharpness_data['tested_by'] = None
        sharpness_data['tested_at'] = None
        
        pdf_filename = generate_calibration_pdf(camera_id, lens_id, username, calibration_date_obj, calibrated_image_path, sharpness_data)
        
        # Create calibration session record
        session_record = CalibrationSession(
            user_id=session['user_id'],
            camera_id=camera_id,
            lens_id=lens_id,
            calibration_date=calibration_date_obj,
            status='completed',
            pdf_filename=pdf_filename,
            image_filename=calibrated_image_path,
            sharpness_10m=sharpness_data.get('sharpness_10m') if sharpness_data else None,
            sharpness_20m=sharpness_data.get('sharpness_20m') if sharpness_data else None,
            sharpness_40m=sharpness_data.get('sharpness_40m') if sharpness_data else None
        )
        db.session.add(session_record)
        db.session.commit()
        
        # Reset calibration status so user can start a new calibration
        calibration_status['completed'] = False
        calibration_status['running'] = False
        calibration_status['error'] = None
        calibration_status['start_time'] = None
        calibration_status['end_time'] = None
        
        if pdf_filename:
            flash('Calibration session saved successfully! PDF report generated.', 'success')
        else:
            flash('Calibration session saved successfully! PDF generation failed.', 'warning')
        
        return redirect(url_for('dashboard'))
    
    return render_template('calibration_complete.html')

@app.route('/toggle_field_test/<int:session_id>', methods=['POST'])
def toggle_field_test(session_id):
    """Toggle the tested on field status for a calibration session"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get the calibration session (any user can toggle any session)
    calibration_session = CalibrationSession.query.filter_by(
        id=session_id
    ).first()
    
    if not calibration_session:
        return jsonify({'error': 'Session not found'}), 404
    
    # Get user information
    user = User.query.get(session['user_id'])
    user_email = user.email if user else 'Unknown User'
    
    # Toggle the field test status
    calibration_session.tested_on_field = not calibration_session.tested_on_field
    
    if calibration_session.tested_on_field:
        calibration_session.tested_by = user_email
        calibration_session.tested_at = datetime.utcnow()
    else:
        calibration_session.tested_by = None
        calibration_session.tested_at = None
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'tested_on_field': calibration_session.tested_on_field,
        'tested_by': calibration_session.tested_by,
        'tested_at': calibration_session.tested_at.strftime('%Y-%m-%d %H:%M') if calibration_session.tested_at else None
    })

@app.route('/download_pdf/<int:session_id>')
def download_pdf(session_id):
    """Download PDF report for a calibration session"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get the calibration session (any user can download any PDF)
    calibration_session = CalibrationSession.query.filter_by(
        id=session_id
    ).first()
    
    if not calibration_session:
        flash('PDF report not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Get user information for the calibration
    user = User.query.get(calibration_session.user_id)
    username = user.email if user else 'Unknown User'
    
    # Load sharpness data if available
    sharpness_data = None
    # Use the image_filename to find the sharpness file
    if calibration_session.image_filename:
        # Replace .jpg extension with _sharpness.json
        sharpness_file = calibration_session.image_filename.replace('.jpg', '_sharpness.json')
        
        if os.path.exists(sharpness_file):
            try:
                with open(sharpness_file, 'r') as f:
                    sharpness_data = json.load(f)
            except Exception as e:
                print(f"Error loading sharpness data: {e}")
    
    # Add current field test data to sharpness_data
    if sharpness_data is None:
        sharpness_data = {}
    
    sharpness_data['tested_on_field'] = calibration_session.tested_on_field
    sharpness_data['tested_by'] = calibration_session.tested_by
    sharpness_data['tested_at'] = calibration_session.tested_at.strftime('%Y-%m-%d %H:%M') if calibration_session.tested_at else None
    
    # Use the stored image filename from the calibration session
    calibrated_image_path = calibration_session.image_filename or 'Output.jpg'
    
    # Generate a new PDF with current data
    pdf_filename = generate_calibration_pdf(
        calibration_session.camera_id, 
        calibration_session.lens_id, 
        username, 
        calibration_session.calibration_date or datetime.now(), 
        calibrated_image_path, 
        sharpness_data
    )
    
    # Check if PDF file exists
    if pdf_filename and os.path.exists(pdf_filename):
        return send_file(
            pdf_filename,
            as_attachment=True,
            download_name=f"calibration_report_{calibration_session.camera_id}_{calibration_session.lens_id}.pdf"
        )
    else:
        flash('PDF file not found on server', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download_summary')
def download_summary():
    """Download calibration history as Excel file"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.cell.cell import MergedCell
        from openpyxl.utils import get_column_letter
        
        # Get all calibration sessions
        calibration_sessions = CalibrationSession.query.join(User).order_by(
            CalibrationSession.created_at.desc()
        ).all()
        
        # Create a new workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Calibration History"
        
        # Define styles
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=12)
        title_font = Font(bold=True, size=14)
        center_alignment = Alignment(horizontal="center", vertical="center")
        
        # Title
        ws.merge_cells('A1:I1')
        ws['A1'] = 'Calibration History Summary'
        ws['A1'].font = title_font
        ws['A1'].alignment = center_alignment
        
        # Headers
        headers = [
            'Vehicle ID', 'Lens ID', 'Calibrated By', 'Calibration Date',
            'Sharpness 10m', 'Sharpness 20m', 'Sharpness 40m', 'Status',
            'Tested on Field', 'Tested By', 'Tested At', 'Created'
        ]
        
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col_num)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_alignment
        
        # Data rows
        for row_num, calib_session in enumerate(calibration_sessions, 4):
            ws.cell(row=row_num, column=1).value = calib_session.camera_id or 'N/A'
            ws.cell(row=row_num, column=2).value = calib_session.lens_id or 'N/A'
            ws.cell(row=row_num, column=3).value = calib_session.user.email if calib_session.user else 'Unknown User'
            ws.cell(row=row_num, column=4).value = calib_session.calibration_date.strftime('%Y-%m-%d') if calib_session.calibration_date else 'N/A'
            ws.cell(row=row_num, column=5).value = round(calib_session.sharpness_10m, 1) if calib_session.sharpness_10m else 'N/A'
            ws.cell(row=row_num, column=6).value = round(calib_session.sharpness_20m, 1) if calib_session.sharpness_20m else 'N/A'
            ws.cell(row=row_num, column=7).value = round(calib_session.sharpness_40m, 1) if calib_session.sharpness_40m else 'N/A'
            ws.cell(row=row_num, column=8).value = calib_session.status.title()
            ws.cell(row=row_num, column=9).value = 'Yes' if calib_session.tested_on_field else 'No'
            ws.cell(row=row_num, column=10).value = calib_session.tested_by or 'N/A'
            ws.cell(row=row_num, column=11).value = calib_session.tested_at.strftime('%Y-%m-%d %H:%M') if calib_session.tested_at else 'N/A'
            ws.cell(row=row_num, column=12).value = calib_session.created_at.strftime('%Y-%m-%d %H:%M')
        
        # Auto-adjust column widths
        for col_num, col in enumerate(ws.columns, 1):
            max_length = 0
            for cell in col:
                try:
                    # Skip merged cells
                    if isinstance(cell, MergedCell):
                        continue
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            if max_length > 0:
                # Get column letter from column number
                column_letter = get_column_letter(col_num)
                adjusted_width = (max_length + 2) * 1.2
                ws.column_dimensions[column_letter].width = adjusted_width
        
        # Set row height for title
        ws.row_dimensions[1].height = 30
        
        # Save to BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'calibration_summary_{timestamp}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error generating Excel file: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download_all_pdfs')
def download_all_pdfs():
    """Download all calibration PDFs merged into one PDF file"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # Get all calibration sessions with PDF files
        calibration_sessions = CalibrationSession.query.filter(
            CalibrationSession.pdf_filename.isnot(None),
            CalibrationSession.status == 'completed'
        ).order_by(CalibrationSession.created_at.asc()).all()
        
        if not calibration_sessions:
            flash('No PDF reports available to download', 'warning')
            return redirect(url_for('dashboard'))
        
        # Create a PDF merger
        merger = PdfMerger()
        
        # Track if any PDFs were successfully added
        pdfs_added = 0
        
        # Add each PDF to the merger
        for calib_session in calibration_sessions:
            if calib_session.pdf_filename and os.path.exists(calib_session.pdf_filename):
                try:
                    merger.append(calib_session.pdf_filename)
                    pdfs_added += 1
                except Exception as e:
                    print(f"Error adding PDF {calib_session.pdf_filename}: {e}")
                    continue
        
        if pdfs_added == 0:
            flash('No valid PDF files found', 'error')
            merger.close()
            return redirect(url_for('dashboard'))
        
        # Save to BytesIO
        output = BytesIO()
        merger.write(output)
        merger.close()
        output.seek(0)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'all_calibration_reports_{timestamp}.pdf'
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error generating merged PDF: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
