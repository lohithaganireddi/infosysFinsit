import json
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db
from services import calculate_portfolio_metrics
from blueprints.utils import login_required, sanitize_input, get_current_user

investments_bp = Blueprint('investments', __name__)

INVESTMENT_TYPES = ['Stocks', 'Bonds', 'Mutual Fund', 'ETF', 'Fixed Deposit', 'Real Estate', 'Crypto']


def _blank_investment():
    return {
        'id': None,
        'investment_name': '',
        'investment_type': '',
        'purchase_price': '',
        'current_price': '',
        'quantity': '',
        'purchase_date': '',
        'broker': '',
        'notes': '',
    }


def _validate_investment(form):
    """Validate and coerce form data. Returns (data_dict, errors_list)."""
    data = {
        'investment_name': sanitize_input(form.get('investment_name', '')),
        'investment_type': sanitize_input(form.get('investment_type', '')),
        'purchase_price': form.get('purchase_price', ''),
        'current_price': form.get('current_price', ''),
        'quantity': form.get('quantity', ''),
        'purchase_date': form.get('purchase_date', ''),
        'broker': sanitize_input(form.get('broker', '')),
        'notes': sanitize_input(form.get('notes', '')),
    }
    errors = []

    if not data['investment_name']:
        errors.append('Investment name is required.')
    if data['investment_type'] not in INVESTMENT_TYPES:
        errors.append('Please select a valid investment type.')

    try:
        data['purchase_price'] = float(data['purchase_price'])
        if data['purchase_price'] <= 0:
            errors.append('Purchase price must be greater than zero.')
    except (ValueError, TypeError):
        errors.append('Enter a valid purchase price.')

    try:
        data['current_price'] = float(data['current_price'])
        if data['current_price'] < 0:
            errors.append('Current price must be zero or greater.')
    except (ValueError, TypeError):
        errors.append('Enter a valid current price.')

    try:
        data['quantity'] = float(data['quantity'])
        if data['quantity'] <= 0:
            errors.append('Quantity must be greater than zero.')
    except (ValueError, TypeError):
        errors.append('Enter a valid quantity.')

    if not data['purchase_date']:
        errors.append('Purchase date is required.')

    return data, errors


# ── LIST / PORTFOLIO DASHBOARD ──────────────────────────────────────────────

@investments_bp.route('/investments/')
@login_required
def investment_list():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    rows = db.execute(
        '''SELECT id, investment_name, investment_type, purchase_price, current_price,
                  quantity, purchase_date, broker, notes
           FROM investments
           WHERE user_id = ?
           ORDER BY purchase_date DESC''',
        (user['id'],)
    ).fetchall()
    investments = [dict(r) for r in rows]

    # KPI summary from service
    portfolio = calculate_portfolio_metrics(user['id'])

    # Asset-type breakdown for chart + table
    type_rows = db.execute(
        '''SELECT investment_type,
                  SUM(purchase_price * quantity) AS invested_value,
                  SUM(current_price  * quantity) AS current_value,
                  COUNT(*) AS count
           FROM investments
           WHERE user_id = ?
           GROUP BY investment_type
           ORDER BY current_value DESC''',
        (user['id'],)
    ).fetchall()
    type_breakdown = [dict(r) for r in type_rows]

    # JSON for Chart.js — percentage of total current value
    total_cv = portfolio['current_value'] or 1
    type_breakdown_json = json.dumps([
        {'label': r['investment_type'],
         'value': round((r['current_value'] / total_cv) * 100, 2)}
        for r in type_breakdown
    ])

    return render_template(
        'investments.html',
        user=user,
        investments=investments,
        portfolio=portfolio,
        type_breakdown=type_breakdown,
        type_breakdown_json=type_breakdown_json,
    )


# ── ADD INVESTMENT ───────────────────────────────────────────────────────────

@investments_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_investment():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    investment = _blank_investment()

    if request.method == 'POST':
        data, errors = _validate_investment(request.form)
        # Keep form values on error
        investment.update(data)

        if errors:
            for e in errors:
                flash(e, 'error')
        else:
            db = get_db()
            try:
                db.execute(
                    '''INSERT INTO investments
                       (user_id, investment_name, investment_type, purchase_price,
                        current_price, quantity, purchase_date, broker, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (user['id'], data['investment_name'], data['investment_type'],
                     data['purchase_price'], data['current_price'], data['quantity'],
                     data['purchase_date'], data['broker'], data['notes'])
                )
                db.commit()
                flash('Investment added successfully.', 'success')
                return redirect(url_for('investments.investment_list'))
            except Exception:
                flash('Failed to save investment. Please try again.', 'error')

    return render_template(
        'investment_form.html',
        user=user,
        investment=investment,
        investment_types=INVESTMENT_TYPES,
        form_action=url_for('investments.add_investment'),
        page_title='Add Investment',
        page_description='Record a new security, mutual fund, or asset in your portfolio.',
    )


# ── EDIT INVESTMENT ──────────────────────────────────────────────────────────

@investments_bp.route('/investments/<int:investment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_investment(investment_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    row = db.execute(
        'SELECT * FROM investments WHERE id = ? AND user_id = ?',
        (investment_id, user['id'])
    ).fetchone()

    if not row:
        flash('Investment not found.', 'error')
        return redirect(url_for('investments.investment_list'))

    investment = dict(row)

    if request.method == 'POST':
        data, errors = _validate_investment(request.form)
        investment.update(data)

        if errors:
            for e in errors:
                flash(e, 'error')
        else:
            try:
                db.execute(
                    '''UPDATE investments
                       SET investment_name=?, investment_type=?, purchase_price=?,
                           current_price=?, quantity=?, purchase_date=?, broker=?, notes=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id = ? AND user_id = ?''',
                    (data['investment_name'], data['investment_type'], data['purchase_price'],
                     data['current_price'], data['quantity'], data['purchase_date'],
                     data['broker'], data['notes'], investment_id, user['id'])
                )
                db.commit()
                flash('Investment updated successfully.', 'success')
                return redirect(url_for('investments.investment_list'))
            except Exception:
                flash('Failed to update investment. Please try again.', 'error')

    return render_template(
        'investment_form.html',
        user=user,
        investment=investment,
        investment_types=INVESTMENT_TYPES,
        form_action=url_for('investments.edit_investment', investment_id=investment_id),
        page_title='Edit Investment',
        page_description='Update the details of this investment position.',
    )


# ── DELETE INVESTMENT ────────────────────────────────────────────────────────

@investments_bp.route('/investments/<int:investment_id>/delete', methods=['POST'])
@login_required
def delete_investment(investment_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM investments WHERE id = ? AND user_id = ?',
        (investment_id, user['id'])
    ).fetchone()

    if not row:
        flash('Investment not found.', 'error')
        return redirect(url_for('investments.investment_list'))

    try:
        db.execute('DELETE FROM investments WHERE id = ? AND user_id = ?',
                   (investment_id, user['id']))
        db.commit()
        flash('Investment deleted.', 'success')
    except Exception:
        flash('Failed to delete investment. Please try again.', 'error')

    return redirect(url_for('investments.investment_list'))
