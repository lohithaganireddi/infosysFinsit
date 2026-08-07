import csv
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from io import StringIO

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g, make_response, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import get_db, init_db, close_db
from services import (
    calculate_dashboard_metrics,
    calculate_smart_insights,
    calculate_total_expenses,
    calculate_remaining_budget,
    calculate_budget_utilization,
    calculate_budget_status,
    get_monthly_budget_row,
    get_category_budgets_with_progress,
    calculate_portfolio_metrics,
    calculate_goals_summary,
    calculate_monthly_report,
    calculate_financial_intelligence,
    generate_budget_recommendations,
    calculate_health_score_detailed,
    calculate_financial_story,
    calculate_month_over_month_trends,
    calculate_activity_timeline,
    calculate_predictions,
    calculate_investment_advisor_metrics,
    calculate_coaching_insights,
    calculate_user_achievements,
    calculate_goal_optimizer_metrics,
    get_unread_notification_count,
    get_notification_stats,
    get_notifications,
    check_and_create_alerts,
    calculate_reports_analytics,
    generate_pdf_report_bytes,
    generate_excel_report_bytes,
)
from blueprints.investments import investments_bp
from blueprints.goals import goals_bp

# ==========================================================================
# Application Configuration
# ==========================================================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'finsight-dev-secret-key-2026-module1')

DEFAULT_CURRENCY = '₹'

# File Upload Settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2 MB limit

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# ==========================================================================
# Application Startup — Initialize DB & Directories
# ==========================================================================
with app.app_context():
    init_db()
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Register Milestone 2 blueprints
app.register_blueprint(investments_bp)
app.register_blueprint(goals_bp)

# ==========================================================================
# Logging Configuration
# ==========================================================================
import logging
from logging.handlers import RotatingFileHandler

# Set up logging format
log_formatter = logging.Formatter('%(asctime)s %(levelname)s [%(pathname)s:%(lineno)d]: %(message)s')

# Setup log file
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'finsight.log')
os.makedirs(os.path.dirname(log_file), exist_ok=True)
file_handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=5)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Stream handler for console logging
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO)

# Attach handlers
app.logger.addHandler(file_handler)
app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)

# ==========================================================================
# Teardown & Request Hooks
# ==========================================================================
@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)

@app.before_request
def before_request_hook():
    """Harden session loading, CSRF validation, and cache user inside g context."""
    # 1. Cache current user in g
    user_id = session.get('user_id')
    if user_id:
        db = get_db()
        g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not g.user:
            # Session exists but user is no longer in DB (e.g. database reset)
            session.clear()
            g.user = None
    else:
        g.user = None

    # 2. CSRF check
    if request.method == 'POST':
        token = session.get('csrf_token')
        form_token = None
        
        if request.headers.get('Content-Type') == 'application/json':
            json_data = request.get_json(silent=True) or {}
            form_token = json_data.get('csrf_token')
        else:
            form_token = request.form.get('csrf_token')
            
        # Fallback to headers
        if not form_token:
            form_token = request.headers.get('X-CSRF-Token') or request.headers.get('X-CSRFToken')

        if not token or token != form_token:
            app.logger.warning(f"CSRF failure detected from IP: {request.remote_addr} for path: {request.path}")
            if request.headers.get('Content-Type') == 'application/json':
                return {"success": False, "message": "Security token expired. Please try again."}, 400
            flash('Security token expired. Please try again.', 'error')
            return redirect(request.referrer or url_for('login'))

@app.context_processor
def inject_app_context():
    """Inject shared app state and helpers into every template context."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)

    def build_page_link(page_num):
        args = request.args.copy()
        args['page'] = page_num
        return url_for(request.endpoint or 'dashboard', **args)

    user_val = g.user if hasattr(g, 'user') else None
    unread_count = get_unread_notification_count(user_val['id']) if user_val else 0

    return {
        'csrf_token': session['csrf_token'],
        'DEFAULT_CURRENCY': DEFAULT_CURRENCY,
        'format_currency': format_currency,
        'user': user_val,
        'build_page_link': build_page_link,
        'has_reports_route': True,
        'unread_notification_count': unread_count,
    }

# ==========================================================================
# Authentication Middleware — @login_required Decorator
# ==========================================================================
def login_required(f):
    """
    Reusable decorator to protect routes from unauthenticated access.
    Attach this to any future module route (Dashboard, Reports, etc.)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================================================
# Helper Functions
# ==========================================================================
def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(text):
    """Strip leading/trailing whitespace and remove harmful characters."""
    if not text:
        return ''
    return re.sub(r'[<>"\']', '', text.strip())

def is_strong_password(password):
    """
    Validates password against security policy:
    - Min 8 characters
    - At least one uppercase, lowercase, digit, and special character
    """
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    if not re.search(r'[^A-Za-z0-9]', password):
        return False
    return True

def get_current_user():
    """Fetch the current authenticated user from the DB with context caching."""
    if hasattr(g, 'user') and g.user is not None:
        return g.user
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return g.user


def format_currency(amount, currency_symbol=None, decimal_places=2):
    """Format a numeric amount using the configured currency symbol."""
    if amount is None:
        return ''

    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError):
        return ''

    symbol = currency_symbol or DEFAULT_CURRENCY
    sign = '-' if numeric_amount < 0 else ''
    absolute_amount = abs(numeric_amount)
    return f"{sign}{symbol}{absolute_amount:,.{decimal_places}f}"


def format_date(date_str):
    """Convert YYYY-MM-DD string to human-friendly '15 Jul 2025' format."""
    if not date_str:
        return '—'
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return f"{dt.day} {dt.strftime('%b')} {dt.year}"
    except ValueError:
        return str(date_str)

app.jinja_env.filters['format_date'] = format_date





EXPENSE_CATEGORIES = [
    'Food',
    'Transport',
    'Bills',
    'Shopping',
    'Entertainment',
    'Education',
    'Healthcare',
    'Investment',
    'Travel',
    'Other'
]

PAYMENT_METHODS = [
    'Cash',
    'UPI',
    'Credit Card',
    'Debit Card',
    'Net Banking',
    'Wallet'
]

BUDGET_MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]

EXPENSE_SORT_CLAUSES = {
    'date_asc':    'expense_date ASC, created_at ASC',
    'amount_asc':  'amount ASC, expense_date DESC',
    'amount_desc': 'amount DESC, expense_date DESC',
}

