# FinSight – Personal Finance & Investment Intelligence Platform

> **Smart Finance. Smarter Decisions.**

A complete, production-ready authentication module built with Python/Flask, SQLite, and a premium dark glassmorphism UI.

---

## Project Structure

```
loginform/
├── app.py                  # Flask application & all routes
├── database.py             # SQLite schema & connection helpers
├── requirements.txt        # Python dependencies
├── instance/
│   └── finsight.db         # SQLite database (auto-created on first run)
├── static/
│   ├── css/style.css       # Full FinSight design system
│   ├── js/app.js           # Frontend validation, charts, interactions
│   ├── images/
│   │   ├── logo.svg        # Custom FinSight logo
│   │   └── favicon.svg     # Browser favicon
│   └── uploads/            # User profile picture uploads
└── templates/
    ├── base.html           # Reusable HTML skeleton
    ├── login.html          # Premium split-screen login
    ├── register.html       # Multi-field registration form
    ├── email_sent.html     # Verification / reset link display
    ├── verify_email.html   # Email confirmed success screen
    ├── forgot_password.html
    ├── reset_password.html
    ├── dashboard.html      # Protected landing page
    ├── 404.html
    └── 500.html
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

The app starts at **http://127.0.0.1:5000**

> The SQLite database and uploads folder are **automatically created** on first run. No manual setup required.

---

## Authentication Flow

### Registration
1. Visit `http://127.0.0.1:5000/register`
2. Fill in your details and submit
3. You will see the **Email Sent** page with a developer simulation link
4. Click the link to verify your account
5. You are redirected to Login

### Login
1. Visit `http://127.0.0.1:5000/login`
2. Enter your verified credentials
3. On success: loading spinner → success animation → Dashboard redirect

### Forgot Password
1. Visit `http://127.0.0.1:5000/forgot-password`
2. Enter your registered email
3. Click the simulation reset link on the Email Sent page
4. Enter and confirm your new password
5. Redirected to Login with success message

---

## Security Features

| Feature | Implementation |
|---|---|
| Password Hashing | Werkzeug SHA-256 |
| CSRF Protection | Custom token middleware |
| SQL Injection Prevention | Parameterized queries |
| Session Management | Flask secure sessions |
| Input Sanitization | Server-side regex stripping |
| File Upload Validation | Extension & size checks |
| Email Enumeration Protection | Generic auth error messages |
| Route Protection | `@login_required` decorator |

---

## Design System

| Token | Value |
|---|---|
| Primary Background | `#081A2F` |
| Secondary Background | `#12395F` |
| Primary Accent | `#10B981` |
| Success | `#22C55E` |
| Warning | `#F59E0B` |
| Error | `#EF4444` |
| Font | Inter (Google Fonts) |
| Border Radius | 18px cards, 8px inputs |
| Spacing Grid | 8px multiples |

---

## Future Modules

This authentication system is architected for seamless extension into:

- Expense Tracker
- Budget Planner
- Income Tracking
- Savings Goals
- Investment Portfolio
- Reports & Analytics
- Notifications
- User Profile & Settings
- Admin Panel

All future routes should use the `@login_required` decorator from `app.py`.

---

&copy; 2026 FinSight Technologies Inc.
