import calendar
import os
import re
import secrets
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import get_db, init_db, close_db

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

# ==========================================================================
# Teardown: Close DB Connection After Each Request
# ==========================================================================
@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)

# ==========================================================================
# CSRF Protection
# ==========================================================================
@app.before_request
def csrf_protect():
    """Validate CSRF token on every mutating POST request."""
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
            if request.headers.get('Content-Type') == 'application/json':
                return {"success": False, "message": "Security token expired. Please try again."}, 400
            flash('Security token expired. Please try again.', 'error')
            return redirect(request.referrer or url_for('login'))

@app.context_processor
def inject_app_context():
    """Inject shared app state and helpers into every template context."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return {
        'csrf_token': session['csrf_token'],
        'DEFAULT_CURRENCY': DEFAULT_CURRENCY,
        'format_currency': format_currency,
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
    """Fetch the current authenticated user from the DB."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


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


def get_dashboard_metrics(user_id):
    """Build the dashboard metrics from the current user's budgets and expenses."""
    db = get_db()
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')

    budget_row = db.execute(
        'SELECT amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?',
        (user_id, now.strftime('%B'), now.year)
    ).fetchone()

    monthly_budget = float(budget_row['amount']) if budget_row else None

    monthly_expenses = db.execute(
        'SELECT * FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ? ORDER BY expense_date DESC, created_at DESC',
        (user_id, current_month_key)
    ).fetchall()

    total_expenses = sum(float(expense['amount']) for expense in monthly_expenses)
    remaining_budget = monthly_budget - total_expenses if monthly_budget is not None else None
    budget_utilization = round((total_expenses / monthly_budget) * 100, 1) if monthly_budget and monthly_budget > 0 else None

    if monthly_budget is None or monthly_budget <= 0:
        budget_status = 'Warning'
    elif total_expenses <= 0:
        budget_status = 'Safe'
    elif budget_utilization is not None and budget_utilization >= 100:
        budget_status = 'Over Budget'
    elif budget_utilization is not None and budget_utilization >= 70:
        budget_status = 'Warning'
    else:
        budget_status = 'Safe'

    recent_expenses = db.execute(
        'SELECT * FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()

    latest_expense = recent_expenses[0] if recent_expenses else None

    category_totals = {}
    for expense in monthly_expenses:
        category = expense['category']
        category_totals[category] = category_totals.get(category, 0.0) + float(expense['amount'])

    highest_expense_category = None
    highest_expense_category_amount = None
    if category_totals:
        highest_expense_category, highest_expense_category_amount = max(category_totals.items(), key=lambda item: item[1])
        highest_expense_category_amount = round(highest_expense_category_amount, 2)

    category_breakdown = []
    if category_totals:
        total_for_breakdown = sum(category_totals.values())
        for category, amount in sorted(category_totals.items(), key=lambda item: item[1], reverse=True):
            category_breakdown.append({
                'category': category,
                'amount': round(amount, 2),
                'percent': round((amount / total_for_breakdown) * 100, 1) if total_for_breakdown else 0.0
            })

    daily_expenses_labels = []
    daily_expenses_values = []
    if monthly_expenses:
        daily_totals = {}
        for expense in monthly_expenses:
            expense_day = int(expense['expense_date'][-2:]) if expense['expense_date'] else 1
            daily_totals[expense_day] = daily_totals.get(expense_day, 0.0) + float(expense['amount'])
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        daily_expenses_labels = [str(day) for day in range(1, days_in_month + 1)]
        daily_expenses_values = [round(daily_totals.get(day, 0.0), 2) for day in range(1, days_in_month + 1)]

    all_expenses = db.execute(
        'SELECT expense_date, amount FROM expenses WHERE user_id = ? ORDER BY expense_date',
        (user_id,)
    ).fetchall()

    monthly_totals = {}
    for expense in all_expenses:
        if expense['expense_date']:
            month_key = expense['expense_date'][:7]
            monthly_totals[month_key] = monthly_totals.get(month_key, 0.0) + float(expense['amount'])

    monthly_expenses_labels = []
    monthly_expenses_values = []
    for month_key in sorted(monthly_totals.keys())[-6:]:
        year, month = map(int, month_key.split('-'))
        monthly_expenses_labels.append(datetime(year, month, 1).strftime('%b %Y'))
        monthly_expenses_values.append(round(monthly_totals.get(month_key, 0.0), 2))

    return {
        'month_label': now.strftime('%B %Y'),
        'budget_amount': monthly_budget,
        'total_expenses': round(total_expenses, 2),
        'remaining_budget': round(remaining_budget, 2) if remaining_budget is not None else None,
        'transaction_count': len(monthly_expenses),
        'budget_utilization': budget_utilization,
        'budget_status': budget_status,
        'highest_expense_category': highest_expense_category,
        'highest_expense_category_amount': highest_expense_category_amount,
        'latest_expense': latest_expense,
        'recent_expenses': recent_expenses,
        'category_breakdown': category_breakdown,
        'daily_expenses_labels': daily_expenses_labels,
        'daily_expenses_values': daily_expenses_values,
        'monthly_expenses_labels': monthly_expenses_labels,
        'monthly_expenses_values': monthly_expenses_values,
    }


def get_smart_insights(user_id):
    """
    Computes intelligent financial insights dynamically from SQLite data.
    Provides personal greetings, health score, summaries, trend alerts, and advice.
    """
    db = get_db()
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')

    user_row = db.execute('SELECT name FROM users WHERE id = ?', (user_id,)).fetchone()
    first_name = user_row['name'].split()[0] if user_row and user_row['name'] else 'there'
    if now.hour < 12:
        greeting = f"Good morning, {first_name}!"
    elif now.hour < 18:
        greeting = f"Good afternoon, {first_name}!"
    else:
        greeting = f"Good evening, {first_name}!"
    
    # Calculate previous month year-month key
    if now.month == 1:
        prev_month_key = f"{now.year - 1}-12"
    else:
        prev_month_key = f"{now.year}-{now.month - 1:02d}"

    # 1. Fetch current month expenses
    curr_expenses = db.execute(
        'SELECT category, amount, expense_date FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ?',
        (user_id, current_month_key)
    ).fetchall()
    
    curr_total = sum(float(e['amount']) for e in curr_expenses)

    # 2. Fetch previous month expenses
    prev_total_row = db.execute(
        'SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ?',
        (user_id, prev_month_key)
    ).fetchone()
    prev_total = float(prev_total_row['total']) if (prev_total_row and prev_total_row['total'] is not None) else 0.0

    # 3. Fetch current budget
    curr_budget_row = db.execute(
        'SELECT amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?',
        (user_id, now.strftime('%B'), now.year)
    ).fetchone()
    curr_budget = float(curr_budget_row['amount']) if curr_budget_row else None

    # Initializing values
    health_score = 100
    health_label = 'Excellent'
    insights = []
    summary = ""
    trend_analysis = ""
    budget_recommendation = ""
    savings_insights = ""
    habit_detection = ""
    highest_category = None
    highest_category_amount = None

    # Check if we have transactions at all
    all_expenses_count_row = db.execute(
        'SELECT COUNT(*) as count FROM expenses WHERE user_id = ?', (user_id,)
    ).fetchone()
    all_expenses_count = all_expenses_count_row['count'] if all_expenses_count_row else 0

    if all_expenses_count == 0:
        health_score = 60
        summary = "No transactions recorded yet. Add an expense or budget to initialize FinSight intelligence calculations."
        insights.append({
            "type": "info",
            "title": "Welcome to FinSight Intelligence Hub!",
            "message": "Once you enter discretionary items and monthly limits, our AI engine will automatically check transaction rates, compute your Health Score, and output saving recommendations."
        })
        return {
            "greeting": greeting,
            "health_score": health_score,
            "health_label": health_label,
            "insights": insights,
            "summary": summary,
            "trend_analysis": "Insufficient transactions to compute trend lines.",
            "budget_recommendation": "Establish a budget limit to receive smart boundary advice.",
            "savings_insights": "No savings computed for this period.",
            "habit_detection": "No spending pattern detected.",
            "highest_category": highest_category,
            "highest_category_amount": highest_category_amount,
        }

    # --- Financial Health Score Calculation ---
    deductions = 0
    if curr_budget is not None and curr_budget > 0:
        utilization = (curr_total / curr_budget) * 100
        if utilization > 100:
            deductions += min(40, int((utilization - 100) * 0.4) + 15)  # Overspent penalty
        elif utilization >= 85:
            deductions += 10  # Warning zone
        elif utilization >= 70:
            deductions += 5
    else:
        deductions += 15  # Penalty for not establishing a budget limit

    # Check database for past overspent budgets
    overspent_months = db.execute(
        '''SELECT COUNT(*) as count FROM budgets b
           JOIN (SELECT strftime('%Y', expense_date) as yr, strftime('%B', expense_date) as mo, SUM(amount) as total FROM expenses WHERE user_id = ? GROUP BY yr, mo) e
           ON b.month = e.mo AND b.year = CAST(e.yr AS INTEGER)
           WHERE b.user_id = ? AND e.total > b.amount''',
        (user_id, user_id)
    ).fetchone()
    overspent_count = overspent_months['count'] if overspent_months else 0
    deductions += min(15, overspent_count * 5)

    # Large single purchases penalty
    large_purchases = sum(1 for e in curr_expenses if float(e['amount']) > 1000)
    deductions += min(15, large_purchases * 5)

    health_score = max(10, 100 - deductions)
    if health_score >= 85:
        health_label = 'Strong'
    elif health_score >= 65:
        health_label = 'Steady'
    else:
        health_label = 'Needs Attention'

    # --- Spending Trend Analysis ---
    if prev_total > 0:
        diff_pct = ((curr_total - prev_total) / prev_total) * 100
        if diff_pct > 5:
            trend_analysis = f"Your current monthly spending is {diff_pct:.1f}% higher than your previous month total ({format_currency(prev_total)})."
            insights.append({
                "type": "warning",
                "title": "Spending Trend Escalating",
                "message": f"Discretionary items have increased by {format_currency(curr_total - prev_total)} compared to last month."
            })
        elif diff_pct < -5:
            trend_analysis = f"Excellent conservation! Your spending is {abs(diff_pct):.1f}% lower than your previous month total ({format_currency(prev_total)})."
            insights.append({
                "type": "success",
                "title": "Spending Velocity Decreasing",
                "message": f"You preserved {format_currency(prev_total - curr_total)} compared to your historical spending average."
            })
        else:
            trend_analysis = f"Your monthly spending is holding steady, changing by only {diff_pct:.1f}% compared to last month."
    else:
        trend_analysis = "Compare current spending to next month's totals to build consecutive trend analysis charts."

    # --- Highest Spending Category Analysis & Smart Budget Recommendations ---
    cat_totals = {}
    for e in curr_expenses:
        cat_totals[e['category']] = cat_totals.get(e['category'], 0.0) + float(e['amount'])

    if cat_totals:
        highest_cat, highest_amt = max(cat_totals.items(), key=lambda x: x[1])
        highest_category = highest_cat
        highest_category_amount = highest_amt
        pct_of_total = (highest_amt / curr_total) * 100 if curr_total > 0 else 0.0
        habit_detection = f"Discretionary spending is dominated by {highest_cat}, taking up {pct_of_total:.1f}% of your monthly activity."
        
        # Recommendations: Suggest budget 10% higher than spending, rounded up
        rec_val = round(highest_amt * 1.10, -1)
        budget_recommendation = f"We recommend configuring a {highest_cat} limit at {format_currency(rec_val)} based on current item velocity."
        
        insights.append({
            "type": "info",
            "title": f"Discretionary Spend Concentration",
            "message": f"Your spending in {highest_cat} ({format_currency(highest_amt)}) represents a significant portion of this month's activity."
        })
    else:
        habit_detection = "Insufficient transactions to detect spending habits."
        budget_recommendation = "Establish spending transactions to trigger budget envelope calculations."

    # --- Savings Insights ---
    if curr_budget is not None and curr_budget > 0:
        if curr_total < curr_budget:
            savings = curr_budget - curr_total
            savings_pct = (savings / curr_budget) * 100
            savings_insights = f"You saved {savings_pct:.1f}% ({format_currency(savings)}) of your overall monthly budget limit!"
            insights.append({
                "type": "success",
                "title": "Savings Target Achieved",
                "message": f"Remaining safety margin: {format_currency(savings)} kept inside your vault accounts."
            })
        else:
            overspent = curr_total - curr_budget
            savings_insights = f"Exceeded current budget margin by {format_currency(overspent)}."
            insights.append({
                "type": "danger",
                "title": "Spending Cap Exceeded",
                "message": f"Cut back discretionary spending by {format_currency(overspent)} to restore safe financial limits."
            })
    else:
        savings_insights = "Configure a monthly budget to calculate saving rates and safe buffer guidelines."

    # --- Monthly Financial Summary ---
    if curr_total > 0:
        summary = f"Summary: You recorded {len(curr_expenses)} transactions totaling {format_currency(curr_total)} in the current month."
    else:
        summary = "No transactions recorded for the current month yet. Add transaction cards to review spending summary charts."

    return {
        "greeting": greeting,
        "health_score": health_score,
        "health_label": health_label,
        "insights": insights,
        "summary": summary,
        "trend_analysis": trend_analysis,
        "budget_recommendation": budget_recommendation,
        "savings_insights": savings_insights,
        "habit_detection": habit_detection,
        "highest_category": highest_category,
        "highest_category_amount": highest_category_amount,
    }


EXPENSE_CATEGORIES = [
    'Housing',
    'Food',
    'Transport',
    'Utilities',
    'Entertainment',
    'Health',
    'Travel',
    'Education',
    'Shopping',
    'Miscellaneous'
]

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
            if is_json:
                return {"success": False, "message": AUTH_ERROR}, 401
            flash(AUTH_ERROR, 'error')
            return render_template('login.html')

        # Block unverified accounts
        if not user['is_verified']:
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
            flash('An account with this email already exists.', 'error')
            return render_template('register.html')

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

        db.execute(
            '''INSERT INTO users
               (name, email, phone, country, password_hash, profile_image,
                is_verified, verification_token, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)''',
            (name, email, phone, country, password_hash,
             profile_image_filename, verification_token, now, now)
        )
        db.commit()

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
    db.execute(
        'UPDATE users SET is_verified = 1, verification_token = NULL, updated_at = ? WHERE id = ?',
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
    )
    db.commit()

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
            db.execute(
                'UPDATE users SET reset_token = ?, updated_at = ? WHERE id = ?',
                (reset_token, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
            )
            db.commit()
            reset_link = url_for('reset_password', token=reset_token, _external=True)

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
        db.execute(
            'UPDATE users SET password_hash = ?, reset_token = NULL, updated_at = ? WHERE id = ?',
            (password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user['id'])
        )
        db.commit()

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

    # Read and clear the new_login flag for the welcome animation
    new_login = session.pop('new_login', False)
    dashboard_data = get_dashboard_metrics(user['id'])
    smart_insights = get_smart_insights(user['id'])
    return render_template('dashboard.html', user=user, new_login=new_login, dashboard_data=dashboard_data, smart_insights=smart_insights)

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
        'SELECT * FROM budgets WHERE user_id = ? ORDER BY year DESC, month DESC',
        (user['id'],)
    ).fetchall()

    now = datetime.now()
    current_month = now.strftime('%B')
    current_year = now.year
    current_month_key = now.strftime('%Y-%m')

    budget_row = db.execute(
        'SELECT * FROM budgets WHERE user_id = ? AND month = ? AND year = ?',
        (user['id'], current_month, current_year)
    ).fetchone()

    monthly_budget = float(budget_row['amount']) if budget_row else None
    monthly_expenses = db.execute(
        'SELECT amount FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ?',
        (user['id'], current_month_key)
    ).fetchall()

    total_expenses = sum(float(expense['amount']) for expense in monthly_expenses)
    remaining_budget = monthly_budget - total_expenses if monthly_budget is not None else None
    budget_utilization = round((total_expenses / monthly_budget) * 100, 1) if monthly_budget and monthly_budget > 0 else None

    if monthly_budget is None or monthly_budget <= 0:
        budget_status = 'No Budget'
        progress_percent = 0
    elif remaining_budget is not None and remaining_budget < 0:
        budget_status = 'Over Budget'
        progress_percent = min(100, 100)
    elif budget_utilization is not None and budget_utilization >= 70:
        budget_status = 'Near Limit'
        progress_percent = min(100, int(budget_utilization))
    else:
        budget_status = 'Safe'
        progress_percent = min(100, int(budget_utilization or 0))

    budget_summary = {
        'month_label': now.strftime('%B %Y'),
        'monthly_budget': monthly_budget,
        'total_expenses': round(total_expenses, 2),
        'remaining_budget': round(remaining_budget, 2) if remaining_budget is not None else None,
        'budget_utilization': budget_utilization,
        'budget_status': budget_status,
        'progress_percent': progress_percent,
        'is_over_budget': remaining_budget is not None and remaining_budget < 0,
    }

    return render_template('budgets.html', user=user, budgets=budgets, budget_summary=budget_summary)


@app.route('/budgets/new', methods=['GET', 'POST'])
@login_required
def create_budget():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    current_year = datetime.now().year
    budget = {'month': None, 'year': current_year, 'amount': None, 'description': ''}

    if request.method == 'POST':
        month = sanitize_input(request.form.get('month', ''))
        year = request.form.get('year', '')
        amount = request.form.get('amount', '')
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

        budget = {'month': month, 'year': year, 'amount': amount, 'description': description}

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'budget_form.html',
                user=user,
                months=months,
                budget=budget,
                current_year=current_year,
                page_title='Create Budget',
                page_description='Create a monthly budget for tracking',
                form_action=url_for('create_budget'),
                submit_text='Create Budget'
            )

        db = get_db()
        try:
            db.execute(
                'INSERT INTO budgets (user_id, month, year, amount, description) VALUES (?, ?, ?, ?, ?)',
                (user['id'], month, year_int, amount_value, description)
            )
            db.commit()
            flash('Budget created.', 'success')
            return redirect(url_for('budgets'))
        except Exception:
            flash('Could not create budget. Perhaps a budget for that month/year already exists.', 'error')

    return render_template(
        'budget_form.html',
        user=user,
        months=months,
        budget=budget,
        current_year=current_year,
        page_title='Create Budget',
        page_description='Create a monthly budget for tracking',
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

    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    current_year = datetime.now().year
    budget = {'month': budget_row['month'], 'year': budget_row['year'], 'amount': budget_row['amount'], 'description': budget_row['description']}

    if request.method == 'POST':
        month = sanitize_input(request.form.get('month', ''))
        year = request.form.get('year', '')
        amount = request.form.get('amount', '')
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

        budget = {'month': month, 'year': year, 'amount': amount, 'description': description}

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'budget_form.html',
                user=user,
                months=months,
                budget=budget,
                current_year=current_year,
                page_title='Edit Budget',
                page_description='Edit monthly budget',
                form_action=url_for('edit_budget', budget_id=budget_id),
                submit_text='Update Budget'
            )

        db.execute(
            'UPDATE budgets SET month = ?, year = ?, amount = ?, description = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            (month, year_int, amount_value, description, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), budget_id, user['id'])
        )
        db.commit()
        flash('Budget updated.', 'success')
        return redirect(url_for('budgets'))

    return render_template(
        'budget_form.html',
        user=user,
        months=months,
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
    result = db.execute('DELETE FROM budgets WHERE id = ? AND user_id = ?', (budget_id, user['id']))
    db.commit()

    if result.rowcount == 0:
        flash('Budget not found or access denied.', 'error')
    else:
        flash('Budget deleted.', 'success')

    return redirect(url_for('budgets'))

# --- Expense Tracking ---
@app.route('/expenses')
@login_required
def expenses():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    db = get_db()
    query = 'SELECT * FROM expenses WHERE user_id = ?'
    params = [user['id']]
    filters = []

    search = sanitize_input(request.args.get('q', '').strip())
    category = sanitize_input(request.args.get('category', '').strip())
    sort = sanitize_input(request.args.get('sort', 'date_desc').strip())

    if search:
        filters.append('(category LIKE ? OR description LIKE ? OR expense_date LIKE ?)')
        like_search = f'%{search}%'
        params.extend([like_search, like_search, like_search])
    if category:
        filters.append('category = ?')
        params.append(category)

    if filters:
        query += ' AND ' + ' AND '.join(filters)

    sort_clause = {
        'date_asc':    'expense_date ASC, created_at ASC',
        'amount_asc':  'amount ASC, expense_date DESC',
        'amount_desc': 'amount DESC, expense_date DESC',
    }.get(sort, 'expense_date DESC, created_at DESC')
    query += f' ORDER BY {sort_clause}'
    expenses = db.execute(query, tuple(params)).fetchall()

    expense_amounts = [float(expense['amount']) for expense in expenses]
    summary = {
        'total_expenses': round(sum(expense_amounts), 2),
        'total_transactions': len(expenses),
        'highest_expense': round(max(expense_amounts), 2) if expense_amounts else 0.0,
        'average_expense': round(sum(expense_amounts) / len(expense_amounts), 2) if expense_amounts else 0.0,
    }

    return render_template(
        'expenses.html',
        user=user,
        expenses=expenses,
        categories=EXPENSE_CATEGORIES,
        summary=summary,
        sort=sort,
        search=search,
        category=category,
    )

@app.route('/expenses/new', methods=['GET', 'POST'])
@login_required
def create_expense():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for('login'))

    expense = {'category': None, 'amount': None, 'description': '', 'expense_date': ''}
    if request.method == 'POST':
        category = sanitize_input(request.form.get('category', ''))
        amount = request.form.get('amount', '')
        description = sanitize_input(request.form.get('description', ''))
        expense_date = request.form.get('expense_date', '')

        errors = []
        if category not in EXPENSE_CATEGORIES:
            errors.append('Please select a valid expense category.')
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append('Amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Enter a valid numeric amount.')

        if not expense_date:
            errors.append('Expense date is required.')

        expense = {
            'category': category,
            'amount': amount,
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
                page_title='Add Expense',
                page_description='Record a new expense for your monthly budget.',
                form_action=url_for('create_expense'),
                submit_text='Save Expense'
            )

        db = get_db()
        db.execute(
            '''INSERT INTO expenses (user_id, category, amount, description, expense_date)
               VALUES (?, ?, ?, ?, ?)''',
            (user['id'], category, amount_value, description, expense_date)
        )
        db.commit()
        flash('Expense added successfully.', 'success')
        return redirect(url_for('expenses'))

    return render_template(
        'expense_form.html',
        user=user,
        expense=expense,
        categories=EXPENSE_CATEGORIES,
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
        'category': expense['category'],
        'amount': expense['amount'],
        'description': expense['description'],
        'expense_date': expense['expense_date']
    }

    if request.method == 'POST':
        category = sanitize_input(request.form.get('category', ''))
        amount = request.form.get('amount', '')
        description = sanitize_input(request.form.get('description', ''))
        expense_date = request.form.get('expense_date', '')

        errors = []
        if category not in EXPENSE_CATEGORIES:
            errors.append('Please select a valid expense category.')
        try:
            amount_value = float(amount)
            if amount_value <= 0:
                errors.append('Amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Enter a valid numeric amount.')

        if not expense_date:
            errors.append('Expense date is required.')

        expense_data = {
            'category': category,
            'amount': amount,
            'description': description,
            'expense_date': expense_date
        }

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'expense_form.html',
                user=user,
                expense=expense_data,
                categories=EXPENSE_CATEGORIES,
                page_title='Edit Expense',
                page_description='Update the details for this expense.',
                form_action=url_for('edit_expense', expense_id=expense_id),
                submit_text='Update Expense'
            )

        db.execute(
            '''UPDATE expenses
               SET category = ?, amount = ?, description = ?, expense_date = ?, updated_at = ?
               WHERE id = ? AND user_id = ?''',
            (category, amount_value, description, expense_date,
             datetime.now().strftime('%Y-%m-%d %H:%M:%S'), expense_id, user['id'])
        )
        db.commit()
        flash('Expense updated successfully.', 'success')
        return redirect(url_for('expenses'))

    return render_template(
        'expense_form.html',
        user=user,
        expense=expense_data,
        categories=EXPENSE_CATEGORIES,
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
    result = db.execute(
        'DELETE FROM expenses WHERE id = ? AND user_id = ?',
        (expense_id, user['id'])
    )
    db.commit()

    if result.rowcount == 0:
        flash('Expense not found or access denied.', 'error')
    else:
        flash('Expense deleted successfully.', 'success')

    return redirect(url_for('expenses'))

# --- Logout ---
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    """Securely destroy the user session and redirect to login."""
    session.clear()
    flash('You have been securely signed out.', 'success')
    return redirect(url_for('login'))

# ==========================================================================
# Custom Error Handlers
# ==========================================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

@app.errorhandler(413)
def file_too_large(e):
    flash('Uploaded file exceeds the 2MB size limit.', 'error')
    return redirect(request.referrer or url_for('register'))

# ==========================================================================
# Entry Point
# ==========================================================================
if __name__ == '__main__':
    app.run(debug=True, port=5000)
