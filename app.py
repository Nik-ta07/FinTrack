from flask import Flask, render_template, request, redirect, url_for, send_from_directory, Response
import sqlite3
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'transactions.db')

# Ensure data directory exists
os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,
        category TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

# Ensure config table exists for budget

def init_config():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

init_config()

from datetime import datetime

@app.route('/budget', methods=['GET', 'POST'])
def budget():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if request.method == 'POST':
        budget = request.form['budget']
        c.execute('REPLACE INTO config (key, value) VALUES (?, ?)', ('monthly_budget', budget))
        conn.commit()
    c.execute('SELECT value FROM config WHERE key = ?', ('monthly_budget',))
    row = c.fetchone()
    current_budget = row[0] if row else ''
    conn.close()
    return render_template('budget.html', budget=current_budget)

@app.route('/', methods=['GET'])
def index():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    type_ = request.args.get('type')
    query = 'SELECT date, description, amount, type, category, id FROM transactions WHERE 1=1'
    params = []
    if start_date:
        query += ' AND date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND date <= ?'
        params.append(end_date)
    if category and category != 'All':
        query += ' AND category = ?'
        params.append(category)
    if type_ and type_ != 'All':
        query += ' AND type = ?'
        params.append(type_)
    query += ' ORDER BY date DESC'
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, params)
    transactions = c.fetchall()
    # Budget logic
    now = datetime.now()
    month_start = now.replace(day=1).strftime('%Y-%m-%d')
    c.execute('SELECT SUM(amount) FROM transactions WHERE type = ? AND date >= ? AND date <= ?',
              ('Expense', month_start, now.strftime('%Y-%m-%d')))
    total_expense = c.fetchone()[0] or 0
    c.execute('SELECT value FROM config WHERE key = ?', ('monthly_budget',))
    row = c.fetchone()
    budget = float(row[0]) if row and row[0] else None
    over_budget = budget is not None and total_expense > budget
    conn.close()
    categories = ['All', 'Food', 'Transport', 'Bills', 'Rent', 'Other']
    return render_template('index.html', transactions=transactions, start_date=start_date, end_date=end_date, category=category, categories=categories, budget=budget, total_expense=total_expense, over_budget=over_budget, type=type_)

@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        amount = float(request.form['amount'])
        type_ = request.form['type']
        category = request.form['category']
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO transactions (date, description, amount, type, category) VALUES (?, ?, ?, ?, ?)',
                  (date, description, amount, type_, category))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    return render_template('add.html')

@app.route('/edit/<int:transaction_id>', methods=['GET', 'POST'])
def edit(transaction_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if request.method == 'POST':
        date = request.form['date']
        description = request.form['description']
        amount = float(request.form['amount'])
        type_ = request.form['type']
        category = request.form['category']
        c.execute('UPDATE transactions SET date=?, description=?, amount=?, type=?, category=? WHERE id=?',
                  (date, description, amount, type_, category, transaction_id))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    else:
        c.execute('SELECT id, date, description, amount, type, category FROM transactions WHERE id=?', (transaction_id,))
        transaction = c.fetchone()
        conn.close()
        if not transaction:
            return redirect(url_for('index'))
        categories = ['Food', 'Transport', 'Bills', 'Rent', 'Other']
        return render_template('edit.html', transaction=transaction, categories=categories)

@app.route('/delete/<int:transaction_id>', methods=['POST'])
def delete(transaction_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id=?', (transaction_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/charts')
def charts():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('SELECT * FROM transactions', conn)
    conn.close()
    pie_path = None
    line_path = None
    if not df.empty:
        # Pie chart: Expenses by category
        expenses = df[df['type'] == 'Expense']
        if not expenses.empty:
            pie = expenses.groupby('category')['amount'].sum()
            plt.figure(figsize=(5,5))
            pie.plot.pie(autopct='%1.1f%%', startangle=90)
            plt.title('Spending by Category')
            pie_path = os.path.join('static', 'pie.png')
            plt.savefig(os.path.join(os.path.dirname(__file__), pie_path), bbox_inches='tight')
            plt.close()
        # Line chart: Monthly income vs expenses
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.to_period('M')
        monthly = df.groupby(['month', 'type'])['amount'].sum().unstack(fill_value=0)
        plt.figure(figsize=(7,4))
        if 'Income' in monthly:
            plt.plot(monthly.index.astype(str), monthly['Income'], label='Income', marker='o')
        if 'Expense' in monthly:
            plt.plot(monthly.index.astype(str), monthly['Expense'], label='Expense', marker='o')
        plt.title('Monthly Income vs Expenses')
        plt.xlabel('Month')
        plt.ylabel('Amount')
        plt.legend()
        plt.xticks(rotation=45)
        line_path = os.path.join('static', 'line.png')
        plt.tight_layout()
        plt.savefig(os.path.join(os.path.dirname(__file__), line_path))
        plt.close()
    return render_template('charts.html', pie_chart=pie_path, line_chart=line_path)

@app.route('/export')
def export():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT date, description, amount, type, category FROM transactions ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    def generate():
        yield 'Date,Description,Amount,Type,Category\n'
        for row in rows:
            yield ','.join([str(x).replace(',', ' ') for x in row]) + '\n'
    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=transactions.csv"})

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 