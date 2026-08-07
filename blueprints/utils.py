import re
from functools import wraps
from flask import redirect, url_for, flash, session
from database import get_db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def sanitize_input(text):
    if not text:
        return ''
    return re.sub(r'[<>"\']', '', str(text).strip())

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
