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

    # Create expenses table for user-specific expense tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            description TEXT,
            expense_date DATE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date)')

    # Create budgets table for monthly user budgets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (user_id, month, year)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_budgets_user_id ON budgets(user_id)')

    conn.commit()
    conn.close()

def close_db(exception):
    """
    Closes the database connection at the end of the request context.
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
