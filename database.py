import sqlite3
import os
from flask import g

# Database path inside instance folder
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
DB_PATH = os.path.join(DB_DIR, 'finsight.db')

def get_db():
    """
    Returns a database connection with dict-like row formatting.
    Stores the connection in flask's 'g' request context.
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        # Enable dictionary-like row behavior
        db.row_factory = sqlite3.Row
        # Enforce foreign key constraints for referential integrity
        db.execute('PRAGMA foreign_keys = ON')
    return db

def init_db(app=None):
    """
    Initializes the database. Creates directories and tables if they do not exist.
    """
    # Ensure instance directory exists
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

    # Establish initial database structure
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            profile_image TEXT,
            country TEXT NOT NULL,
            is_verified INTEGER DEFAULT 0,
            verification_token TEXT,
            reset_token TEXT,
            last_login DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create email index for rapid searches
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)')

    # Create categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # Populate categories
    default_categories = ['Food', 'Transport', 'Bills', 'Shopping', 'Entertainment', 'Education', 'Healthcare', 'Investment', 'Travel', 'Other']
    for cat in default_categories:
        cursor.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))

    # Create payment_methods table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # Populate payment methods
    default_methods = ['Cash', 'UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Wallet']
    for method in default_methods:
        cursor.execute('INSERT OR IGNORE INTO payment_methods (name) VALUES (?)', (method,))

    # Create expenses table for user-specific expense tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'Cash',
            currency TEXT NOT NULL DEFAULT 'INR',
            description TEXT,
            expense_date DATE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (category) REFERENCES categories(name) ON DELETE RESTRICT,
            FOREIGN KEY (payment_method) REFERENCES payment_methods(name) ON DELETE RESTRICT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date)')

    # Run migrations for existing expenses table if needed
    cursor.execute('PRAGMA table_info(expenses)')
    cols = [row[1] for row in cursor.fetchall()]
    if 'payment_method' not in cols:
        cursor.execute("ALTER TABLE expenses ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Cash'")

    # Create budgets table for monthly user budgets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (category) REFERENCES categories(name) ON DELETE CASCADE,
            UNIQUE (user_id, month, year, category)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_budgets_user_id ON budgets(user_id)')

    # Run migrations for existing budgets table if needed
    cursor.execute('PRAGMA table_info(budgets)')
    cols = [row[1] for row in cursor.fetchall()]
    if 'category' not in cols:
        cursor.execute("ALTER TABLE budgets ADD COLUMN category TEXT")

    # ── Milestone 2: investments table ──────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS investments (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            investment_name  TEXT    NOT NULL,
            investment_type  TEXT    NOT NULL,
            purchase_price   REAL    NOT NULL,
            current_price    REAL    NOT NULL,
            quantity         REAL    NOT NULL,
            purchase_date    DATE    NOT NULL,
            broker           TEXT,
            notes            TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_investments_type    ON investments(investment_type)')

    # ── Milestone 2: financial_goals table ───────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financial_goals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            goal_name     TEXT    NOT NULL,
            goal_type     TEXT    NOT NULL,
            target_amount REAL    NOT NULL,
            saved_amount  REAL    NOT NULL DEFAULT 0,
            deadline      DATE    NOT NULL,
            priority      TEXT    NOT NULL DEFAULT 'Medium',
            status        TEXT    NOT NULL DEFAULT 'Active',
            notes         TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_goals_user_id ON financial_goals(user_id)')

    # ── Milestone 3: notifications table ─────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            type       TEXT    NOT NULL,
            title      TEXT    NOT NULL,
            message    TEXT    NOT NULL,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_is_read  ON notifications(is_read)')

    conn.commit()
    conn.close()

def close_db(exception):
    """
    Closes the database connection at the end of the request context.
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