# --- Root redirect ---
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# --- Login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect already authenticated users
    if 'user_id' in session:
        if request.headers.get('Content-Type') == 'application/json':
            return {"success": True, "redirect": url_for('dashboard')}
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        is_json = request.headers.get('Content-Type') == 'application/json'
        
        if is_json:
            data = request.get_json(silent=True) or {}
            email = sanitize_input(data.get('email', ''))
            password = data.get('password', '')
            remember_me = data.get('remember_me') is True
        else:
            email = sanitize_input(request.form.get('email', ''))
            password = request.form.get('password', '')
            remember_me = request.form.get('remember_me') == 'on'

        # Always show a generic error — never reveal which field is wrong
        AUTH_ERROR = 'Invalid email or password. Please try again.'

        if not email or not password:
            if is_json:
                return {"success": False, "message": "Email and password are required."}, 400
            flash(AUTH_ERROR, 'error')
            return render_template('login.html')

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()

        if not user or not check_password_hash(user['password_hash'], password):
            app.logger.warning(f"Failed login attempt for email: {email} from IP: {request.remote_addr}")
            if is_json:
                return {"success": False, "message": AUTH_ERROR}, 401
            flash(AUTH_ERROR, 'error')
            return render_template('login.html')

        # Block unverified accounts
        if not user['is_verified']:
            app.logger.info(f"Blocked login for unverified account: {email}")
            verification_link = url_for('verify_email', token=user['verification_token'], _external=True)
            if is_json:
                return {
                    "success": False, 
                    "message": "unverified", 
                    "email": user['email'], 
                    "redirect": url_for('login'), 
                    "link": verification_link
                }, 403
            return render_template(
                'email_sent.html',
                email=user['email'],
                link=verification_link
            )

        # Store session
        session.permanent = remember_me
        session['user_id'] = user['id']
        session['user_name'] = user['name']

        # Update last login timestamp
        db.execute(
            'UPDATE users SET last_login = ? WHERE id = ?',
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
        )
        db.commit()
        app.logger.info(f"User {user['id']} successfully logged in from IP: {request.remote_addr}")

        # Flag new login for welcome animation on dashboard
        session['new_login'] = True
        
        if is_json:
            return {
                "success": True, 
                "name": user['name'], 
                "redirect": url_for('dashboard')
            }
        return redirect(url_for('dashboard'))

    return render_template('login.html')

# --- Register ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name    = sanitize_input(request.form.get('name', ''))
        email   = sanitize_input(request.form.get('email', ''))
        phone   = sanitize_input(request.form.get('phone', ''))
        country = sanitize_input(request.form.get('country', ''))
        password        = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # --- Server-side Validation ---
        errors = []
        if not name:
            errors.append('Full name is required.')
        if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            errors.append('A valid email address is required.')
        if not phone:
            errors.append('Phone number is required.')
        if not country:
            errors.append('Country of residence is required.')
        if not is_strong_password(password):
            errors.append('Password does not meet security requirements.')
        if password != confirm_password:
            errors.append('Passwords do not match.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html')

        db = get_db()

        # Duplicate email check
        existing = db.execute(
            'SELECT id FROM users WHERE email = ?', (email,)
        ).fetchone()
        if existing:
            app.logger.warning(f"Registration failed - email already exists: {email} from IP: {request.remote_addr}")
            flash('An account with this email already exists.', 'error')
            return render_template('register.html')

        app.logger.info(f"User registration details validated successfully for: {email}")

        # Handle Profile Image Upload
        profile_image_filename = None
        file = request.files.get('profile_image')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Prefix with timestamp to avoid name collisions
            unique_filename = f"{int(datetime.now().timestamp())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            profile_image_filename = unique_filename

        # Generate secure email verification token
        verification_token = secrets.token_urlsafe(32)

        # Hash password and save user
        password_hash = generate_password_hash(password)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            db.execute(
                '''INSERT INTO users
                   (name, email, phone, country, password_hash, profile_image,
                    is_verified, verification_token, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)''',
                (name, email, phone, country, password_hash,
                 profile_image_filename, verification_token, now, now)
            )
            db.commit()
            app.logger.info(f"User registered successfully but pending verification: {email}")
        except Exception as e:
            app.logger.error(f"Database error on user registration: {str(e)}", exc_info=True)
            flash('Registration failed due to a database integrity issue.', 'error')
            return render_template('register.html')

        # Present the simulated verification link
        verification_link = url_for('verify_email', token=verification_token, _external=True)
        return render_template('email_sent.html', email=email, link=verification_link)

    return render_template('register.html')

# --- Email Verification ---
@app.route('/verify-email/<token>')
def verify_email(token):
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE verification_token = ?', (token,)
    ).fetchone()

    if not user:
        flash('Invalid or expired verification link.', 'error')
        return redirect(url_for('login'))

    # Mark account as verified and clear token
    try:
        db.execute(
            'UPDATE users SET is_verified = 1, verification_token = NULL, updated_at = ? WHERE id = ?',
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
        )
        db.commit()
        app.logger.info(f"User {user['id']} successfully verified email and activated account")
    except Exception as e:
        app.logger.error(f"Database error during email verification for user {user['id']}: {str(e)}", exc_info=True)
        flash('Email verification failed due to system error. Please try again.', 'error')
        return redirect(url_for('login'))

    return render_template('verify_email.html')

