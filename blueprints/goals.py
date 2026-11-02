from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db
from services import calculate_goals_summary
from blueprints.utils import login_required, sanitize_input, get_current_user

goals_bp = Blueprint('goals', __name__)

GOAL_TYPES = ['Emergency Fund', 'Vacation', 'Education', 'Home Purchase',
              'Retirement', 'Debt Payoff', 'Other']
PRIORITIES = ['Low', 'Medium', 'High']
STATUSES   = ['Active', 'Completed', 'Paused']


def _blank_goal():
    return {
        'id': None,
        'goal_name': '',
        'goal_type': '',
        'target_amount': '',
        'saved_amount': '0',
        'deadline': '',
        'priority': 'Medium',
        'status': 'Active',
        'notes': '',
    }


def _validate_goal(form):
    """Validate and coerce form data. Returns (data_dict, errors_list)."""
    data = {
        'goal_name':     sanitize_input(form.get('goal_name', '')),
        'goal_type':     sanitize_input(form.get('goal_type', '')),
        'target_amount': form.get('target_amount', ''),
        'saved_amount':  form.get('saved_amount', '0'),
        'deadline':      form.get('deadline', ''),
        'priority':      sanitize_input(form.get('priority', 'Medium')),
        'status':        sanitize_input(form.get('status', 'Active')),
        'notes':         sanitize_input(form.get('notes', '')),
    }
    errors = []

    if not data['goal_name']:
        errors.append('Goal name is required.')
    if data['goal_type'] not in GOAL_TYPES:
        errors.append('Please select a valid goal type.')

    try:
        data['target_amount'] = float(data['target_amount'])
        if data['target_amount'] <= 0:
            errors.append('Target amount must be greater than zero.')
    except (ValueError, TypeError):
        errors.append('Enter a valid target amount.')

    try:
        data['saved_amount'] = float(data['saved_amount'] or 0)
        if data['saved_amount'] < 0:
            errors.append('Saved amount cannot be negative.')
    except (ValueError, TypeError):
        errors.append('Enter a valid saved amount.')

    if data['priority'] not in PRIORITIES:
        data['priority'] = 'Medium'
    if data['status'] not in STATUSES:
        data['status'] = 'Active'
    if not data['deadline']:
        errors.append('Deadline is required.')

    return data, errors


# ── LIST / GOALS DASHBOARD ───────────────────────────────────────────────────

@goals_bp.route('/goals')
@goals_bp.route('/goals/')
@login_required
def goal_list():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    rows = db.execute(
        '''SELECT id, goal_name, goal_type, target_amount, saved_amount,
                  deadline, priority, status, notes
           FROM financial_goals
           WHERE user_id = ?
           ORDER BY
             CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
             deadline ASC''',
        (user['id'],)
    ).fetchall()
    goals = [dict(r) for r in rows]

    summary = calculate_goals_summary(user['id'])

    return render_template(
        'goals.html',
        user=user,
        goals=goals,
        summary=summary,
    )


# ── ADD GOAL ─────────────────────────────────────────────────────────────────

@goals_bp.route('/goals/new', methods=['GET', 'POST'])
@login_required
def add_goal():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    goal = _blank_goal()

    if request.method == 'POST':
        data, errors = _validate_goal(request.form)
        goal.update(data)

        if errors:
            for e in errors:
                flash(e, 'error')
        else:
            db = get_db()
            try:
                db.execute(
                    '''INSERT INTO financial_goals
                       (user_id, goal_name, goal_type, target_amount,
                        saved_amount, deadline, priority, status, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (user['id'], data['goal_name'], data['goal_type'],
                     data['target_amount'], data['saved_amount'], data['deadline'],
                     data['priority'], data['status'], data['notes'])
                )
                db.commit()
                flash('Goal created successfully.', 'success')
                return redirect(url_for('goals.goal_list'))
            except Exception:
                flash('Failed to save goal. Please try again.', 'error')

    return render_template(
        'goal_form.html',
        user=user,
        goal=goal,
        goal_types=GOAL_TYPES,
        priorities=PRIORITIES,
        form_action=url_for('goals.add_goal'),
        page_title='Create Goal',
        page_description='Set a new savings target, timeline, and priority.',
    )


# ── EDIT GOAL ─────────────────────────────────────────────────────────────────

@goals_bp.route('/goals/<int:goal_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_goal(goal_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    row = db.execute(
        'SELECT * FROM financial_goals WHERE id = ? AND user_id = ?',
        (goal_id, user['id'])
    ).fetchone()

    if not row:
        flash('Goal not found.', 'error')
        return redirect(url_for('goals.goal_list'))

    goal = dict(row)

    if request.method == 'POST':
        data, errors = _validate_goal(request.form)
        goal.update(data)

        if errors:
            for e in errors:
                flash(e, 'error')
        else:
            try:
                db.execute(
                    '''UPDATE financial_goals
                       SET goal_name=?, goal_type=?, target_amount=?, saved_amount=?,
                           deadline=?, priority=?, status=?, notes=?
                       WHERE id = ? AND user_id = ?''',
                    (data['goal_name'], data['goal_type'], data['target_amount'],
                     data['saved_amount'], data['deadline'], data['priority'],
                     data['status'], data['notes'], goal_id, user['id'])
                )
                db.commit()
                flash('Goal updated successfully.', 'success')
                return redirect(url_for('goals.goal_list'))
            except Exception:
                flash('Failed to update goal. Please try again.', 'error')

    return render_template(
        'goal_form.html',
        user=user,
        goal=goal,
        goal_types=GOAL_TYPES,
        priorities=PRIORITIES,
        form_action=url_for('goals.edit_goal', goal_id=goal_id),
        page_title='Edit Goal',
        page_description='Update this savings goal\'s details and progress.',
    )


# ── DELETE GOAL ───────────────────────────────────────────────────────────────

@goals_bp.route('/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM financial_goals WHERE id = ? AND user_id = ?',
        (goal_id, user['id'])
    ).fetchone()

    if not row:
        flash('Goal not found.', 'error')
        return redirect(url_for('goals.goal_list'))

    try:
        db.execute('DELETE FROM financial_goals WHERE id = ? AND user_id = ?',
                   (goal_id, user['id']))
        db.commit()
        flash('Goal deleted.', 'success')
    except Exception:
        flash('Failed to delete goal. Please try again.', 'error')

    return redirect(url_for('goals.goal_list'))


# ── ADD GOAL CONTRIBUTION ───────────────────────────────────────────────────

@goals_bp.route('/goals/<int:goal_id>/contribute', methods=['POST'])
@login_required
def add_contribution(goal_id):
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))

    amount_str = request.form.get('amount', '')
    contribution_date = request.form.get('contribution_date', datetime.now().strftime('%Y-%m-%d'))
    note = sanitize_input(request.form.get('note', ''))

    try:
        amount = float(amount_str)
        if amount <= 0:
            flash('Contribution amount must be greater than zero.', 'error')
            return redirect(url_for('goals.goal_list'))
    except (ValueError, TypeError):
        flash('Enter a valid contribution amount.', 'error')
        return redirect(url_for('goals.goal_list'))

    from services import add_goal_contribution
    success = add_goal_contribution(user['id'], goal_id, amount, contribution_date, note)
    if success:
        flash('Goal contribution recorded successfully.', 'success')
    else:
        flash('Goal not found or access denied.', 'error')

    return redirect(url_for('goals.goal_list'))

