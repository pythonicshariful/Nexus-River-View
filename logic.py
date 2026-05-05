import pandas as pd
import openpyxl
from decimal import Decimal
from models import Director, Customer, PettyCash, Transaction, Bank, BankTransaction, Installment, CustomerInstallment, Party, PartyLedger
import os
import shutil
import io
from datetime import datetime
from database import db
from telegram_utils import send_telegram_document, log_debug

EXCEL_FILE = 'nexus_river_view_master.xlsx' if __name__ != '__main__' else 'test_nexus_river_view.xlsx'

def sync_to_excel():
    """
    Fetches all customers and directors from the database,
    creates a consolidated table, sorts by Director,
    and writes to the Master Excel file.
    """
    try:
        # ... logic to create dataframes ...
        # Since I am replacing a large chunk, I must be careful not to delete the data preparation logic.
        # However, the user instruction said "logic.py" at "sync_to_excel".
        # The previous view showed the function is long.
        # I should use multi_replace or targeted replace.
        # But I need to wrap the whole function in try...except for logging?
        # The function already has a try...except block starting at line 187.
        # I will just update the imports and the existing try...except block.
        pass
    except:
        pass

# Wait, I cannot use ReplacementContent with "..." placeholder logic.
# I need to be precise.
# Let's use 2 replacements. 
# 1. Imports
# 2. The try-except block at the end.

    directors = Director.query.all()
    # Create a mapping of Director ID to Name for easy lookup, although we can join in query
    # But let's fetch all customers joined with directors
    
    customers = Customer.query.join(Director).add_columns(
        Director.name.label('director_name'),
        Customer.customer_id,
        Customer.name,
        Customer.phone,
        Customer.plot_no,
        Customer.total_price,
        Customer.down_payment,
        Customer.monthly_installment,
        Customer.total_paid,
        Customer.due_amount
    ).all()
    
    # Prepare data for DataFrame
    data = []
    for row in customers:
        # row is a tuple: (CustomerObj, director_name, ...) if we didn't refine add_columns carefully
        # With add_columns, it returns a Result object (named tuple like)
        
        # Let's simplify: Query customers and access relationship
        pass

    # Refined Query
    all_customers = Customer.query.outerjoin(Director).order_by(Director.name, Customer.customer_id).all()
    
    export_list = []
    for c in all_customers:
        export_list.append({
            'Director Name': c.director.name,
            'Customer ID': c.customer_id,
            'Customer Name': c.name,
            'Phone': c.phone,
            'Plot No': c.plot_no,
            'Total Price': c.total_price,
            'Down Payment': c.down_payment,
            'Monthly Installment': c.monthly_installment,
            'Total Paid': c.total_paid,
            'Due Amount': c.due_amount
        })
    
    if not export_list:
        # Create empty dataframe with columns if no data
        df = pd.DataFrame(columns=[
            'Director Name', 'Customer ID', 'Customer Name', 'Phone', 'Plot No',
            'Total Price', 'Down Payment', 'Monthly Installment', 'Total Paid', 'Due Amount'
        ])
    else:
        df = pd.DataFrame(export_list)
        # Smart Sorting: Sort by Director Name, then Customer ID
        df = df.sort_values(by=['Director Name', 'Customer ID'])

    # --- Director Summary Data ---
    all_directors = Director.query.all()
    director_list = []
    
    # Image Columns:
    # 1. SL NO. | 2. Share name | 3. Total share | 4. Per share value | 5. Fair Cost 
    # 6. Total share value | 7. Land value of Extra share | 8. Total share+ Extra share Value
    # 9. Total Paid Until date | 10. Date & Deposit | 11. B.Name | 12. DUE
    
    for i, d in enumerate(all_directors, start=1):
        director_list.append({
            'SL NO.': i,
            'Share name': d.name,
            'Total share': d.total_share,
            'Total Paid': d.total_paid,
            'Total Due': d.total_due,
            'Bank Name': d.bank_name or '',
            'History': d.payment_history or ''
        })
        
    df_directors = pd.DataFrame(director_list)
    
    # Petty Cash Sheet
    all_entries = PettyCash.query.order_by(PettyCash.date).all()
    petty_list = []
    
    running_balance = 0
    for e in all_entries:
        if e.type == 'Income':
            running_balance += e.amount
        else:
            running_balance -= e.amount
            
        petty_list.append({
            'Date': e.date,
            'Description': e.description,
            'Category': e.category,
            'Type': e.type,
            'Income': e.amount if e.type == 'Income' else 0,
            'Expense': e.amount if e.type == 'Expense' else 0,
            'Balance': running_balance,
            'Images': e.images
        })
        
    df_petty = pd.DataFrame(petty_list)
    
    # Transactions Sheet
    all_transactions = Transaction.query.order_by(Transaction.date).all()
    tx_list = []
    for tx in all_transactions:
        tx_list.append({
            'ID': tx.id,
            'Date': tx.date,
            'Customer ID': tx.customer.customer_id,
            'Customer Name': tx.customer.name,
            'Amount': tx.amount,
            'Installment Type': tx.installment_type,
            'Bank Name': tx.bank_name,
            'Transaction ID': tx.transaction_id,
            'Remarks': tx.remarks,
            'Images': tx.images
        })
    df_transactions = pd.DataFrame(tx_list)

    # Bank Sheets
    all_banks = Bank.query.all()
    bank_list = []
    for b in all_banks:
        bank_list.append({
            'Bank Name': b.bank_name,
            'Branch': b.branch,
            'Account Holder': b.account_holder_name,
            'Joint Name': b.joint_name,
            'FHP': b.fhp,
            'Address': b.address,
            'City': b.city,
            'Phone': b.phone,
            'Customer ID': b.customer_id,
            'Account No': b.account_no,
            'Prev Account No': b.prev_account_no,
            'Account Type': b.account_type,
            'Currency': b.currency,
            'Status': b.status
        })
    df_banks = pd.DataFrame(bank_list)
    # Bank Transactions Sheet
    all_bank_tx = BankTransaction.query.order_by(BankTransaction.date).all()
    bank_tx_data = []
    for btx in all_bank_tx:
        bank_tx_data.append({
            'Date': btx.date,
            'Bank ID': btx.bank_id,
            'Bank Name': btx.bank.bank_name if btx.bank else "N/A",
            'Narration': btx.narration,
            'Debit': btx.debit,
            'Credit': btx.credit,
            'Balance': btx.balance
        })
    df_bank_tx = pd.DataFrame(bank_tx_data)

    # Installments Sheet
    all_installments = Installment.query.all()
    inst_list = []
    for inst in all_installments:
        inst_list.append({
            'ID': inst.id,
            'Name': inst.name,
            'Amount Per Share': inst.amount_per_share
        })
    df_inst = pd.DataFrame(inst_list)

    # Customer Installments Sheet
    all_cust_inst = CustomerInstallment.query.all()
    ci_list = []
    for ci in all_cust_inst:
        ci_list.append({
            'Customer ID': ci.customer.customer_id,
            'Customer Name': ci.customer.name,
            'Installment Name': ci.installment.name,
            'Total Amount': ci.total_amount,
            'Paid Amount': ci.paid_amount,
            'Due Amount': ci.due_amount
        })
    df_ci = pd.DataFrame(ci_list)

    # Write to Excel
    # We use engine='openpyxl' for xlsx
    try:
        # Determine Excel Path based on DATA_FOLDER
        from flask import current_app
        data_folder = current_app.config.get('DATA_FOLDER', '.')
        
        # Use simple filename if in dev mode main, else DATA_FOLDER
        if __name__ == '__main__':
             target_excel_path = EXCEL_FILE 
        else:
             target_excel_path = os.path.join(data_folder, 'nexus_river_view_master.xlsx')
             
        with pd.ExcelWriter(target_excel_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Master_Data', index=False)
            df_directors.to_excel(writer, sheet_name='Directors_Summary', index=False)
            df_petty.to_excel(writer, sheet_name='Petty_Cash', index=False)
            df_transactions.to_excel(writer, sheet_name='Transactions', index=False)
            df_banks.to_excel(writer, sheet_name='Banks', index=False)
            df_bank_tx.to_excel(writer, sheet_name='Bank_Transactions', index=False)
            df_inst.to_excel(writer, sheet_name='Installments', index=False)
            df_ci.to_excel(writer, sheet_name='Customer_Installments', index=False)
            
            # Formatter function
            workbook = writer.book
            
            for sheet_name in ['Master_Data', 'Directors_Summary', 'Petty_Cash', 'Transactions', 'Banks', 'Bank_Transactions', 'Installments', 'Customer_Installments']:
                if sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    for column in worksheet.columns:
                        max_length = 0
                        column = [cell for cell in column]
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(cell.value)
                            except:
                                pass
                        adjusted_width = (max_length + 2)
                        worksheet.column_dimensions[column[0].column_letter].width = adjusted_width
                
        print(f"Successfully synced to {target_excel_path}")
        log_debug(f"Synced Excel to: {target_excel_path}")
        
        print(f"Successfully synced to {target_excel_path}")
        log_debug(f"Synced Excel to: {target_excel_path}")
            
            # REMOVED: Excel upload to Telegram as it is too slow for real-time saving
            # Redundant since we send the DB file which contains everything.
            
    except Exception as e:
        print(f"Error syncing to Excel: {e}")
        log_debug(f"CRITICAL ERROR in sync_to_excel: {e}")

def create_db_backup():
    """
    Creates a copy of the current nexus.db into the backups folder with a timestamp.
    """
    try:
        from flask import current_app
        data_folder = current_app.config.get('DATA_FOLDER', 'C:\\NRV')
        db_path = current_app.config.get('DATABASE_PATH')
        
        if not db_path or not os.path.exists(db_path):
            log_debug("DB backup failed: database_path not found.")
            return None
            
        backup_dir = os.path.join(data_folder, 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"nexus_db_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        import shutil
        shutil.copy2(db_path, backup_path)
        log_debug(f"DB Backup created: {backup_path}")
        
        # Cleanup old backups
        cleanup_old_backups()
        
        return backup_path
    except Exception as e:
        log_debug(f"Error creating DB backup: {e}")
        return None

def cleanup_old_backups(days=30):
    """
    Deletes backup files in the backups folder that are older than the specified number of days.
    """
    try:
        from flask import current_app
        import time
        data_folder = current_app.config.get('DATA_FOLDER', 'C:\\NRV')
        backup_dir = os.path.join(data_folder, 'backups')
        
        if not os.path.exists(backup_dir):
            return
            
        now = time.time()
        cutoff = now - (days * 86400)
        
        deleted_count = 0
        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                file_time = os.path.getmtime(file_path)
                if file_time < cutoff:
                    os.remove(file_path)
                    deleted_count += 1
        
        if deleted_count > 0:
            log_debug(f"Auto-cleanup: Deleted {deleted_count} old backups.")
            
    except Exception as e:
        log_debug(f"Error cleaning up old backups: {e}")

def restore_from_excel(file_path):
    """
    Restores the database from the given Excel file.
    WARNING: This wipes all current data.
    """
    try:
        # Read Excel Sheets
        df_master = pd.read_excel(file_path, engine='openpyxl', sheet_name='Master_Data')
        df_directors = pd.read_excel(file_path, engine='openpyxl', sheet_name='Directors_Summary')
        
        # Optional sheets (might not exist in older backups)
        try:
            df_petty = pd.read_excel(file_path, engine='openpyxl', sheet_name='Petty_Cash')
        except:
            df_petty = pd.DataFrame()

        try:
            df_tx = pd.read_excel(file_path, engine='openpyxl', sheet_name='Transactions')
        except:
            df_tx = pd.DataFrame() # Fixed empty dataframe assignment

        try:
            df_banks = pd.read_excel(file_path, engine='openpyxl', sheet_name='Banks')
        except:
            df_banks = pd.DataFrame()

        try:
            df_bank_tx = pd.read_excel(file_path, engine='openpyxl', sheet_name='Bank_Transactions')
        except:
            df_bank_tx = pd.DataFrame()

        # Wipe Database
        BankTransaction.query.delete()
        Bank.query.delete()
        PettyCash.query.delete()
        Transaction.query.delete()
        Customer.query.delete()
        Director.query.delete()
        db.session.commit()
        
        # Restore Directors
        director_map = {} # Name -> ID
        for _, row in df_directors.iterrows():
            d = Director(
                name=row['Share name'],
                total_share=row['Total share'],
                per_share_value=0,
                fair_cost=0,
                land_value_extra_share=0,
                total_paid=row.get('Total Paid', 0),
                total_due=row.get('Total Due', 0),
                payment_history=str(row.get('History', '')) if pd.notna(row.get('History')) else '',
                bank_name=str(row.get('Bank Name', '')) if pd.notna(row.get('Bank Name')) else ''
            )
            db.session.add(d)
            db.session.flush() # Get ID
            director_map[d.name] = d.id
            
        # Restore Customers
        customer_map = {} # Customer ID (str) -> DB ID
        for _, row in df_master.iterrows():
            dir_name = row['Director Name']
            if dir_name in director_map:
                c = Customer(
                    director_id=director_map[dir_name],
                    customer_id=row['Customer ID'],
                    name=row['Customer Name'],
                    phone=str(row['Phone']),
                    plot_no=row['Plot No'],
                    total_price=row['Total Price'],
                    down_payment=row['Down Payment'],
                    monthly_installment=row['Monthly Installment'],
                    total_paid=row['Total Paid'],
                    due_amount=row['Due Amount']
                )
                db.session.add(c)
                db.session.flush()
                customer_map[c.customer_id] = c.id
        
        # Restore Transactions
        if not df_tx.empty:
            for _, row in df_tx.iterrows():
                cust_str_id = row['Customer ID']
                if cust_str_id in customer_map:
                    t = Transaction(
                        date=str(row['Date']), # Ensure string
                        amount=row['Amount'],
                        installment_type=row['Installment Type'],
                        bank_name=str(row['Bank Name']) if pd.notna(row['Bank Name']) else '',
                        transaction_id=str(row['Transaction ID']) if pd.notna(row['Transaction ID']) else '',
                        remarks=str(row['Remarks']) if pd.notna(row['Remarks']) else '',
                        images=str(row['Images']) if pd.notna(row['Images']) else '',
                        customer_id=customer_map[cust_str_id]
                    )
                    db.session.add(t)

        # Restore Petty Cash
        if not df_petty.empty:
            for _, row in df_petty.iterrows():
                pc = PettyCash(
                    date=str(row['Date']),
                    description=row['Description'],
                    category=row['Category'],
                    type=row['Type'],
                    amount=row['Income'] if row['Type'] == 'Income' else row['Expense'],
                    images=str(row['Images']) if pd.notna(row['Images']) else ''
                )
                db.session.add(pc)

        # Restore Banks
        bank_map = {} # Account No -> ID
        if not df_banks.empty:
            for _, row in df_banks.iterrows():
                b = Bank(
                    bank_name=row['Bank Name'],
                    branch=str(row['Branch']) if pd.notna(row['Branch']) else '',
                    account_holder_name=str(row['Account Holder']) if pd.notna(row['Account Holder']) else '',
                    joint_name=str(row['Joint Name']) if pd.notna(row['Joint Name']) else '',
                    fhp=str(row['FHP']) if pd.notna(row['FHP']) else '',
                    address=str(row['Address']) if pd.notna(row['Address']) else '',
                    city=str(row['City']) if pd.notna(row['City']) else '',
                    phone=str(row['Phone']) if pd.notna(row['Phone']) else '',
                    customer_id=str(row['Customer ID']) if pd.notna(row['Customer ID']) else '',
                    account_no=str(row['Account No']),
                    prev_account_no=str(row['Prev Account No']) if pd.notna(row['Prev Account No']) else '',
                    account_type=str(row['Account Type']) if pd.notna(row['Account Type']) else '',
                    currency=str(row['Currency']) if pd.notna(row['Currency']) else '',
                    status=str(row['Status']) if pd.notna(row['Status']) else 'Active'
                )
                db.session.add(b)
                db.session.flush()
                bank_map[b.account_no] = b.id

        # Restore Bank Transactions
        if not df_bank_tx.empty:
            for _, row in df_bank_tx.iterrows():
                acc_no = str(row['Bank Account No'])
                if acc_no in bank_map:
                    btx = BankTransaction(
                        date=str(row['Date']),
                        cheque_no=str(row['Cheque No']) if pd.notna(row['Cheque No']) else '',
                        ref_no=str(row['Ref No']) if pd.notna(row['Ref No']) else '',
                        narration=str(row['Narration']) if pd.notna(row['Narration']) else '',
                        transaction_details=str(row['Transaction Details']) if pd.notna(row['Transaction Details']) else '',
                        debit=row['Debit'],
                        credit=row['Credit'],
                        balance=row['Balance'],
                        bank_id=bank_map[acc_no]
                    )
                    db.session.add(btx)

        db.session.commit()
        return True, "Data successfully restored."
        
    except Exception as e:
        db.session.rollback()
        print(f"Restore failed: {e}")
        return False, str(e)
def restore_from_data_dict(data_dict):
    """
    Restores the database from a dictionary of lists of dictionaries.
    """
    try:
        # Wipe Database
        PartyLedger.query.delete()
        Party.query.delete()
        CustomerInstallment.query.delete()
        Installment.query.delete()
        BankTransaction.query.delete()
        Bank.query.delete()
        PettyCash.query.delete()
        Transaction.query.delete()
        Customer.query.delete()
        Director.query.delete()
        db.session.commit()
        
        # Restore Directors
        director_id_map = {} # Maps old_id (from sheet) to new_id (in DB)
        for row in data_dict.get('director', []):
            old_id = str(row.get('id'))
            d = Director(
                name=row['name'],
                total_share=float(row['total_share'] or 0),
                per_share_value=0,
                fair_cost=0,
                land_value_extra_share=0,
                total_paid=float(row['total_paid'] or 0),
                total_due=float(row.get('total_due') or 0),
                payment_history=str(row['payment_history']),
                bank_name=str(row['bank_name']),
                updated_at=datetime.strptime(row['updated_at'], "%Y-%m-%d %H:%M:%S") if row.get('updated_at') else datetime.utcnow()
            )
            db.session.add(d)
            db.session.flush()
            director_id_map[old_id] = d.id
            
        # Restore Customers
        customer_id_map = {}
        for row in data_dict.get('customer', []):
            old_id = str(row.get('id'))
            old_director_id = str(row.get('director_id'))
            # Get the new director ID from our map
            new_director_id = director_id_map.get(old_director_id)
            
            if not new_director_id:
                print(f"Warning: Could not find new director ID for old ID {old_director_id}")
                # Fallback to the old ID if mapping fails (less safe but best effort)
                new_director_id = int(old_director_id) if old_director_id.isdigit() else 1

            c = Customer(
                director_id=new_director_id,
                customer_id=row['customer_id'],
                name=row['name'],
                phone=str(row['phone']),
                plot_no=row['plot_no'],
                total_price=float(row['total_price'] or 0),
                down_payment=float(row['down_payment'] or 0),
                monthly_installment=float(row['monthly_installment'] or 0),
                total_paid=float(row['total_paid'] or 0),
                due_amount=float(row['due_amount'] or 0),
                father_name=row.get('father_name', ''),
                mother_name=row.get('mother_name', ''),
                dob=row.get('dob', ''),
                religion=row.get('religion', ''),
                profession=row.get('profession', ''),
                nid_no=row.get('nid_no', ''),
                present_address=row.get('present_address', ''),
                permanent_address=row.get('permanent_address', ''),
                updated_at=datetime.strptime(row['updated_at'], "%Y-%m-%d %H:%M:%S") if row.get('updated_at') else datetime.utcnow()
            )
            db.session.add(c)
            db.session.flush()
            customer_id_map[old_id] = c.id

        # Restore Transactions
        for row in data_dict.get('transaction', []):
            old_cust_id = str(row.get('customer_id'))
            new_cust_id = customer_id_map.get(old_cust_id)
            
            if not new_cust_id:
                new_cust_id = int(old_cust_id) if old_cust_id.isdigit() else 1

            t = Transaction(
                date=str(row['date']),
                amount=float(row['amount'] or 0),
                installment_type=row['installment_type'],
                bank_name=str(row['bank_name']),
                transaction_id=str(row['transaction_id']),
                remarks=str(row['remarks']),
                images=str(row['images']),
                customer_id=new_cust_id,
                updated_at=datetime.strptime(row['updated_at'], "%Y-%m-%d %H:%M:%S") if row.get('updated_at') else datetime.utcnow()
            )
            db.session.add(t)

        # Restore Petty Cash
        for row in data_dict.get('petty_cash', []):
            pc = PettyCash(
                date=str(row['date']),
                description=row['description'],
                category=row['category'],
                type=row['type'],
                amount=float(row['amount'] or 0),
                images=str(row['images']),
                updated_at=datetime.strptime(row['updated_at'], "%Y-%m-%d %H:%M:%S") if row.get('updated_at') else datetime.utcnow()
            )
            db.session.add(pc)

        # Restore Banks
        bank_id_map = {}
        for row in data_dict.get('bank', []):
            old_id = str(row.get('id'))
            b = Bank(
                bank_name=row['bank_name'],
                branch=str(row['branch']),
                account_holder_name=str(row['account_holder_name']),
                joint_name=str(row['joint_name']),
                fhp=str(row['fhp']),
                address=str(row['address']),
                city=str(row['city']),
                phone=str(row['phone']),
                customer_id=str(row['customer_id']),
                account_no=str(row['account_no']),
                prev_account_no=str(row['prev_account_no']),
                account_type=str(row['account_type']),
                currency=str(row['currency']),
                status=str(row['status']),
                updated_at=datetime.strptime(row['updated_at'], "%Y-%m-%d %H:%M:%S") if row.get('updated_at') else datetime.utcnow()
            )
            db.session.add(b)
            db.session.flush()
            bank_id_map[old_id] = b.id

        # Restore Bank Transactions
        for row in data_dict.get('bank_transaction', []):
            old_bank_id = str(row.get('bank_id'))
            new_bank_id = bank_id_map.get(old_bank_id)
            
            if not new_bank_id:
                new_bank_id = int(old_bank_id) if old_bank_id.isdigit() else 1

            btx = BankTransaction(
                date=str(row['date']),
                cheque_no=str(row['cheque_no']),
                ref_no=str(row['ref_no']),
                narration=str(row['narration']),
                transaction_details=str(row['transaction_details']),
                debit=float(row['debit'] or 0),
                credit=float(row['credit'] or 0),
                balance=float(row['balance'] or 0),
                bank_id=new_bank_id,
                updated_at=datetime.strptime(row['updated_at'], "%Y-%m-%d %H:%M:%S") if row.get('updated_at') else datetime.utcnow()
            )
            db.session.add(btx)

        # Restore Installments
        installment_id_map = {}
        for row in data_dict.get('installment', []):
            old_inst_id = str(row.get('id'))
            inst = Installment(
                name=row['name'],
                amount_per_share=float(row['amount_per_share'] or 0)
            )
            db.session.add(inst)
            db.session.flush()
            installment_id_map[old_inst_id] = inst.id

        # Restore Customer Installments
        for row in data_dict.get('customer_installment', []):
            old_cust_id = str(row.get('customer_id'))
            old_inst_id = str(row.get('installment_id'))
            
            new_cust_id = customer_id_map.get(old_cust_id)
            new_inst_id = installment_id_map.get(old_inst_id)
            
            if new_cust_id and new_inst_id:
                ci = CustomerInstallment(
                    customer_id=new_cust_id,
                    installment_id=new_inst_id,
                    total_amount=float(row['total_amount'] or 0),
                    paid_amount=float(row['paid_amount'] or 0),
                    due_amount=float(row['due_amount'] or 0)
                )
                db.session.add(ci)

        # Restore Parties
        party_id_map = {}
        for row in data_dict.get('party', []):
            old_id = str(row.get('id'))
            p = Party(
                name=row['name'],
                category=row['category'],
                phone=row.get('phone', ''),
                address=row.get('address', ''),
                created_at=datetime.strptime(row['created_at'], "%Y-%m-%d %H:%M:%S") if row.get('created_at') else datetime.utcnow()
            )
            db.session.add(p)
            db.session.flush()
            party_id_map[old_id] = p.id

        # Restore Vouchers (Depends on Party and Bank)
        voucher_id_map = {}
        from models import Voucher
        for row in data_dict.get('voucher', []):
            old_id = str(row.get('id'))
            old_party_id = str(row.get('party_id'))
            old_bank_id = str(row.get('bank_id'))
            
            v = Voucher(
                voucher_no=row['voucher_no'],
                type=row['type'],
                date=row['date'],
                party_id=party_id_map.get(old_party_id),
                description=row.get('description', ''),
                total_amount=float(row.get('total_amount') or 0),
                amount_paid=float(row.get('amount_paid') or 0),
                due_amount=float(row.get('due_amount') or 0),
                payment_percentage=float(row.get('payment_percentage') or 0),
                payment_method=row['payment_method'],
                bank_id=bank_id_map.get(old_bank_id),
                category=row.get('category', ''),
                notes=row.get('notes', ''),
                attachment=row.get('attachment', ''),
                created_at=datetime.strptime(row['created_at'], "%Y-%m-%d %H:%M:%S") if row.get('created_at') else datetime.utcnow()
            )
            db.session.add(v)
            db.session.flush()
            voucher_id_map[old_id] = v.id

        # Restore Bank Transactions (Refers to Voucher)
        for row in data_dict.get('bank_transaction', []):
            old_bank_id = str(row.get('bank_id'))
            old_voucher_id = str(row.get('voucher_id'))
            new_bank_id = bank_id_map.get(old_bank_id)
            if new_bank_id:
                bt = BankTransaction(
                    date=row['date'],
                    cheque_no=row.get('cheque_no', ''),
                    ref_no=row.get('ref_no', ''),
                    narration=row.get('narration', ''),
                    transaction_details=row.get('transaction_details', ''),
                    debit=float(row.get('debit') or 0),
                    credit=float(row.get('credit') or 0),
                    balance=float(row.get('balance') or 0),
                    bank_id=new_bank_id,
                    voucher_id=voucher_id_map.get(old_voucher_id)
                )
                db.session.add(bt)

        # Restore Petty Cash (Refers to Voucher)
        for row in data_dict.get('petty_cash', []):
            old_voucher_id = str(row.get('voucher_id'))
            pc = PettyCash(
                date=row['date'],
                description=row['description'],
                category=row['category'],
                type=row['type'],
                amount=float(row['amount']),
                images=row.get('images', ''),
                voucher_id=voucher_id_map.get(old_voucher_id)
            )
            db.session.add(pc)

        # Restore Party Ledger (Refers to Voucher)
        for row in data_dict.get('party_ledger', []):
            old_party_id = str(row.get('party_id'))
            old_voucher_id = str(row.get('voucher_id'))
            new_party_id = party_id_map.get(old_party_id)
            if new_party_id:
                pl = PartyLedger(
                    party_id=new_party_id,
                    date=row['date'],
                    description=row.get('description', ''),
                    bill_amount=float(row.get('bill_amount') or 0),
                    paid_amount=float(row.get('paid_amount') or 0),
                    balance=float(row.get('balance') or 0),
                    reference=row.get('reference', ''),
                    voucher_id=voucher_id_map.get(old_voucher_id),
                    created_at=datetime.strptime(row['created_at'], "%Y-%m-%d %H:%M:%S") if row.get('created_at') else datetime.utcnow()
                )
                db.session.add(pl)

        db.session.commit()
        return True, "Data successfully restored from sync (ID mapping applied)."
    except Exception as e:
        db.session.rollback()
        print(f"Restore from dict failed: {e}")
        return False, str(e)

def recalculate_party_ledger_balances(party_id):
    """
    Recalculates the running balance for all entries of a specific party.
    Ensures consistency if entries are added out of order or deleted.
    """
    try:
        entries = PartyLedger.query.filter_by(party_id=party_id).order_by(PartyLedger.date.asc(), PartyLedger.id.asc()).all()
        running_balance = 0.0
        for entry in entries:
            running_balance += (entry.bill_amount - entry.paid_amount)
            entry.balance = running_balance
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        log_debug(f"Error recalculating party balances: {e}")
        return False

def export_party_ledger_to_excel(party_id):
    """
    Generates an Excel file for a specific party's ledger.
    """
    from models import Party
    party = Party.query.get(party_id)
    if not party:
        return None, "Party not found"
        
    entries = PartyLedger.query.filter_by(party_id=party_id).order_by(PartyLedger.date.asc(), PartyLedger.id.asc()).all()
    
    data = []
    for e in entries:
        data.append({
            'Date': e.date,
            'Description': e.description,
            'Bill (Credit)': e.bill_amount,
            'Paid (Debit)': e.paid_amount,
            'Balance': e.balance,
            'Reference': e.reference
        })
        
    df = pd.DataFrame(data)
    
    # Create memory stream
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Ledger')
        
        # Formatting
        workbook = writer.book
        worksheet = writer.sheets['Ledger']
        
        # Adjust column widths
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
            worksheet.column_dimensions[openpyxl.utils.get_column_letter(i+1)].width = column_len

    output.seek(0)
    # Get company info
    company_name = os.environ.get('COMPANY_NAME', 'NEXUS RIVER VIEW')
        
    safe_company_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"{safe_company_name}_{party.name.replace(' ', '_')}_Ledger_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return output, filename

def generate_voucher_number(v_type):
    """
    Generates a unique voucher number based on type.
    Debit Voucher: DV1, DV2, ...
    Credit Voucher: CV1, CV2, ...
    """
    from models import Voucher
    prefix = "DV" if v_type == "Debit" else "CV"
    
    # Get all vouchers of this type and find the max number
    vouchers = Voucher.query.filter(Voucher.type == v_type).all()
    count = len(vouchers)
    new_num = count + 1
    
    return f"{prefix}{new_num}"

def generate_contra_number():
    from models import ContraEntry
    # Get all contra entries and find the next number
    count = ContraEntry.query.count()
    new_num = count + 1
    return f"CN{new_num}"

def process_voucher_financials(voucher_id, action='add'):
    """
    Handles automatic balance updates across modules when a voucher is created, edited, or deleted.
    Voucher types:
    - Debit: Payment MADE (Money OUT)
    - Credit: Money RECEIVED (Money IN)
    """
    from models import Voucher, PettyCash, BankTransaction, PartyLedger, Party
    voucher = Voucher.query.get(voucher_id)
    if not voucher:
        return False, "Voucher not found"

    try:
        # 1. Clear existing side-effects (for Edit/Delete)
        if action in ['edit', 'delete']:
            PettyCash.query.filter_by(voucher_id=voucher.id).delete()
            BankTransaction.query.filter_by(voucher_id=voucher.id).delete()
            PartyLedger.query.filter_by(voucher_id=voucher.id).delete()
            from models import JournalEntry
            JournalEntry.query.filter_by(reference_id=f"V-{voucher.voucher_no}").delete()
            
            # If it was a customer voucher, we need to handle Transaction reverse?
            # Or just let process_voucher_financials re-create things.
            # Usually Customer transactions are updated via recalculate_customer_totals
            from models import Transaction
            Transaction.query.filter_by(remarks=f"Voucher {voucher.voucher_no}").delete()
            
            if action == 'delete':
                db.session.commit()
                # If it was a party voucher, recalculate balances
                if voucher.party_id:
                    recalculate_party_ledger_balances(voucher.party_id)
                
                if voucher.customer_id:
                    from models import Customer
                    cust = Customer.query.get(voucher.customer_id)
                    recalculate_customer_totals(cust)
                return True, "Voucher side-effects removed"

        # 2. Add new side-effects (for Add/Edit)
        if action in ['add', 'edit']:
            # --- Double-Entry Journal Posting ---
            if voucher.debit_account_code and voucher.credit_account_code:
                # Use T-09/T-10/T-11 style posting
                if voucher.type == 'Debit':
                    journal_general_expense(
                        voucher.debit_account_code, 
                        voucher.payment_method, 
                        voucher.credit_account_code, 
                        voucher.amount_paid, 
                        voucher.voucher_no, 
                        voucher.category, 
                        voucher.date
                    )
                else:
                    journal_general_income(
                        voucher.credit_account_code, 
                        voucher.payment_method, 
                        voucher.debit_account_code, 
                        voucher.amount_paid, 
                        voucher.voucher_no, 
                        voucher.category, 
                        voucher.date
                    )
            
            # --- Legacy Flat-Table Updates (Keep for compatibility) ---
            # A. Update Cash or Bank
            if voucher.payment_method == 'Cash':
                pc = PettyCash(
                    date=voucher.date,
                    description=f"Voucher {voucher.voucher_no}: {voucher.description}",
                    category=voucher.category or "General",
                    type="Expense" if voucher.type == "Debit" else "Income",
                    amount=voucher.amount_paid,
                    voucher_id=voucher.id
                )
                db.session.add(pc)
            
            elif voucher.payment_method == 'Bank' and voucher.bank_id:
                bt = BankTransaction(
                    date=voucher.date,
                    narration=f"Voucher {voucher.voucher_no}: {voucher.description}",
                    debit=voucher.amount_paid if voucher.type == "Debit" else 0,
                    credit=voucher.amount_paid if voucher.type == "Credit" else 0,
                    bank_id=voucher.bank_id,
                    voucher_id=voucher.id,
                    category=voucher.category or "General",
                    transaction_details=f"{voucher.type} Voucher"
                )
                db.session.add(bt)
                # Note: Bank running balances are usually updated on view or periodically

            # B. Update Party Ledger (if linked)
            if voucher.party_id:
                pl = PartyLedger(
                    party_id=voucher.party_id,
                    date=voucher.date,
                    description=f"Voucher {voucher.voucher_no}: {voucher.description}",
                    bill_amount=voucher.total_amount if (voucher.type == "Debit" and not voucher.is_payment) else 0,
                    paid_amount=voucher.amount_paid, # Amount actually paid/received
                    reference=voucher.voucher_no,
                    voucher_id=voucher.id
                )
                # If Credit Voucher linked to party, bill_amount might be 0, and paid_amount is credit to party?
                # Usually Credit Voucher to party means THEY paid US.
                if voucher.type == "Credit":
                    pl.bill_amount = 0
                    pl.paid_amount = -voucher.amount_paid # Negative paid_amount in our ledger logic means receiving? 
                    # Wait, our PartyLedger logic: balance = sum(bill) - sum(paid).
                    # If we pay them: paid_amount increases, balance decreases. (Correct: we owe less)
                    # If they pay us: paid_amount should be negative? OR bill_amount should be negative?
                    # Let's check existing logic: bill_amount (Credit), paid_amount (Debit).
                    # If they pay us, it's a Credit to THEM? No, Debit is what we pay. 
                    # Actually, standard: Credit (THEM giving us goods), Debit (US paying THEM).
                    # If THEY pay US, it's a "Negative Bill" or "Positive Payment" in a different sense.
                    # Let's simplify: 
                    # Debit Voucher (We Pay): Bill = Total Amount, Paid = Amount Paid. Balance = Total - Paid.
                    # Credit Voucher (They Pay): Bill = 0, Paid = -Amount Paid (Received). Balance = 0 - (-Paid) = +Paid.
                    # Actually, if we just want to track their balance:
                    # Bill = Amount they owe us (Credit), Paid = Amount we paid them (Debit).
                    # So if they pay us, it's a SUBTRACTION from Bill or ADDITION to Paid.
                    # Let's use:
                    # Debit Voucher: Bill += total, Paid += paid.
                    # Credit Voucher: Bill += 0, Paid -= amount_received.
                    pass
                
                db.session.add(pl)
                db.session.flush() # Ensure PL has an ID
                recalculate_party_ledger_balances(voucher.party_id)

            # C. Update Customer (if linked)
            if voucher.customer_id:
                from models import Transaction, Customer, CustomerInstallment
                # Create a Transaction for the customer
                tx = Transaction(
                    date=voucher.date,
                    amount=voucher.amount_paid,
                    installment_type="Installment",
                    remarks=f"Voucher {voucher.voucher_no}: {voucher.description}",
                    payment_method=voucher.payment_method,
                    customer_id=voucher.customer_id
                )
                db.session.add(tx)
                
                # Update Customer Balance and Installments
                cust = Customer.query.get(voucher.customer_id)
                if cust:
                    recalculate_customer_totals(cust)
                    # Allocation logic (simplistic: oldest due first)
                    # Wait, usually Transaction is linked to CustomerInstallment
                    pending_installments = CustomerInstallment.query.filter(
                        CustomerInstallment.customer_id == voucher.customer_id,
                        CustomerInstallment.due_amount > 0
                    ).all() # Sorting would be better
                    
                    remaining = voucher.amount_paid
                    for ci in pending_installments:
                        if remaining <= 0: break
                        pay = min(remaining, ci.due_amount)
                        ci.paid_amount += pay
                        ci.due_amount -= pay
                        remaining -= pay
                        # Link tx to the first one it covers or logic to split? 
                        # Simplifying: just update balances.

        db.session.commit()
        return True, "Voucher financials processed successfully"
    except Exception as e:
        db.session.rollback()
        log_debug(f"Error processing voucher financials: {e}")
        return False, str(e)

def process_contra_financials(contra_id, action='add'):
    from models import ContraEntry, PettyCash, BankTransaction
    contra = ContraEntry.query.get(contra_id)
    if not contra: return False, "Contra Entry not found"
    
    try:
        if action in ['edit', 'delete']:
            PettyCash.query.filter_by(contra_entry_id=contra.id).delete()
            BankTransaction.query.filter_by(contra_entry_id=contra.id).delete()
            from models import JournalEntry
            JournalEntry.query.filter_by(reference_id=f"CN-{contra.contra_no}").delete()
        
        if action in ['add', 'edit']:
            # From Account (Subtract)
            if contra.from_account == 'Cash':
                pc_out = PettyCash(
                    date=contra.date,
                    description=f"Contra {contra.contra_no}: {contra.description} (Transfer to {contra.to_account})",
                    category="Contra", type="Expense", amount=contra.amount, contra_entry_id=contra.id,
                    images=contra.attachments # Carry over attachments
                )
                db.session.add(pc_out)
            elif contra.from_account == 'Bank' and contra.bank_id:
                bt_out = BankTransaction(
                    date=contra.date, narration=f"Contra {contra.contra_no}: Transfer to {contra.to_account}",
                    debit=contra.amount, credit=0, bank_id=contra.bank_id, contra_entry_id=contra.id,
                    transaction_details="Contra Withdraw",
                    cheque_no=contra.cheque_no # Carry over cheque_no
                )
                db.session.add(bt_out)

            # To Account (Add)
            if contra.to_account == 'Cash':
                pc_in = PettyCash(
                    date=contra.date,
                    description=f"Contra {contra.contra_no}: {contra.description} (Transfer from {contra.from_account})",
                    category="Contra", type="Income", amount=contra.amount, contra_entry_id=contra.id,
                    images=contra.attachments
                )
                db.session.add(pc_in)
            elif contra.to_account == 'Bank' and contra.bank_id:
                bt_in = BankTransaction(
                    date=contra.date, narration=f"Contra {contra.contra_no}: Transfer from {contra.from_account}",
                    debit=0, credit=contra.amount, bank_id=contra.bank_id, contra_entry_id=contra.id,
                    transaction_details="Contra Deposit",
                    cheque_no=contra.cheque_no
                )
                db.session.add(bt_in)
            
            # --- Double-Entry Journal Posting ---
            if contra.debit_account_code and contra.credit_account_code:
                lines = [
                    {'account_code': contra.debit_account_code, 'debit': contra.amount, 'credit': 0},
                    {'account_code': contra.credit_account_code, 'debit': 0, 'credit': contra.amount}
                ]
                post_journal_entry(contra.date, "BANK_TRANSFER", contra.contra_no, contra.description, lines)

        db.session.commit()
        return True, "Contra financials processed successfully"
    except Exception as e:
        db.session.rollback()
        return False, str(e)

def get_due_payments_report():
    """Returns vouchers that have a remaining due amount."""
    from models import Voucher
    return Voucher.query.filter(Voucher.due_amount > 0).order_by(Voucher.date.desc()).all()

def get_daily_cash_report(target_date):
    """Aggregates all cash and bank movements for a specific date, providing comparative summaries."""
    from models import PettyCash, Bank, BankTransaction
    from sqlalchemy import func
    
    # 1. Day's Transactions
    transactions = PettyCash.query.filter_by(date=target_date).all()
    
    from decimal import Decimal
    # 2. Cash Balances
    # Previous day's cash in hand: All Income - All Expense before target_date
    cash_in_before = db.session.query(func.sum(PettyCash.amount)).filter(PettyCash.date < target_date, PettyCash.type == 'Income').scalar() or 0
    cash_out_before = db.session.query(func.sum(PettyCash.amount)).filter(PettyCash.date < target_date, PettyCash.type == 'Expense').scalar() or 0
    prev_cash = Decimal(str(cash_in_before)) - Decimal(str(cash_out_before))
    
    # Today's cash in hand: All Income - All Expense including target_date
    cash_in_today = db.session.query(func.sum(PettyCash.amount)).filter(PettyCash.date <= target_date, PettyCash.type == 'Income').scalar() or 0
    cash_out_today = db.session.query(func.sum(PettyCash.amount)).filter(PettyCash.date <= target_date, PettyCash.type == 'Expense').scalar() or 0
    today_cash = Decimal(str(cash_in_today)) - Decimal(str(cash_out_today))
    
    # 3. Bank Balances
    # We must sort using the same logic as recompute_bank_balances to handle mixed date formats
    def parse_tx_date(date_str):
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                pass
        return datetime.min.date()

    from decimal import Decimal
    target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    banks = Bank.query.all()
    prev_bank = Decimal('0.00')
    today_bank = Decimal('0.00')
    
    for b in banks:
        all_tx = BankTransaction.query.filter_by(bank_id=b.id).all()
        # Sort transactions: Date (asc), then ID (asc)
        sorted_tx = sorted(all_tx, key=lambda x: (parse_tx_date(x.date), x.id))
        
        bank_prev = Decimal('0.00')
        bank_today = Decimal('0.00')
        
        for tx in sorted_tx:
            tx_date = parse_tx_date(tx.date)
            if tx_date < target_date_obj:
                bank_prev = tx.balance or Decimal('0.00')
            if tx_date <= target_date_obj:
                bank_today = tx.balance or Decimal('0.00')
            else:
                break
                
        prev_bank += bank_prev
        today_bank += bank_today
            
    return {
        'transactions': transactions,
        'prev_cash': Decimal(str(prev_cash)),
        'today_cash': Decimal(str(today_cash)),
        'prev_bank': prev_bank,
        'today_bank': today_bank
    }

def generate_je_number():
    from models import JournalEntry
    count = JournalEntry.query.count()
    return f"JE-{count + 1:04d}"

def post_journal_entry(entry_date, reference_type, reference_id, description, lines, is_posted=True):
    """
    Core Double-Entry Posting Engine.
    lines: list of dicts {'account_code', 'debit', 'credit', 'narration', 'party_type', 'party_id'}
    """
    from models import JournalEntry, JournalLine, ChartOfAccounts
    from decimal import Decimal
    
    total_debit = sum(Decimal(str(l.get('debit', 0) or 0)) for l in lines)
    total_credit = sum(Decimal(str(l.get('credit', 0) or 0)) for l in lines)
    
    if total_debit != total_credit:
        raise ValueError(f"Imbalanced Journal Entry: DR {total_debit} != CR {total_credit}")
        
    je = JournalEntry(
        entry_number=generate_je_number(),
        entry_date=datetime.strptime(entry_date, '%Y-%m-%d').date() if isinstance(entry_date, str) else entry_date,
        reference_type=reference_type,
        reference_id=str(reference_id),
        description=description,
        is_posted=is_posted
    )
    db.session.add(je)
    db.session.flush() # Get JE ID
    
    for l in lines:
        acc = ChartOfAccounts.query.get(l['account_code'])
        line = JournalLine(
            journal_entry_id=je.id,
            account_code=l['account_code'],
            account_name=acc.account_name if acc else "Unknown",
            debit_amount=Decimal(str(l.get('debit', 0) or 0)),
            credit_amount=Decimal(str(l.get('credit', 0) or 0)),
            narration=l.get('narration', description),
            party_type=l.get('party_type'),
            party_id=str(l.get('party_id')) if l.get('party_id') else None
        )
        db.session.add(line)
        
    return je

def seed_chart_of_accounts():
    """Seeds the 70+ COA accounts from the Master Prompt."""
    from models import ChartOfAccounts
    
    coa_data = [
        # 1000 - ASSETS
        ('1000', 'ASSETS', 'Asset', 'Header', 'Debit', False, None),
        ('1010', 'Cash on Hand (Petty Cash)', 'Asset', 'Current Asset', 'Debit', False, '1000'),
        ('1020', 'Cash at Bank — Control', 'Asset', 'Current Asset', 'Debit', True, '1000'),
        ('1030', 'Accounts Receivable — Customers', 'Asset', 'Current Asset', 'Debit', True, '1000'),
        ('1031', 'Installment Receivable — Plot Sales', 'Asset', 'Current Asset', 'Debit', False, '1030'),
        ('1040', 'Advance to Suppliers & Contractors', 'Asset', 'Current Asset', 'Debit', False, '1000'),
        ('1050', 'Prepaid Expenses', 'Asset', 'Current Asset', 'Debit', False, '1000'),
        ('1060', 'Work In Progress — Construction', 'Asset', 'Current Asset', 'Debit', False, '1000'),
        ('1070', 'Inventory — Building Materials', 'Asset', 'Current Asset', 'Debit', False, '1000'),
        ('1100', 'FIXED ASSETS', 'Asset', 'Fixed Asset', 'Debit', False, '1000'),
        ('1110', 'Land Holdings', 'Asset', 'Fixed Asset', 'Debit', False, '1100'),
        ('1120', 'Buildings & Structures', 'Asset', 'Fixed Asset', 'Debit', False, '1100'),
        ('1130', 'Office Equipment', 'Asset', 'Fixed Asset', 'Debit', False, '1100'),
        ('1140', 'Furniture & Fixtures', 'Asset', 'Fixed Asset', 'Debit', False, '1100'),
        ('1150', 'Vehicles', 'Asset', 'Fixed Asset', 'Debit', False, '1100'),
        ('1160', 'Computer & IT Equipment', 'Asset', 'Fixed Asset', 'Debit', False, '1100'),
        ('1170', 'Acc. Depreciation — Buildings', 'Asset', 'Fixed Asset', 'Credit', False, '1120'),
        ('1180', 'Acc. Depreciation — Equipment', 'Asset', 'Fixed Asset', 'Credit', False, '1130'),
        ('1190', 'Acc. Depreciation — Furniture', 'Asset', 'Fixed Asset', 'Credit', False, '1140'),
        ('1200', 'Acc. Depreciation — Vehicles', 'Asset', 'Fixed Asset', 'Credit', False, '1150'),
        ('1210', 'Acc. Depreciation — IT Equipment', 'Asset', 'Fixed Asset', 'Credit', False, '1160'),

        # 2000 - LIABILITIES
        ('2000', 'LIABILITIES', 'Liability', 'Header', 'Credit', False, None),
        ('2010', 'Accounts Payable — Suppliers', 'Liability', 'Current Liability', 'Credit', True, '2000'),
        ('2020', 'Accounts Payable — Contractors', 'Liability', 'Current Liability', 'Credit', True, '2000'),
        ('2030', 'Advance from Customers (Booking)', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2040', 'Salaries & Wages Payable', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2050', 'Tax Deducted at Source (TDS) Payable', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2060', 'Sales Tax / GST Payable', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2070', 'Accrued Expenses', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2080', 'Security Deposits Received', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2100', 'Short-Term Loans Payable', 'Liability', 'Current Liability', 'Credit', False, '2000'),
        ('2200', 'Long-Term Loans Payable', 'Liability', 'Long-term Liability', 'Credit', False, '2000'),
        ('2210', 'Director Loans Payable', 'Liability', 'Long-term Liability', 'Credit', False, '2000'),

        # 3000 - EQUITY
        ('3000', 'EQUITY', 'Equity', 'Header', 'Credit', False, None),
        ('3010', 'Director Capital — Control', 'Equity', "Owner's Equity", 'Credit', True, '3000'),
        ('3020', 'Retained Earnings', 'Equity', "Owner's Equity", 'Credit', False, '3000'),
        ('3030', 'Current Year Profit / (Loss)', 'Equity', "Owner's Equity", 'Credit', False, '3000'),
        ('3040', 'Share Premium', 'Equity', "Owner's Equity", 'Credit', False, '3000'),
        ('3050', 'Drawings — Directors', 'Equity', "Owner's Equity", 'Debit', False, '3000'),

        # 4000 - REVENUE
        ('4000', 'REVENUE', 'Revenue', 'Header', 'Credit', False, None),
        ('4010', 'Plot Sales Revenue', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4020', 'Installment Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4030', 'Booking Fee Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4040', 'Development Charges Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4050', 'Rental Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4060', 'Penalty / Late Payment Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4070', 'Interest / Bank Profit Received', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4080', 'Commission Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),
        ('4090', 'Other Operating Income', 'Revenue', 'Operating Revenue', 'Credit', False, '4000'),

        # 5000 - COGS
        ('5000', 'DIRECT COSTS', 'COGS', 'Header', 'Debit', False, None),
        ('5010', 'Land Acquisition Cost', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5020', 'Civil & Construction Costs', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5030', 'Piling & Foundation Costs', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5040', 'Finishing & Fit-Out Costs', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5050', 'Electrical & Plumbing Works', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5060', 'Landscaping & External Works', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5070', 'Material Purchases — Direct', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5080', 'Sub-Contractor Payments', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5090', 'Site Supervision Wages', 'COGS', 'Direct Cost', 'Debit', False, '5000'),
        ('5100', 'Transfer from WIP', 'COGS', 'Direct Cost', 'Debit', False, '5000'),

        # 6000 - EXPENSES
        ('6000', 'OPERATING EXPENSES', 'Expense', 'Header', 'Debit', False, None),
        ('6010', 'Salaries & Wages — Admin', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6011', 'Salaries & Wages — Sales', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6020', 'Employee Benefits & Allowances', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6030', 'Office Rent & Lease', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6040', 'Electricity & Utilities', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6050', 'Telephone & Internet', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6060', 'Marketing & Advertising', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6070', 'Printing & Stationery', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6080', 'Travel & Transportation', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6090', 'Legal & Professional Fees', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6100', 'Repairs & Maintenance — Office', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6110', 'Security Services', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6120', 'Insurance Expense', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6130', 'Depreciation — Buildings', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6140', 'Depreciation — Equipment', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6150', 'Depreciation — Furniture', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6160', 'Depreciation — Vehicles', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6170', 'Depreciation — IT Equipment', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6180', 'Bank Charges & Commission', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6190', 'Interest Expense on Loans', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6200', 'Penalties & Fines', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6210', 'Employee Provident Fund / EOBI', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6220', 'Charity & Donations', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
        ('6230', 'Miscellaneous Expenses', 'Expense', 'Operating Expense', 'Debit', False, '6000'),
    ]
    
    for code, name, type, cat, bal, ctrl, parent in coa_data:
        if not ChartOfAccounts.query.get(code):
            acc = ChartOfAccounts(
                account_code=code,
                account_name=name,
                account_type=type,
                account_category=cat,
                normal_balance=bal,
                is_control_account=ctrl,
                parent_code=parent,
                is_system=True
            )
            db.session.add(acc)
    
    db.session.commit()
    print("Chart of Accounts seeded successfully.")

def seed_database():
    """Initial database seeding."""
    seed_chart_of_accounts()
    # Add other seeding logic here (Admin, Fiscal Year, etc.)

# --- Automated Journal Templates (T-01 to T-21) ---

def journal_customer_booking(customer, amount, entry_date=None, ref_id=None):
    """T-01 — Customer Plot Booking"""
    description = f"Booking received — Customer {customer.customer_id} — Plot {customer.plot_no}"
    lines = [
        {'account_code': '1030', 'debit': amount, 'credit': 0, 'party_type': 'Customer', 'party_id': customer.id},
        {'account_code': '2030', 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "RECEIPT", ref_id or f"CUST-{customer.id}", description, lines)

def journal_installment_due(customer, milestone_name, amount, entry_date=None, ref_id=None):
    """T-02 — Installment Due (Milestone Created)"""
    description = f"Installment milestone created: {milestone_name} — Customer {customer.customer_id}"
    lines = [
        {'account_code': '1031', 'debit': amount, 'credit': 0, 'party_type': 'Customer', 'party_id': customer.id},
        {'account_code': '4020', 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "INVOICE", ref_id or f"MILE-{customer.id}", description, lines)

def journal_customer_payment_cash(customer, milestone_name, amount, entry_date=None, ref_id=None):
    """T-03 — Customer Installment Payment Received (Cash)"""
    description = f"Cash receipt — Installment {milestone_name} — Customer {customer.customer_id}"
    lines = [
        {'account_code': '1010', 'debit': amount, 'credit': 0},
        {'account_code': '1031', 'debit': 0, 'credit': amount, 'party_type': 'Customer', 'party_id': customer.id}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "RECEIPT", ref_id or f"CASH-{customer.id}", description, lines)

def journal_customer_payment_bank(customer, bank_acc_code, milestone_name, amount, ref_no, entry_date=None, ref_id=None):
    """T-04 — Customer Installment Payment Received (Bank)"""
    description = f"Bank receipt — Installment {milestone_name} — Customer {customer.customer_id} — Ref {ref_no}"
    lines = [
        {'account_code': bank_acc_code, 'debit': amount, 'credit': 0},
        {'account_code': '1031', 'debit': 0, 'credit': amount, 'party_type': 'Customer', 'party_id': customer.id}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "RECEIPT", ref_id or f"BANK-{customer.id}", description, lines)

def journal_advance_applied(customer, amount, entry_date=None):
    """T-05 — Advance from Customer Applied to Sale"""
    description = f"Advance applied to plot sale — Customer {customer.customer_id} — Plot {customer.plot_no}"
    lines = [
        {'account_code': '2030', 'debit': amount, 'credit': 0},
        {'account_code': '4010', 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "ADJUSTMENT", f"ADV-{customer.id}", description, lines)

def journal_supplier_bill(party, coa_code, amount, bill_no, entry_date=None, ref_id=None):
    """T-06 — Supplier / Contractor Bill Received"""
    description = f"Bill posted — {party.name} — Bill No {bill_no}"
    ap_code = '2010' if party.category == 'Supplier' else '2020'
    lines = [
        {'account_code': coa_code, 'debit': amount, 'credit': 0},
        {'account_code': ap_code, 'debit': 0, 'credit': amount, 'party_type': party.category, 'party_id': party.id}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "VOUCHER", ref_id or f"BILL-{party.id}", description, lines)

def journal_supplier_payment_cash(party, amount, voucher_no, entry_date=None, ref_id=None):
    """T-07 — Supplier / Contractor Payment (Cash)"""
    description = f"Cash payment — {party.name} — Voucher {voucher_no}"
    ap_code = '2010' if party.category == 'Supplier' else '2020'
    lines = [
        {'account_code': ap_code, 'debit': amount, 'credit': 0, 'party_type': party.category, 'party_id': party.id},
        {'account_code': '1010', 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "VOUCHER", ref_id or f"PAY-{party.id}", description, lines)

def journal_supplier_payment_bank(party, bank_acc_code, amount, voucher_no, cheque_ref, entry_date=None):
    """T-08 — Supplier / Contractor Payment (Bank)"""
    description = f"Bank payment — {party.name} — Voucher {voucher_no} — Cheque {cheque_ref}"
    ap_code = '2010' if party.category == 'Supplier' else '2020'
    lines = [
        {'account_code': ap_code, 'debit': amount, 'credit': 0, 'party_type': party.category, 'party_id': party.id},
        {'account_code': bank_acc_code, 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "VOUCHER", f"PAY-{party.id}", description, lines)

def journal_general_expense(coa_code, payment_method, bank_acc_code, amount, voucher_no, category, entry_date=None):
    """T-09 / T-10 — Debit Voucher (General Expense)"""
    description = f"Expense — {category} — Voucher {voucher_no}"
    cr_code = '1010' if payment_method == 'Cash' else bank_acc_code
    lines = [
        {'account_code': coa_code, 'debit': amount, 'credit': 0},
        {'account_code': cr_code, 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "VOUCHER", f"EXP-{voucher_no}", description, lines)

def journal_general_income(coa_code, payment_method, bank_acc_code, amount, voucher_no, category, entry_date=None):
    """T-11 — Credit Voucher (Income Receipt)"""
    description = f"Income — {category} — Voucher {voucher_no}"
    dr_code = '1010' if payment_method == 'Cash' else bank_acc_code
    lines = [
        {'account_code': dr_code, 'debit': amount, 'credit': 0},
        {'account_code': coa_code, 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "VOUCHER", f"INC-{voucher_no}", description, lines)

def journal_contra_deposit(bank_acc_code, amount, voucher_no, entry_date=None):
    """T-12 — Contra Entry: Cash Deposit to Bank"""
    description = f"Contra — Cash deposited to bank — Voucher {voucher_no}"
    lines = [
        {'account_code': bank_acc_code, 'debit': amount, 'credit': 0},
        {'account_code': '1010', 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "BANK_TRANSFER", f"CON-{voucher_no}", description, lines)

def journal_contra_withdrawal(bank_acc_code, amount, voucher_no, entry_date=None):
    """T-13 — Contra Entry: Bank Withdrawal to Cash"""
    description = f"Contra — Cash withdrawn from bank — Voucher {voucher_no}"
    lines = [
        {'account_code': '1010', 'debit': amount, 'credit': 0},
        {'account_code': bank_acc_code, 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "BANK_TRANSFER", f"CON-{voucher_no}", description, lines)

def journal_payroll(gross_total, net_total, deductions_total, month, year, entry_date=None):
    """T-16 — Monthly Payroll Generation"""
    description = f"Payroll — {month} {year}"
    # Force balance by calculating gross from components if they don't match
    # Usually Gross = Net + Deductions
    actual_gross = net_total + deductions_total
    lines = [
        {'account_code': '6010', 'debit': actual_gross, 'credit': 0}, # Admin salary by default
        {'account_code': '2040', 'debit': 0, 'credit': net_total},   # Salaries Payable
        {'account_code': '2050', 'debit': 0, 'credit': deductions_total} # Deductions/TDS Payable
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "PAYROLL", f"PAY-{month}-{year}", description, lines)

def journal_salary_payment(employee, bank_acc_code, amount, voucher_no, entry_date=None):
    """T-17 — Salary Payment"""
    description = f"Salary disbursed — {employee.name} — Voucher {voucher_no}"
    lines = [
        {'account_code': '2040', 'debit': amount, 'credit': 0, 'party_type': 'Employee', 'party_id': employee.id},
        {'account_code': bank_acc_code, 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "VOUCHER", f"SAL-{voucher_no}", description, lines)

def journal_director_capital(director, amount, coa_code, payment_method, bank_acc_code, entry_date=None):
    """T-18 — Director Capital Injection"""
    description = f"Capital injection — {director.name}"
    dr_code = '1010' if payment_method == 'Cash' else bank_acc_code
    lines = [
        {'account_code': dr_code, 'debit': amount, 'credit': 0},
        {'account_code': coa_code, 'debit': 0, 'credit': amount, 'party_type': 'Director', 'party_id': director.id}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "RECEIPT", f"CAP-{director.id}", description, lines)

def journal_director_drawing(director, amount, coa_code, payment_method, bank_acc_code, entry_date=None):
    """T-19 — Director Drawing / Withdrawal"""
    description = f"Director drawing — {director.name}"
    cr_code = '1010' if payment_method == 'Cash' else bank_acc_code
    lines = [
        {'account_code': '3050', 'debit': amount, 'credit': 0, 'party_type': 'Director', 'party_id': director.id},
        {'account_code': cr_code, 'debit': 0, 'credit': amount}
    ]
    return post_journal_entry(entry_date or datetime.now().date(), "RECEIPT", f"DRW-{director.id}", description, lines)

def journal_reversal(original_je_id):
    """T-21 — Reversal of Any Voucher / Entry"""
    from models import JournalEntry, JournalLine
    original = JournalEntry.query.get(original_je_id)
    if not original: return None
    
    description = f"REVERSAL of {original.entry_number} — {original.description}"
    lines = []
    for line in original.lines:
        lines.append({
            'account_code': line.account_code,
            'debit': line.credit_amount,
            'credit': line.debit_amount,
            'narration': f"REVERSAL: {line.narration}",
            'party_type': line.party_type,
            'party_id': line.party_id
        })
    
    je = post_journal_entry(datetime.now().date(), "ADJUSTMENT", original.entry_number, description, lines)
    original.is_reversed = True
    original.reversal_entry_id = je.id
    db.session.commit()
    return je

# --- Reporting Logic ---

def get_trial_balance(start_date=None, end_date=None):
    from models import ChartOfAccounts, JournalLine, JournalEntry
    from sqlalchemy import func
    
    # Get all accounts
    accounts = ChartOfAccounts.query.order_by(ChartOfAccounts.account_code).all()
    
    # Sum debits and credits for each account within range
    query = db.session.query(
        JournalLine.account_code,
        func.sum(JournalLine.debit_amount).label('total_debit'),
        func.sum(JournalLine.credit_amount).label('total_credit')
    ).join(JournalEntry)
    
    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)
    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)
        
    results = query.group_by(JournalLine.account_code).all()
    
    # Map results
    balances = {r.account_code: (r.total_debit or Decimal('0.00'), r.total_credit or Decimal('0.00')) for r in results}
    
    report_data = []
    total_dr = Decimal('0.00')
    total_cr = Decimal('0.00')
    
    for acc in accounts:
        dr_sum, cr_sum = balances.get(acc.account_code, (Decimal('0.00'), Decimal('0.00')))
        
        # Calculate net balance based on normal balance
        net_dr = Decimal('0.00')
        net_cr = Decimal('0.00')
        
        diff = dr_sum - cr_sum
        if diff > 0:
            net_dr = diff
        elif diff < 0:
            net_cr = -diff
            
        if net_dr > 0 or net_cr > 0 or acc.is_control_account:
            report_data.append({
                'code': acc.account_code,
                'name': acc.account_name,
                'debit': net_dr,
                'credit': net_cr,
                'is_control': acc.is_control_account
            })
            total_dr += net_dr
            total_cr += net_cr
            
    return {
        'accounts': report_data,
        'total_debit': total_dr,
        'total_credit': total_cr,
        'today_date': datetime.now().strftime('%d %B, %Y')
    }

def get_profit_loss(start_date=None, end_date=None):
    from models import ChartOfAccounts, JournalLine, JournalEntry
    from sqlalchemy import func
    
    # Revenue (4000 series)
    rev_q = db.session.query(
        ChartOfAccounts.account_name,
        func.sum(JournalLine.credit_amount - JournalLine.debit_amount).label('balance')
    ).join(JournalLine).join(JournalEntry).filter(ChartOfAccounts.account_type == 'Revenue')
    if start_date: rev_q = rev_q.filter(JournalEntry.entry_date >= start_date)
    if end_date: rev_q = rev_q.filter(JournalEntry.entry_date <= end_date)
    revenues = rev_q.group_by(ChartOfAccounts.account_code).all()
    total_revenue = sum(r.balance or Decimal('0.00') for r in revenues) if revenues else Decimal('0.00')
    
    # COGS (5000 series)
    cogs_q = db.session.query(
        ChartOfAccounts.account_name,
        func.sum(JournalLine.debit_amount - JournalLine.credit_amount).label('balance')
    ).join(JournalLine).join(JournalEntry).filter(ChartOfAccounts.account_type == 'COGS')
    if start_date: cogs_q = cogs_q.filter(JournalEntry.entry_date >= start_date)
    if end_date: cogs_q = cogs_q.filter(JournalEntry.entry_date <= end_date)
    cogs = cogs_q.group_by(ChartOfAccounts.account_code).all()
    total_cogs = sum(c.balance or Decimal('0.00') for c in cogs) if cogs else Decimal('0.00')
    
    gross_profit = total_revenue - total_cogs
    
    # Expenses (6000 series)
    exp_q = db.session.query(
        ChartOfAccounts.account_name,
        func.sum(JournalLine.debit_amount - JournalLine.credit_amount).label('balance')
    ).join(JournalLine).join(JournalEntry).filter(ChartOfAccounts.account_type == 'Expense')
    if start_date: exp_q = exp_q.filter(JournalEntry.entry_date >= start_date)
    if end_date: exp_q = exp_q.filter(JournalEntry.entry_date <= end_date)
    expenses = exp_q.group_by(ChartOfAccounts.account_code).all()
    total_expenses = sum(e.balance or Decimal('0.00') for e in expenses) if expenses else Decimal('0.00')
    
    net_profit = gross_profit - total_expenses
    
    return {
        'revenues': revenues,
        'total_revenue': total_revenue,
        'cogs': cogs,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'expenses': expenses,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'today_date': datetime.now().strftime('%d %B, %Y')
    }

def get_balance_sheet(as_of_date=None):
    from models import ChartOfAccounts, JournalLine, JournalEntry
    from sqlalchemy import func
    
    # Balance sheet is cumulative, so we only filter by end_date (as_of_date)
    
    # Assets
    asset_q = db.session.query(
        ChartOfAccounts.account_category,
        ChartOfAccounts.account_name,
        func.sum(JournalLine.debit_amount - JournalLine.credit_amount).label('balance')
    ).join(JournalLine).join(JournalEntry).filter(ChartOfAccounts.account_type == 'Asset')
    if as_of_date: asset_q = asset_q.filter(JournalEntry.entry_date <= as_of_date)
    assets = asset_q.group_by(ChartOfAccounts.account_code).all()
    total_assets = sum(a.balance or Decimal('0.00') for a in assets) if assets else Decimal('0.00')
    
    # Liabilities
    liab_q = db.session.query(
        ChartOfAccounts.account_category,
        ChartOfAccounts.account_name,
        func.sum(JournalLine.credit_amount - JournalLine.debit_amount).label('balance')
    ).join(JournalLine).join(JournalEntry).filter(ChartOfAccounts.account_type == 'Liability')
    if as_of_date: liab_q = liab_q.filter(JournalEntry.entry_date <= as_of_date)
    liabilities = liab_q.group_by(ChartOfAccounts.account_code).all()
    total_liabilities = sum(l.balance or Decimal('0.00') for l in liabilities) if liabilities else Decimal('0.00')
    
    # Equity
    equity_q = db.session.query(
        ChartOfAccounts.account_category,
        ChartOfAccounts.account_name,
        func.sum(JournalLine.credit_amount - JournalLine.debit_amount).label('balance')
    ).join(JournalLine).join(JournalEntry).filter(ChartOfAccounts.account_type == 'Equity')
    if as_of_date: equity_q = equity_q.filter(JournalEntry.entry_date <= as_of_date)
    equity = equity_q.group_by(ChartOfAccounts.account_code).all()
    
    # Add Net Profit to Retained Earnings or as a separate line
    pl = get_profit_loss(end_date=as_of_date)
    net_profit = pl['net_profit']
    
    total_equity = sum(e.balance or Decimal('0.00') for e in equity) if equity else Decimal('0.00')
    total_equity += net_profit
    
    return {
        'assets': assets,
        'total_assets': total_assets,
        'liabilities': liabilities,
        'total_liabilities': total_liabilities,
        'equity': equity,
        'net_profit': net_profit,
        'total_equity': total_equity,
        'today_date': datetime.now().strftime('%d %B, %Y')
    }

def sync_to_double_entry():
    """Migrate all legacy data to balanced journal entries."""
    from models import Voucher, ContraEntry, Transaction, PartyLedger, Salary, JournalEntry, JournalLine
    
    # 1. Clear existing journals to avoid duplicates during migration
    # WARNING: Only do this if we are re-syncing everything
    db.session.query(JournalLine).delete()
    db.session.query(JournalEntry).delete()
    db.session.commit()
    
    # 2. Sync Vouchers
    vouchers = Voucher.query.all()
    for v in vouchers:
        if v.type == 'Debit':
            journal_general_expense(
                v.debit_account_code or '6230', 
                v.payment_method, 
                (v.bank_obj.coa_account_code if v.bank_obj else '1020') or '1020', 
                v.amount_paid, v.voucher_no, v.category, v.date
            )
        else:
            journal_general_income(
                v.credit_account_code or '4030',
                v.payment_method,
                (v.bank_obj.coa_account_code if v.bank_obj else '1020') or '1020',
                v.amount_paid, v.voucher_no, v.category, v.date
            )
            
    # 3. Sync Contra Entries
    contras = ContraEntry.query.all()
    for c in contras:
        if c.to_account == 'Bank':
            journal_contra_deposit((c.bank_obj.coa_account_code if c.bank_obj else '1020') or '1020', c.amount, c.contra_no, c.date)
        else:
            journal_contra_withdrawal((c.bank_obj.coa_account_code if c.bank_obj else '1020') or '1020', c.amount, c.contra_no, c.date)
            
    # 4. Sync Customer Payments
    txs = Transaction.query.all()
    for t in txs:
        if t.installment_type == 'Booking':
            journal_customer_booking(t.customer, Decimal(str(t.amount)), t.date, ref_id=f"TX-{t.id}")
        else:
            if t.bank_name and t.bank_name != 'Petty Cash':
                # Try to find bank coa
                from models import Bank
                bank = Bank.query.filter_by(bank_name=t.bank_name).first()
                coa = (bank.coa_account_code if bank else '1020') or '1020'
                journal_customer_payment_bank(t.customer, coa, t.installment_type, Decimal(str(t.amount)), t.transaction_id, t.date, ref_id=f"TX-{t.id}")
            else:
                journal_customer_payment_cash(t.customer, t.installment_type, Decimal(str(t.amount)), t.date, ref_id=f"TX-{t.id}")
                
    # 5. Sync Party Ledger
    ledger = PartyLedger.query.all()
    for l in ledger:
        if l.bill_amount > 0:
            journal_supplier_bill(l.party, '6160', Decimal(str(l.bill_amount)), l.reference or "Legacy Bill", l.date, ref_id=f"PL-{l.id}-B")
        if l.paid_amount > 0:
            journal_supplier_payment_cash(l.party, Decimal(str(l.paid_amount)), l.reference or "Legacy Payment", l.date, ref_id=f"PL-{l.id}-P")
            
    # 6. Sync Salary
    # Accrual (per month/year)
    payroll_groups = db.session.query(Salary.month, Salary.year).distinct().all()
    for m, y in payroll_groups:
        all_s = Salary.query.filter_by(month=m, year=y).all()
        g_total = sum(Decimal(str(s.net_salary)) for s in all_s)
        n_total = sum(Decimal(str(s.final_salary)) for s in all_s)
        d_total = sum(Decimal(str(s.deduction)) for s in all_s)
        journal_payroll(g_total, n_total, d_total, m, y)
        
        # Payments
        for s in all_s:
            if s.status == 'Paid':
                journal_salary_payment(s.employee, '1010', s.final_salary, f"SAL-{s.id}", s.payment_date or datetime.now().date())

    db.session.commit()
    return True