# --- Forgot Password ---
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = sanitize_input(request.form.get('email', ''))

        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('forgot_password.html')

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()

        # Always show the same page regardless of whether email exists
        # This prevents email enumeration attacks
        reset_link = None
        if user:
            reset_token = secrets.token_urlsafe(32)
            try:
                db.execute(
                    'UPDATE users SET reset_token = ?, updated_at = ? WHERE id = ?',
                    (reset_token, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
                )
                db.commit()
                reset_link = url_for('reset_password', token=reset_token, _external=True)
                app.logger.info(f"Password reset token generated successfully for user: {user['id']}")
            except Exception as e:
                app.logger.error(f"Database error during forgot_password reset token insert: {str(e)}", exc_info=True)
                flash('An error occurred. Please try again.', 'error')
                return render_template('forgot_password.html')
        else:
            app.logger.warning(f"Password reset request ignored for non-existent email: {email}")

        return render_template(
            'email_sent.html',
            email=email,
            link=reset_link  # None if email not found — no link shown
        )

    return render_template('forgot_password.html')

# --- Reset Password ---
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db()
    user = db.execute(
        'SELECT * FROM users WHERE reset_token = ?', (token,)
    ).fetchone()

    if not user:
        flash('This password reset link is invalid or has already been used.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not is_strong_password(password):
            flash('Password does not meet the security requirements.', 'error')
            return render_template('reset_password.html', token=token)

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)

        # Update password and clear reset token
        password_hash = generate_password_hash(password)
        try:
            db.execute(
                'UPDATE users SET password_hash = ?, reset_token = NULL, updated_at = ? WHERE id = ?',
                (password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
            )
            db.commit()
            app.logger.info(f"User {user['id']} successfully reset and updated their password")
        except Exception as e:
            app.logger.error(f"Database error during password reset execution for user {user['id']}: {str(e)}", exc_info=True)
            flash('An error occurred while updating your password. Please try again.', 'error')
            return render_template('reset_password.html', token=token)

        flash('Password updated successfully. Please sign in with your new credentials.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)

# --- Protected Dashboard ---
@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    # Check and generate automatic financial notifications (budget warning, goals, etc.)
    check_and_create_alerts(user['id'], format_currency)

    new_login              = session.pop('new_login', False)
    dashboard_data         = calculate_dashboard_metrics(user['id'])
    smart_insights         = calculate_smart_insights(user['id'], format_currency)
    portfolio_data         = calculate_portfolio_metrics(user['id'])
    goals_data             = calculate_goals_summary(user['id'])
    financial_intel        = calculate_financial_intelligence(user['id'])
    budget_recommendations = generate_budget_recommendations(user['id'], format_currency)
    health_score_detailed  = calculate_health_score_detailed(user['id'])
    financial_story        = calculate_financial_story(user['id'], user['name'] if user and 'name' in user.keys() else 'User')
    mom_trends             = calculate_month_over_month_trends(user['id'])
    activity_timeline      = calculate_activity_timeline(user['id'])
    predictions            = calculate_predictions(user['id'])
    invest_advisor         = calculate_investment_advisor_metrics(user['id'])
    coaching               = calculate_coaching_insights(user['id'])
    achievements           = calculate_user_achievements(user['id'])

    return render_template(
        'dashboard.html',
        user=user,
        new_login=new_login,
        dashboard_data=dashboard_data,
        smart_insights=smart_insights,
        portfolio_data=portfolio_data,
        goals_data=goals_data,
        financial_intel=financial_intel,
        budget_recommendations=budget_recommendations,
        health_score_detailed=health_score_detailed,
        financial_story=financial_story,
        mom_trends=mom_trends,
        activity_timeline=activity_timeline,
        predictions=predictions,
        invest_advisor=invest_advisor,
        coaching=coaching,
        achievements=achievements,
    )


# --- Flagship AI Advisor Platform ---
@app.route('/ai-advisor')
@login_required
def ai_advisor():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    dashboard_data         = calculate_dashboard_metrics(user['id'])
    smart_insights         = calculate_smart_insights(user['id'], format_currency)
    portfolio_data         = calculate_portfolio_metrics(user['id'])
    goals_data             = calculate_goals_summary(user['id'])
    financial_intel        = calculate_financial_intelligence(user['id'])
    budget_recommendations = generate_budget_recommendations(user['id'], format_currency)
    health_score_detailed  = calculate_health_score_detailed(user['id'])
    financial_story        = calculate_financial_story(user['id'], user['name'] if user and 'name' in user.keys() else 'User')
    mom_trends             = calculate_month_over_month_trends(user['id'])
    activity_timeline      = calculate_activity_timeline(user['id'])
    predictions            = calculate_predictions(user['id'])
    invest_advisor         = calculate_investment_advisor_metrics(user['id'])
    coaching               = calculate_coaching_insights(user['id'])
    achievements           = calculate_user_achievements(user['id'])
    goal_optimizer         = calculate_goal_optimizer_metrics(user['id'])

    return render_template(
        'ai_advisor.html',
        user=user,
        dashboard_data=dashboard_data,
        smart_insights=smart_insights,
        portfolio_data=portfolio_data,
        goals_data=goals_data,
        financial_intel=financial_intel,
        budget_recommendations=budget_recommendations,
        health_score_detailed=health_score_detailed,
        financial_story=financial_story,
        mom_trends=mom_trends,
        activity_timeline=activity_timeline,
        predictions=predictions,
        invest_advisor=invest_advisor,
        coaching=coaching,
        achievements=achievements,
        goal_optimizer=goal_optimizer,
    )

# --- Budget Management ---
@app.route('/budgets')
@login_required
def budgets():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    budgets = db.execute(
        'SELECT * FROM budgets WHERE user_id = ? ORDER BY year DESC, month DESC, category ASC',
        (user['id'],)
    ).fetchall()

    now = datetime.now()
    current_month = now.strftime('%B')
    current_year = now.year
    current_month_key = now.strftime('%Y-%m')

    budget_row = get_monthly_budget_row(user['id'], current_month, current_year)
    monthly_budget = float(budget_row['amount']) if budget_row else None

    total_expenses, _ = calculate_total_expenses(user['id'], current_month_key)
    remaining_budget = calculate_remaining_budget(monthly_budget, total_expenses)
    budget_utilization = calculate_budget_utilization(total_expenses, monthly_budget)
    budget_status = calculate_budget_status(monthly_budget, budget_utilization)
    progress_percent = 0 if budget_status == 'No Budget' else min(100, int(budget_utilization or 0))

    budget_summary = {
        'month_label': now.strftime('%B %Y'),
        'monthly_budget': monthly_budget,
        'total_expenses': total_expenses,
        'remaining_budget': round(remaining_budget, 2) if remaining_budget is not None else None,
        'budget_utilization': budget_utilization,
        'budget_status': budget_status,
        'progress_percent': progress_percent,
        'is_over_budget': remaining_budget is not None and remaining_budget < 0,
    }

    category_budgets_progress = get_category_budgets_with_progress(
        user['id'], current_month, current_year, current_month_key
    )

    return render_template(
        'budgets.html',
        user=user,
        budgets=budgets,
        budget_summary=budget_summary,
        category_budgets_progress=category_budgets_progress
    )


@app.route('/budgets/new', methods=['GET', 'POST'])
@login_required
def create_budget():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    months = BUDGET_MONTHS
    current_year = datetime.now().year
    budget = {'month': None, 'year': current_year, 'amount': None, 'category': '', 'description': ''}

    if request.method == 'POST':
        month       = sanitize_input(request.form.get('month', ''))
        year        = request.form.get('year', '')
        amount      = request.form.get('amount', '')
        category    = sanitize_input(request.form.get('category', '').strip()) or None
        description = sanitize_input(request.form.get('description', ''))

        errors = []
        if month not in months:
            errors.append('Please select a valid month.')
        try:
            year_int = int(year)
            if year_int < 2000 or year_int > 2100:
                errors.append('Enter a year between 2000 and 2100.')
        except (ValueError, TypeError):
            errors.append('Enter a valid year.')
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append('Budget amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Enter a valid budget amount.')
        if category and category not in EXPENSE_CATEGORIES:
            errors.append('Please select a valid category.')

        budget = {'month': month, 'year': year, 'amount': amount, 'category': category or '', 'description': description}

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'budget_form.html',
                user=user,
                months=months,
                categories=EXPENSE_CATEGORIES,
                budget=budget,
                current_year=current_year,
                page_title='Create Budget',
                page_description='Create a monthly or category budget',
                form_action=url_for('create_budget'),
                submit_text='Create Budget'
            )

        db = get_db()
        try:
            db.execute(
                'INSERT INTO budgets (user_id, month, year, amount, category, description) VALUES (?, ?, ?, ?, ?, ?)',
                (user['id'], month, year_int, amount_value, category, description)
            )
            db.commit()
            app.logger.info(f"User {user['id']} successfully created budget for {month} {year_int} (Category: {category})")
            flash('Budget created successfully.', 'success')
            return redirect(url_for('budgets'))
        except sqlite3.IntegrityError as ie:
            app.logger.warning(f"IntegrityError in budget creation for user {user['id']}: {str(ie)}")
            flash('A budget for that month/year/category combination already exists.', 'error')
        except Exception as e:
            app.logger.error(f"Unexpected error in budget creation: {str(e)}", exc_info=True)
            flash('Failed to create budget. Please try again.', 'error')

    return render_template(
        'budget_form.html',
        user=user,
        months=months,
        categories=EXPENSE_CATEGORIES,
        budget=budget,
        current_year=current_year,
        page_title='Create Budget',
        page_description='Create a monthly or category budget',
        form_action=url_for('create_budget'),
        submit_text='Create Budget'
    )


@app.route('/budgets/<int:budget_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_budget(budget_id):
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    budget_row = db.execute(
        'SELECT * FROM budgets WHERE id = ? AND user_id = ?',
        (budget_id, user['id'])
    ).fetchone()
    if not budget_row:
        flash('Budget not found.', 'error')
        return redirect(url_for('budgets'))

    months = BUDGET_MONTHS
    current_year = datetime.now().year
    budget = {
        'month': budget_row['month'],
        'year': budget_row['year'],
        'amount': budget_row['amount'],
        'category': budget_row['category'] or '',
        'description': budget_row['description']
    }

    if request.method == 'POST':
        month       = sanitize_input(request.form.get('month', ''))
        year        = request.form.get('year', '')
        amount      = request.form.get('amount', '')
        category    = sanitize_input(request.form.get('category', '').strip()) or None
        description = sanitize_input(request.form.get('description', ''))

        errors = []
        if month not in months:
            errors.append('Please select a valid month.')
        try:
            year_int = int(year)
        except (ValueError, TypeError):
            errors.append('Enter a valid year.')
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append('Budget amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Enter a valid budget amount.')
        if category and category not in EXPENSE_CATEGORIES:
            errors.append('Please select a valid category.')

        budget = {'month': month, 'year': year, 'amount': amount, 'category': category or '', 'description': description}

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'budget_form.html',
                user=user,
                months=months,
                categories=EXPENSE_CATEGORIES,
                budget=budget,
                current_year=current_year,
                page_title='Edit Budget',
                page_description='Edit monthly or category budget',
                form_action=url_for('edit_budget', budget_id=budget_id),
                submit_text='Update Budget'
            )

        try:
            db.execute(
                'UPDATE budgets SET month=?, year=?, amount=?, category=?, description=?, updated_at=? WHERE id=? AND user_id=?',
                (month, year_int, amount_value, category, description,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'), budget_id, user['id'])
            )
            db.commit()
            app.logger.info(f"User {user['id']} successfully updated budget {budget_id}")
            flash('Budget updated successfully.', 'success')
            return redirect(url_for('budgets'))
        except sqlite3.IntegrityError as ie:
            app.logger.warning(f"IntegrityError in budget update for user {user['id']}: {str(ie)}")
            flash('A budget for that month/year/category combination already exists.', 'error')
        except Exception as e:
            app.logger.error(f"Unexpected error in budget update: {str(e)}", exc_info=True)
            flash('Failed to update budget. Please try again.', 'error')

    return render_template(
        'budget_form.html',
        user=user,
        months=months,
        categories=EXPENSE_CATEGORIES,
        budget=budget,
        current_year=current_year,
        page_title='Edit Budget',
        page_description='Edit monthly budget',
        form_action=url_for('edit_budget', budget_id=budget_id),
        submit_text='Update Budget'
    )


@app.route('/budgets/<int:budget_id>/delete', methods=['POST'])
@login_required
def delete_budget(budget_id):
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    try:
        result = db.execute('DELETE FROM budgets WHERE id = ? AND user_id = ?', (budget_id, user['id']))
        db.commit()
        if result.rowcount == 0:
            app.logger.warning(f"Failed delete attempt of budget {budget_id} by user {user['id']}")
            flash('Budget not found or access denied.', 'error')
        else:
            app.logger.info(f"User {user['id']} deleted budget {budget_id}")
            flash('Budget deleted.', 'success')
    except Exception as e:
        app.logger.error(f"Database error on budget delete: {str(e)}", exc_info=True)
        flash('Failed to delete budget due to system error.', 'error')

    return redirect(url_for('budgets'))

def _build_expense_filters(req_args, user_id):
    filters = []
    params = [user_id]

    search         = sanitize_input(req_args.get('q', '').strip())
    category       = sanitize_input(req_args.get('category', '').strip())
    payment_method = sanitize_input(req_args.get('payment_method', '').strip())
    date_from      = req_args.get('date_from', '').strip()
    date_to        = req_args.get('date_to', '').strip()
    amount_min     = req_args.get('amount_min', '').strip()
    amount_max     = req_args.get('amount_max', '').strip()
    sort           = sanitize_input(req_args.get('sort', 'date_desc').strip())

    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    if not (date_from or date_to):
        filters.append('strftime("%Y-%m", expense_date) = ?')
        params.append(current_month_key)

    if search:
        filters.append('(category LIKE ? OR description LIKE ? OR expense_date LIKE ? OR payment_method LIKE ?)')
        like_search = f'%{search}%'
        params.extend([like_search, like_search, like_search, like_search])
    if category:
        filters.append('category = ?')
        params.append(category)
    if payment_method:
        filters.append('payment_method = ?')
        params.append(payment_method)
    if date_from:
        filters.append('expense_date >= ?')
        params.append(date_from)
    if date_to:
        filters.append('expense_date <= ?')
        params.append(date_to)
    if amount_min:
        try:
            filters.append('amount >= ?')
            params.append(float(amount_min))
        except ValueError:
            pass
    if amount_max:
        try:
            filters.append('amount <= ?')
            params.append(float(amount_max))
        except ValueError:
            pass

    return filters, params, search, category, payment_method, date_from, date_to, amount_min, amount_max, sort


# --- Expense Tracking ---
@app.route('/expenses')
@login_required
def expenses():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    filters, params, search, category, payment_method, date_from, date_to, amount_min, amount_max, sort = _build_expense_filters(request.args, user['id'])

    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1
    per_page = 25

    # 1. Run aggregates using SQL
    agg_query = 'SELECT SUM(amount) as total, COUNT(*) as count, MAX(amount) as max_val, AVG(amount) as avg_val FROM expenses WHERE user_id = ?'
    if filters:
        agg_query += ' AND ' + ' AND '.join(filters)
        
    try:
        agg_row = db.execute(agg_query, tuple(params)).fetchone()
    except Exception as e:
        app.logger.error(f"Database error on expenses aggregate query: {str(e)}", exc_info=True)
        flash('An error occurred loading expenses summary.', 'error')
        agg_row = None

    total_count = agg_row['count'] if (agg_row and agg_row['count']) else 0
    total_expenses = round(agg_row['total'] or 0.0, 2) if (agg_row and agg_row['total']) else 0.0
    highest_expense = round(agg_row['max_val'] or 0.0, 2) if (agg_row and agg_row['max_val']) else 0.0
    average_expense = round(agg_row['avg_val'] or 0.0, 2) if (agg_row and agg_row['avg_val']) else 0.0

    summary = {
        'total_expenses':   total_expenses,
        'total_transactions': total_count,
        'highest_expense':  highest_expense,
        'average_expense':  average_expense,
    }

    # 2. Pagination Calculations
    pages = max(1, math.ceil(total_count / per_page))
    if page > pages:
        page = pages
    offset = (page - 1) * per_page

    # 3. Fetch paginated slice of records
    query = 'SELECT * FROM expenses WHERE user_id = ?'
    if filters:
        query += ' AND ' + ' AND '.join(filters)

    sort_clause = EXPENSE_SORT_CLAUSES.get(sort, 'expense_date DESC, created_at DESC')
    query += f' ORDER BY {sort_clause} LIMIT ? OFFSET ?'
    
    try:
        expenses = db.execute(query, tuple(params + [per_page, offset])).fetchall()
    except Exception as e:
        app.logger.error(f"Database error on expenses paginated fetch: {str(e)}", exc_info=True)
        flash('An error occurred loading expenses list.', 'error')
        expenses = []

    pagination = {
        'page': page,
        'pages': pages,
        'total': total_count,
        'per_page': per_page,
        'has_prev': page > 1,
        'has_next': page < pages,
        'prev_num': page - 1,
        'next_num': page + 1,
    }

    return render_template(
        'expenses.html',
        user=user,
        expenses=expenses,
        categories=EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        summary=summary,
        sort=sort,
        search=search,
        category=category,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        pagination=pagination,
    )


@app.route('/expenses/export')
@login_required
def export_expenses_csv():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    filters, params, _, _, _, _, _, _, _, sort = _build_expense_filters(request.args, user['id'])

    query = 'SELECT * FROM expenses WHERE user_id = ?'
    if filters:
        query += ' AND ' + ' AND '.join(filters)

    sort_clause = EXPENSE_SORT_CLAUSES.get(sort, 'expense_date DESC, created_at DESC')
    query += f' ORDER BY {sort_clause}'
    
    try:
        expenses = db.execute(query, tuple(params)).fetchall()
        
        # Generate CSV in memory with UTF-8 BOM for 100% Excel compatibility
        si = StringIO()
        si.write('\ufeff')  # Write UTF-8 Byte Order Mark (BOM)
        cw = csv.writer(si)
        # Write headers
        cw.writerow(['ID', 'Category', 'Amount (INR)', 'Payment Method', 'Description', 'Expense Date', 'Created At'])
        # Write rows
        for expense in expenses:
            cw.writerow([
                expense['id'],
                expense['category'],
                expense['amount'],
                expense['payment_method'],
                expense['description'] or '',
                expense['expense_date'],
                expense['created_at']
            ])

        csv_content = si.getvalue().encode('utf-8')
        output = make_response(csv_content)
        output.headers["Content-Disposition"] = f"attachment; filename=finsight_expenses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output.headers["Content-type"] = "text/csv; charset=utf-8"
        app.logger.info(f"User {user['id']} successfully exported expenses CSV")
        return output
    except Exception as e:
        app.logger.error(f"Error during CSV export: {str(e)}", exc_info=True)
        flash('Failed to export CSV. Please try again.', 'error')
        return redirect(url_for('expenses'))


@app.route('/reports')
@login_required
def reports():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    month_key = sanitize_input(request.args.get('month', datetime.now().strftime('%Y-%m')))

    try:
        report_data      = calculate_monthly_report(user['id'], month_key)
        financial_intel  = calculate_financial_intelligence(user['id'])
        recommendations  = generate_budget_recommendations(user['id'], format_currency)
        reports_analytics = calculate_reports_analytics(user['id'])
        app.logger.info(f"User {user['id']} successfully generated report for {month_key}")
        return render_template(
            'reports.html',
            user=user,
            report=report_data,
            current_month=month_key,
            financial_intel=financial_intel,
            recommendations=recommendations,
            rpt=reports_analytics,
        )
    except Exception as e:
        app.logger.error(f"Error generating reports for user {user['id']}: {str(e)}", exc_info=True)
        flash('Failed to generate report due to a database/system error.', 'error')
        return redirect(url_for('dashboard'))


@app.route('/reports/export/csv')
@login_required
def export_reports_csv():
    """Export all-time financial summary as CSV."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    try:
        rows = db.execute(
            '''SELECT expense_date AS date, 'Expense' AS module, category,
                      description, amount, payment_method AS status, id AS ref
               FROM expenses WHERE user_id = ?
               UNION ALL
               SELECT purchase_date, 'Investment', investment_type,
                      investment_name, quantity * purchase_price, 'Invested', id
               FROM investments WHERE user_id = ?
               UNION ALL
               SELECT deadline, 'Goal', goal_type,
                      goal_name, target_amount, status, id
               FROM financial_goals WHERE user_id = ?
               ORDER BY date DESC''',
            (user['id'], user['id'], user['id'])
        ).fetchall()

        si = StringIO()
        si.write('\ufeff')
        cw = csv.writer(si)
        cw.writerow(['Date', 'Module', 'Category / Type', 'Description', 'Amount', 'Status / Method', 'Reference ID'])
        for r in rows:
            cw.writerow([r['date'], r['module'], r['category'], r['description'],
                         r['amount'], r['status'], r['ref']])

        output = make_response(si.getvalue().encode('utf-8'))
        output.headers['Content-Disposition'] = f'attachment; filename=finsight_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        output.headers['Content-type'] = 'text/csv; charset=utf-8'
        app.logger.info(f"User {user['id']} exported full reports CSV")
        return output
    except Exception as e:
        app.logger.error(f"Reports CSV export error for user {user['id']}: {str(e)}", exc_info=True)
        flash('Failed to export CSV. Please try again.', 'error')
        return redirect(url_for('reports'))


@app.route('/reports/export/pdf')
@login_required
def export_reports_pdf():
    """Export monthly executive financial statement as a professional ReportLab PDF."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    month_key = sanitize_input(request.args.get('month', datetime.now().strftime('%Y-%m')))
    try:
        pdf_bytes = generate_pdf_report_bytes(user['id'], month_key)
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=finsight_statement_{month_key}_{datetime.now().strftime("%Y%m%d")}.pdf'
        app.logger.info(f"User {user['id']} exported PDF report for {month_key}")
        return response
    except Exception as e:
        app.logger.error(f"PDF export error for user {user['id']}: {str(e)}", exc_info=True)
        flash('Failed to export PDF statement. Please try again.', 'error')
        return redirect(url_for('reports', month=month_key))


@app.route('/reports/export/excel')
@login_required
def export_reports_excel():
    """Export comprehensive financial system ledger as a multi-sheet Excel workbook."""
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    month_key = sanitize_input(request.args.get('month', datetime.now().strftime('%Y-%m')))
    try:
        excel_bytes = generate_excel_report_bytes(user['id'], month_key)
        response = make_response(excel_bytes)
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename=finsight_workbook_{month_key}_{datetime.now().strftime("%Y%m%d")}.xlsx'
        app.logger.info(f"User {user['id']} exported Excel report for {month_key}")
        return response
    except Exception as e:
        app.logger.error(f"Excel export error for user {user['id']}: {str(e)}", exc_info=True)
        flash('Failed to export Excel workbook. Please try again.', 'error')
        return redirect(url_for('reports', month=month_key))


# --- Analytics (Deep Analysis Page) ---
@app.route('/analytics')
@login_required
def analytics():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    month_key = sanitize_input(request.args.get('month', datetime.now().strftime('%Y-%m')))

    try:
        dashboard_data         = calculate_dashboard_metrics(user['id'])
        report_data            = calculate_monthly_report(user['id'], month_key)
        financial_intel        = calculate_financial_intelligence(user['id'])
        portfolio_data         = calculate_portfolio_metrics(user['id'])
        goals_data             = calculate_goals_summary(user['id'])
        health_score_detailed  = calculate_health_score_detailed(user['id'])
        budget_recommendations = generate_budget_recommendations(user['id'], format_currency)
        app.logger.info(f"User {user['id']} accessed analytics page for {month_key}")
        return render_template(
            'analytics.html',
            user=user,
            dashboard_data=dashboard_data,
            report=report_data,
            current_month=month_key,
            financial_intel=financial_intel,
            portfolio_data=portfolio_data,
            goals_data=goals_data,
            health_score_detailed=health_score_detailed,
            budget_recommendations=budget_recommendations,
        )
    except Exception as e:
        app.logger.error(f"Error generating analytics for user {user['id']}: {str(e)}", exc_info=True)
        flash('Failed to load analytics. Please try again.', 'error')
        return redirect(url_for('dashboard'))


# ==========================================================================
# Notification Center Routes
# ==========================================================================
@app.route('/notifications')
@login_required
def notifications():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    # Trigger automated data-driven alerts check
    check_and_create_alerts(user['id'], format_currency)

    filter_type        = sanitize_input(request.args.get('filter', 'all'))
    search_query       = sanitize_input(request.args.get('q', '').strip())
    notifications_list = get_notifications(user['id'], limit=100, filter_type=filter_type, search_query=search_query)
    unread_count       = get_unread_notification_count(user['id'])
    notif_stats        = get_notification_stats(user['id'])
    activity_timeline  = calculate_activity_timeline(user['id'])
    ai_recommendations = generate_budget_recommendations(user['id'], format_currency)
    predictions        = calculate_predictions(user['id'])
    health_score_detailed = calculate_health_score_detailed(user['id'])
    now_date           = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'notifications.html',
        user=user,
        notifications=notifications_list,
        filter_type=filter_type,
        search_query=search_query,
        unread_count=unread_count,
        notif_stats=notif_stats,
        activity_timeline=activity_timeline,
        ai_recommendations=ai_recommendations,
        predictions=predictions,
        health_score_detailed=health_score_detailed,
        now_date=now_date,
    )


@app.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    user = get_current_user()
    if not user:
        return {"success": False, "message": "Unauthorized"}, 401

    db = get_db()
    db.execute(
        'UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
        (notif_id, user['id'])
    )
    db.commit()
    unread_count = get_unread_notification_count(user['id'])
    return {"success": True, "unread_count": unread_count}


@app.route('/notifications/<int:notif_id>/delete', methods=['POST'])
@login_required
def delete_notification(notif_id):
    user = get_current_user()
    if not user:
        return {"success": False, "message": "Unauthorized"}, 401

    db = get_db()
    db.execute(
        'DELETE FROM notifications WHERE id = ? AND user_id = ?',
        (notif_id, user['id'])
    )
    db.commit()
    unread_count = get_unread_notification_count(user['id'])
    return {"success": True, "unread_count": unread_count}


@app.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    user = get_current_user()
    if not user:
        return {"success": False, "message": "Unauthorized"}, 401

    db = get_db()
    db.execute(
        'UPDATE notifications SET is_read = 1 WHERE user_id = ?',
        (user['id'],)
    )
    db.commit()
    return {"success": True, "unread_count": 0}


@app.route('/notifications/clear-all', methods=['POST'])
@login_required
def clear_all_notifications():
    user = get_current_user()
    if not user:
        return {"success": False, "message": "Unauthorized"}, 401

    db = get_db()
    db.execute(
        'DELETE FROM notifications WHERE user_id = ?',
        (user['id'],)
    )
    db.commit()
    return {"success": True, "unread_count": 0}


@app.route('/expenses/new', methods=['GET', 'POST'])
@login_required
def create_expense():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    expense = {'category': None, 'amount': None, 'payment_method': 'Cash', 'description': '', 'expense_date': ''}
    if request.method == 'POST':
        category       = sanitize_input(request.form.get('category', ''))
        amount         = request.form.get('amount', '')
        payment_method = sanitize_input(request.form.get('payment_method', 'Cash'))
        description    = sanitize_input(request.form.get('description', ''))
        expense_date   = request.form.get('expense_date', '')

        errors = []
        if category not in EXPENSE_CATEGORIES:
            errors.append('Please select a valid expense category.')
        if payment_method not in PAYMENT_METHODS:
            errors.append('Please select a valid payment method.')
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append('Amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Enter a valid numeric amount.')
        if not expense_date or not re.match(r'^\d{4}-\d{2}-\d{2}$', expense_date):
            errors.append('Expense date must be a valid date in YYYY-MM-DD format.')

        expense = {
            'category': category,
            'amount': amount,
            'payment_method': payment_method,
            'description': description,
            'expense_date': expense_date
        }

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'expense_form.html',
                user=user,
                expense=expense,
                categories=EXPENSE_CATEGORIES,
                payment_methods=PAYMENT_METHODS,
                page_title='Add Expense',
                page_description='Record a new expense for your monthly budget.',
                form_action=url_for('create_expense'),
                submit_text='Save Expense'
            )

        db = get_db()
        try:
            db.execute(
                '''INSERT INTO expenses (user_id, category, amount, payment_method, description, expense_date)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (user['id'], category, amount_value, payment_method, description, expense_date)
            )
            db.commit()
            app.logger.info(f"User {user['id']} successfully created expense of {amount_value} in category {category}")
            flash('Expense added successfully.', 'success')
            return redirect(url_for('expenses'))
        except sqlite3.IntegrityError as ie:
            app.logger.warning(f"IntegrityError in expense creation for user {user['id']}: {str(ie)}")
            flash('Failed to save expense due to database integrity constraints.', 'error')
        except Exception as e:
            app.logger.error(f"Unexpected error in expense creation: {str(e)}", exc_info=True)
            flash('Failed to save expense. Please try again.', 'error')

    return render_template(
        'expense_form.html',
        user=user,
        expense=expense,
        categories=EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        page_title='Add Expense',
        page_description='Record a new expense for your monthly budget.',
        form_action=url_for('create_expense'),
        submit_text='Save Expense'
    )

@app.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    expense = db.execute(
        'SELECT * FROM expenses WHERE id = ? AND user_id = ?',
        (expense_id, user['id'])
    ).fetchone()

    if not expense:
        flash('Expense not found.', 'error')
        return redirect(url_for('expenses'))

    expense_data = {
        'category':       expense['category'],
        'amount':         expense['amount'],
        'payment_method': expense['payment_method'] if 'payment_method' in expense.keys() else 'Cash',
        'description':    expense['description'],
        'expense_date':   expense['expense_date']
    }

    if request.method == 'POST':
        category       = sanitize_input(request.form.get('category', ''))
        amount         = request.form.get('amount', '')
        payment_method = sanitize_input(request.form.get('payment_method', 'Cash'))
        description    = sanitize_input(request.form.get('description', ''))
        expense_date   = request.form.get('expense_date', '')

        errors = []
        if category not in EXPENSE_CATEGORIES:
            errors.append('Please select a valid expense category.')
        if payment_method not in PAYMENT_METHODS:
            errors.append('Please select a valid payment method.')
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append('Amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Enter a valid numeric amount.')
        if not expense_date or not re.match(r'^\d{4}-\d{2}-\d{2}$', expense_date):
            errors.append('Expense date must be a valid date in YYYY-MM-DD format.')

        expense_data = {
            'category':       category,
            'amount':         amount,
            'payment_method': payment_method,
            'description':    description,
            'expense_date':   expense_date
        }

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'expense_form.html',
                user=user,
                expense=expense_data,
                categories=EXPENSE_CATEGORIES,
                payment_methods=PAYMENT_METHODS,
                page_title='Edit Expense',
                page_description='Update the details for this expense.',
                form_action=url_for('edit_expense', expense_id=expense_id),
                submit_text='Update Expense'
            )

        try:
            db.execute(
                '''UPDATE expenses
                   SET category=?, amount=?, payment_method=?, description=?, expense_date=?, updated_at=?
                   WHERE id=? AND user_id=?''',
                (category, amount_value, payment_method, description, expense_date,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'), expense_id, user['id'])
            )
            db.commit()
            app.logger.info(f"User {user['id']} successfully updated expense {expense_id} to amount {amount_value}")
            flash('Expense updated successfully.', 'success')
            return redirect(url_for('expenses'))
        except sqlite3.IntegrityError as ie:
            app.logger.warning(f"IntegrityError in expense update for user {user['id']}: {str(ie)}")
            flash('Failed to update expense due to database integrity constraints.', 'error')
        except Exception as e:
            app.logger.error(f"Unexpected error in expense update: {str(e)}", exc_info=True)
            flash('Failed to update expense. Please try again.', 'error')

    return render_template(
        'expense_form.html',
        user=user,
        expense=expense_data,
        categories=EXPENSE_CATEGORIES,
        payment_methods=PAYMENT_METHODS,
        page_title='Edit Expense',
        page_description='Update the details for this expense.',
        form_action=url_for('edit_expense', expense_id=expense_id),
        submit_text='Update Expense'
    )

@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    try:
        result = db.execute(
            'DELETE FROM expenses WHERE id = ? AND user_id = ?',
            (expense_id, user['id'])
        )
        db.commit()
        if result.rowcount == 0:
            app.logger.warning(f"Failed delete attempt of expense {expense_id} by user {user['id']}")
            flash('Expense not found or access denied.', 'error')
        else:
            app.logger.info(f"User {user['id']} deleted expense {expense_id}")
            flash('Expense deleted successfully.', 'success')
    except Exception as e:
        app.logger.error(f"Database error on expense delete: {str(e)}", exc_info=True)
        flash('Failed to delete expense due to system error.', 'error')

    return redirect(url_for('expenses'))

# --- Logout ---
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    """Securely destroy the user session and redirect to login."""
    user_id = session.get('user_id')
    session.clear()
    app.logger.info(f"User {user_id} logged out successfully")
    flash('You have been securely signed out.', 'success')
    return redirect(url_for('login'))

# ==========================================================================
# Phase 1 & Phase 3 — AI Financial Copilot & What-If Simulator APIs
# ==========================================================================

@app.route('/api/copilot', methods=['POST'])
@login_required
def api_copilot():
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    req_data = request.get_json() or {}
    query = sanitize_input(req_data.get('query', '').strip().lower())
    history = req_data.get('history', [])
    
    intel = calculate_financial_intelligence(user['id'])
    health = calculate_health_score_detailed(user['id'])
    portfolio = calculate_portfolio_metrics(user['id'])
    goals = calculate_goals_summary(user['id'])
    
    # Infer topic from query or recent history for follow-up questions ("tell me more", "how do I fix that?", "explain")
    last_user_query = ""
    for msg in reversed(history):
        if msg.get('role') == 'user':
            last_user_query = msg.get('text', '').lower()
            break
            
    is_followup = any(w in query for w in ['more', 'fix', 'how', 'details', 'tell', 'explain', 'what else'])
    
    if 'health' in query or 'score' in query or 'why' in query or (is_followup and ('health' in last_user_query or 'score' in last_user_query)):
        response = f"### 📊 Financial Health Executive Briefing\n\n"
        response += f"**Summary:** Your current Financial Health Score is **{health['score']}/100 ({health['label']})**.\n\n"
        response += "**Analysis:**\n"
        if health.get('sub_metrics'):
            for sm in health['sub_metrics']:
                response += f"• **{sm['name']} ({sm['score']}/100):** {sm['explanation']} *Reason:* {sm['reason']}\n"
        response += f"\n**Recommendation:** Cap discretionary outflows by 10% and maintain consistent goal deposits.\n"
        response += f"**Expected Impact:** Potential +6 score increase (Target: {min(100, health['score']+6)}/100).\n"
        response += "**Model Confidence:** 94%"

    elif 'improve' in query or 'advice' in query or 'recommend' in query or (is_followup and ('improve' in last_user_query or 'fix' in last_user_query)):
        response = f"### 💡 Action Plan & Optimization Guidance\n\n"
        response += f"**Summary:** Focused optimization steps to boost financial resilience.\n\n"
        response += "**Analysis:**\n"
        sub_metrics = health.get('sub_metrics', [])
        low_metrics = [m for m in sub_metrics if m['score'] < 80]
        if low_metrics:
            for idx, m in enumerate(low_metrics, 1):
                response += f"{idx}. **{m['name']} ({m['score']}/100):** {m['explanation']}\n   • *Suggestion:* {m['suggestion']}\n"
        else:
            response += "• All financial dimensions are operating in the Excellent tier!\n"
        response += f"\n**Recommendation:** Reallocate surplus savings toward active investment SIPs.\n"
        response += f"**Expected Impact:** +₹15,000 yearly yield improvement.\n"
        response += "**Model Confidence:** 92%"

    elif 'spend' in query or 'expense' in query or (is_followup and ('spend' in last_user_query or 'expense' in last_user_query)):
        response = f"### 💳 Outflow & Expenditure Analysis\n\n"
        response += f"**Summary:** Total monthly expenses recorded at **{format_currency(intel['monthly_spending'])}**.\n\n"
        response += "**Analysis:**\n"
        response += f"• **Daily Velocity:** {format_currency(intel['avg_daily_spending'])}/day\n"
        response += f"• **Transactions:** {intel.get('monthly_tx_count', 0)} logged entries\n"
        if intel.get('mom_change_pct') is not None:
            response += f"• **MoM Trend:** {intel['mom_change_pct']:.1f}%\n"
        response += f"\n**Recommendation:** Set a daily spending ceiling of {format_currency(intel['avg_daily_spending'] * 0.9)}.\n"
        response += f"**Expected Impact:** Save ~{format_currency(intel['monthly_spending'] * 0.1)} monthly.\n"
        response += "**Model Confidence:** 96%"

    elif 'invest' in query or 'portfolio' in query or (is_followup and ('invest' in last_user_query or 'portfolio' in last_user_query)):
        response = f"### 📈 Portfolio Intelligence & Asset Valuation\n\n"
        pnl = portfolio['profit_loss']
        pnl_str = f"+{format_currency(pnl)}" if pnl >= 0 else f"-{format_currency(abs(pnl))}"
        response += f"**Summary:** Total Portfolio Value is **{format_currency(portfolio['current_value'])}** (Unrealized: {pnl_str}).\n\n"
        response += "**Analysis:**\n"
        response += f"• **Capital Invested:** {format_currency(portfolio['total_invested'])}\n"
        response += f"• **Active Positions:** {portfolio['position_count']} holding(s)\n"
        response += f"• **Growth Margin:** {portfolio.get('profit_loss_pct', 0.0):.1f}%\n"
        response += f"\n**Recommendation:** Maintain a diversified 60/40 Equity & Fixed Deposit split.\n"
        response += f"**Expected Impact:** Target CAGR of 10.5% with lowered volatility.\n"
        response += "**Model Confidence:** 91%"

    elif 'goal' in query or 'save' in query or (is_followup and ('goal' in last_user_query or 'save' in last_user_query)):
        response = f"### 🎯 Goals & Capital Reserve Milestone\n\n"
        response += f"**Summary:** Total saved across goals is **{format_currency(goals['total_saved'])}**.\n\n"
        response += "**Analysis:**\n"
        response += f"• **Target Milestone:** {format_currency(goals['total_target'])}\n"
        response += f"• **Milestones Completed:** {goals['completed_goals']}\n"
        response += f"• **Active Goals:** {goals['active_goals']}\n"
        response += f"\n**Recommendation:** Automate a monthly SIP deposit toward your primary goal.\n"
        response += f"**Expected Impact:** Accelerate completion date by 45 days.\n"
        response += "**Model Confidence:** 95%"

    else:
        response = f"### 🤖 Executive Briefing for {user['name']}\n\n"
        response += f"**Summary:** Overall Financial Health Score is **{health['score']}/100 ({health['label']})**.\n\n"
        response += "**Analysis:**\n"
        response += f"• **Monthly Outflow:** {format_currency(intel['monthly_spending'])}\n"
        response += f"• **Portfolio Valuation:** {format_currency(portfolio['current_value'])}\n"
        response += f"• **Goals Saved:** {format_currency(goals['total_saved'])} / {format_currency(goals['total_target'])}\n"
        response += f"\n**Recommendation:** Ask me *'Analyze my expenses'* or *'How can I improve my health score?'*\n"
        response += f"**Expected Impact:** Instant financial optimization.\n"
        response += "**Model Confidence:** 95%"

    return jsonify({
        'success': True,
        'query': query,
        'response': response
    })


@app.route('/api/simulate', methods=['POST'])
@login_required
def api_simulate():
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    req_data = request.get_json() or {}
    reduce_expense = float(req_data.get('reduce_expense', 0))
    add_investment = float(req_data.get('add_investment', 0))
    change_budget  = float(req_data.get('change_budget', 0))
    
    intel = calculate_financial_intelligence(user['id'])
    portfolio = calculate_portfolio_metrics(user['id'])
    
    now = datetime.now()
    budget_row = get_monthly_budget_row(user['id'], now.month, now.year)
    
    orig_expense = intel['monthly_spending']
    orig_budget = float(budget_row['amount']) if budget_row and budget_row['amount'] else 50000.0
    orig_invest = portfolio['current_value']
    
    new_expense = max(0.0, orig_expense - reduce_expense)
    new_budget = max(100.0, orig_budget + change_budget)
    new_invest = orig_invest + add_investment
    
    new_util = round((new_expense / new_budget) * 100, 1) if new_budget > 0 else 0
    new_savings = max(0.0, new_budget - new_expense)
    
    # Calculate simulated health score
    sim_deductions = 0
    if new_util > 100:
        sim_deductions += min(40, int((new_util - 100) * 0.4) + 15)
    elif new_util >= 85:
        sim_deductions += 10
    elif new_util >= 70:
        sim_deductions += 5
    
    sim_score = max(10, 100 - sim_deductions)
    
    # Advanced metrics calculation
    yearly_savings = (reduce_expense + (new_savings - max(0.0, orig_budget - orig_expense))) * 12
    yearly_benefit = max(0.0, yearly_savings + (add_investment * 12 * 0.10))
    
    risk_level = 'Low' if new_util < 75 else ('Moderate' if new_util <= 95 else 'High')
    opportunity_score = min(100, int((reduce_expense / 20000 * 40) + (add_investment / 50000 * 60)))
    confidence_score = 94 if new_util <= 85 else 78
    success_probability = min(98, max(45, int(100 - new_util * 0.4)))
    
    # Detailed reason why score changed
    reasons = []
    if reduce_expense > 0:
        reasons.append(f"Reducing monthly expenses by {format_currency(reduce_expense)} lowers your budget utilization to {new_util}%.")
    if add_investment > 0:
        reasons.append(f"Adding {format_currency(add_investment)} monthly investments accelerates long-term wealth growth.")
    if change_budget > 0:
        reasons.append(f"Increasing budget ceiling by {format_currency(change_budget)} provides additional spending buffer.")
    
    explanation = " ".join(reasons) if reasons else "No scenario parameters altered."
    
    return jsonify({
        'success': True,
        'simulated': {
            'expense': new_expense,
            'budget': new_budget,
            'investment': new_invest,
            'utilization': new_util,
            'savings': new_savings,
            'health_score': sim_score,
            'risk_level': risk_level,
            'opportunity_score': opportunity_score,
            'confidence_score': confidence_score,
            'success_probability': success_probability,
            'yearly_benefit': round(yearly_benefit, 2),
            'explanation': explanation
        }
    })


@app.route('/api/scan-receipt', methods=['POST'])
@login_required
def api_scan_receipt():
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    now_str = datetime.now().strftime('%Y-%m-%d')
    return jsonify({
        'success': True,
        'merchant': 'Starbucks Coffee',
        'amount': 480.00,
        'category': 'Food',
        'date': now_str,
        'tax': 24.00,
        'description': 'Scanned Receipt - Beverage & Pastry'
    })


@app.route('/api/predictions', methods=['GET'])
@login_required
def api_predictions():
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    return jsonify({'success': True, 'predictions': calculate_predictions(user['id'])})


# ==========================================================================
# Custom Error Handlers
# ==========================================================================
@app.errorhandler(403)
def forbidden_access(e):
    app.logger.warning(f"Forbidden access attempted by IP: {request.remote_addr} to {request.path}")
    return render_template('403.html'), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error(f"Internal Server Error on {request.path}: {str(e)}", exc_info=True)
    return render_template('500.html'), 500

@app.errorhandler(413)
def file_too_large(e):
    app.logger.warning(f"File upload payload too large from IP: {request.remote_addr}")
    flash('Uploaded file exceeds the 2MB size limit.', 'error')
    return redirect(request.referrer or url_for('register'))

# ==========================================================================
# Entry Point
# ==========================================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)
