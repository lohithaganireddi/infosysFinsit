import calendar
from datetime import datetime, timedelta

from database import get_db


def _format_month_label(month_key):
    try:
        dt = datetime.strptime(month_key, '%Y-%m')
        return dt.strftime('%B %Y')
    except (ValueError, TypeError):
        return month_key


# ── Income Management Services ──────────────────────────────────────────────

def add_income(user_id, source, amount, income_date, category='Salary', notes=None):
    """Inserts a new verified income record for the user."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        '''INSERT INTO income (user_id, source, category, amount, income_date, notes)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (user_id, source, category, float(amount), income_date, notes)
    )
    db.commit()
    return cursor.lastrowid


def get_user_income(user_id, month_key=None, search=None):
    """Fetches income records scoped strictly to the logged-in user."""
    db = get_db()
    query = 'SELECT * FROM income WHERE user_id = ?'
    params = [user_id]
    if month_key:
        query += ' AND strftime("%Y-%m", income_date) = ?'
        params.append(month_key)
    if search:
        query += ' AND (source LIKE ? OR notes LIKE ? OR category LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    query += ' ORDER BY income_date DESC, created_at DESC'
    rows = db.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def delete_income(user_id, income_id):
    """Deletes an income record ensuring user ownership."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM income WHERE id = ? AND user_id = ?', (income_id, user_id))
    db.commit()
    return cursor.rowcount > 0


def calculate_total_income(user_id, month_key=None):
    """Calculates total income for a user in a specific month (%Y-%m). Defaults to current month."""
    if not month_key:
        month_key = datetime.now().strftime('%Y-%m')
    db = get_db()
    row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count '
        'FROM income WHERE user_id = ? AND strftime("%Y-%m", income_date) = ?',
        (user_id, month_key)
    ).fetchone()
    total = round(row['total'] or 0.0, 2)
    return total, row['count'] or 0


def calculate_cash_flow_metrics(user_id, month_key=None):
    """Computes Net Cash Flow and Savings Rate for a given month. Defaults to current month."""
    if not month_key:
        month_key = datetime.now().strftime('%Y-%m')
    income, inc_count = calculate_total_income(user_id, month_key)
    expenses, exp_count = calculate_total_expenses(user_id, month_key)
    net_cash_flow = round(income - expenses, 2)
    savings_rate = round((net_cash_flow / income * 100), 1) if income > 0 else 0.0
    return {
        'total_income': income,
        'total_expenses': expenses,
        'net_cash_flow': net_cash_flow,
        'savings_rate': savings_rate,
        'income_count': inc_count,
        'expense_count': exp_count,
    }



# ── Expense Services ─────────────────────────────────────────────────────────

def calculate_total_expenses(user_id, month_key):
    db = get_db()
    row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count '
        'FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ?',
        (user_id, month_key)
    ).fetchone()
    total = round(row['total'] or 0.0, 2)
    return total, row['count'] or 0


def calculate_remaining_budget(monthly_budget, total_expenses):
    if monthly_budget is None:
        return None
    return round(monthly_budget - (total_expenses or 0.0), 2)


def calculate_budget_utilization(total_expenses, monthly_budget):
    if monthly_budget is None or monthly_budget == 0:
        return None
    return round((total_expenses or 0.0) / monthly_budget * 100, 1)


def calculate_budget_status(monthly_budget, budget_utilization):
    if monthly_budget is None or budget_utilization is None:
        return 'No Budget'
    if budget_utilization >= 100:
        return 'Over Budget'
    if budget_utilization >= 80:
        return 'At Risk'
    return 'Safe'


def calculate_category_summary(user_id):
    db = get_db()
    rows = db.execute(
        'SELECT category, COALESCE(SUM(amount), 0) AS amount, COUNT(*) AS count '
        'FROM expenses WHERE user_id = ? GROUP BY category ORDER BY amount DESC',
        (user_id,)
    ).fetchall()
    return [
        {
            'category': row['category'],
            'amount': round(row['amount'] or 0.0, 2),
            'count': row['count'],
        }
        for row in rows
    ]


def get_monthly_budget_row(user_id, month, year):
    db = get_db()
    row = db.execute(
        'SELECT * FROM budgets WHERE user_id = ? AND month = ? AND year = ? AND category IS NULL',
        (user_id, month, year)
    ).fetchone()
    if row:
        return row
    row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?',
        (user_id, month, year)
    ).fetchone()
    if row and row['amount']:
        return {'amount': round(row['amount'], 2)}
    return None


def get_category_budgets_with_progress(user_id, current_month, current_year, current_month_key):
    db = get_db()
    rows = db.execute(
        '''SELECT b.*, COALESCE(SUM(e.amount), 0) AS spent
           FROM budgets b
           LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category
             AND strftime("%Y-%m", e.expense_date) = ?
           WHERE b.user_id = ? AND b.month = ? AND b.year = ? AND b.category IS NOT NULL
           GROUP BY b.id, b.category
           ORDER BY b.category ASC''',
        (current_month_key, user_id, current_month, current_year)
    ).fetchall()

    result = []
    for budget in rows:
        category = budget['category']
        budget_amount = round(budget['amount'] or 0.0, 2)
        spent = round(budget['spent'] or 0.0, 2)
        utilization = round((spent / budget_amount * 100), 1) if budget_amount else 0.0
        status = 'Over Budget' if utilization >= 100 else 'At Risk' if utilization >= 80 else 'On Track'
        remaining = round(budget_amount - spent, 2)

        result.append({
            'id': budget['id'],
            'category': category,
            'limit': budget_amount,
            'budget_amount': budget_amount,
            'spent': spent,
            'remaining': remaining,
            'util_pct': utilization,
            'utilization': utilization,
            'status': status,
        })
    return result


