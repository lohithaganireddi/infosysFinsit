import os
import re
import sqlite3
from flask import g
from dotenv import load_dotenv

# Load environment variables from project root .env if present
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path)

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Unified IntegrityError tuple so callers can catch integrity issues across backends
if PSYCOPG2_AVAILABLE:
    IntegrityError = (sqlite3.IntegrityError, psycopg2.IntegrityError)
else:
    IntegrityError = (sqlite3.IntegrityError,)

# Database path inside instance folder for local SQLite development
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
DB_PATH = os.path.join(DB_DIR, 'finsight.db')


def is_postgres():
    """Returns True if DATABASE_URL is configured for PostgreSQL."""
    url = os.environ.get('DATABASE_URL', '').strip()
    return url.startswith('postgres://') or url.startswith('postgresql://')


def get_database_url():
    """Returns the PostgreSQL connection URL, normalizing postgres:// to postgresql://."""
    url = os.environ.get('DATABASE_URL', '').strip()
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


def translate_sql_for_postgres(sql):
    """
    Translates SQLite-compatible SQL queries into PostgreSQL syntax:
    1. Returns None for SQLite PRAGMA statements (no-op in PostgreSQL).
    2. Converts SQLite strftime("%Y-%m", col) -> TO_CHAR(col, 'YYYY-MM').
    3. Converts INSERT OR IGNORE INTO -> INSERT INTO ... ON CONFLICT DO NOTHING.
    4. Converts LIKE / NOT LIKE to case-insensitive ILIKE / NOT ILIKE in PostgreSQL,
       casting date/timestamp columns to ::text for type compatibility.
    5. Normalizes double-quoted literal values to standard single-quoted SQL literals.
    6. Replaces '?' parameter placeholders with '%s' outside quoted string literals.
    """
    if not sql:
        return sql

    stripped = sql.strip()
    if stripped.upper().startswith('PRAGMA'):
        return None

    # 1. strftime(...) conversions
    def _replace_strftime(match):
        fmt = match.group(1)
        col = match.group(2)
        fmt_map = {
            '%Y-%m': 'YYYY-MM',
            '%Y-%m-%d': 'YYYY-MM-DD',
            '%Y': 'YYYY',
            '%m': 'MM',
            '%d': 'DD',
            '%H:%M:%S': 'HH24:MI:SS'
        }
        pg_fmt = fmt_map.get(fmt, fmt.replace('%Y', 'YYYY').replace('%m', 'MM').replace('%d', 'DD'))
        return f"TO_CHAR({col}, '{pg_fmt}')"

    translated = re.sub(
        r'strftime\s*\(\s*["\']([^"\']+)["\']\s*,\s*([a-zA-Z0-9_\.]+)\s*\)',
        _replace_strftime,
        sql,
        flags=re.IGNORECASE
    )

    # 2. INSERT OR IGNORE INTO -> INSERT INTO ... ON CONFLICT DO NOTHING
    if re.search(r'INSERT\s+OR\s+IGNORE\s+INTO\s+', translated, re.IGNORECASE):
        translated = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO\s+', 'INSERT INTO ', translated, flags=re.IGNORECASE)
        if 'ON CONFLICT' not in translated.upper():
            translated = translated.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

    # 3. Convert LIKE / NOT LIKE to PostgreSQL case-insensitive ILIKE / NOT ILIKE
    # Cast date/timestamp columns to text so ILIKE operates validly without type mismatch
    def _replace_like(match):
        quoted = match.group(1)
        if quoted:
            return quoted
        col = match.group(2)
        op = match.group(3)
        ilike_op = "NOT ILIKE" if "NOT" in op.upper() else "ILIKE"
        if col:
            col_name = col.split('.')[-1].strip().lower()
            if col_name in ('expense_date', 'created_at', 'income_date', 'purchase_date', 'deadline'):
                return f"{col}::text {ilike_op}"
            return f"{col} {ilike_op}"
        return ilike_op

    like_pattern = r"('[^']*'|\"[^\"]*\")|(?:([a-zA-Z0-9_\.]+)\s+)?\b(NOT\s+LIKE|LIKE)\b"
    translated = re.sub(like_pattern, _replace_like, translated, flags=re.IGNORECASE)

    # 4. Normalize double-quoted literal values following = or LIKE/ILIKE to standard single-quoted literals
    translated = re.sub(r'(=|LIKE|ILIKE)\s*"([^"]+)"', r"\1 '\2'", translated, flags=re.IGNORECASE)

    # 5. Escape literal '%' to '%%' for psycopg2 and replace '?' with '%s' outside quotes
    out = []
    in_single = False
    in_double = False
    i = 0
    n = len(translated)
    while i < n:
        c = translated[i]
        if c == "'" and not in_double:
            in_single = not in_single
            out.append(c)
        elif c == '"' and not in_single:
            in_double = not in_double
            out.append(c)
        elif c == '?' and not in_single and not in_double:
            out.append('%s')
        elif c == '%':
            if i + 1 < n and translated[i + 1] == '%':
                out.append('%%')
                i += 1
            else:
                out.append('%%')
        else:
            out.append(c)
        i += 1
    return "".join(out)


