import sys
import os
from datetime import datetime, timedelta

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from database import get_db, init_db
from werkzeug.security import generate_password_hash

def seed_demo_data():
    """
    Seeds a clean, multi-month synthetic demo user and sample financial records into finsight.db.
    Safe for development testing and clean application setup on any environment.
    """
    print("Initializing clean database structure...")
    with app.app_context():
        init_db()
        db = get_db()
        cursor = db.cursor()

        # Check if demo user already exists
        demo_user = db.execute("SELECT * FROM users WHERE email = ?", ("demo@finsight.app",)).fetchone()
        if not demo_user:
            print("Creating synthetic demo user...")
            cursor.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, country, currency, is_verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    "Demo User",
                    "demo@finsight.app",
                    "9876543210",
                    generate_password_hash("DemoPass123!"),
                    "India",
                    "₹",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            user_id = cursor.lastrowid
            print(f"Created demo user with ID: {user_id}")
        else:
            user_id = demo_user['id']
            print(f"Demo user exists (ID: {user_id}). Seeding/updating multi-month records...")

        # Seed User Preference
        cursor.execute(
            """
            INSERT INTO user_preferences (user_id, currency)
            VALUES (?, '₹')
            ON CONFLICT(user_id) DO UPDATE SET currency = '₹'
            """,
            (user_id,)
        )

        now = datetime.now()
        today = now.date()

        # Seed 4 Months of Budgets
        for i in range(4):
            dt = today - timedelta(days=i*30)
            month_name = dt.strftime("%B")
            year_val = dt.year
            cursor.execute(
                """
                INSERT OR IGNORE INTO budgets (user_id, month, year, amount, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, month_name, year_val, 55000.0, f"Base Budget for {month_name} {year_val}")
            )

        # Seed 4 Months of Income Ledger Entries
        income_entries = [
            # Current month
            ("TechCorp Salary", 75000.0, "Monthly", today.strftime("%Y-%m-01"), "Salary", "Primary Employment Income"),
            ("Design Freelance", 12500.0, "One-time", (today - timedelta(days=5)).strftime("%Y-%m-%d"), "Freelance", "UI Design Project"),
            # Prior Month 1
            ("TechCorp Salary", 75000.0, "Monthly", (today - timedelta(days=30)).strftime("%Y-%m-01"), "Salary", "Primary Employment Income"),
            ("Consulting Fee", 10000.0, "One-time", (today - timedelta(days=38)).strftime("%Y-%m-%d"), "Freelance", "Tech Advisory"),
            # Prior Month 2
            ("TechCorp Salary", 75000.0, "Monthly", (today - timedelta(days=60)).strftime("%Y-%m-01"), "Salary", "Primary Employment Income"),
            ("Dividend Payout", 3500.0, "Quarterly", (today - timedelta(days=65)).strftime("%Y-%m-%d"), "Investment Income", "Mutual Fund Dividend"),
            # Prior Month 3
            ("TechCorp Salary", 75000.0, "Monthly", (today - timedelta(days=90)).strftime("%Y-%m-01"), "Salary", "Primary Employment Income"),
        ]

        # Check existing income to avoid duplicate seeding
        existing_income = cursor.execute("SELECT COUNT(*) as cnt FROM income WHERE user_id = ?", (user_id,)).fetchone()
        if existing_income['cnt'] == 0:
            for src, amt, freq, dr, cat, notes in income_entries:
                cursor.execute(
                    """
                    INSERT INTO income (user_id, source, amount, category, income_date, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, src, amt, cat, dr, notes)
                )
            print("Seeded 4 months of income entries.")

        # Seed 4 Months of Categorized Expenses
        expense_samples = [
            # Current Month Expenses
            ("Food", 1250.0, "UPI", "Grocery Shopping", today.strftime("%Y-%m-%d")),
            ("Transport", 450.0, "UPI", "Cab fare to office", (today - timedelta(days=1)).strftime("%Y-%m-%d")),
            ("Bills", 2100.0, "Net Banking", "Monthly Internet & Utilities", (today - timedelta(days=3)).strftime("%Y-%m-%d")),
            ("Shopping", 3400.0, "Credit Card", "Apparel Purchase", (today - timedelta(days=5)).strftime("%Y-%m-%d")),
            ("Healthcare", 1500.0, "UPI", "Pharmacy & Medical Checkup", (today - timedelta(days=8)).strftime("%Y-%m-%d")),
            ("Food", 2800.0, "Credit Card", "Team Dinner", (today - timedelta(days=10)).strftime("%Y-%m-%d")),
            ("Entertainment", 800.0, "UPI", "Movie tickets", (today - timedelta(days=12)).strftime("%Y-%m-%d")),
            
            # Month -1 Expenses
            ("Food", 8900.0, "UPI", "Monthly Groceries & Dining", (today - timedelta(days=32)).strftime("%Y-%m-%d")),
            ("Bills", 4200.0, "Net Banking", "Electricity & Mobile Bills", (today - timedelta(days=35)).strftime("%Y-%m-%d")),
            ("Transport", 2100.0, "UPI", "Fuel & Commute", (today - timedelta(days=40)).strftime("%Y-%m-%d")),
            ("Shopping", 6500.0, "Credit Card", "Electronics Upgrade", (today - timedelta(days=45)).strftime("%Y-%m-%d")),
            ("Education", 3000.0, "Net Banking", "Online Certification Course", (today - timedelta(days=50)).strftime("%Y-%m-%d")),

            # Month -2 Expenses
            ("Food", 9200.0, "UPI", "Groceries & Supermarket", (today - timedelta(days=62)).strftime("%Y-%m-%d")),
            ("Bills", 4100.0, "Net Banking", "Utilities", (today - timedelta(days=65)).strftime("%Y-%m-%d")),
            ("Transport", 2300.0, "UPI", "Metro & Rides", (today - timedelta(days=70)).strftime("%Y-%m-%d")),
            ("Travel", 12000.0, "Credit Card", "Weekend Getaway Flight", (today - timedelta(days=75)).strftime("%Y-%m-%d")),

            # Month -3 Expenses
            ("Food", 8500.0, "UPI", "Groceries", (today - timedelta(days=92)).strftime("%Y-%m-%d")),
            ("Bills", 3900.0, "Net Banking", "Monthly Bills", (today - timedelta(days=95)).strftime("%Y-%m-%d")),
            ("Shopping", 4000.0, "Credit Card", "Household Supplies", (today - timedelta(days=100)).strftime("%Y-%m-%d")),
        ]

        existing_expenses = cursor.execute("SELECT COUNT(*) as cnt FROM expenses WHERE user_id = ?", (user_id,)).fetchone()
        if existing_expenses['cnt'] < 5:
            for cat, amt, pm, desc, dt in expense_samples:
                cursor.execute(
                    """
                    INSERT INTO expenses (user_id, category, amount, payment_method, currency, description, expense_date)
                    VALUES (?, ?, ?, ?, 'INR', ?, ?)
                    """,
                    (user_id, cat, amt, pm, desc, dt)
                )
            print("Seeded multi-month expense history.")

        # Seed Sample Investments
        existing_inv = cursor.execute("SELECT COUNT(*) as cnt FROM investments WHERE user_id = ?", (user_id,)).fetchone()
        if existing_inv['cnt'] == 0:
            investments = [
                ("Nifty 50 Index Fund", "Mutual Fund", 15000.0, 17800.0, 100.0, "2026-01-10", "Zerodha"),
                ("TCS Ltd Shares", "Stocks", 3200.0, 3550.0, 10.0, "2026-02-15", "Groww"),
                ("Fixed Deposit Reserve", "Fixed Deposit", 50000.0, 52500.0, 1.0, "2026-03-01", "HDFC Bank")
            ]
            for name, itype, pprice, cprice, qty, pdate, broker in investments:
                cursor.execute(
                    """
                    INSERT INTO investments (user_id, investment_name, investment_type, purchase_price, current_price, quantity, purchase_date, broker)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, name, itype, pprice, cprice, qty, pdate, broker)
                )
            print("Seeded investment portfolio.")

        # Seed Sample Financial Goals & Goal Contribution Ledger
        existing_goals = cursor.execute("SELECT COUNT(*) as cnt FROM financial_goals WHERE user_id = ?", (user_id,)).fetchone()
        if existing_goals['cnt'] == 0:
            goals = [
                ("Emergency Fund", "Emergency Fund", 150000.0, 60000.0, "2027-12-31", "High", "Active"),
                ("Vacation Fund", "Travel", 50000.0, 25000.0, "2026-11-30", "Medium", "Active")
            ]
            for gname, gtype, target, saved, deadline, priority, status in goals:
                cursor.execute(
                    """
                    INSERT INTO financial_goals (user_id, goal_name, goal_type, target_amount, saved_amount, deadline, priority, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, gname, gtype, target, saved, deadline, priority, status)
                )
                goal_id = cursor.lastrowid
                
                # Seed contribution ledger entries
                cursor.execute(
                    """
                    INSERT INTO goal_contributions (goal_id, user_id, amount, contribution_date, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (goal_id, user_id, saved / 2, (today - timedelta(days=60)).strftime("%Y-%m-%d"), "Initial Savings Contribution")
                )
                cursor.execute(
                    """
                    INSERT INTO goal_contributions (goal_id, user_id, amount, contribution_date, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (goal_id, user_id, saved / 2, (today - timedelta(days=30)).strftime("%Y-%m-%d"), "Monthly Automated Transfer")
                )
            print("Seeded goals and goal contribution ledger.")

        db.commit()
        print("Demo financial data seeded successfully!")
        print("Credentials -> Email: demo@finsight.app | Password: DemoPass123!")

if __name__ == "__main__":
    seed_demo_data()
