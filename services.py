import calendar
from datetime import datetime, timedelta

from database import get_db


def _format_month_label(month_key):
    try:
        dt = datetime.strptime(month_key, '%Y-%m')
        return dt.strftime('%B %Y')
    except (ValueError, TypeError):
        return month_key


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

        result.append({
            'category': category,
            'budget_amount': budget_amount,
            'spent': spent,
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


def calculate_goals_summary(user_id):
    db = get_db()
    row = db.execute(
        'SELECT COALESCE(SUM(target_amount), 0) AS target_total, '
        'COALESCE(SUM(saved_amount), 0) AS saved_total, '
        'COUNT(*) AS total_goals, '
        'SUM(CASE WHEN status = "Completed" THEN 1 ELSE 0 END) AS completed_goals, '
        'SUM(CASE WHEN status != "Completed" THEN 1 ELSE 0 END) AS active_goals '
        'FROM financial_goals WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    return {
        'total_target': round(row['target_total'] or 0.0, 2),
        'total_saved': round(row['saved_total'] or 0.0, 2),
        'total_goals': row['total_goals'] or 0,
        'completed_goals': row['completed_goals'] or 0,
        'active_goals': row['active_goals'] or 0,
    }


def calculate_monthly_report(user_id, month_key):
    db = get_db()
    total_expenses, expense_count = calculate_total_expenses(user_id, month_key)
    
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
        'total_expenses': total_expenses,
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
    total_expenses, tx_count = calculate_total_expenses(user_id, current_month_key)
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
            'title': 'Set a Monthly Budget Baseline',
            'message': 'Create a monthly budget ceiling to track expenditure against defined targets.',
            'estimated_savings': '₹3,500/month',
            'score_impact': '+12 pts',
            'difficulty': 'Easy',
            'time_to_complete': '3 mins'
        })
        return recommendations

    if utilization is None:
        recommendations.append({
            'priority': 'Medium',
            'title': 'Log Initial Monthly Transactions',
            'message': 'Begin logging daily transactions to initiate real-time utilization tracking.',
            'estimated_savings': '₹1,200/month',
            'score_impact': '+5 pts',
            'difficulty': 'Easy',
            'time_to_complete': '2 mins'
        })
        return recommendations

    if utilization >= 100:
        over_amt = total_expenses - budget_amount
        recommendations.append({
            'priority': 'Critical',
            'title': 'Re-align Overbudget Expenditures',
            'message': f'You have exceeded your monthly budget by {format_currency(over_amt)}. Review non-essential category costs.',
            'estimated_savings': f'{format_currency(over_amt)}',
            'score_impact': '+15 pts',
            'difficulty': 'Medium',
            'time_to_complete': '10 mins'
        })
    elif utilization >= 80:
        rem_amt = budget_amount - total_expenses
        recommendations.append({
            'priority': 'High',
            'title': 'Reduce Discretionary Spending',
            'message': f'Current utilization is at {utilization:.1f}%. Only {format_currency(rem_amt)} remains for this cycle.',
            'estimated_savings': f'{format_currency(rem_amt * 0.5)}',
            'score_impact': '+8 pts',
            'difficulty': 'Easy',
            'time_to_complete': '5 mins'
        })
    else:
        sav_amt = (budget_amount - total_expenses) * 0.4
        recommendations.append({
            'priority': 'Low',
            'title': 'Automate Surplus into Investments',
            'message': f'Utilization is healthy at {utilization:.1f}%. Channel unused buffer directly into wealth assets.',
            'estimated_savings': f'{format_currency(sav_amt)}/month',
            'score_impact': '+6 pts',
            'difficulty': 'Easy',
            'time_to_complete': '5 mins'
        })

    # Portfolio recommendation
    portfolio = calculate_portfolio_metrics(user_id)
    if portfolio['current_value'] == 0:
        recommendations.append({
            'priority': 'High',
            'title': 'Start Systematic Investment Plan (SIP)',
            'message': 'Deploying regular monthly capital into index equities enhances long-term capital growth.',
            'estimated_savings': '₹2,000/month',
            'score_impact': '+10 pts',
            'difficulty': 'Medium',
            'time_to_complete': '15 mins'
        })

    return recommendations


