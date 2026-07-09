from app import app, get_db
from werkzeug.security import generate_password_hash

with app.app_context():
    db = get_db()
    db.execute("DELETE FROM expenses WHERE user_id IN (SELECT id FROM users WHERE email = ?)", ('dashboard-enhanced@example.com',))
    db.execute("DELETE FROM budgets WHERE user_id IN (SELECT id FROM users WHERE email = ?)", ('dashboard-enhanced@example.com',))
    db.execute("DELETE FROM users WHERE email = ?", ('dashboard-enhanced@example.com',))
    db.commit()
    db.execute(
        "INSERT INTO users (name, email, phone, password_hash, country, is_verified, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))",
        ('Dashboard Enhanced', 'dashboard-enhanced@example.com', '1234567890', generate_password_hash('Password123!'), 'US'),
    )
    user_id = db.execute("SELECT id FROM users WHERE email = ?", ('dashboard-enhanced@example.com',)).fetchone()['id']
    db.execute("INSERT INTO budgets (user_id, month, year, amount, description) VALUES (?, ?, ?, ?, ?)", (user_id, 'July', 2026, 1200.0, 'Demo budget'))
    db.execute("INSERT INTO expenses (user_id, category, amount, description, expense_date) VALUES (?, ?, ?, ?, ?)", (user_id, 'Food', 180.0, 'Groceries', '2026-07-04'))
    db.execute("INSERT INTO expenses (user_id, category, amount, description, expense_date) VALUES (?, ?, ?, ?, ?)", (user_id, 'Transport', 55.0, 'Metro pass', '2026-07-06'))
    db.commit()

client = app.test_client()
with client.session_transaction() as sess:
    sess['user_id'] = user_id
resp = client.get('/dashboard')
body = resp.get_data(as_text=True).lower()
print(resp.status_code)
print('monthly budget' in body)
print('highest expense category' in body)
print('budget status' in body)
