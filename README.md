# 💰 FinSight — Personal Finance & Investment Intelligence Platform

> **Smart Finance. Smarter Decisions.**

FinSight is a Flask-based personal finance and investment intelligence platform that helps users track income, manage expenses and budgets, monitor financial goals and investments, analyze cash flow & financial health, generate reports, and receive personalized AI-assisted financial insights.

---

## 📌 Table of Contents

* [Overview](#-overview)
* [Key Features](#-key-features)
* [Smart Financial Advisor (Gemini AI Integration)](#-smart-financial-advisor-gemini-ai-integration)
* [Explainable Financial Health Score](#-explainable-financial-health-score)
* [Technology Stack](#-technology-stack)
* [System Architecture](#-system-architecture)
* [Project Structure](#-project-structure)
* [Database Schema](#-database-schema)
* [Authentication & Security](#-authentication--security)
* [Installation & Environment Setup](#-installation--environment-setup)
* [Running the Application](#-running-the-application)
* [Verification & Testing](#-verification--testing)
* [Interview & Engineering Highlights](#-interview--engineering-highlights)
* [Author](#-author)
* [License](#-license)

---

# 🌟 Overview

Managing personal finances manually can make it difficult to understand spending patterns, control budgets, track cash flow, monitor investments, and evaluate long-term financial progress.

**FinSight** solves this by providing a unified, data-grounded financial management platform where users can:

* Log and track verified income streams (`Salary`, `Freelance`, `Investment Income`, etc.)
* Log and categorize daily expenses in INR (₹) or custom currencies
* Calculate true **Net Cash Flow** (`Total Income - Total Expenses`) and **Savings Rate**
* Set and monitor monthly category-level budgets
* Track investment portfolios and asset diversification
* Log contribution ledgers towards dynamic financial goals with deadline-driven targets
* Monitor an explainable 6-dimension Financial Health Score (0–100)
* Receive live AI-driven financial explanations powered by **Google Gemini AI**
* Export professional financial statements as PDF and multi-sheet Excel workbooks

---

# 🚀 Key Features

## 🔐 User Authentication & Session Security
* User registration and login with scrypt password hashing
* Protected routes with session-based authentication & CSRF validation
* Per-user data isolation enforcing strict database ownership queries (IDOR protection)

## 💵 Income Ledger & Net Cash Flow Tracking
* Record recurring and one-time income streams with category and source metadata
* Real-time calculation of Monthly Income, Net Cash Flow, and Savings Rate
* Fully integrated with executive dashboard and AI financial context

## 💸 Expense Management
* Log expenses with categories (`Food`, `Transport`, `Bills`, `Shopping`, `Entertainment`, `Education`, `Healthcare`, `Investment`, `Travel`, `Other`)
* Search, filter, and paginated sorting of expense records
* Export expenses to Excel-compatible CSV format

## 💰 Budget Management & Utilization
* Set total monthly budget and category-level spending ceilings
* Real-time budget utilization calculation (`(spent / budget) * 100`)
* Threshold alerts at 80% (Warning) and 100% (Over Budget)

## 📈 Investment Portfolio Monitoring
* Record equity stocks, mutual funds, ETFs, fixed deposits, and assets
* Track invested capital, current valuation, and unrealized profit/loss
* Asset diversification scoring based on allocation concentration

## 🎯 Dynamic Goal Tracker & Contribution Ledger
* Target savings milestone tracking with dynamic deadline calculations
* Detailed contribution ledger tracking every savings deposit
* Real-time status indicators (`Active Tracking`, `Goal Achieved 🎉`, `Deadline Passed`)

## 📊 Reports & Statement Generator
* Executive summary metrics synchronized with live SQLite queries
* Downloadable **PDF Statements** via ReportLab
* Downloadable **Multi-Sheet Excel Ledgers** via OpenPyXL

---

# 🤖 Smart Financial Advisor (Gemini AI Integration)

FinSight features a dedicated **AI Financial Advisor Service** (`ai_service.py`) powered by Google's **Gemini AI API** (with `gemini-2.5-flash` fallback).

### System Design & Workflow:
```text
User Question
    │
    ▼
Flask Backend (/api/copilot)
    │
    ▼
Fetch Real FinSight SQLite Data
    │
    ▼
build_financial_context(user_id)  ──>  [Structured Financial JSON Context]
    │
    ▼
call_gemini(prompt, system_instruction)  ──>  [Gemini API]
    │
    ▼
Response Validation & Fallback Engine
    │
    ▼
Render Data-Supported AI Explanation in UI
```

### Context Security & Guardrails:
- The AI context includes ONLY computed, aggregated financial figures (monthly income, spending, budget, health score, portfolio value, goal progress).
- System instructions enforce strict factual boundaries: *"Use ONLY the financial data provided. Never invent transactions, returns, balances, or dates. Provide educational guidance, not guaranteed advice."*
- **Offline Rule Engine Fallback**: If `GEMINI_API_KEY` is not set or network timeouts occur, FinSight gracefully falls back to an offline rule-based financial explanation engine, guaranteeing 100% application stability.

---

# ❤️ Explainable Financial Health Score

FinSight features a transparent, 6-dimension mathematical scoring engine rated from 0 to 100:

| Dimension | Weight | Methodology |
| :--- | :--- | :--- |
| **Budget Discipline** | **25%** | Evaluated against monthly budget utilization percentage. |
| **Cash Flow & Savings Rate** | **25%** | Evaluated against net cash flow and monthly savings rate percentage. |
| **Emergency Fund Coverage** | **20%** | Evaluated by Emergency Fund goal coverage relative to monthly expenses. |
| **Expense Stability** | **15%** | Evaluated by multi-month spending variance and ticket size stability. |
| **Goal Progress** | **10%** | Ratio of completed financial milestones to active goals. |
| **Asset-Class Concentration** | **5%** | Concentration scoring across investment asset classes. |

---

# 🛠️ Technology Stack

* **Backend**: Python 3.10+, Flask 3.0.3, Werkzeug, Jinja2
* **Database**: SQLite 3 with dictionary row formatting and Foreign Keys enabled
* **AI Engine**: Google Gemini API via `requests` & `ai_service.py`
* **Frontend**: HTML5, CSS3 (Glassmorphism Dark Navy theme), Vanilla JavaScript, Chart.js
* **Reporting**: ReportLab (PDF generation), OpenPyXL (Excel generation)
* **Configuration**: `python-dotenv` for secure environment variable loading

---

# 📁 Project Structure

```text
infosysFinsite/
├── app.py                     # Main Flask Application & Endpoints
├── database.py                # Database Initialization & SQLite Context
├── services.py                # Financial Calculation & Report Services
├── ai_service.py              # Gemini AI Integration & Context Service
├── blueprints/                # Modular Route Blueprints (investments, goals)
├── scripts/
│   └── seed_demo.py           # Multi-Month Synthetic Data Seed Script
├── scratch/
│   └── test_full_system.py    # Full System Automated Test Suite
├── requirements.txt           # Python Package Dependencies
├── instance/                  # Local SQLite Database Folder
├── static/
│   ├── css/style.css          # Glassmorphism Dark Theme Stylesheet
│   └── js/app.js              # Client Interactivity & Chart.js Controllers
└── templates/                 # Jinja2 HTML Templates
    ├── landing.html           # Public Portfolio Landing Page
    ├── dashboard.html         # Main Executive Financial Dashboard
    ├── ai_advisor.html        # Smart AI Financial Advisor Workspace
    ├── income.html            # Income Ledger Workspace
    ├── expenses.html          # Expense Tracker Workspace
    ├── budgets.html           # Budget Management Workspace
    ├── investments.html       # Portfolio Monitoring Workspace
    ├── goals.html             # Financial Goals & Ledger Workspace
    ├── reports.html           # Executive Statements Workspace
    ├── analytics.html         # Deep Financial Analytics Workspace
    ├── notifications.html     # Financial Notification Center
    ├── profile.html           # User Profile & Health Index Summary
    └── settings.html          # App Preferences & Currency Selector
```

---

# 🗄️ Database Schema

SQLite schema enforces referential integrity via `PRAGMA foreign_keys = ON`:

- `users` (id, name, email, phone, password_hash, profile_image, country, currency, is_verified, created_at)
- `income` (id, user_id, source, category, amount, income_date, notes, created_at)
- `expenses` (id, user_id, category, amount, payment_method, currency, description, expense_date)
- `budgets` (id, user_id, month, year, amount, category, description)
- `investments` (id, user_id, investment_name, investment_type, purchase_price, current_price, quantity, purchase_date, broker, symbol, price_source)
- `financial_goals` (id, user_id, goal_name, goal_type, target_amount, saved_amount, deadline, priority, status)
- `goal_contributions` (id, goal_id, user_id, amount, contribution_date, note)
- `user_preferences` (user_id, currency, notify_budget_alert, notify_high_expense, notify_portfolio_alert, notify_goal_milestone)
- `notifications` (id, user_id, type, title, message, is_read, created_at)

---

# ⚙️ Installation & Environment Setup

### 1. Clone Repository
```bash
git clone https://github.com/lohithaganireddi/infosysFinsit.git
cd infosysFinsit
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

# ▶️ Running the Application

### Seed Demo Account (Optional)
```bash
python scripts/seed_demo.py
```
*Demo Credentials*: `demo@finsight.app` | Password: `DemoPass123!`

### Start Flask Server
```bash
python app.py
```
Open your browser and navigate to:
```text
http://127.0.0.1:5000/
```

---

# 🧪 Verification & Testing

Run the full automated system test suite:
```bash
python scratch/test_full_system.py
```

---

# 💡 Interview & Engineering Highlights

When presenting FinSight in technical discussions or interviews:

1. **Deterministic Calculation vs. LLM Explanation**:
   *"Financial calculations (income, cash flow, remaining budget, health score, goal targets) are executed deterministically in Python/SQL. Gemini is used specifically as an explanation engine over verified financial context data, preventing hallucinated financial figures."*

2. **6-Dimension Financial Health Model**:
   *"The Health Score combines budget discipline (25%), cash flow & savings rate (25%), emergency fund coverage (20%), expense stability (15%), goal progress (10%), and asset diversification (5%) into an explainable 0–100 index."*

3. **API Security & Resiliency**:
   *"API keys are strictly managed via environment variables. If the Gemini API is unreachable, `ai_service.py` safely switches to an offline rule-based explanation engine, ensuring zero downtime."*

---

# 👩‍💻 Author

## Lohitha Sai Priya Devi Ganireddi
**B.Tech — Computer Science & Engineering (Artificial Intelligence & Machine Learning)**

---

# 📄 License

Developed for educational, portfolio, and internship project purposes.