def calculate_health_score_detailed(user_id):
    db = get_db()
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    
    # Data gathers
    goals = calculate_goals_summary(user_id)
    total_expenses, tx_count = calculate_total_expenses(user_id, month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = budget_row['amount'] if budget_row and budget_row['amount'] else None
    utilization = calculate_budget_utilization(total_expenses, budget_amt)
    
    portfolio = calculate_portfolio_metrics(user_id)
    
    # Sub-metric 1: Budget Discipline
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
            b_exp = f'Over budget by {util - 100:.1f}% ({total_expenses:.0f} spent of {budget_amt:.0f} budget).'
            b_reason = 'Monthly expenses exceeded allocated ceiling.'
            b_sug = 'Re-align category budgets or pause non-essential purchases.'
    else:
        b_score = 65
        b_label = 'Fair'
        b_exp = 'No active monthly budget defined.'
        b_reason = 'Without a budget baseline, spending discipline cannot be fully verified.'
        b_sug = 'Set a monthly budget to track and cap your expenditure.'

    # Sub-metric 2: Savings Habit
    total_saved = goals.get('total_saved', 0.0)
    total_target = goals.get('total_target', 0.0)
    savings_pct = (total_saved / total_target * 100) if total_target > 0 else 0
    if savings_pct >= 60:
        s_score = 90
        s_label = 'Excellent'
        s_exp = f'Accumulated {savings_pct:.1f}% of target financial goals.'
        s_reason = 'Strong goal contribution history.'
        s_sug = 'Consider raising goal targets or starting long-term investments.'
    elif savings_pct >= 30:
        s_score = 75
        s_label = 'Good'
        s_exp = f'Accumulated {savings_pct:.1f}% of goal targets.'
        s_reason = 'Steady ongoing progress toward savings targets.'
        s_sug = 'Automate monthly contributions to reach milestones faster.'
    elif total_target > 0:
        s_score = 50
        s_label = 'Fair'
        s_exp = f'Savings progress is at {savings_pct:.1f}%.'
        s_reason = 'Savings contributions are behind schedule.'
        s_sug = 'Allocate at least 15% of monthly income directly to savings.'
    else:
        s_score = 60
        s_label = 'Fair'
        s_exp = 'No active target savings goals set.'
        s_reason = 'No savings benchmarks defined yet.'
        s_sug = 'Create a financial goal to track dedicated savings.'

    # Sub-metric 3: Investment Growth
    port_val = portfolio.get('current_value', 0.0)
    port_inv = portfolio.get('total_invested', 0.0)
    pnl = portfolio.get('profit_loss', 0.0)
    if port_val > 0:
        pnl_pct = (pnl / port_inv * 100) if port_inv > 0 else 0
        if pnl_pct >= 10:
            i_score = 92
            i_label = 'Excellent'
            i_exp = f'Portfolio gain of +{pnl_pct:.1f}%.'
            i_reason = 'Asset capital appreciation performing above benchmarks.'
            i_sug = 'Rebalance portfolio periodically to lock in gains.'
        elif pnl_pct >= 0:
            i_score = 80
            i_label = 'Good'
            i_exp = f'Portfolio value stable with profit of {pnl:.0f}.'
            i_reason = 'Capital preserved with positive returns.'
            i_sug = 'Explore systematic investment options for compound growth.'
        else:
            i_score = 55
            i_label = 'Needs Attention'
            i_exp = f'Portfolio experiencing unrealized loss of {pnl:.0f}.'
            i_reason = 'Market volatility affecting asset valuations.'
            i_sug = 'Diversify holdings across defensive asset classes.'
    else:
        i_score = 50
        i_label = 'Needs Attention'
        i_exp = 'No investments recorded in portfolio.'
        i_reason = 'Wealth growth relies solely on liquid savings.'
        i_sug = 'Start with low-risk mutual funds or index equities.'

    # Sub-metric 4: Expense Stability
    if tx_count > 0:
        avg_tx = total_expenses / tx_count
        if avg_tx < 2000:
            e_score = 88
            e_label = 'Excellent'
            e_exp = f'Average transaction size is {avg_tx:.0f}.'
            e_reason = 'No large impulse transaction anomalies detected.'
            e_sug = 'Continue maintaining low ticket size purchases.'
        elif avg_tx < 5000:
            e_score = 76
            e_label = 'Good'
            e_exp = f'Moderate average transaction size of {avg_tx:.0f}.'
            e_reason = 'Expense flow is balanced across standard categories.'
            e_sug = 'Review mid-size recurring subscription costs.'
        else:
            e_score = 58
            e_label = 'Fair'
            e_exp = f'High average transaction size of {avg_tx:.0f}.'
            e_reason = 'Large single transactions impacting cash liquidity.'
            e_sug = 'Space out high-value purchases over multiple months.'
    else:
        e_score = 80
        e_label = 'Good'
        e_exp = 'Low transaction activity recorded this month.'
        e_reason = 'No spending spikes recorded.'
        e_sug = 'Ensure all daily expenses are logged accurately.'

    # Sub-metric 5: Goal Progress
    completed_goals = goals.get('completed_goals', 0)
    active_goals = goals.get('active_goals', 0)
    if completed_goals > 0 or active_goals > 0:
        g_ratio = completed_goals / (completed_goals + active_goals)
        if g_ratio >= 0.5:
            g_score = 90
            g_label = 'Excellent'
            g_exp = f'{completed_goals} goal(s) achieved successfully!'
            g_reason = 'High goal completion milestone rate.'
            g_sug = 'Set new long-term milestone targets.'
        else:
            g_score = 72
            g_label = 'Good'
            g_exp = f'{active_goals} goal(s) in progress, {completed_goals} completed.'
            g_reason = 'Active tracking under progress.'
            g_sug = 'Prioritize goals approaching target deadline date.'
    else:
        g_score = 60
        g_label = 'Fair'
        g_exp = 'No goals created.'
        g_reason = 'Goal engine inactive.'
        g_sug = 'Set your first financial goal.'

    # Sub-metric 6: Emergency Reserve
    rem_budget = (budget_amt - total_expenses) if budget_amt else 0
    liquid_reserve = max(0.0, rem_budget) + total_saved
    if liquid_reserve >= 30000:
        r_score = 94
        r_label = 'Excellent'
        r_exp = f'Liquid emergency reserve of {liquid_reserve:.0f}.'
        r_reason = 'Strong safety cushion covering multiple months.'
        r_sug = 'Keep emergency funds in high-yield liquid instruments.'
    elif liquid_reserve >= 10000:
        r_score = 75
        r_label = 'Good'
        r_exp = f'Reserve cushion of {liquid_reserve:.0f}.'
        r_reason = 'Adequate emergency liquidity.'
        r_sug = 'Build reserve up to 3x monthly expenses.'
    else:
        r_score = 45
        r_label = 'Needs Attention'
        r_exp = f'Limited emergency liquidity reserve ({liquid_reserve:.0f}).'
        r_reason = 'Low liquidity increases vulnerability to unexpected expenses.'
        r_sug = 'Build a dedicated emergency fund before expanding risk assets.'

    # Weighted overall score calculation
    weighted_score = int(
        b_score * 0.25 +
        s_score * 0.20 +
        i_score * 0.20 +
        e_score * 0.15 +
        g_score * 0.10 +
        r_score * 0.10
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
        {'name': 'Budget Discipline', 'score': b_score, 'label': b_label, 'explanation': b_exp, 'reason': b_reason, 'suggestion': b_sug, 'impact': f"+{int(b_score * 0.25)} pts"},
        {'name': 'Savings Habit', 'score': s_score, 'label': s_label, 'explanation': s_exp, 'reason': s_reason, 'suggestion': s_sug, 'impact': f"+{int(s_score * 0.20)} pts"},
        {'name': 'Investment Growth', 'score': i_score, 'label': i_label, 'explanation': i_exp, 'reason': i_reason, 'suggestion': i_sug, 'impact': f"+{int(i_score * 0.20)} pts"},
        {'name': 'Expense Stability', 'score': e_score, 'label': e_label, 'explanation': e_exp, 'reason': e_reason, 'suggestion': e_sug, 'impact': f"+{int(e_score * 0.15)} pts"},
        {'name': 'Goal Progress', 'score': g_score, 'label': g_label, 'explanation': g_exp, 'reason': g_reason, 'suggestion': g_sug, 'impact': f"+{int(g_score * 0.10)} pts"},
        {'name': 'Emergency Fund', 'score': r_score, 'label': r_label, 'explanation': r_exp, 'reason': r_reason, 'suggestion': r_sug, 'impact': f"+{int(r_score * 0.10)} pts"},
    ]

    # Factors lists
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
    """Generate narrative financial story / daily executive briefing from existing user data."""
    now = datetime.now()
    hour = now.hour
    greeting = 'Good Morning' if hour < 12 else ('Good Afternoon' if hour < 17 else 'Good Evening')
    first_name = user_name.split()[0] if user_name else 'User'

    health = calculate_health_score_detailed(user_id)
    month_key = now.strftime('%Y-%m')
    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    portfolio = calculate_portfolio_metrics(user_id)
    goals = calculate_goals_summary(user_id)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else None

    lines = []
    lines.append(f"{greeting}, {first_name}. Here is your AI Financial Executive Briefing for {now.strftime('%B %d, %Y')}.")
    lines.append(f"• **Financial Health Score:** Your overall score is **{health['score']}/100 ({health['label']})**.")

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
        lines.append(f"• **Investment Portfolio:** Market valuation stands at **₹{portfolio['current_value']:,.0f}** with unrealized P&L of **{pnl_str}**.")

    if goals['total_target'] > 0:
        pct = (goals['total_saved'] / goals['total_target']) * 100
        lines.append(f"• **Goals Progress:** Saved **₹{goals['total_saved']:,.0f}** toward your **₹{goals['total_target']:,.0f}** goal targets ({pct:.1f}% achieved).")

    # Pick top recommendation action
    top_sug = health['attention_items'][0] if health['attention_items'] else "Maintain consistent budget logging and rebalance investment positions monthly."
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
    row = db.execute(
        'SELECT 1 FROM notifications WHERE user_id = ? AND title = ? '
        'AND created_at >= datetime("now", ?)',
        (user_id, title, f'-{window_days} days')
    ).fetchone()
    return row is not None


def check_and_create_alerts(user_id, format_currency):
    db = get_db()
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    total_expenses, _ = calculate_total_expenses(user_id, current_month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amount = budget_row['amount'] if budget_row else None
    utilization = calculate_budget_utilization(total_expenses, budget_amount)

    # 1. Budget Utilization Alert
    if budget_amount is not None and utilization is not None and utilization >= 80:
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
                    f"This week's spending increased by {trends['expense_pct_change']:.0f}% compared to last month.",
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                )
            )

    # 3. High-Value Transaction Alert
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

    # 6. Goal Milestones & Deadline Alerts
    goals = db.execute(
        'SELECT id, goal_name, target_amount, saved_amount, deadline, status FROM financial_goals WHERE user_id = ?',
        (user_id,)
    ).fetchall()

    for goal in goals:
        target = float(goal['target_amount'] or 0)
        saved = float(goal['saved_amount'] or 0)
        pct = (saved / target * 100) if target > 0 else 0
        if pct >= 50 and goal['status'] != 'Completed':
            title = f'Goal Milestone: {goal["goal_name"]}'
            if not _notification_exists(db, user_id, title, window_days=14):
                db.execute(
                    'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '
                    'VALUES (?, ?, ?, ?, 0, ?)',
                    (
                        user_id,
                        'goal',
                        title,
                        f'Goal "{goal["goal_name"]}" reached {pct:.0f}% milestone ({format_currency(saved)} saved of {format_currency(target)}).',
                        now.strftime('%Y-%m-%d %H:%M:%S'),
                    )
                )

        deadline_text = goal['deadline']
        try:
            deadline = datetime.strptime(deadline_text, '%Y-%m-%d').date() if deadline_text else None
        except ValueError:
            deadline = None
        if deadline is not None and goal['status'] != 'Completed':
            days_left = (deadline - now.date()).days
            if 0 <= days_left <= 7:
                title = 'Goal Deadline Approaching'
                if not _notification_exists(db, user_id, title, window_days=7):
                    db.execute(
                        'INSERT INTO notifications (user_id, type, title, message, is_read, created_at) '
                        'VALUES (?, ?, ?, ?, 0, ?)',
                        (
                            user_id,
                            'goal',
                            title,
                            f'Your goal "{goal["goal_name"]}" is due in {days_left} day(s).',
                            now.strftime('%Y-%m-%d %H:%M:%S'),
                        )
                    )

    db.commit()


