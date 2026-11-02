-- ==============================================================================
-- FinSight Production Schema for PostgreSQL / Neon
-- Purpose: Clean, initial database structure for production deployment.
-- NOTE: Contains zero demo users or personal financial records.
-- ==============================================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    profile_image TEXT,
    country TEXT NOT NULL,
    currency TEXT DEFAULT 'INR',
    is_verified INTEGER DEFAULT 0,
    verification_token TEXT,
    reset_token TEXT,
    reset_token_expires TIMESTAMP,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 2. Expense Categories Reference Table
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Seed standard categories (idempotent)
INSERT INTO categories (name) VALUES
    ('Food'),
    ('Transport'),
    ('Bills'),
    ('Shopping'),
    ('Entertainment'),
    ('Education'),
    ('Healthcare'),
    ('Investment'),
    ('Travel'),
    ('Other')
ON CONFLICT (name) DO NOTHING;

-- 3. Payment Methods Reference Table
CREATE TABLE IF NOT EXISTS payment_methods (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Seed standard payment methods (idempotent)
INSERT INTO payment_methods (name) VALUES
    ('Cash'),
    ('UPI'),
    ('Credit Card'),
    ('Debit Card'),
    ('Net Banking'),
    ('Wallet')
ON CONFLICT (name) DO NOTHING;

-- 4. Expenses Table
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'Cash',
    currency TEXT NOT NULL DEFAULT 'INR',
    description TEXT,
    expense_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_expenses_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_expenses_category FOREIGN KEY (category) REFERENCES categories(name) ON DELETE RESTRICT,
    CONSTRAINT fk_expenses_method FOREIGN KEY (payment_method) REFERENCES payment_methods(name) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
CREATE INDEX IF NOT EXISTS idx_expenses_expense_date ON expenses(expense_date);

-- 5. Income Table
CREATE TABLE IF NOT EXISTS income (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Salary',
    amount DOUBLE PRECISION NOT NULL,
    income_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_income_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_income_user_id ON income(user_id);
CREATE INDEX IF NOT EXISTS idx_income_date ON income(income_date);

-- 6. Budgets Table
CREATE TABLE IF NOT EXISTS budgets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    year INTEGER NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    category TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_budgets_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_budgets_category FOREIGN KEY (category) REFERENCES categories(name) ON DELETE CASCADE,
    CONSTRAINT uq_user_month_year_category UNIQUE (user_id, month, year, category)
);
CREATE INDEX IF NOT EXISTS idx_budgets_user_id ON budgets(user_id);

-- 7. Investments Table
CREATE TABLE IF NOT EXISTS investments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    investment_name TEXT NOT NULL,
    investment_type TEXT NOT NULL,
    purchase_price DOUBLE PRECISION NOT NULL,
    current_price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    purchase_date DATE NOT NULL,
    broker TEXT,
    symbol TEXT,
    price_source TEXT DEFAULT 'manual',
    price_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_investments_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id);
CREATE INDEX IF NOT EXISTS idx_investments_type ON investments(investment_type);

-- 8. Financial Goals Table
CREATE TABLE IF NOT EXISTS financial_goals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    goal_name TEXT NOT NULL,
    goal_type TEXT NOT NULL,
    target_amount DOUBLE PRECISION NOT NULL,
    saved_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
    deadline DATE NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Medium',
    status TEXT NOT NULL DEFAULT 'Active',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_goals_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_goals_user_id ON financial_goals(user_id);

-- 9. Goal Contributions Ledger Table
CREATE TABLE IF NOT EXISTS goal_contributions (
    id SERIAL PRIMARY KEY,
    goal_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    contribution_date DATE NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_contrib_goal FOREIGN KEY (goal_id) REFERENCES financial_goals(id) ON DELETE CASCADE,
    CONSTRAINT fk_contrib_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_goal_contrib_goal_id ON goal_contributions(goal_id);
CREATE INDEX IF NOT EXISTS idx_goal_contrib_user_id ON goal_contributions(user_id);

-- 10. User Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    currency TEXT DEFAULT 'INR',
    notify_budget_alert INTEGER DEFAULT 1,
    notify_high_expense INTEGER DEFAULT 1,
    notify_portfolio_alert INTEGER DEFAULT 1,
    notify_goal_milestone INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_preferences_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 11. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
