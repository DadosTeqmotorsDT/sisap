from flask import Flask, render_template, request, redirect, url_for, session, flash
from sheets_service import get_user_by_login, get_assigned_proposals, get_public_proposals, log_login, get_login_log, get_unique_public_origem_empresa
from datetime import datetime, date
import os
from decimal import Decimal, InvalidOperation

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.template_filter('currencyformat')
def currencyformat(value):
    try:
        # Convert to float, handling both string and numeric input
        f_value = float(str(value).replace('.', '').replace(',', '.'))
        test = f_value / 1000
        
        if test <= 99:
            val = f_value
        else:
            val = f_value / 100
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value  # Return original value if conversion fails

@app.template_filter('cpf_format')
def cpf_format(value):
    s = str(value).zfill(11)
    if len(s) == 11:
        return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
    return value

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_name = request.form['login']
        password = request.form['password']
        user = get_user_by_login(login_name)
        if user and user['password'] == password:
            session['user'] = user
            log_login(login_name)
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Usuário ou senha inválidos')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = session['user']
    assigned = get_assigned_proposals(user)
    public = get_public_proposals(user)

    # Obtenção e parsing das datas de filtro (ISO format)
    public_date_start = request.args.get('public_date_start')
    public_date_end = request.args.get('public_date_end')
    public_origem_empresa = request.args.get('public_origem_empresa', '')
    start_date = None
    end_date = None
    try:
        if public_date_start:
            start_date = datetime.strptime(public_date_start, '%Y-%m-%d').date()
        if public_date_end:
            end_date = datetime.strptime(public_date_end, '%Y-%m-%d').date()
    except ValueError:
        # Se parsing falhar, manter como None (sem filtro para essa data)
        flash('Formato de data inválido para filtro', 'warning')

    # Função de filtro unificada, convertendo Proposta_Data (dd/mm/YYYY) para date
    def in_range(p):
        raw = p.get('Proposta_Data', '')
        if not raw:
            return False
        try:
            prop_date = datetime.strptime(raw, '%d/%m/%Y').date()
        except ValueError:
            return False
        if start_date and prop_date < start_date:
            return False
        if end_date and prop_date > end_date:
            return False
        return True

    if start_date or end_date:
        public = [p for p in public if in_range(p)]

    if public_origem_empresa:
        public = [p for p in public if public_origem_empresa.lower() in str(p.get('Origem_Detalhe', '')).lower()]

    message = request.args.get('message')
    public_origem_empresa_options = get_unique_public_origem_empresa()
    return render_template('dashboard.html', user=user, assigned=assigned, public=public, message=message, public_origem_empresa=public_origem_empresa, public_origem_empresa_options=public_origem_empresa_options)

@app.route('/login_log')
def login_log():
    if 'user' not in session:
        return redirect(url_for('login'))
    log_entries = get_login_log()
    return render_template('login_log.html', user=session['user'], log_entries=log_entries)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
