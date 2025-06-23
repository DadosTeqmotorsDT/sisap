import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json
from dotenv import load_dotenv

load_dotenv()

SHEET_ID = '1nVkk8WJ3AHuPdPO1RYYEbGmJzGUMqdfQp9L1LrLmssQ'

info = json.loads(os.environ["SHEETS_CREDS"])

# Gera credenciais a partir do dict
creds = Credentials.from_service_account_info(
    info,
    scopes=[
       'https://www.googleapis.com/auth/spreadsheets',
       'https://www.googleapis.com/auth/drive'
    ]
)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)

def get_user_by_login(login):
    users_ws = sh.worksheet('Users')
    users = users_ws.get_all_records()
    for user in users:
        if user['login'] == login:
            return user
    return None

def get_assigned_proposals(user):
    approvals_ws = sh.worksheet('Approvals')
    proposals = approvals_ws.get_all_records()
    assigned = [
        p for p in proposals
        if p['Usuario'] == user['approval_table_username'] and p['Status'] not in ('Public', 'Sold')
    ]
    return assigned

def get_public_proposals(user):
    approvals_ws = sh.worksheet('Approvals')
    proposals = approvals_ws.get_all_records()
    public = [p for p in proposals if p['Status'] == 'Public']
    return public

def log_login(login):
    log_ws = sh.worksheet('Login Log')
    log_ws.append_row([login, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

def get_login_log():
    log_ws = sh.worksheet('Login Log')
    return log_ws.get_all_records() 