import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

SERVICE_ACCOUNT_FILE = 'service_account.json'
SHEET_ID = '1nVkk8WJ3AHuPdPO1RYYEbGmJzGUMqdfQp9L1LrLmssQ'

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)

DATE_FMT = '%d/%m/%Y'

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, DATE_FMT)
    except Exception:
        return None

def get_users():
    users_ws = sh.worksheet('Users')
    return users_ws.get_all_records()

def get_proposals():
    approvals_ws = sh.worksheet('Approvals')
    return approvals_ws.get_all_records(), approvals_ws

def get_proposal_log():
    log_ws = sh.worksheet('Proposal Log')
    return log_ws.get_all_records(), log_ws

def get_sales_cpfs():
    sales_ws = sh.worksheet('Sales')
    sales = sales_ws.get_all_records()
    return set(s['Cliente_cpf'] for s in sales)

def update_proposal_row(approvals_ws, row_idx, proposal):
    approvals_ws.update(f'A{row_idx}:J{row_idx}', [
        [proposal['Origem_empresa'], proposal['Origem_Detalhe'], proposal['Proposta_Numero'], proposal['Proposta_Data'],
         proposal['Usuario'], proposal['Cliente_nome'], proposal['Cliente_cpf'], proposal['Veiculo_descricao'], proposal['Valor_liberado'], proposal['Status']]
    ])

def add_proposal_log(log_ws, proposta_numero, username):
    log_ws.append_row([
        proposta_numero,
        datetime.now().strftime(DATE_FMT),
        username
    ])

def main():
    approvals_ws = sh.worksheet('Approvals')
    sales_ws = sh.worksheet('Sales')
    users_ws = sh.worksheet('Users')
    log_ws = sh.worksheet('Proposal Log')

    approvals_data = approvals_ws.get_all_values()
    sales_data = sales_ws.get_all_values()
    users_data = users_ws.get_all_values()
    log_data = log_ws.get_all_values()

    header = approvals_data[0]
    approvals_rows = approvals_data[1:]
    sales_cpfs = set(row[1] for row in sales_data[1:])
    users_by_username = {row[2]: {'state': row[3]} for row in users_data[1:]}
    users_by_state = {}
    for row in users_data[1:]:
        users_by_state.setdefault(row[3], []).append(row[2])

    # Build log of previous handlers and their assignment dates
    handlers_by_proposal = {}
    for row in log_data[1:]:
        propNum, date_str, username = row
        if propNum not in handlers_by_proposal:
            handlers_by_proposal[propNum] = []
        handlers_by_proposal[propNum].append((username, parse_date(date_str)))

    statusCol = header.index('Status')
    usuarioCol = header.index('Usuario')
    propostaDataCol = header.index('Proposta_Data')
    propostaNumCol = header.index('Proposta_Numero')
    clienteCpfCol = header.index('Cliente_cpf')

    rr_pointers = {}  # state -> last assigned username
    updated_rows = []
    updated_indices = []
    log_updates = []

    now = datetime.now()

    for i, row in enumerate(approvals_rows):
        status = row[statusCol]
        usuario = row[usuarioCol]
        proposta_data = parse_date(row[propostaDataCol])
        proposta_num = row[propostaNumCol]
        cpf = row[clienteCpfCol]
        changed = False
        print(f"Processing proposal {proposta_num} (CPF: {cpf})")

        # NEW RULE: If approval date is more than 7 days ago, go directly to public pool
        if proposta_data and (now - proposta_data).days > 7:
            if status != 'Public':
                row[statusCol] = 'Public'
                row[usuarioCol] = ''
                log_updates.append([proposta_num, now.strftime(DATE_FMT), 'public'])
                changed = True
                print(f"  -> Approval date > 7 days, moved directly to Public")
        else:
            # Step 1: Sold/Not Sold
            if cpf in sales_cpfs:
                if status != 'Sold':
                    row[statusCol] = 'Sold'
                    changed = True
                    print(f"  -> Marked as Sold")
            else:
                if status != 'Not Sold':
                    row[statusCol] = 'Not Sold'
                    changed = True
                    print(f"  -> Marked as Not Sold")

            # Step 2: Only process Not Sold for reassignment
            if row[statusCol] == 'Not Sold':
                # Get the log for this proposal, sorted by date
                handlers = sorted(handlers_by_proposal.get(proposta_num, []), key=lambda x: x[1] or now)
                already_handled = [h[0] for h in handlers if h[0] != 'public']
                num_handlers = len(already_handled)
                last_handler, last_date = (usuario, proposta_data)
                if handlers:
                    last_handler, last_date = handlers[-1]
                if not last_date:
                    last_date = proposta_data
                days_since_assignment = (now - last_date).days if last_date else 0
                print(f"  -> Handlers: {already_handled}, num_handlers: {num_handlers}, days_since_assignment: {days_since_assignment}")

                # Determine allowed days for the current handler
                allowed_days = 3 if num_handlers == 0 else 1

                if days_since_assignment >= allowed_days:
                    user_state = users_by_username.get(usuario, {}).get('state')
                    if user_state:
                        eligible_users = [
                            u for u in users_by_state[user_state]
                            if u != usuario and u not in already_handled
                        ]
                        if num_handlers < 3 and eligible_users:
                            last_assigned = rr_pointers.get(user_state)
                            idx = eligible_users.index(last_assigned) if last_assigned in eligible_users else -1
                            next_idx = (idx + 1) % len(eligible_users)
                            new_user = eligible_users[next_idx]
                            row[usuarioCol] = new_user
                            row[propostaDataCol] = now.strftime(DATE_FMT)
                            log_updates.append([proposta_num, now.strftime(DATE_FMT), new_user])
                            rr_pointers[user_state] = new_user
                            changed = True
                            print(f"  -> Reassigned to {new_user}")
                        else:
                            row[statusCol] = 'Public'
                            row[usuarioCol] = ''
                            log_updates.append([proposta_num, now.strftime(DATE_FMT), 'public'])
                            changed = True
                            print(f"  -> Moved to Public")

        if changed:
            updated_row = [str(val) for val in row]
            updated_rows.append(updated_row)
            updated_indices.append(i + 2)  # +2 for 1-based index and header row

    print("Rows to update:", len(updated_rows))
    for i, row in enumerate(updated_rows):
        print(f"Row {updated_indices[i]}: {row}")

    # Batch update Approvals using batch_update
    if updated_rows:
        requests = []
        for i, row_idx in enumerate(updated_indices):
            rng = f'A{row_idx}:J{row_idx}'
            requests.append({'range': rng, 'values': [updated_rows[i]]})
        import pprint
        pprint.pprint(requests)
        try:
            approvals_ws.batch_update(requests)
            print(f"Updated {len(updated_rows)} proposals.")
        except Exception as e:
            print(f"Error during batch_update: {e}")
    else:
        print("No rows to update.")

    # Batch append to Proposal Log
    if log_updates:
        log_ws.append_rows(log_updates)
        print(f"Appended {len(log_updates)} log entries.")

if __name__ == '__main__':
    main() 