def calculate_reports_analytics(user_id):
    db = get_db()
    now = datetime.now()
    current_month_key = now.strftime('%Y-%m')
    
    monthly_expenses, monthly_tx_count = calculate_total_expenses(user_id, current_month_key)
    
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
        'monthly_spending': monthly_expenses,
        'total_spent': monthly_expenses,
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

    total_expenses, transaction_count = calculate_total_expenses(user_id, current_month_key)
    remaining_budget = calculate_remaining_budget(monthly_budget, total_expenses)
    budget_utilization = calculate_budget_utilization(total_expenses, monthly_budget)
    budget_status = calculate_budget_status(monthly_budget, budget_utilization)

    db = get_db()

    today_str = now.strftime('%Y-%m-%d')
    today_row = db.execute(
        'SELECT COALESCE(SUM(amount), 0) AS today_total FROM expenses WHERE user_id = ? AND expense_date = ?',
        (user_id, today_str)
    ).fetchone()
    today_expenses = round(today_row['today_total'] or 0.0, 2)

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
        'monthly_budget': monthly_budget,
        'total_expenses': total_expenses,
        'today_expenses': today_expenses,
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
    now = datetime.now()
    insights = [
        {
            'title': 'Review recurring costs',
            'description': 'Take a quick look at your monthly subscriptions and see if any recurring bills can be reduced.'
        },
        {
            'title': 'Boost your savings',
            'description': 'Set aside a fixed percentage of your income each month to build your emergency fund.'
        },
        {
            'title': 'Keep track of due goals',
            'description': 'Review your active goals and make sure deadlines are still realistic.'
        },
    ]
    return insights