def calculate_portfolio_metrics(user_id):
    db = get_db()
    row = db.execute(
        'SELECT COALESCE(SUM(purchase_price * quantity), 0) AS invested, '
        'COALESCE(SUM(current_price * quantity), 0) AS current_value, COUNT(*) AS count '
        'FROM investments WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    invested = round(row['invested'] or 0.0, 2)
    current_value = round(row['current_value'] or 0.0, 2)
    return {
        'total_invested': invested,
        'current_value': current_value,
        'profit_loss': round(current_value - invested, 2),
        'position_count': row['count'] or 0,
    }


# ── Goal & Contributions Ledger Services ────────────────────────────────────

def add_goal_contribution(user_id, goal_id, amount, contribution_date, note=None):
    """Adds a goal contribution and updates the goal's saved_amount."""
    db = get_db()
    cursor = db.cursor()
    # Enforce ownership
    goal = cursor.execute('SELECT * FROM financial_goals WHERE id = ? AND user_id = ?', (goal_id, user_id)).fetchone()
    if not goal:
        return False

    cursor.execute(
        'INSERT INTO goal_contributions (goal_id, user_id, amount, contribution_date, note) VALUES (?, ?, ?, ?, ?)',
        (goal_id, user_id, float(amount), contribution_date, note)
    )

    new_saved = round(float(goal['saved_amount']) + float(amount), 2)
    status = 'Completed' if goal['target_amount'] > 0 and new_saved >= goal['target_amount'] else 'Active'

    cursor.execute(
        'UPDATE financial_goals SET saved_amount = ?, status = ? WHERE id = ?',
        (new_saved, status, goal_id)
    )
    db.commit()
    return True



def get_goal_contributions(user_id, goal_id=None):
    """Retrieves contribution history for user goals."""
    db = get_db()
    if goal_id:
        rows = db.execute(
            'SELECT gc.*, g.goal_name FROM goal_contributions gc '
            'JOIN financial_goals g ON gc.goal_id = g.id '
            'WHERE gc.user_id = ? AND gc.goal_id = ? ORDER BY gc.contribution_date DESC, gc.created_at DESC',
            (user_id, goal_id)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT gc.*, g.goal_name FROM goal_contributions gc '
            'JOIN financial_goals g ON gc.goal_id = g.id '
            'WHERE gc.user_id = ? ORDER BY gc.contribution_date DESC, gc.created_at DESC',
            (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def calculate_goals_summary(user_id):
    db = get_db()
    goals_rows = db.execute(
        'SELECT g.id, g.target_amount, '
        'COALESCE((SELECT SUM(amount) FROM goal_contributions WHERE goal_id = g.id), g.saved_amount) AS calc_saved, '
        'g.status '
        'FROM financial_goals g WHERE g.user_id = ?',
        (user_id,)
    ).fetchall()

    target_total = 0.0
    saved_total = 0.0
    total_goals = len(goals_rows)
    completed_goals = 0
    active_goals = 0

    for row in goals_rows:
        target = float(row['target_amount'] or 0.0)
        saved = float(row['calc_saved'] or 0.0)
        target_total += target
        saved_total += saved
        if row['status'] == 'Completed' or (target > 0 and saved >= target):
            completed_goals += 1
        else:
            active_goals += 1

    return {
        'total_target': round(target_total, 2),
        'total_saved': round(saved_total, 2),
        'total_goals': total_goals,
        'completed_goals': completed_goals,
        'active_goals': active_goals,
    }


def calculate_monthly_report(user_id, month_key):
    db = get_db()
    total_expenses, expense_count = calculate_total_expenses(user_id, month_key)
    total_income, income_count = calculate_total_income(user_id, month_key)
    cash_flow = calculate_cash_flow_metrics(user_id, month_key)
    
    try:
        dt = datetime.strptime(month_key, '%Y-%m')
        month_name = dt.strftime('%B')
        year_num = dt.year
    except (ValueError, TypeError):
        now = datetime.now()
        month_name = now.strftime('%B')
        year_num = now.year

    budget_row = get_monthly_budget_row(user_id, month_name, year_num)
    monthly_budget = float(budget_row['amount']) if budget_row and budget_row['amount'] else None
    remaining_budget = calculate_remaining_budget(monthly_budget, total_expenses)
    budget_utilization = calculate_budget_utilization(total_expenses, monthly_budget)

    try:
        dt = datetime.strptime(month_key, '%Y-%m')
        days_in_month = calendar.monthrange(dt.year, dt.month)[1]
    except Exception:
        days_in_month = 30
    daily_avg = round(total_expenses / max(1, days_in_month), 2)

    category_rows = db.execute(
        'SELECT category, COALESCE(SUM(amount), 0) AS amount, COUNT(*) AS count '
        'FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ? '
        'GROUP BY category ORDER BY amount DESC',
        (user_id, month_key)
    ).fetchall()

    cat_list = [
        {
            'category': row['category'],
            'amount': round(row['amount'] or 0.0, 2),
            'count': row['count'] or 0,
        }
        for row in category_rows
    ]

    return {
        'month_label': _format_month_label(month_key),
        'month_key': month_key,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_cash_flow': cash_flow['net_cash_flow'],
        'savings_rate': cash_flow['savings_rate'],
        'transaction_count': expense_count,
        'monthly_budget': monthly_budget,
        'remaining_budget': remaining_budget,
        'budget_utilization': budget_utilization,
        'daily_avg': daily_avg,
        'category_summary': cat_list,
        'category_breakdown': cat_list,
    }


def calculate_financial_intelligence(user_id):
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    cash_flow = calculate_cash_flow_metrics(user_id, current_month_key)
    total_expenses, tx_count = cash_flow['total_expenses'], cash_flow['expense_count']
    total_income = cash_flow['total_income']
    
    current_days = calendar.monthrange(now.year, now.month)[1]
    avg_daily_spending = round(total_expenses / current_days, 2) if current_days else 0.0
    previous_month = (now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    previous_expenses, _ = calculate_total_expenses(user_id, previous_month)

    mom_change_pct = 0.0
    if previous_expenses and previous_expenses > 0:
        mom_change_pct = round(((total_expenses - previous_expenses) / previous_expenses) * 100, 1)
    elif total_expenses > 0:
        mom_change_pct = 100.0

    goals = calculate_goals_summary(user_id)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amount = float(budget_row['amount']) if budget_row and budget_row['amount'] else None
    health_score = calculate_health_score_detailed(user_id)['score']
    portfolio = calculate_portfolio_metrics(user_id)

    return {
        'month_label': _format_month_label(current_month_key),
        'monthly_tx_count': tx_count,
        'total_income': total_income,
        'net_cash_flow': cash_flow['net_cash_flow'],
        'savings_rate': cash_flow['savings_rate'],
        'total_saved': goals['total_saved'],
        'monthly_spending': total_expenses,
        'avg_daily_spending': avg_daily_spending,
        'mom_change_pct': mom_change_pct,
        'total_expenses': total_expenses,
        'budget_amount': budget_amount,
        'health_score': health_score,
        'portfolio_value': portfolio['current_value'],
    }


def generate_budget_recommendations(user_id, format_currency):
    """Generates budget recommendations derived strictly from real user spending and budget data."""
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    total_expenses, _ = calculate_total_expenses(user_id, month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amount = budget_row['amount'] if budget_row else None
    utilization = calculate_budget_utilization(total_expenses, budget_amount)
    recommendations = []

    if budget_amount is None:
        recommendations.append({
            'priority': 'High',
            'title': 'Set a Monthly Budget Ceiling',
            'message': 'Establish a monthly budget ceiling to track expenditure against defined targets.',
            'estimated_savings': 'N/A',
            'score_impact': 'Improves Health Score',
            'difficulty': 'Easy',
            'time_to_complete': '3 mins'
        })
        return recommendations

    if utilization is None:
        recommendations.append({
            'priority': 'Medium',
            'title': 'Log Initial Monthly Transactions',
            'message': 'Begin logging daily transactions to track monthly utilization.',
            'estimated_savings': 'N/A',
            'score_impact': 'Improves Tracking',
            'difficulty': 'Easy',
            'time_to_complete': '2 mins'
        })
        return recommendations

    if utilization >= 100:
        over_amt = total_expenses - budget_amount
        recommendations.append({
            'priority': 'Critical',
            'title': 'Re-align Overbudget Expenditures',
            'message': f'You have exceeded your monthly budget by {format_currency(over_amt)}. Consider reducing non-essential spending by {format_currency(over_amt)} to return within budget limits.',
            'estimated_savings': f'{format_currency(over_amt)}',
            'score_impact': 'High Priority',
            'difficulty': 'Medium',
            'time_to_complete': '10 mins'
        })
    elif utilization >= 80:
        rem_amt = budget_amount - total_expenses
        recommendations.append({
            'priority': 'High',
            'title': 'Reduce Discretionary Spending',
            'message': f'Current utilization is at {utilization:.1f}%. Only {format_currency(rem_amt)} remains for this cycle.',
            'estimated_savings': f'{format_currency(rem_amt)} remaining buffer',
            'score_impact': 'Medium Priority',
            'difficulty': 'Easy',
            'time_to_complete': '5 mins'
        })
    else:
        surplus_amt = budget_amount - total_expenses
        recommendations.append({
            'priority': 'Low',
            'title': 'Allocate Monthly Surplus',
            'message': f'Utilization is healthy at {utilization:.1f}%. Unused budget buffer is {format_currency(surplus_amt)}.',
            'estimated_savings': f'{format_currency(surplus_amt)} buffer',
            'score_impact': 'Maintain Discipline',
            'difficulty': 'Easy',
            'time_to_complete': '5 mins'
        })

    # Portfolio recommendation
    portfolio = calculate_portfolio_metrics(user_id)
    if portfolio['current_value'] == 0:
        recommendations.append({
            'priority': 'High',
            'title': 'Establish Investment Holdings',
            'message': 'Recording your investment holdings allows FinSight to track your portfolio value and asset allocation.',
            'estimated_savings': 'N/A',
            'score_impact': 'Builds Portfolio',
            'difficulty': 'Medium',
            'time_to_complete': '15 mins'
        })

    return recommendations


def calculate_health_score_detailed(user_id, custom_expenses=None, custom_budget=None, custom_investments=None):
    """
    Calculates the 6-dimension explainable FinSight Financial Health Score (0-100).
    Can accept optional custom_expenses, custom_budget, custom_investments for scenario simulation.
    """
    db = get_db()
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    
    goals = calculate_goals_summary(user_id)
    cash_flow = calculate_cash_flow_metrics(user_id, month_key)
    
    if custom_expenses is not None:
        total_expenses = float(custom_expenses)
        tx_count = 10
    else:
        total_expenses, tx_count = calculate_total_expenses(user_id, month_key)

    if custom_budget is not None:
        budget_amt = float(custom_budget)
    else:
        budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
        budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else None

    utilization = calculate_budget_utilization(total_expenses, budget_amt)

    if custom_investments is not None:
        port_val = float(custom_investments)
    else:
        portfolio = calculate_portfolio_metrics(user_id)
        port_val = portfolio.get('current_value', 0.0)
    
    # Sub-metric 1: Budget Discipline (Weight: 25%)
    if budget_amt and budget_amt > 0:
        util = utilization if utilization is not None else 0
        if util <= 65:
            b_score = 95
            b_label = 'Excellent'
            b_exp = f'Used only {util:.1f}% of your allocated monthly budget.'
            b_reason = 'Low spending velocity leaves significant buffer.'
            b_sug = 'Maintain current spending habits to maximize monthly savings.'
        elif util <= 85:
            b_score = 80
            b_label = 'Good'
            b_exp = f'Used {util:.1f}% of monthly budget.'
            b_reason = 'Spending is within limits but approaching peak threshold.'
            b_sug = 'Monitor non-essential category spending for the remainder of the month.'
        elif util <= 100:
            b_score = 62
            b_label = 'Fair'
            b_exp = f'Used {util:.1f}% of budget, nearing capacity.'
            b_reason = 'High budget utilization limits flexible savings.'
            b_sug = 'Limit discretionary spending until next budget cycle.'
        else:
            b_score = 35
            b_label = 'Needs Attention'
            b_exp = f'Over budget by {util - 100:.1f}%.'
            b_reason = 'Monthly expenses exceeded allocated ceiling.'
            b_sug = 'Re-align category budgets or pause non-essential purchases.'
    else:
        b_score = 65
        b_label = 'Fair'
        b_exp = 'No active monthly budget defined.'
        b_reason = 'Without a budget baseline, spending discipline cannot be fully verified.'
        b_sug = 'Set a monthly budget to track and cap your expenditure.'

    # Sub-metric 2: Net Cash Flow / Savings Rate (Weight: 25%)
    total_income = cash_flow['total_income']
    net_flow = cash_flow['net_cash_flow']
    sav_rate = cash_flow['savings_rate']
    
    if total_income > 0:
        if sav_rate >= 30:
            s_score = 95
            s_label = 'Excellent'
            s_exp = f'Savings rate is {sav_rate:.1f}% (Net Cash Flow: {net_flow:,.0f}).'
            s_reason = 'Healthy monthly surplus.'
            s_sug = 'Maintain high savings rate to build long-term capital.'
        elif sav_rate >= 15:
            s_score = 80
            s_label = 'Good'
            s_exp = f'Savings rate is {sav_rate:.1f}% (Net Cash Flow: {net_flow:,.0f}).'
            s_reason = 'Positive cash flow buffer.'
            s_sug = 'Automate contributions to financial goals.'
        elif sav_rate > 0:
            s_score = 60
            s_label = 'Fair'
            s_exp = f'Savings rate is {sav_rate:.1f}%.'
            s_reason = 'Low positive cash flow.'
            s_sug = 'Look for non-essential expenses to cut.'
        else:
            s_score = 35
            s_label = 'Negative Cash Flow'
            s_exp = f'Monthly expenses exceed income by {abs(net_flow):,.0f}.'
            s_reason = 'Outflow exceeds inflow this month.'
            s_sug = 'Reduce monthly expenditure immediately.'
    else:
        # Fallback to goal saved progress if income not logged
        total_saved = goals.get('total_saved', 0.0)
        total_target = goals.get('total_target', 0.0)
        savings_pct = (total_saved / total_target * 100) if total_target > 0 else 0
        if savings_pct >= 50:
            s_score = 80
            s_label = 'Good'
            s_exp = f'Accumulated {savings_pct:.1f}% of goal targets.'
            s_reason = 'Steady ongoing progress toward savings targets.'
            s_sug = 'Log monthly income for complete cash flow tracking.'
        else:
            s_score = 55
            s_label = 'Limited History'
            s_exp = 'Income data not logged for cash flow tracking.'
            s_reason = 'Log monthly income to calculate exact savings rate.'
            s_sug = 'Add your monthly income entries in the Income section.'

    # Sub-metric 3: Estimated Expense Coverage (Weight: 20%)
    em_goal = db.execute(
        "SELECT * FROM financial_goals WHERE user_id = ? AND (goal_type LIKE '%Emergency%' OR goal_name LIKE '%Emergency%') LIMIT 1",
        (user_id,)
    ).fetchone()

    if em_goal and float(em_goal['saved_amount'] or 0) > 0:
        em_saved = float(em_goal['saved_amount'] or 0)
        essential_exp = max(100.0, total_expenses)
        coverage_months = round(em_saved / essential_exp, 1)
        if coverage_months >= 6:
            r_score = 95
            r_label = 'Excellent'
            r_exp = f'Estimated expense coverage: {coverage_months} months of expenses.'
            r_reason = 'Robust liquid reserve cushion.'
            r_sug = 'Keep emergency funds in liquid instruments.'
        elif coverage_months >= 3:
            r_score = 80
            r_label = 'Good'
            r_exp = f'Estimated expense coverage: {coverage_months} months of expenses.'
            r_reason = 'Adequate emergency liquidity.'
            r_sug = 'Target 6 months of expense coverage.'
        else:
            r_score = 55
            r_label = 'Fair'
            r_exp = f'Estimated expense coverage: {coverage_months} month(s) of expenses.'
            r_reason = 'Reserve cushion is limited.'
            r_sug = 'Build emergency reserves up to 3-6 months of expenses.'
    else:
        r_score = 50
        r_label = 'Limited History'
        r_exp = 'No active Emergency Fund goal defined.'
        r_reason = 'Emergency reserve status unverified.'
        r_sug = 'Create an Emergency Fund goal to track dedicated liquid reserves.'

    # Sub-metric 4: Expense Stability (Weight: 15%)
    # Check past 3 months of expenses
    past_months = db.execute(
        'SELECT strftime("%Y-%m", expense_date) AS m_key, SUM(amount) AS m_tot '
        'FROM expenses WHERE user_id = ? GROUP BY m_key ORDER BY m_key DESC LIMIT 3',
        (user_id,)
    ).fetchall()

    if len(past_months) >= 2:
        vals = [float(r['m_tot'] or 0) for r in past_months]
        mean_val = sum(vals) / len(vals)
        if mean_val > 0:
            variance = sum((x - mean_val) ** 2 for x in vals) / len(vals)
            std_dev = variance ** 0.5
            cov = (std_dev / mean_val) * 100
            if cov <= 20:
                e_score = 90
                e_label = 'High Stability'
                e_exp = f'Monthly spending is stable (Coefficient of Variation: {cov:.1f}%).'
                e_reason = 'Consistent spending pattern across recent months.'
                e_sug = 'Maintain predictable monthly spending.'
            elif cov <= 40:
                e_score = 75
                e_label = 'Moderate Stability'
                e_exp = f'Moderate spending variation (Coefficient of Variation: {cov:.1f}%).'
                e_reason = 'Slight fluctuation in monthly outflows.'
                e_sug = 'Monitor irregular discretionary purchases.'
            else:
                e_score = 55
                e_label = 'Variable Outflow'
                e_exp = f'High spending variation across recent months (CV: {cov:.1f}%).'
                e_reason = 'Significant monthly expense fluctuations.'
                e_sug = 'Smooth out major purchases over multiple months.'
        else:
            e_score = 75
            e_label = 'Good'
            e_exp = 'Minimal monthly expenditure logged.'
            e_reason = 'Low spending activity.'
            e_sug = 'Log all daily transactions.'
    else:
        e_score = 70
        e_label = 'Limited History'
        e_exp = 'Fewer than 2 months of expense data logged.'
        e_reason = 'Multi-month expense stability requires historical records.'
        e_sug = 'Continue logging transactions for multi-month trend analysis.'

    # Sub-metric 5: Goal Completion Rate (Weight: 10%)
    completed_goals = goals.get('completed_goals', 0)
    active_goals = goals.get('active_goals', 0)
    total_g = completed_goals + active_goals
    if total_g > 0:
        g_ratio = completed_goals / total_g
        if g_ratio >= 0.5:
            g_score = 90
            g_label = 'Excellent'
            g_exp = f'{completed_goals} goal milestone(s) completed.'
            g_reason = 'High goal milestone completion rate.'
            g_sug = 'Set new milestone targets.'
        else:
            g_score = 72
            g_label = 'Good'
            g_exp = f'{active_goals} active goal(s) in progress, {completed_goals} completed.'
            g_reason = 'Active goal tracking under progress.'
            g_sug = 'Prioritize goals approaching deadline.'
    else:
        g_score = 60
        g_label = 'Fair'
        g_exp = 'No active financial goals defined.'
        g_reason = 'Goal engine inactive.'
        g_sug = 'Create your first financial goal.'

    # Sub-metric 6: Asset-Class Concentration (Weight: 5%)
    type_rows = db.execute(
        'SELECT investment_type, SUM(quantity * current_price) AS type_val FROM investments WHERE user_id = ? GROUP BY investment_type',
        (user_id,)
    ).fetchall()
    num_types = len(type_rows)

    if port_val > 0 and type_rows:
        hhi = sum(((float(r['type_val'] or 0) / port_val) ** 2) for r in type_rows)
        max_type_val = max(float(r['type_val'] or 0) for r in type_rows)
        top_share_pct = (max_type_val / port_val) * 100
        if hhi > 0.5 or top_share_pct >= 70:
            d_score = 40
            d_label = 'High Concentration'
            d_exp = f'High asset-class concentration (top class accounts for {top_share_pct:.1f}%).'
            d_reason = 'High concentration in a single asset type.'
            d_sug = 'Consider diversifying into other asset classes.'
        elif hhi > 0.25 or top_share_pct >= 50:
            d_score = 65
            d_label = 'Moderate Concentration'
            d_exp = f'Moderate asset-class concentration (top class: {top_share_pct:.1f}%).'
            d_reason = 'Moderate asset concentration.'
            d_sug = 'Expand allocations across mutual funds or fixed income.'
        else:
            d_score = 90
            d_label = 'Well Balanced'
            d_exp = f'Balanced asset allocation across {num_types} asset classes.'
            d_reason = 'Balanced asset allocation.'
            d_sug = 'Maintain periodic quarterly rebalancing.'
    else:
        d_score = 50
        d_label = 'No Investments'
        d_exp = 'No investment positions recorded.'
        d_reason = 'Wealth growth relies solely on liquid savings.'
        d_sug = 'Add your investment holdings in the Investments section.'

    weighted_score = int(
        b_score * 0.25 +
        s_score * 0.25 +
        r_score * 0.20 +
        e_score * 0.15 +
        g_score * 0.10 +
        d_score * 0.05
    )
    score = max(10, min(100, weighted_score))

    if score >= 80:
        label = 'Excellent'
        color = '#10B981'
    elif score >= 65:
        label = 'Good'
        color = '#0EA5E9'
    elif score >= 45:
        label = 'Fair'
        color = '#F59E0B'
    else:
        label = 'Needs Attention'
        color = '#EF4444'

    sub_metrics = [
        {'name': 'Budget Discipline', 'weight': '25%', 'score': b_score, 'label': b_label, 'explanation': b_exp, 'reason': b_reason, 'suggestion': b_sug, 'impact': f"+{int(b_score * 0.25)} pts"},
        {'name': 'Cash Flow & Savings Rate', 'weight': '25%', 'score': s_score, 'label': s_label, 'explanation': s_exp, 'reason': s_reason, 'suggestion': s_sug, 'impact': f"+{int(s_score * 0.25)} pts"},
        {'name': 'Estimated Expense Coverage', 'weight': '20%', 'score': r_score, 'label': r_label, 'explanation': r_exp, 'reason': r_reason, 'suggestion': r_sug, 'impact': f"+{int(r_score * 0.20)} pts"},
        {'name': 'Expense Stability', 'weight': '15%', 'score': e_score, 'label': e_label, 'explanation': e_exp, 'reason': e_reason, 'suggestion': e_sug, 'impact': f"+{int(e_score * 0.15)} pts"},
        {'name': 'Goal Completion Rate', 'weight': '10%', 'score': g_score, 'label': g_label, 'explanation': g_exp, 'reason': g_reason, 'suggestion': g_sug, 'impact': f"+{int(g_score * 0.10)} pts"},
        {'name': 'Asset-Class Concentration', 'weight': '5%', 'score': d_score, 'label': d_label, 'explanation': d_exp, 'reason': d_reason, 'suggestion': d_sug, 'impact': f"+{int(d_score * 0.05)} pts"},
    ]

    positive_factors = [m['explanation'] for m in sub_metrics if m['score'] >= 75]
    attention_items  = [m['explanation'] + ' ' + m['suggestion'] for m in sub_metrics if m['score'] < 75]

    return {
        'score': score,
        'label': label,
        'color': color,
        'ring_color': color,
        'sub_metrics': sub_metrics,
        'positive_factors': positive_factors,
        'attention_items': attention_items,
    }


def calculate_financial_story(user_id, user_name='Valued User'):
    """Generates a data-grounded daily executive briefing from actual user records."""
    now = datetime.now()
    hour = now.hour
    greeting = 'Good Morning' if hour < 12 else ('Good Afternoon' if hour < 17 else 'Good Evening')
    first_name = user_name.split()[0] if user_name else 'User'

    health = calculate_health_score_detailed(user_id)
    month_key = now.strftime('%Y-%m')
    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    cash_flow = calculate_cash_flow_metrics(user_id, month_key)
    portfolio = calculate_portfolio_metrics(user_id)
    goals = calculate_goals_summary(user_id)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else None

    lines = []
    lines.append(f"{greeting}, {first_name}. Here is your AI Financial Executive Briefing for {now.strftime('%B %d, %Y')}.")
    lines.append(f"• **Financial Health Score:** Your overall score is **{health['score']}/100 ({health['label']})**.")

    if cash_flow['total_income'] > 0:
        lines.append(f"• **Cash Flow & Savings Rate:** Monthly income logged is **₹{cash_flow['total_income']:,.0f}**, net cash flow is **₹{cash_flow['net_cash_flow']:,.0f}** (Savings Rate: **{cash_flow['savings_rate']:.1f}%**).")

    if budget_amt and budget_amt > 0:
        util = (total_exp / budget_amt) * 100
        rem = budget_amt - total_exp
        if util <= 80:
            lines.append(f"• **Budget Discipline:** You have spent **₹{total_exp:,.0f}** of your **₹{budget_amt:,.0f}** budget ({util:.1f}% used). You have **₹{rem:,.0f}** remaining.")
        else:
            lines.append(f"• **Budget Warning:** You have utilized **{util:.1f}%** of your monthly budget (₹{total_exp:,.0f} spent of ₹{budget_amt:,.0f}).")
    else:
        lines.append(f"• **Expenses:** Total monthly expenditure logged is **₹{total_exp:,.0f}** across {tx_cnt} transactions.")

    if portfolio['current_value'] > 0:
        pnl = portfolio['profit_loss']
        pnl_str = f"+₹{pnl:,.0f}" if pnl >= 0 else f"-₹{abs(pnl):,.0f}"
        lines.append(f"• **Recorded Portfolio Valuation:** Recorded market valuation stands at **₹{portfolio['current_value']:,.0f}** with P&L of **{pnl_str}**.")

    if goals['total_target'] > 0:
        pct = (goals['total_saved'] / goals['total_target']) * 100
        lines.append(f"• **Goals Progress:** Saved **₹{goals['total_saved']:,.0f}** toward your **₹{goals['total_target']:,.0f}** goal targets ({pct:.1f}% achieved).")

    top_sug = health['attention_items'][0] if health['attention_items'] else "Maintain consistent budget logging and rebalance investment positions quarterly."
    lines.append(f"• **Recommended Action:** {top_sug}")

    return {
        'greeting': greeting,
        'story_text': "\n\n".join(lines),
        'summary_bullets': lines,
        'action_item': top_sug
    }


def get_unread_notification_count(user_id):
    db = get_db()
    row = db.execute(
        'SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND is_read = 0',
        (user_id,)
    ).fetchone()
    return row['count'] or 0


def get_notification_stats(user_id):
    db = get_db()
    row = db.execute(
        'SELECT COUNT(*) AS total, '
        'SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread, '
        'SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS read_count, '
        'SUM(CASE WHEN type = "security" OR title LIKE "%Warning%" OR title LIKE "%Alert%" OR title LIKE "%Critical%" OR type = "budget" THEN 1 ELSE 0 END) AS high_priority, '
        'SUM(CASE WHEN type = "ai" OR title LIKE "%Insight%" OR type = "intelligence" THEN 1 ELSE 0 END) AS ai_insights '
        'FROM notifications WHERE user_id = ?',
        (user_id,)
    ).fetchone()

    health = calculate_health_score_detailed(user_id)

    return {
        'total': row['total'] or 0,
        'unread': row['unread'] or 0,
        'read': row['read_count'] or 0,
        'high_priority': row['high_priority'] or 0,
        'ai_insights': row['ai_insights'] or 0,
        'health_score': health['score'],
        'health_label': health['label'],
    }


def get_notifications(user_id, limit=100, filter_type='all', search_query=''):
    db = get_db()
    query = 'SELECT * FROM notifications WHERE user_id = ?'
    params = [user_id]

    if filter_type == 'unread':
        query += ' AND is_read = 0'
    elif filter_type == 'read':
        query += ' AND is_read = 1'
    elif filter_type in ('budget', 'expenses', 'investments', 'goals', 'ai', 'security', 'system'):
        cat_map = {'expenses': 'expense', 'investments': 'investment', 'goals': 'goal'}
        target_type = cat_map.get(filter_type, filter_type)
        query += ' AND (type = ? OR title LIKE ?)'
        params.extend([target_type, f'%{filter_type}%'])
    elif filter_type in ('high_priority', 'critical'):
        query += ' AND (type = "security" OR title LIKE "%Warning%" OR title LIKE "%Alert%" OR title LIKE "%Critical%" OR type = "budget")'

    if search_query:
        query += ' AND (title LIKE ? OR message LIKE ? OR type LIKE ? OR created_at LIKE ?)'
        params.extend([f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'])

    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    rows = db.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _notification_exists(db, user_id, title, window_days=1):
    cutoff = (datetime.now() - timedelta(days=window_days)).strftime('%Y-%m-%d %H:%M:%S')
    row = db.execute(
        'SELECT 1 FROM notifications WHERE user_id = ? AND title = ? '
        'AND created_at >= ?',
        (user_id, title, cutoff)
    ).fetchone()
    return row is not None


def check_and_create_alerts(user_id, format_currency):
    db = get_db()
    pref = db.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
    user_pref = dict(pref) if pref else {'notify_budget_alert': 1, 'notify_high_expense': 1, 'notify_portfolio_alert': 1}

    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    total_expenses, _ = calculate_total_expenses(user_id, current_month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amount = budget_row['amount'] if budget_row else None
    utilization = calculate_budget_utilization(total_expenses, budget_amount)

    # 1. Budget Utilization Alert
    if user_pref.get('notify_budget_alert', 1) and budget_amount is not None and utilization is not None and utilization >= 80:
        title = 'Budget Limit Alert' if utilization >= 100 else 'Budget Warning'
        if not _notification_exists(db, user_id, title, window_days=1):
            db.execute(
                'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '
                'VALUES (?, ?, ?, ?, 0, ?)',
                (
                    user_id,
                    'budget',
                    title,
                    f'You have spent {utilization:.0f}% of your monthly budget ({format_currency(total_expenses)} of {format_currency(budget_amount)}).',
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                )
            )

    # 2. Expense Velocity Alert
    if user_pref.get('notify_budget_alert', 1):
        trends = calculate_month_over_month_trends(user_id)
        if trends['expense_pct_change'] >= 15 and trends['expense_direction'] == 'up':
            title = 'Spending Growth Warning'
            if not _notification_exists(db, user_id, title, window_days=3):
                db.execute(
                    'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '
                    'VALUES (?, ?, ?, ?, 0, ?)',
                    (
                        user_id,
                        'expense',
                        title,
                        f"This cycle's spending increased by {trends['expense_pct_change']:.0f}% compared to last month.",
                        now.strftime('%Y-%m-%d %H:%M:%S'),
                    )
                )

    # 3. High-Value Transaction Alert
    if user_pref.get('notify_high_expense', 1):
        large_txs = db.execute(
            'SELECT COUNT(*) AS cnt, MAX(amount) AS max_amt FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ? AND amount >= 1000',
            (user_id, current_month_key)
        ).fetchone()
        if large_txs and large_txs['cnt'] > 0:
            title = 'High-Value Transactions Detected'
            if not _notification_exists(db, user_id, title, window_days=5):
                db.execute(
                    'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '

                'VALUES (?, ?, ?, ?, 0, ?)',
                (
                    user_id,
                    'security',
                    title,
                    f"{large_txs['cnt']} high-value transaction(s) logged this month (Highest: {format_currency(large_txs['max_amt'])}).",
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                )
            )

    # 4. Investment Portfolio Performance Alert
    portfolio = calculate_portfolio_metrics(user_id)
    if portfolio['current_value'] > 0:
        title = 'Portfolio Intelligence Update'
        pnl = portfolio['profit_loss']
        pnl_str = f"+{format_currency(pnl)}" if pnl >= 0 else f"-{format_currency(abs(pnl))}"
        if not _notification_exists(db, user_id, title, window_days=7):
            db.execute(
                'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '
                'VALUES (?, ?, ?, ?, 0, ?)',
                (
                    user_id,
                    'investment',
                    title,
                    f"Investment portfolio valuation stands at {format_currency(portfolio['current_value'])} ({pnl_str} unrealized P&L).",
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                )
            )

    # 5. Financial Health Index Alert
    health = calculate_health_score_detailed(user_id)
    title = 'Financial Health Report'
    if not _notification_exists(db, user_id, title, window_days=7):
        db.execute(
            'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '
            'VALUES (?, ?, ?, ?, 0, ?)',
            (
                user_id,
                'ai',
                title,
                f"Financial health score is currently {health['score']}/100 ({health['label']}).",
                now.strftime('%Y-%m-%d %H:%M:%S'),
            )
        )

    db.commit()


def calculate_reports_analytics(user_id):
    db = get_db()
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    
    monthly_expenses, monthly_tx_count = calculate_total_expenses(user_id, current_month_key)
    monthly_income, income_count = calculate_total_income(user_id, current_month_key)
    cash_flow = calculate_cash_flow_metrics(user_id, current_month_key)
    
    lifetime_row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS total_expenses, COUNT(*) AS expense_count '
        'FROM expenses WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    lifetime_spent = round(lifetime_row['total_expenses'] or 0.0, 2)
    lifetime_count = lifetime_row['expense_count'] or 0
    
    investment_row = db.execute(
        'SELECT COALESCE(SUM(current_price * quantity), 0) AS current_value, '
        'COALESCE(SUM(purchase_price * quantity), 0) AS invested_value '
        'FROM investments WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    
    goals = calculate_goals_summary(user_id)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    monthly_budget = float(budget_row['amount']) if budget_row and budget_row['amount'] else None
    remaining_budget = calculate_remaining_budget(monthly_budget, monthly_expenses)
    
    current_days = max(1, now.day)
    avg_daily_spend = round(monthly_expenses / current_days, 2)
    avg_transaction = round((monthly_expenses / max(monthly_tx_count, 1)), 2) if monthly_tx_count > 0 else 0.0

    return {
        'total_income': monthly_income,
        'monthly_spending': monthly_expenses,
        'total_spent': monthly_expenses,
        'net_cash_flow': cash_flow['net_cash_flow'],
        'savings_rate': cash_flow['savings_rate'],
        'lifetime_spent': lifetime_spent,
        'expense_count': monthly_tx_count,
        'lifetime_expense_count': lifetime_count,
        'monthly_budget': monthly_budget,
        'remaining_budget': remaining_budget,
        'avg_daily_spend': avg_daily_spend,
        'current_investment_value': round(investment_row['current_value'] or 0.0, 2),
        'invested_value': round(investment_row['invested_value'] or 0.0, 2),
        'total_goals': goals['total_goals'],
        'total_saved': goals['total_saved'],
        'avg_transaction_value': avg_transaction,
    }


def calculate_dashboard_metrics(user_id):
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    current_month = now.strftime('%B')
    current_year = now.year

    monthly_budget_row = get_monthly_budget_row(user_id, current_month, current_year)
    monthly_budget = monthly_budget_row['amount'] if monthly_budget_row else None

    cash_flow = calculate_cash_flow_metrics(user_id, current_month_key)
    total_expenses, transaction_count = cash_flow['total_expenses'], cash_flow['expense_count']
    remaining_budget = calculate_remaining_budget(monthly_budget, total_expenses)
    budget_utilization = calculate_budget_utilization(total_expenses, monthly_budget)
    budget_status = calculate_budget_status(monthly_budget, budget_utilization)

    db = get_db()

    # Actual spending today (SUM of expenses on current date)
    today_str = now.strftime('%Y-%m-%d')
    today_row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS today_total FROM expenses WHERE user_id = ? AND expense_date = ?',
        (user_id, today_str)
    ).fetchone()
    today_expenses = round(today_row['today_total'] or 0.0, 2)

    # Average daily spend month-to-date
    days_elapsed = max(1, now.day)
    avg_daily_spend = round(total_expenses / days_elapsed, 2)

    health = calculate_health_score_detailed(user_id)
    portfolio = calculate_portfolio_metrics(user_id)
    goals = calculate_goals_summary(user_id)
    goal_progress_pct = round((goals['total_saved'] / goals['total_target']) * 100, 1) if goals['total_target'] > 0 else 0.0

    category_rows = db.execute(
        'SELECT category, COALESCE(SUM(amount), 0) AS amount '
        'FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ? '
        'GROUP BY category ORDER BY amount DESC LIMIT 5',
        (user_id, current_month_key)
    ).fetchall()
    category_breakdown = [
        {
            'category': row['category'],
            'amount': round(row['amount'] or 0.0, 2),
        }
        for row in category_rows
    ]

    recent_expenses_rows = db.execute(
        'SELECT * FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()
    recent_expenses = [dict(row) for row in recent_expenses_rows]

    start_year = now.year
    start_month = now.month - 11
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start_month_key = f'{start_year}-{start_month:02d}'

    month_totals_rows = db.execute(
        'SELECT strftime("%Y-%m", expense_date) AS month_key, COALESCE(SUM(amount), 0) AS total '
        'FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) >= ? '
        'GROUP BY month_key',
        (user_id, start_month_key)
    ).fetchall()
    totals_map = {row['month_key']: round(row['total'] or 0.0, 2) for row in month_totals_rows}

    monthly_labels = []
    monthly_values = []
    for offset in range(11, -1, -1):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        m_key = f'{year}-{month:02d}'
        monthly_labels.append(datetime(year, month, 1).strftime('%b'))
        monthly_values.append(totals_map.get(m_key, 0.0))

    return {
        'total_income': cash_flow['total_income'],
        'monthly_budget': monthly_budget,
        'total_expenses': total_expenses,
        'net_cash_flow': cash_flow['net_cash_flow'],
        'savings_rate': cash_flow['savings_rate'],
        'today_expenses': today_expenses,
        'avg_daily_spend': avg_daily_spend,
        'remaining_budget': remaining_budget,
        'budget_utilization': budget_utilization,
        'budget_status': budget_status,
        'health_score': health['score'],
        'portfolio_value': portfolio['current_value'],
        'goal_progress_pct': goal_progress_pct,
        'category_breakdown': category_breakdown,
        'recent_expenses': recent_expenses,
        'monthly_expenses_labels': monthly_labels,
        'monthly_expenses_values': monthly_values,
        'transaction_count': transaction_count,
    }


def calculate_smart_insights(user_id, format_currency):
    insights = [
        {
            'title': 'Review recurring costs',
            'description': 'Take a quick look at your monthly subscriptions and see if any recurring bills can be reduced.'
        },
        {
            'title': 'Boost your savings rate',
            'description': 'Set aside a fixed percentage of your monthly income to build your liquid emergency fund.'
        },
        {
            'title': 'Track goal contributions',
            'description': 'Review your active financial goals and log steady contributions toward target dates.'
        },
    ]
    return insights


def calculate_month_over_month_trends(user_id):
    """Calculate MoM comparisons for expenses and income from actual database records."""
    db = get_db()
    now = datetime.now()
    curr_month_key = now.strftime('%Y-%m')
    
    prev_month_val = now.month - 1 if now.month > 1 else 12
    prev_year_val  = now.year if now.month > 1 else now.year - 1
    prev_month_key = f'{prev_year_val}-{prev_month_val:02d}'

    # Expenses MoM
    curr_exp_row = db.execute(
        'SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ?',
        (user_id, curr_month_key)
    ).fetchone()
    prev_exp_row = db.execute(
        'SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS count FROM expenses WHERE user_id = ? AND strftime("%Y-%m", expense_date) = ?',
        (user_id, prev_month_key)
    ).fetchone()

    curr_total = curr_exp_row['total'] or 0.0
    prev_total = prev_exp_row['total'] or 0.0
    
    has_history = prev_total > 0 or prev_exp_row['count'] > 0
    exp_pct = round(((curr_total - prev_total) / prev_total * 100), 1) if prev_total > 0 else 0.0
    exp_direction = 'down' if exp_pct <= 0 else 'up'
    exp_color = '#34D399' if exp_pct <= 0 else '#F87171'

    curr_cnt = curr_exp_row['count'] or 0
    prev_cnt = prev_exp_row['count'] or 0
    tx_pct = round(((curr_cnt - prev_cnt) / prev_cnt * 100), 1) if prev_cnt > 0 else 0.0

    return {
        'has_history': has_history,
        'curr_expenses': curr_total,
        'prev_expenses': prev_total,
        'expense_pct_change': abs(exp_pct),
        'expense_direction': exp_direction,
        'expense_color': exp_color,
        'curr_tx_count': curr_cnt,
        'prev_tx_count': prev_cnt,
        'tx_pct_change': abs(tx_pct),
    }


def calculate_activity_timeline(user_id):
    """Aggregate recent events across expenses, goals, investments, and income into grouped timeline buckets."""
    db = get_db()
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    yesterday_str = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    week_start_str = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')

    def _to_date_str(val):
        if not val:
            return today_str
        if hasattr(val, 'strftime'):
            return val.strftime('%Y-%m-%d')
        return str(val)[:10]

    events = []

    # 1. Income Entries
    inc_rows = [dict(r) for r in db.execute(
        'SELECT id, source, category, amount, income_date, created_at FROM income WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
        (user_id,)
    ).fetchall()]
    for i in inc_rows:
        date_val = _to_date_str(i['income_date'] or i['created_at'])
        events.append({
            'type': 'income',
            'title': f"Income Received: {i['source']}",
            'description': f"{i['category']} - ₹{i['amount']:,.0f}",
            'date': date_val,
            'timestamp': i['created_at'] or date_val,
            'icon': '💵',
            'color': '#34D399',
            'bg': 'rgba(16,185,129,0.12)'
        })

    # 2. Recent Expenses
    exp_rows = [dict(r) for r in db.execute(
        'SELECT id, description, category, amount, expense_date, created_at FROM expenses WHERE user_id = ? ORDER BY created_at DESC LIMIT 15',
        (user_id,)
    ).fetchall()]
    for e in exp_rows:
        date_val = _to_date_str(e['expense_date'] or e['created_at'])
        events.append({
            'type': 'expense',
            'title': f"Expense Logged: {e['category']}",
            'description': f"{e['description'] or e['category']} - ₹{e['amount']:,.0f}",
            'date': date_val,
            'timestamp': e['created_at'] or date_val,
            'icon': '💳',
            'color': '#F87171',
            'bg': 'rgba(239,68,68,0.12)'
        })

    # 3. Goals
    goal_rows = [dict(r) for r in db.execute(
        'SELECT id, goal_name, target_amount, saved_amount, status, created_at FROM financial_goals WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()]
    for g in goal_rows:
        date_val = _to_date_str(g['created_at'])
        is_done = g['status'] == 'Completed'
        events.append({
            'type': 'goal',
            'title': f"Goal {'Achieved 🎉' if is_done else 'Created'}: {g['goal_name']}",
            'description': f"Target: ₹{g['target_amount']:,.0f} | Saved: ₹{g['saved_amount']:,.0f}",
            'date': date_val,
            'timestamp': g['created_at'] or date_val,
            'icon': '🎯',
            'color': '#34D399' if is_done else '#60A5FA',
            'bg': 'rgba(16,185,129,0.12)' if is_done else 'rgba(59,130,246,0.12)'
        })

    # 4. Investments
    inv_rows = [dict(r) for r in db.execute(
        'SELECT * FROM investments WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()]
    for i in inv_rows:
        date_val = _to_date_str(i['created_at'])
        asset_title = i.get('investment_name') or i.get('investment_type') or 'Investment'
        c_price = float(i.get('current_price') or i.get('purchase_price') or 0)
        qty = float(i.get('quantity') or 1)
        val = c_price * qty
        events.append({
            'type': 'investment',
            'title': f"Investment Position: {asset_title}",
            'description': f"{i.get('investment_type', 'Asset')} | Valuation: ₹{val:,.0f}",
            'date': date_val,
            'timestamp': i['created_at'] or date_val,
            'icon': '📈',
            'color': '#C084FC',
            'bg': 'rgba(168,85,247,0.12)'
        })

    # Sort all events newest first
    events.sort(key=lambda x: str(x['timestamp']), reverse=True)

    today_events = [ev for ev in events if ev['date'] == today_str]
    yesterday_events = [ev for ev in events if ev['date'] == yesterday_str]
    this_week_events = [ev for ev in events if ev['date'] >= week_start_str and ev['date'] not in (today_str, yesterday_str)]
    earlier_events = [ev for ev in events if ev['date'] < week_start_str]

    return {
        'today': today_events,
        'yesterday': yesterday_events,
        'this_week': this_week_events,
        'earlier': earlier_events,
        'all_events': events[:20]
    }


def calculate_predictions(user_id):
    """Run-Rate Spending Forecast: Extrapolates current monthly burn rate across remaining days in the month."""
    db = get_db()
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    
    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else total_exp
    
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = max(1, now.day)
    avg_daily_burn = total_exp / days_elapsed
    projected_month_end = round(avg_daily_burn * days_in_month, 2)
    
    projected_savings = max(0.0, budget_amt - projected_month_end)
    health = calculate_health_score_detailed(user_id)
    portfolio = calculate_portfolio_metrics(user_id)

    forecast = {
        'projected_month_end_spend': {
            'value': projected_month_end,
            'methodology': f'Linear extrapolation based on current daily burn rate of ₹{avg_daily_burn:,.0f}/day across {days_in_month} days in {now.strftime("%B")}.',
            'recommendation': 'Monitor non-essential category spending if current daily burn rate exceeds daily budget allowance.'
        },
        'next_month_expenses': {
            'value': projected_month_end,
            'methodology': f'Projected month-end spending based on current daily burn rate of ₹{avg_daily_burn:,.0f}/day across {days_in_month} days in {now.strftime("%B")}.',
            'recommendation': 'Monitor non-essential category spending if current daily burn rate exceeds daily budget allowance.'
        },
        'expected_savings': {
            'value': projected_savings,
            'methodology': f'Difference between allocated monthly budget (₹{budget_amt:,.0f}) and projected run-rate expenditure (₹{projected_month_end:,.0f}).',
            'recommendation': 'Channel projected surplus into your active Emergency Fund or Goal targets.'
        },
        'current_daily_burn': {
            'value': round(avg_daily_burn, 2),
            'methodology': f'Total logged expenses of ₹{total_exp:,.0f} divided by {days_elapsed} elapsed days.',
            'recommendation': 'Keep daily burn rate below ₹' + f'{(budget_amt / days_in_month):,.0f}' + '/day to remain within budget baseline.' if budget_amt > 0 else 'Set a monthly budget baseline to monitor daily burn allowance.'
        },
        'current_health_score': {
            'value': health['score'],
            'methodology': f'6-dimension explainable health score rating ({health["label"]}).',
            'recommendation': health['attention_items'][0] if health['attention_items'] else 'Maintain current budget compliance.'
        },
        'portfolio_current_valuation': {
            'value': portfolio['current_value'],
            'methodology': f'Sum of current valuations across {portfolio["position_count"]} recorded asset positions.',
            'recommendation': 'Rebalance portfolio quarterly based on asset concentration.'
        }
    }
    return forecast


def calculate_investment_advisor_metrics(user_id):
    """Portfolio Asset Allocation Analysis: Evaluates portfolio concentration using Herfindahl-Hirschman Index (HHI)."""
    db = get_db()
    portfolio = calculate_portfolio_metrics(user_id)
    total_val = portfolio['current_value']
    
    rows = db.execute(
        'SELECT investment_type, SUM(quantity * current_price) AS type_val FROM investments WHERE user_id = ? GROUP BY investment_type',
        (user_id,)
    ).fetchall()
    
    type_alloc = []
    hhi = 0.0
    for r in rows:
        val = float(r['type_val'] or 0)
        pct = (val / total_val * 100) if total_val > 0 else 0.0
        type_alloc.append({'type': r['investment_type'], 'value': val, 'pct': round(pct, 1)})
        if total_val > 0:
            share = val / total_val
            hhi += share * share
        
    if total_val > 0 and rows:
        if hhi <= 0.25:
            div_score = 92
            risk_level = 'Low Concentration Risk'
        elif hhi <= 0.50:
            div_score = 75
            risk_level = 'Moderate Concentration Risk'
        else:
            div_score = 45
            risk_level = 'High Concentration Risk'
    else:
        div_score = 30
        risk_level = 'No Holdings Recorded'
    
    suggestions = []
    if hhi > 0.50 and total_val > 0:
        suggestions.append(f'High asset concentration detected (HHI Index: {hhi:.2f}). Consider rebalancing into non-correlated asset classes.')
    elif hhi > 0.25:
        suggestions.append(f'Moderate asset concentration (HHI Index: {hhi:.2f}). Asset allocation is distributed across recorded categories.')
    elif total_val > 0:
        suggestions.append(f'Balanced portfolio allocation (HHI Index: {hhi:.2f}). Maintain periodic quarterly rebalancing.')
    else:
        suggestions.append('Record investment holdings in the Investments section to enable asset allocation analysis.')

    return {
        'diversification_score': div_score,
        'risk_score': risk_level,
        'hhi': round(hhi, 3),
        'asset_allocation': type_alloc,
        'suggestions': suggestions
    }


def calculate_coaching_insights(user_id):
    """Personal Financial Coach Engine: Generates morning guidance, evening recap, and weekly challenge."""
    db = get_db()
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    today_str = now.strftime('%Y-%m-%d')

    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    
    # Calculate ACTUAL spending today (SUM of expenses where expense_date = CURRENT_DATE)
    today_row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS today_total FROM expenses WHERE user_id = ? AND expense_date = ?',
        (user_id, today_str)
    ).fetchone()
    spent_today = round(today_row['today_total'] or 0.0, 2)

    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else total_exp
    
    rem_budget = max(0.0, budget_amt - total_exp)
    days_left = max(1, calendar.monthrange(now.year, now.month)[1] - now.day + 1)
    daily_allowance = round(rem_budget / days_left, 0)

    morning_coach = {
        'title': '🌅 Morning Financial Focus',
        'target_budget': f'₹{daily_allowance:,.0f}',
        'advice': f'Your recommended daily spending allowance is ₹{daily_allowance:,.0f} to stay within your monthly ceiling.'
    }
    
    evening_coach = {
        'title': '🌆 Evening Spending Recap',
        'spent_today': f'₹{spent_today:,.0f}',
        'remaining_budget': f'₹{rem_budget:,.0f}',
        'advice': f'Actual spent today: ₹{spent_today:,.0f}. You have ₹{rem_budget:,.0f} remaining for the final {days_left} day(s) of this cycle.'
    }

    weekly_coach = {
        'title': '🎯 Weekly Financial Challenge',
        'challenge': 'Zero Discretionary Dining Day',
        'description': 'Prepare all meals at home for 2 consecutive days to reduce discretionary spending.'
    }

    return {
        'morning': morning_coach,
        'evening': evening_coach,
        'weekly': weekly_coach
    }


def calculate_user_achievements(user_id):
    """Achievement System Engine: Evaluates user data against 7 gamified milestone badges."""
    db = get_db()
    month_key = datetime.now().strftime('%Y-%m')
    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    goals = calculate_goals_summary(user_id)
    portfolio = calculate_portfolio_metrics(user_id)
    budget_row = get_monthly_budget_row(user_id, datetime.now().strftime('%B'), datetime.now().year)

    badges = [
        {
            'id': 'expense_tracker',
            'title': 'Expense Tracker',
            'icon': '📝',
            'unlocked': tx_cnt >= 5,
            'progress': min(100, int(tx_cnt / 5 * 100)),
            'description': 'Log 5 or more transactions'
        },
        {
            'id': 'budget_master',
            'title': 'Budget Master',
            'icon': '🛡️',
            'unlocked': budget_row is not None and (total_exp <= float(budget_row['amount'])),
            'progress': 100 if budget_row and total_exp <= float(budget_row['amount']) else 50,
            'description': 'Maintain expenditure within monthly budget'
        },
        {
            'id': 'smart_saver',
            'title': 'Smart Saver',
            'icon': '💰',
            'unlocked': goals['total_saved'] >= 5000,
            'progress': min(100, int(goals['total_saved'] / 5000 * 100)),
            'description': 'Accumulate ₹5,000+ in goal savings'
        },
        {
            'id': 'goal_crusher',
            'title': 'Goal Crusher',
            'icon': '🏆',
            'unlocked': goals['completed_goals'] >= 1,
            'progress': 100 if goals['completed_goals'] >= 1 else 0,
            'description': 'Achieve at least 1 financial goal milestone'
        },
        {
            'id': 'investment_beginner',
            'title': 'Investment Beginner',
            'icon': '🌱',
            'unlocked': portfolio['current_value'] > 0,
            'progress': 100 if portfolio['current_value'] > 0 else 0,
            'description': 'Record your first investment holding'
        },
        {
            'id': 'investment_expert',
            'title': 'Investment Expert',
            'icon': '🚀',
            'unlocked': portfolio['position_count'] >= 3,
            'progress': min(100, int(portfolio['position_count'] / 3 * 100)),
            'description': 'Build a portfolio with 3+ asset holdings'
        },
        {
            'id': 'discipline_30',
            'title': '30-Day Discipline',
            'icon': '⚡',
            'unlocked': True,
            'progress': 100,
            'description': 'Active FinSight user streak'
        }
    ]
    return badges


def calculate_goal_optimizer_metrics(user_id):
    """Dynamic Goal Optimizer: Computes required monthly contribution based on target, saved, and deadline date."""
    db = get_db()
    now = datetime.now()
    
    goal = db.execute(
        "SELECT * FROM financial_goals WHERE user_id = ? AND status != 'Completed' ORDER BY deadline ASC LIMIT 1",
        (user_id,)
    ).fetchone()

    if not goal:
        return {
            'goal_name': 'No Active Goals',
            'status': 'No active financial goals defined',
            'suggested_monthly_contribution': 0,
            'days_remaining': 0,
            'expected_completion_date': 'N/A',
            'target_amount': 0.0,
            'saved_amount': 0.0,
            'remaining_amount': 0.0,
            'progress_pct': 0.0
        }

    target = float(goal['target_amount'] or 0)
    saved = float(goal['saved_amount'] or 0)
    rem_target = max(0.0, target - saved)
    progress_pct = round((saved / target * 100), 1) if target > 0 else 0.0

    try:
        deadline_date = datetime.strptime(goal['deadline'], '%Y-%m-%d').date()
        days_remaining = (deadline_date - now.date()).days
    except (ValueError, TypeError):
        deadline_date = None
        days_remaining = 0

    if saved >= target:
        status_str = 'Goal achieved 🎉'
        sug_monthly = 0.0
    elif days_remaining <= 0:
        status_str = 'Deadline passed'
        sug_monthly = rem_target
    else:
        status_str = f'Active tracking ({days_remaining} days left)'
        months_remaining = max(0.5, days_remaining / 30.0)
        sug_monthly = round(rem_target / months_remaining, 2)

    return {
        'goal_name': goal['goal_name'],
        'status': status_str,
        'target_amount': target,
        'saved_amount': saved,
        'remaining_amount': rem_target,
        'progress_pct': progress_pct,
        'suggested_monthly_contribution': sug_monthly,
        'days_remaining': max(0, days_remaining),
        'expected_completion_date': goal['deadline']
    }


# =========================================================================
# PDF & Excel Export Services
# =========================================================================

def generate_pdf_report_bytes(user_id, month_key):
    """Generates a financial statement PDF byte buffer using ReportLab."""
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    report = calculate_monthly_report(user_id, month_key)
    health = calculate_health_score_detailed(user_id)
    portfolio = calculate_portfolio_metrics(user_id)
    goals = calculate_goals_summary(user_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#081A2F')
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#64748B')
    )
    section_heading = ParagraphStyle(
        'SecHead',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=5
    )
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E293B')
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0F172A')
    )

    elements = []

    # Document Header
    elements.append(Paragraph("FinSight — Monthly Financial Statement", title_style))
    elements.append(Paragraph(f"Prepared for: <b>{user['name']}</b> | Statement Period: <b>{report['month_label']}</b> | Generated: <b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>", subtitle_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#10B981'), spaceAfter=12))

    # Executive Summary KPI Table
    elements.append(Paragraph("1. Financial Summary", section_heading))
    kpi_data = [
        [Paragraph("<b>Financial Metric</b>", cell_bold), Paragraph("<b>Value</b>", cell_bold), Paragraph("<b>Context</b>", cell_bold)],
        [Paragraph("Total Monthly Income", cell_style), Paragraph(f"₹{report['total_income']:,.2f}", cell_bold), Paragraph("Logged inflows", cell_style)],
        [Paragraph("Monthly Outflow", cell_style), Paragraph(f"₹{report['total_expenses']:,.2f}", cell_bold), Paragraph(f"{report['transaction_count']} logged transactions", cell_style)],
        [Paragraph("Net Cash Flow", cell_style), Paragraph(f"₹{report['net_cash_flow']:,.2f}", cell_bold), Paragraph(f"Savings Rate: {report['savings_rate']:.1f}%", cell_style)],
        [Paragraph("Monthly Budget Limit", cell_style), Paragraph(f"₹{(report['monthly_budget'] or 0):,.2f}", cell_bold), Paragraph(f"Utilization: {report['budget_utilization'] or 0:.1f}%", cell_style)],
        [Paragraph("Remaining Allocation Buffer", cell_style), Paragraph(f"₹{(report['remaining_budget'] or 0):,.2f}", cell_bold), Paragraph("Available spending cap", cell_style)],
        [Paragraph("Financial Health Score", cell_style), Paragraph(f"<b>{health['score']}/100</b>", cell_bold), Paragraph(health['label'], cell_style)],
        [Paragraph("Recorded Portfolio Valuation", cell_style), Paragraph(f"₹{portfolio['current_value']:,.2f}", cell_bold), Paragraph(f"Net Gain/Loss: ₹{portfolio['profit_loss']:,.2f}", cell_style)],
        [Paragraph("Goal Accumulated Savings", cell_style), Paragraph(f"₹{goals['total_saved']:,.2f}", cell_bold), Paragraph(f"Target Reserve: ₹{goals['total_target']:,.2f}", cell_style)],
    ]
    kpi_table = Table(kpi_data, colWidths=[160, 130, 250])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 10))

    # Category Breakdown Table
    elements.append(Paragraph("2. Category Outflow Allocation", section_heading))
    cat_data = [[Paragraph("<b>Category</b>", cell_bold), Paragraph("<b>Amount (₹)</b>", cell_bold), Paragraph("<b>Transactions</b>", cell_bold), Paragraph("<b>Share %</b>", cell_bold)]]
    tot = max(1.0, report['total_expenses'])
    for cat in report['category_breakdown']:
        pct = (cat['amount'] / tot) * 100
        cat_data.append([
            Paragraph(cat['category'], cell_style),
            Paragraph(f"₹{cat['amount']:,.2f}", cell_bold),
            Paragraph(str(cat['count']), cell_style),
            Paragraph(f"{pct:.1f}%", cell_style)
        ])
    cat_table = Table(cat_data, colWidths=[160, 130, 120, 130])
    cat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(cat_table)

    # Document Footer
    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=8))
    elements.append(Paragraph("FinSight Personal Finance & Investment Intelligence Platform", subtitle_style))

    doc.build(elements)
    return buffer.getvalue()


def generate_excel_report_bytes(user_id, month_key):
    """Generates a multi-sheet Excel workbook byte buffer using openpyxl."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    report = calculate_monthly_report(user_id, month_key)
    health = calculate_health_score_detailed(user_id)
    portfolio = calculate_portfolio_metrics(user_id)
    goals = calculate_goals_summary(user_id)

    wb = openpyxl.Workbook()

    header_fill = PatternFill(start_color="081A2F", end_color="081A2F", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font  = Font(name="Calibri", size=14, bold=True, color="081A2F")

    # Sheet 1: Executive Summary
    ws1 = wb.active
    ws1.title = "Executive Summary"
    ws1.views.sheetView[0].showGridLines = True

    ws1['A1'] = "FinSight Monthly Financial Statement"
    ws1['A1'].font = title_font
    ws1['A2'] = f"User: {user['name']} | Period: {report['month_label']} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    ws1.append([])
    ws1.append(["Metric", "Value", "Status / Notes"])
    for col in range(1, 4):
        cell = ws1.cell(row=4, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    rows1 = [
        ["Total Monthly Income", report['total_income'], "Logged inflows"],
        ["Total Monthly Outflow", report['total_expenses'], "Logged transactions"],
        ["Net Cash Flow", report['net_cash_flow'], f"Savings rate: {report['savings_rate']:.1f}%"],
        ["Monthly Budget Ceiling", report['monthly_budget'] or 0, "Set monthly limit"],
        ["Remaining Allocation Buffer", report['remaining_budget'] or 0, "Available allocation"],
        ["Budget Utilization", (report['budget_utilization'] or 0) / 100.0, "Percent of ceiling"],
        ["Financial Health Score", health['score'], health['label']],
        ["Recorded Portfolio Valuation", portfolio['current_value'], f"Invested: {portfolio['total_invested']}"],
        ["Unrealized Capital P&L", portfolio['profit_loss'], "Market net gain/loss"],
        ["Goal Accumulated Savings", goals['total_saved'], f"Target: {goals['total_target']}"],
    ]
    for r in rows1:
        ws1.append(r)

    # Sheet 2: Expenses Ledger
    ws2 = wb.create_sheet(title="Expenses Ledger")
    ws2.views.sheetView[0].showGridLines = True
    ws2.append(["Date", "Category", "Description", "Payment Method", "Currency", "Amount"])
    for col in range(1, 7):
        cell = ws2.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    exp_rows = db.execute("SELECT expense_date, category, description, payment_method, currency, amount FROM expenses WHERE user_id = ? ORDER BY expense_date DESC", (user_id,)).fetchall()
    for er in exp_rows:
        ws2.append([er['expense_date'], er['category'], er['description'], er['payment_method'], er['currency'], er['amount']])

    # Sheet 3: Income Ledger
    ws3 = wb.create_sheet(title="Income Ledger")
    ws3.views.sheetView[0].showGridLines = True
    ws3.append(["Date", "Source", "Category", "Notes", "Amount"])
    for col in range(1, 6):
        cell = ws3.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    inc_rows = db.execute("SELECT income_date, source, category, notes, amount FROM income WHERE user_id = ? ORDER BY income_date DESC", (user_id,)).fetchall()
    for ir in inc_rows:
        ws3.append([ir['income_date'], ir['source'], ir['category'], ir['notes'], ir['amount']])

    # Sheet 4: Investments
    ws4 = wb.create_sheet(title="Investments")
    ws4.views.sheetView[0].showGridLines = True
    ws4.append(["Asset Name", "Asset Type", "Broker", "Purchase Date", "Quantity", "Purchase Price", "Current Price", "Invested Capital", "Current Valuation", "Gain/Loss"])
    for col in range(1, 11):
        cell = ws4.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    inv_rows = db.execute("SELECT investment_name, investment_type, broker, purchase_date, quantity, purchase_price, current_price FROM investments WHERE user_id = ?", (user_id,)).fetchall()
    for ir in inv_rows:
        inv_cap = ir['quantity'] * ir['purchase_price']
        cur_val = ir['quantity'] * ir['current_price']
        ws4.append([ir['investment_name'], ir['investment_type'], ir['broker'], ir['purchase_date'], ir['quantity'], ir['purchase_price'], ir['current_price'], inv_cap, cur_val, cur_val - inv_cap])

    # Sheet 5: Financial Goals
    ws5 = wb.create_sheet(title="Financial Goals")
    ws5.views.sheetView[0].showGridLines = True
    ws5.append(["Goal Name", "Goal Type", "Priority", "Target Amount", "Saved Amount", "Remaining Amount", "Deadline", "Status"])
    for col in range(1, 9):
        cell = ws5.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    goal_rows = db.execute("SELECT goal_name, goal_type, priority, target_amount, saved_amount, deadline, status FROM financial_goals WHERE user_id = ?", (user_id,)).fetchall()
    for gr in goal_rows:
        ws5.append([gr['goal_name'], gr['goal_type'], gr['priority'], gr['target_amount'], gr['saved_amount'], max(0.0, gr['target_amount'] - gr['saved_amount']), gr['deadline'], gr['status']])

    # Auto-adjust column widths
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def calculate_analytics_history(user_id):
    """
    Fetches 100% database-grounded monthly historical data for analytics charts.
    Returns real historical trend arrays without synthetic multipliers.
    """
    db = get_db()
    
    # 1. Real monthly expenses history
    exp_rows = db.execute(
        '''SELECT strftime('%Y-%m', expense_date) as m_key, SUM(amount) as total
           FROM expenses WHERE user_id = ?
           GROUP BY m_key ORDER BY m_key ASC LIMIT 12''',
        (user_id,)
    ).fetchall()

    # 2. Real monthly income history
    inc_rows = db.execute(
        '''SELECT strftime('%Y-%m', income_date) as m_key, SUM(amount) as total
           FROM income WHERE user_id = ?
           GROUP BY m_key ORDER BY m_key ASC LIMIT 12''',
        (user_id,)
    ).fetchall()

    # 3. Real monthly goal contribution history
    contrib_rows = db.execute(
        '''SELECT strftime('%Y-%m', contribution_date) as m_key, SUM(amount) as total
           FROM goal_contributions WHERE user_id = ?
           GROUP BY m_key ORDER BY m_key ASC LIMIT 12''',
        (user_id,)
    ).fetchall()

    # 4. Real investment asset-class breakdown
    inv_rows = db.execute(
        '''SELECT investment_type, SUM(purchase_price * quantity) as invested, SUM(current_price * quantity) as current_val
           FROM investments WHERE user_id = ?
           GROUP BY investment_type''',
        (user_id,)
    ).fetchall()

    return {
        'expense_history': [{'month': r['m_key'], 'total': round(r['total'], 2)} for r in exp_rows],
        'income_history': [{'month': r['m_key'], 'total': round(r['total'], 2)} for r in inc_rows],
        'contrib_history': [{'month': r['m_key'], 'total': round(r['total'], 2)} for r in contrib_rows],
        'investment_breakdown': [{'type': r['investment_type'], 'invested': round(r['invested'], 2), 'current': round(r['current_val'], 2)} for r in inv_rows]
    }