class PostgresRow:
    """
    Row wrapper that mimics sqlite3.Row for PostgreSQL queries:
    - Dict-style key access: row['name'], row['NAME'], row['Name']
    - Integer index access: row[0], row[1]
    - Python mapping protocol for dict(row)
    - Membership testing: 'col' in row, 'col' in row.keys()
    """
    __slots__ = ('_cols', '_vals', '_map', '_map_lower')

    def __init__(self, cols, vals):
        self._cols = list(cols)
        self._vals = list(vals)
        self._map = {c: v for c, v in zip(self._cols, self._vals)}
        self._map_lower = {str(c).lower(): v for c, v in zip(self._cols, self._vals)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        if key in self._map:
            return self._map[key]
        lk = str(key).lower()
        if lk in self._map_lower:
            return self._map_lower[lk]
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return self._cols

    def values(self):
        return self._vals

    def items(self):
        return [(c, self._map[c]) for c in self._cols]

    def __iter__(self):
        # Enables dict(row) -> {col: val}
        return iter(self._cols)

    def __len__(self):
        return len(self._cols)

    def __contains__(self, key):
        return key in self._map or str(key).lower() in self._map_lower

    def __repr__(self):
        return f"<PostgresRow {dict(self.items())}>"


class PostgresCursor:
    """
    Wraps psycopg2 cursor with automatic SQL dialect translation,
    sqlite3-compatible lastrowid tracking, and dict/index row access.
    """
    def __init__(self, raw_cursor):
        self.raw_cursor = raw_cursor
        self._lastrowid = None

    def execute(self, sql, params=None):
        translated = translate_sql_for_postgres(sql)
        if translated is None:
            return self

        # Inspect if this is an INSERT statement to capture lastrowid
        is_insert = translated.strip().upper().startswith('INSERT INTO')
        has_returning = 'RETURNING' in translated.upper()

        if is_insert and not has_returning:
            exec_sql = translated.rstrip().rstrip(';') + ' RETURNING id;'
            try:
                self.raw_cursor.execute("SAVEPOINT insert_savepoint")
                if params is not None:
                    self.raw_cursor.execute(exec_sql, params)
                else:
                    self.raw_cursor.execute(exec_sql)
                ret_row = self.raw_cursor.fetchone()
                if ret_row:
                    self._lastrowid = ret_row[0]
                self.raw_cursor.execute("RELEASE SAVEPOINT insert_savepoint")
                return self
            except Exception:
                self.raw_cursor.execute("ROLLBACK TO SAVEPOINT insert_savepoint")
                # Fall back to standard execution if table lacks 'id' column

        if params is not None:
            self.raw_cursor.execute(translated, params)
        else:
            self.raw_cursor.execute(translated)
        return self

    def executemany(self, sql, seq_of_parameters):
        translated = translate_sql_for_postgres(sql)
        if translated is None:
            return self
        self.raw_cursor.executemany(translated, seq_of_parameters)
        return self

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self.raw_cursor.rowcount

    @property
    def description(self):
        return self.raw_cursor.description

    def fetchone(self):
        row = self.raw_cursor.fetchone()
        if row is None:
            return None
        cols = [col[0] for col in self.raw_cursor.description]
        return PostgresRow(cols, row)

    def fetchall(self):
        rows = self.raw_cursor.fetchall()
        if not rows:
            return []
        cols = [col[0] for col in self.raw_cursor.description]
        return [PostgresRow(cols, r) for r in rows]

    def fetchmany(self, size=None):
        rows = self.raw_cursor.fetchmany() if size is None else self.raw_cursor.fetchmany(size)
        if not rows:
            return []
        cols = [col[0] for col in self.raw_cursor.description]
        return [PostgresRow(cols, r) for r in rows]

    def close(self):
        return self.raw_cursor.close()

    def __iter__(self):
        row = self.fetchone()
        while row is not None:
            yield row
            row = self.fetchone()


class PostgresConnection:
    """
    Wraps psycopg2 connection to expose sqlite3-compatible .execute() method
    and context manager semantics.
    """
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn

    def cursor(self):
        return PostgresCursor(self.raw_conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        return self.raw_conn.commit()

    def rollback(self):
        return self.raw_conn.rollback()

    def close(self):
        return self.raw_conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


def get_db():
    """
    Returns an active database connection with dict-like row formatting.
    Caches connection in Flask's 'g' request context.
    - Uses PostgreSQL if DATABASE_URL is configured.
    - Uses local SQLite (instance/finsight.db) by default.
    """
    db = getattr(g, '_database', None)
    if db is None:
        if is_postgres():
            if not PSYCOPG2_AVAILABLE:
                raise RuntimeError("psycopg2 is required when DATABASE_URL is configured.")
            raw_conn = psycopg2.connect(get_database_url())
            db = g._database = PostgresConnection(raw_conn)
        else:
            db = g._database = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys = ON')
            db.execute('PRAGMA journal_mode = WAL')
    return db


def init_db(app=None):
    """
    Initializes the database schema.
    - In PostgreSQL mode: Runs scripts/schema_postgres.sql if 'users' table is absent.
    - In SQLite mode: Creates instance/finsight.db tables, migrations, and reference seeds.
    """
    if is_postgres():
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 is required when DATABASE_URL is configured.")
        conn = psycopg2.connect(get_database_url())
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                );
            """)
            table_exists = cur.fetchone()[0]
            if not table_exists:
                schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'schema_postgres.sql')
                if os.path.exists(schema_path):
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        ddl = f.read()
                    cur.execute(ddl)
                    conn.commit()
            cur.close()
        finally:
            conn.close()
        return

    # SQLite (local development default)
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode = WAL')

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            reset_token_expires DATETIME,
            last_login DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)')

    cursor.execute('PRAGMA table_info(users)')
    user_cols = [row[1] for row in cursor.fetchall()]
    if 'currency' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'INR'")
    if 'reset_token_expires' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token_expires DATETIME")

    # Categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    default_categories = ['Food', 'Transport', 'Bills', 'Shopping', 'Entertainment', 'Education', 'Healthcare', 'Investment', 'Travel', 'Other']
    for cat in default_categories:
        cursor.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))

    # Payment methods table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    default_methods = ['Cash', 'UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Wallet']
    for method in default_methods:
        cursor.execute('INSERT OR IGNORE INTO payment_methods (name) VALUES (?)', (method,))

    # Expenses table
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

    cursor.execute('PRAGMA table_info(expenses)')
    cols = [row[1] for row in cursor.fetchall()]
    if 'payment_method' not in cols:
        cursor.execute("ALTER TABLE expenses ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Cash'")

    # Income table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Salary',
            amount REAL NOT NULL,
            income_date DATE NOT NULL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_income_user_id ON income(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_income_date ON income(income_date)')

    # Budgets table
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

    cursor.execute('PRAGMA table_info(budgets)')
    cols = [row[1] for row in cursor.fetchall()]
    if 'category' not in cols:
        cursor.execute("ALTER TABLE budgets ADD COLUMN category TEXT")

    # Investments table
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
            symbol           TEXT,
            price_source     TEXT    DEFAULT 'manual',
            price_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes            TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_investments_type    ON investments(investment_type)')

    cursor.execute('PRAGMA table_info(investments)')
    inv_cols = [row[1] for row in cursor.fetchall()]
    if 'symbol' not in inv_cols:
        cursor.execute("ALTER TABLE investments ADD COLUMN symbol TEXT")
    if 'price_source' not in inv_cols:
        cursor.execute("ALTER TABLE investments ADD COLUMN price_source TEXT DEFAULT 'manual'")
    if 'price_updated_at' not in inv_cols:
        cursor.execute("ALTER TABLE investments ADD COLUMN price_updated_at DATETIME")

    # Financial goals table
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

    # Goal contributions ledger table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goal_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            contribution_date DATE NOT NULL,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (goal_id) REFERENCES financial_goals(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_goal_contrib_goal_id ON goal_contributions(goal_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_goal_contrib_user_id ON goal_contributions(user_id)')

    # User preferences table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            currency TEXT DEFAULT 'INR',
            notify_budget_alert INTEGER DEFAULT 1,
            notify_high_expense INTEGER DEFAULT 1,
            notify_portfolio_alert INTEGER DEFAULT 1,
            notify_goal_milestone INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Notifications table
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


def close_db(exception=None):
    """
    Closes the database connection at the end of the request context.
    """
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()