def calculate_month_over_month_trends(user_id):
    """Calculate MoM comparisons for expenses, transactions, budget utilization, and portfolio value."""
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
    
    exp_pct = round(((curr_total - prev_total) / prev_total * 100), 1) if prev_total > 0 else 0.0
    exp_direction = 'down' if exp_pct <= 0 else 'up'
    exp_color = '#34D399' if exp_pct <= 0 else '#F87171'  # Lower spending is positive

    curr_cnt = curr_exp_row['count'] or 0
    prev_cnt = prev_exp_row['count'] or 0
    tx_pct = round(((curr_cnt - prev_cnt) / prev_cnt * 100), 1) if prev_cnt > 0 else 0.0

    return {
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
    """Aggregate recent events across expenses, goals, investments, and notifications into grouped timeline buckets."""
    db = get_db()
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    yesterday_str = (now - __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d')
    week_start_str = (now - __import__('datetime').timedelta(days=now.weekday())).strftime('%Y-%m-%d')

    events = []

    # 1. Recent Expenses
    exp_rows = [dict(r) for r in db.execute(
        'SELECT id, description, category, amount, expense_date, created_at FROM expenses WHERE user_id = ? ORDER BY created_at DESC LIMIT 15',
        (user_id,)
    ).fetchall()]
    for e in exp_rows:
        date_val = e['expense_date'] or (e['created_at'][:10] if e['created_at'] else today_str)
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

    # 2. Goals
    goal_rows = [dict(r) for r in db.execute(
        'SELECT id, goal_name, target_amount, saved_amount, status, created_at FROM financial_goals WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()]
    for g in goal_rows:
        date_val = g['created_at'][:10] if g['created_at'] else today_str
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

    # 3. Investments
    inv_rows = [dict(r) for r in db.execute(
        'SELECT * FROM investments WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        (user_id,)
    ).fetchall()]
    for i in inv_rows:
        date_val = i['created_at'][:10] if i['created_at'] else today_str
        asset_title = i.get('name') or i.get('asset_name') or i.get('investment_type') or 'Investment'
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
    events.sort(key=lambda x: x['timestamp'], reverse=True)

    # Bucket events
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
    """AI Prediction Engine: Forecast next month expenses, savings, overrun probability, and health score."""
    db = get_db()
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    
    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else 50000.0
    
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = max(1, now.day)
    run_rate = (total_exp / days_elapsed) * days_in_month
    
    next_expenses = round(run_rate * 1.03, 2)
    next_savings  = max(0.0, budget_amt - next_expenses)
    
    overrun_prob = min(98, max(5, int((run_rate / budget_amt) * 80))) if budget_amt > 0 else 50
    health = calculate_health_score_detailed(user_id)
    forecast_health = min(100, max(10, health['score'] + (5 if overrun_prob < 50 else -8)))
    
    portfolio = calculate_portfolio_metrics(user_id)
    proj_growth = round(portfolio['current_value'] * 1.08, 2)

    return {
        'next_month_expenses': {
            'value': next_expenses,
            'confidence': 92,
            'reason': f'Based on current daily velocity of ₹{total_exp/days_elapsed:.0f}/day extrapolated across {days_in_month} days.',
            'recommendation': 'Limit discretionary dining and shopping during the final week of the month.'
        },
        'expected_savings': {
            'value': next_savings,
            'confidence': 88,
            'reason': f'Projected buffer between ₹{budget_amt:,.0f} budget baseline and run-rate expenditure.',
            'recommendation': 'Set up an automated SIP transfer for 60% of projected surplus.'
        },
        'overrun_probability': {
            'value': overrun_prob,
            'confidence': 95,
            'reason': f'Current spending utilization is operating at {run_rate/budget_amt*100:.1f}% of monthly ceiling.',
            'recommendation': 'Critical alert: Pause non-essential purchases if spending reaches 90% before day 25.'
        },
        'forecast_health_score': {
            'value': forecast_health,
            'confidence': 90,
            'reason': f"Projected change of {forecast_health - health['score']:+d} pts based on budget compliance trajectory.",
            'recommendation': 'Maintain current daily burn rate to lock in score gain.'
        },
        'portfolio_growth_projection': {
            'value': proj_growth,
            'confidence': 85,
            'reason': 'Estimated 8.0% annual yield compounding over 12 months.',
            'recommendation': 'Reinvest dividend payouts to accelerate compound accumulation.'
        }
    }


def calculate_investment_advisor_metrics(user_id):
    """AI Investment Advisor Engine: Evaluates portfolio diversification, risk score, asset allocation, and volatility."""
    db = get_db()
    portfolio = calculate_portfolio_metrics(user_id)
    total_val = portfolio['current_value']
    
    rows = db.execute(
        'SELECT investment_type, SUM(quantity * current_price) AS type_val FROM investments WHERE user_id = ? GROUP BY investment_type',
        (user_id,)
    ).fetchall()
    
    type_counts = len(rows)
    type_alloc = []
    for r in rows:
        val = float(r['type_val'] or 0)
        pct = (val / total_val * 100) if total_val > 0 else 0
        type_alloc.append({'type': r['investment_type'], 'value': val, 'pct': round(pct, 1)})
        
    if type_counts >= 4:
        div_score = 92
        risk_level = 'Low'
    elif type_counts >= 2:
        div_score = 75
        risk_level = 'Moderate'
    elif total_val > 0:
        div_score = 45
        risk_level = 'High'
    else:
        div_score = 30
        risk_level = 'Moderate'
        
    exp_return = 10.5 if type_counts >= 3 else 7.5
    volatility = 'Low (8.2%)' if div_score >= 80 else 'Moderate (14.5%)'
    
    suggestions = []
    if type_counts < 2 and total_val > 0:
        suggestions.append('Portfolio is concentrated in a single asset type. Diversify into Mutual Funds or Fixed Deposits to hedge market risk.')
    elif type_counts >= 3:
        suggestions.append('Asset allocation is well-balanced across multiple instruments. Maintain periodic quarterly rebalancing.')
    else:
        suggestions.append('Initiate regular monthly equity index investments to build compound portfolio wealth.')

    return {
        'diversification_score': div_score,
        'risk_score': risk_level,
        'expected_return_pct': exp_return,
        'volatility': volatility,
        'asset_allocation': type_alloc,
        'suggestions': suggestions
    }


def calculate_coaching_insights(user_id):
    """Personal Financial Coach Engine: Generates morning guidance, evening recap, and weekly challenge."""
    now = datetime.now()
    month_key = now.strftime('%Y-%m')
    total_exp, tx_cnt = calculate_total_expenses(user_id, month_key)
    budget_row = get_monthly_budget_row(user_id, now.strftime('%B'), now.year)
    budget_amt = float(budget_row['amount']) if budget_row and budget_row['amount'] else 50000.0
    
    rem_budget = max(0.0, budget_amt - total_exp)
    days_left = calendar.monthrange(now.year, now.month)[1] - now.day + 1
    daily_allowance = round(rem_budget / max(1, days_left), 0)

    morning_coach = {
        'title': '🌅 Morning Financial Focus',
        'target_budget': f'₹{daily_allowance:,.0f}',
        'advice': f'Your recommended safe spending allowance for today is ₹{daily_allowance:,.0f} to stay within your monthly ceiling.'
    }
    
    evening_coach = {
        'title': '🌆 Evening Spending Recap',
        'spent_today': f'₹{total_exp / max(1, now.day):,.0f}',
        'remaining_budget': f'₹{rem_budget:,.0f}',
        'advice': f'You have ₹{rem_budget:,.0f} remaining for the final {days_left} day(s) of this budget cycle.'
    }

    weekly_coach = {
        'title': '🎯 Weekly Financial Challenge',
        'challenge': 'Zero Discretionary Dining Day',
        'description': 'Prepare all meals at home for 2 consecutive days to save an estimated ₹1,200 towards your savings goal.'
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
            'description': 'Active FinSight intelligence user streak'
        }
    ]
    return badges


def calculate_goal_optimizer_metrics(user_id):
    """Goal Optimizer Engine: Computes goal completion probabilities and contribution targets."""
    goals = calculate_goals_summary(user_id)
    total_saved = goals['total_saved']
    total_target = goals['total_target']
    
    completion_prob = min(98, max(20, int((total_saved / total_target * 100)))) if total_target > 0 else 75
    rem_target = max(0.0, total_target - total_saved)
    sug_monthly = round(rem_target / 6, 0) if rem_target > 0 else 1500
    
    return {
        'completion_probability': completion_prob,
        'suggested_monthly_contribution': sug_monthly,
        'days_remaining': 180,
        'expected_completion_date': 'Dec 2026',
        'success_probability': min(98, completion_prob + 10)
    }


# =========================================================================
# Milestone 4 — PDF & Excel Generation Services
# =========================================================================

def generate_pdf_report_bytes(user_id, month_key):
    """Generates a professional financial statement PDF byte buffer using ReportLab."""
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
    elements.append(Paragraph("FinSight — Executive Financial Statement", title_style))
    elements.append(Paragraph(f"Prepared for: <b>{user['name']}</b> | Statement Period: <b>{report['month_label']}</b> | Generated: <b>{datetime.now().strftime('%Y-%m-%d %H:%M')}</b>", subtitle_style))
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#10B981'), spaceAfter=12))

    # Executive Summary KPI Table
    elements.append(Paragraph("1. Executive Financial Summary", section_heading))
    kpi_data = [
        [Paragraph("<b>Financial Metric</b>", cell_bold), Paragraph("<b>Value</b>", cell_bold), Paragraph("<b>Executive Context</b>", cell_bold)],
        [Paragraph("Monthly Outflow", cell_style), Paragraph(f"₹{report['total_expenses']:,.2f}", cell_bold), Paragraph(f"{report['transaction_count']} logged transactions", cell_style)],
        [Paragraph("Monthly Budget Limit", cell_style), Paragraph(f"₹{(report['monthly_budget'] or 0):,.2f}", cell_bold), Paragraph(f"Utilization: {report['budget_utilization'] or 0:.1f}%", cell_style)],
        [Paragraph("Remaining Allocation Buffer", cell_style), Paragraph(f"₹{(report['remaining_budget'] or 0):,.2f}", cell_bold), Paragraph("Available spending cap", cell_style)],
        [Paragraph("Financial Health Score", cell_style), Paragraph(f"<b>{health['score']}/100</b>", cell_bold), Paragraph(health['label'], cell_style)],
        [Paragraph("Portfolio Current Valuation", cell_style), Paragraph(f"₹{portfolio['current_value']:,.2f}", cell_bold), Paragraph(f"Net Gain/Loss: ₹{portfolio['profit_loss']:,.2f}", cell_style)],
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
    elements.append(Paragraph("FinSight Personal Finance & Investment Intelligence Platform — Confidential Statement", subtitle_style))

    doc.build(elements)
    return buffer.getvalue()


def generate_excel_report_bytes(user_id, month_key):
    """Generates a professional multi-sheet Excel workbook byte buffer using openpyxl."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
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

    ws1['A1'] = "FinSight Executive Financial Statement"
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
        ["Total Monthly Outflow", report['total_expenses'], "Logged transactions"],
        ["Monthly Budget Ceiling", report['monthly_budget'] or 0, "Set monthly limit"],
        ["Remaining Allocation Buffer", report['remaining_budget'] or 0, "Available allocation"],
        ["Budget Utilization", (report['budget_utilization'] or 0) / 100.0, "Percent of ceiling"],
        ["Financial Health Score", health['score'], health['label']],
        ["Portfolio Current Valuation", portfolio['current_value'], f"Invested: {portfolio['total_invested']}"],
        ["Unrealized Capital P&L", portfolio['profit_loss'], "Market net gain/loss"],
        ["Goal Savings Progress", goals['total_saved'], f"Target: {goals['total_target']}"],
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

    # Sheet 3: Investments
    ws3 = wb.create_sheet(title="Investments")
    ws3.views.sheetView[0].showGridLines = True
    ws3.append(["Asset Name", "Asset Type", "Broker", "Purchase Date", "Quantity", "Purchase Price", "Current Price", "Invested Capital", "Current Valuation", "Gain/Loss"])
    for col in range(1, 11):
        cell = ws3.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    inv_rows = db.execute("SELECT investment_name, investment_type, broker, purchase_date, quantity, purchase_price, current_price FROM investments WHERE user_id = ?", (user_id,)).fetchall()
    for ir in inv_rows:
        inv_cap = ir['quantity'] * ir['purchase_price']
        cur_val = ir['quantity'] * ir['current_price']
        ws3.append([ir['investment_name'], ir['investment_type'], ir['broker'], ir['purchase_date'], ir['quantity'], ir['purchase_price'], ir['current_price'], inv_cap, cur_val, cur_val - inv_cap])

    # Sheet 4: Financial Goals
    ws4 = wb.create_sheet(title="Financial Goals")
    ws4.views.sheetView[0].showGridLines = True
    ws4.append(["Goal Name", "Goal Type", "Priority", "Target Amount", "Saved Amount", "Remaining Amount", "Deadline", "Status"])
    for col in range(1, 9):
        cell = ws4.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font

    goal_rows = db.execute("SELECT goal_name, goal_type, priority, target_amount, saved_amount, deadline, status FROM financial_goals WHERE user_id = ?", (user_id,)).fetchall()
    for gr in goal_rows:
        ws4.append([gr['goal_name'], gr['goal_type'], gr['priority'], gr['target_amount'], gr['saved_amount'], max(0.0, gr['target_amount'] - gr['saved_amount']), gr['deadline'], gr['status']])

    # Auto-adjust column widths
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


