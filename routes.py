from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from werkzeug.utils import secure_filename
import os
from models import Director, Customer, Transaction, PettyCash, PettyCashCategory, Bank, BankTransaction, Installment, CustomerInstallment
from database import db
from logic import sync_to_excel, restore_from_excel
import pandas as pd
import io
from datetime import datetime
from flask import send_file, jsonify
import random
import string
import json
from telegram_utils import send_telegram_message, send_telegram_document

import threading

def run_in_background(target, app, *args, **kwargs):
    """Universal helper to run a function in a background thread."""
    def run_with_context():
        with app.app_context():
            target(*args, **kwargs)
            
    thread = threading.Thread(target=run_with_context)
    thread.daemon = True
    thread.start()

_global_sync_lock = threading.Lock()

def get_director_initials(name):
    """Generates initials from director name, ignoring special characters."""
    if not name:
        return "DIR"
    
    # Filter for alphanumeric and groups
    clean_name = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in name)
    parts = clean_name.split()
    
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper() if parts else "DI"

def generate_next_customer_id(director_id):
    """Generates next customer ID like AI-01, AH-01 etc."""
    director = Director.query.get(director_id)
    if not director:
        return "CUST-01"
    
    initials = get_director_initials(director.name)
    count = Customer.query.filter_by(director_id=director_id).count()
    return f"{initials}-{count + 1:02d}"

def recalculate_customer_totals(customer):
    """
    Recalculates a customer's total_price, total_paid and due_amount based on
    actual transactions and created installments.
    """
    # 1. Total Paid = Sum of all transactions
    customer.total_paid = sum(t.amount for t in customer.transactions)
    
    # 2. Total Expected = Sum of all CustomerInstallments (true amount owed)
    total_expected = sum(ci.total_amount for ci in customer.installments)
    
    # 3. Sync total_price to reflect true installment total
    #    Only override if installments exist, otherwise keep manual total_price
    if customer.installments:
        customer.total_price = total_expected
    
    # 4. Due = Expected - Paid
    customer.due_amount = total_expected - customer.total_paid
    
    # 5. Sync Director Totals: use total_share (not assigned shares) × installment rates
    director = customer.director
    if director:
        director.total_paid = sum(c.total_paid for c in director.customers)
        # Total expected for director = total_share × sum of all installment amount_per_share
        from models import Installment
        total_rate_per_share = sum(inst.amount_per_share for inst in Installment.query.all())
        director_total_expected = director.total_share * total_rate_per_share
        director.total_due = director_total_expected - director.total_paid
    
    return customer

def background_sync_all(action_name="Data Update"):
    """
    Consolidates all high-latency tasks into a single background thread.
    This prevents multiple threads from competing for SQLite locks or CPU.
    """
    app = current_app._get_current_object()
    
    if not _global_sync_lock.acquire(blocking=False):
        from telegram_utils import log_debug
        log_debug(f"[{action_name}] Sync skipped: A sync is already in progress.")
        return
        
    def sync_task(app_obj):
        try:
            from sync_manager import sync_manager
            from telegram_utils import log_debug
            log_debug(f"Starting Background Tasks due to: {action_name}")
            
            sync_manager.sync_to_sheets()
            
            # 2. Master Excel Sync (Disabled/Moved elsewhere if needed to save time, or we can leave it)
            try:
                sync_to_excel()
            except Exception as e:
                log_debug(f"Background Excel sync failed: {e}")

            # 3. Telegram DB Backup
            try:
                db_path = app_obj.config.get('DATABASE_PATH')
                if db_path and os.path.exists(db_path):
                    from telegram_utils import send_telegram_document
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    caption = f"Backup triggered by: {action_name}\nTime: {timestamp}"
                    send_telegram_document(db_path, caption=caption)
            except Exception as e:
                log_debug(f"Background Telegram sync failed: {e}")
                
        except Exception as e:
             from telegram_utils import log_debug
             log_debug(f"Background Task Error: {e}")
        finally:
             _global_sync_lock.release()

    # Dispatch to thread
    run_in_background(sync_task, app, app)
# For backward compatibility with existing calls, we redefine these to call the consolidated worker
def trigger_sync():
    background_sync_all("Google Sheets Sync")

def trigger_excel_sync():
    background_sync_all("Excel Sync")

def backup_to_telegram(action_name="Database Update"):
    background_sync_all(action_name)

main = Blueprint('main', __name__)

@main.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main.route('/')
def index():
    directors = Director.query.all()
    
    # Calculate Grand Totals (from all customers)
    customers = Customer.query.all()
    grand_total_payable = sum(c.total_price for c in customers)
    grand_total_paid = sum(c.total_paid for c in customers)
    # Total Due = Sum of all individual customer dues
    grand_total_due = sum(c.due_amount for c in customers)
    # Total Outstanding = Total Project Value - Total Collection (Total remaining to be collected)
    grand_total_outstanding = grand_total_payable - grand_total_paid
        
    # Financial Overview Calculation
    total_bank_balance = sum(tx.credit - tx.debit for tx in BankTransaction.query.all())
    
    cash_income = sum(pc.amount for pc in PettyCash.query.filter_by(type='Income').all())
    cash_expense = sum(pc.amount for pc in PettyCash.query.filter_by(type='Expense').all())
    cash_in_hand = cash_income - cash_expense

    # Chart Data (Last 6 Months)
    from collections import defaultdict
    income_by_month = defaultdict(float)
    expense_by_month = defaultdict(float)
    
    def get_month_key(date_str):
        if not date_str: return None
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m')
            except ValueError:
                pass
        return None

    # 1. Customer Transactions (Income)
    for tx in Transaction.query.all():
        m = get_month_key(tx.date)
        if m: income_by_month[m] += tx.amount
        
    # 2. Bank Transactions
    for tx in BankTransaction.query.all():
        m = get_month_key(tx.date)
        if m:
            income_by_month[m] += tx.credit
            expense_by_month[m] += tx.debit
            
    # 3. Petty Cash
    for pc in PettyCash.query.all():
        m = get_month_key(pc.date)
        if m:
            if pc.type == 'Income': income_by_month[m] += pc.amount
            else: expense_by_month[m] += pc.amount

    # Prepare labels and values for the last 6 months
    import calendar
    from datetime import date
    chart_labels = []
    chart_income = []
    chart_expense = []
    
    current_date = date.today().replace(day=1)
    for _ in range(6):
        m_key = current_date.strftime('%Y-%m')
        chart_labels.insert(0, calendar.month_name[current_date.month][:3] + " " + str(current_date.year)[2:])
        chart_income.insert(0, income_by_month[m_key])
        chart_expense.insert(0, expense_by_month[m_key])
        # Move to previous month
        if current_date.month == 1:
            current_date = current_date.replace(year=current_date.year - 1, month=12)
        else:
            current_date = current_date.replace(month=current_date.month - 1)

    return render_template('index.html', directors=directors, 
                         grand_total_payable=grand_total_payable, 
                         grand_total_paid=grand_total_paid, 
                         grand_total_due=grand_total_due,
                         grand_total_outstanding=grand_total_outstanding,
                         total_bank_balance=total_bank_balance,
                         cash_in_hand=cash_in_hand,
                         chart_labels=chart_labels,
                         chart_income=chart_income,
                         chart_expense=chart_expense,
                         installments=Installment.query.order_by(Installment.created_at).all())

def verify_password():
    password = request.form.get('admin_password')
    admin_pass = current_app.config.get('ADMIN_PASSWORD')
    if password == admin_pass:
        return True
    return False

# --- OTP Store (In-Memory for simplicity) ---
otp_store = {}

@main.route('/change_password_request', methods=['GET', 'POST'])
def change_password_request():
    if request.method == 'POST':
        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        
        if send_telegram_message(f"Your OTP for Password Change is: {otp}"):
            otp_store['current_otp'] = otp
            flash('OTP sent to Telegram!', 'info')
            return redirect(url_for('main.verify_otp_page'))
        else:
            flash('Failed to send OTP. Check internet or bot config.', 'danger')
            
    return render_template('change_password_request.html')

@main.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp_page():
    if request.method == 'POST':
        user_otp = request.form.get('otp')
        new_password = request.form.get('new_password')
        
        if 'current_otp' in otp_store and otp_store['current_otp'] == user_otp:
            # Update Password
            # Use DATA_FOLDER to ensure persistence
            data_folder = current_app.config.get('DATA_FOLDER', current_app.root_path)
            config_path = os.path.join(data_folder, 'admin_config.json')
            
            try:
                with open(config_path, 'w') as f:
                    json.dump({"ADMIN_PASSWORD": new_password}, f)
            except Exception as e:
                flash(f'Error saving password: {e}', 'danger')
                return redirect(url_for('main.index'))
            
            # Update Runtime Config
            current_app.config['ADMIN_PASSWORD'] = new_password
            
            # Clear OTP
            del otp_store['current_otp']
            
            flash('Password Changed Successfully!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Invalid OTP!', 'danger')
            
    return render_template('verify_otp.html')


# --- Director Routes ---
@main.route('/director/add', methods=['GET', 'POST'])
def add_director():
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.add_director'))

        name = request.form.get('name')
        phone = request.form.get('phone')
        
        if name:
            new_director = Director(
                name=name, 
                phone=phone,
                bank_name=request.form.get('bank_name'),
                total_share=float(request.form.get('total_share') or 0),
                per_share_value=0,
                fair_cost=0,
                land_value_extra_share=0,
                total_paid=0,
                total_due=0,
                payment_history=request.form.get('payment_history')
            )
            # No calculation needed for new empty director
            db.session.add(new_director)
            db.session.commit()
            trigger_excel_sync()
            trigger_sync()
            backup_to_telegram("Added Director: " + name)
            flash('Director added successfully!', 'success')
            return redirect(url_for('main.index'))
    return render_template('director_form.html')

@main.route('/director/edit/<int:id>', methods=['GET', 'POST'])
def edit_director(id):
    director = Director.query.get_or_404(id)
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.edit_director', id=id))

        director.name = request.form.get('name')
        director.phone = request.form.get('phone')
        director.bank_name = request.form.get('bank_name')
        director.total_share = float(request.form.get('total_share') or 0)
        director.per_share_value = float(request.form.get('per_share_value') or 0)
        director.fair_cost = float(request.form.get('fair_cost') or 0)
        director.land_value_extra_share = float(request.form.get('land_value_extra_share') or 0)
        # total_paid and total_due are handled by background sync or manual recalculation
        
        # Recalculate Totals from Customers
        director.total_paid = sum(c.total_paid for c in director.customers)
        director.total_due = sum(c.due_amount for c in director.customers)

        db.session.commit()
        trigger_excel_sync()
        trigger_sync()
        backup_to_telegram("Edited Director: " + director.name)
        flash('Director updated successfully!', 'success')
        return redirect(url_for('main.index'))
    return render_template('director_form.html', director=director)

@main.route('/director/delete/<int:id>', methods=['POST'])
def delete_director(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.index'))

    director = Director.query.get_or_404(id)
    # Optional: logic to handle orphaned customers (delete or unlink). 
    # For now, let's assume we delete them or db cascade (we didn't set cascade).
    # Ideally we should warn user. But per request, simple Remove.
    # Let's delete customers first manually if constraints exist
    for customer in director.customers:
        db.session.delete(customer)
        
    db.session.delete(director)
    db.session.commit()
    trigger_excel_sync()
    trigger_sync()
    backup_to_telegram("Deleted Director: " + director.name)
    flash('Director and their customers removed!', 'info')
    return redirect(url_for('main.index'))


# --- Customer Routes ---
@main.route('/customer/add', methods=['GET', 'POST'])
def add_customer():
    directors = Director.query.all()
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.add_customer'))

        # Extraction
        director_id = request.form.get('director_id')
        customer_id = request.form.get('customer_id')
        name = request.form.get('name')
        phone = request.form.get('phone')
        father_name = request.form.get('father_name')
        mother_name = request.form.get('mother_name')
        dob = request.form.get('dob')
        religion = request.form.get('religion')
        profession = request.form.get('profession')
        nid_no = request.form.get('nid_no')
        present_address = request.form.get('present_address')
        permanent_address = request.form.get('permanent_address')
        plot_no = request.form.get('plot_no')
        total_price = float(request.form.get('total_price') or 0)
        down_payment = float(request.form.get('down_payment') or 0)
        monthly_installment = float(request.form.get('monthly_installment') or 0)
        total_paid = float(request.form.get('total_paid') or 0)
        shares = float(request.form.get('shares') or 0)
        
        # Validation: Check Director Shares
        director = Director.query.get(director_id)
        if shares > director.available_shares:
            flash(f'Error: Director only has {director.available_shares} shares available.', 'danger')
            return redirect(url_for('main.add_customer'))

        if not customer_id:
            customer_id = generate_next_customer_id(director_id)

        # Calculation
        new_customer = Customer(
            director_id=director_id,
            customer_id=customer_id,
            name=name,
            phone=phone,
            father_name=father_name,
            mother_name=mother_name,
            dob=dob,
            religion=religion,
            profession=profession,
            nid_no=nid_no,
            present_address=present_address,
            permanent_address=permanent_address,
            plot_no=plot_no,
            total_price=total_price,
            down_payment=down_payment,
            monthly_installment=monthly_installment,
            total_paid=total_paid,
            due_amount=0, # Will be recalculated
            shares=shares
        )
        db.session.add(new_customer)
        db.session.flush() # Get ID
        
        # Initial recalculation
        recalculate_customer_totals(new_customer)
        
        db.session.commit()
        trigger_excel_sync()
        trigger_sync()
        backup_to_telegram("Added Customer: " + name)
        flash('Customer added successfully!', 'success')
        return redirect(url_for('main.index'))
        
    return render_template('customer_form.html', directors=directors)

@main.route('/customer/edit/<int:id>', methods=['GET', 'POST'])
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    directors = Director.query.all()
    
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.edit_customer', id=id))

        old_director = Director.query.get(customer.director_id)
        new_director_id = request.form.get('director_id')
        new_director = Director.query.get(new_director_id)
        new_shares = float(request.form.get('shares') or 0)

        # Validation: Check Available Shares (adjusting for current shares)
        available = new_director.available_shares + (customer.shares if old_director.id == new_director.id else 0)
        if new_shares > available:
            flash(f'Error: Director only has {available} shares available.', 'danger')
            return redirect(url_for('main.edit_customer', id=id))

        # Revert old values for Director
        old_director.total_paid -= customer.total_paid
        
        customer.director_id = new_director_id
        customer.customer_id = request.form.get('customer_id')
        customer.name = request.form.get('name')
        customer.phone = request.form.get('phone')
        customer.father_name = request.form.get('father_name')
        customer.mother_name = request.form.get('mother_name')
        customer.dob = request.form.get('dob')
        customer.religion = request.form.get('religion')
        customer.profession = request.form.get('profession')
        customer.nid_no = request.form.get('nid_no')
        customer.present_address = request.form.get('present_address')
        customer.permanent_address = request.form.get('permanent_address')
        customer.plot_no = request.form.get('plot_no')
        customer.total_price = float(request.form.get('total_price') or 0)
        customer.down_payment = float(request.form.get('down_payment') or 0)
        customer.monthly_installment = float(request.form.get('monthly_installment') or 0)
        customer.total_paid = float(request.form.get('total_paid') or 0)
        customer.shares = new_shares
        
        # Calc Due
        customer.due_amount = customer.total_price - customer.total_paid
        
        # Update New Director
        new_director.total_paid += customer.total_paid
        
        # Recalculate Both Directors
        for d in [old_director, new_director]:
            d.total_paid = sum(c.total_paid for c in d.customers)
            d.total_due = sum(c.due_amount for c in d.customers)

        db.session.commit()
        trigger_excel_sync()
        trigger_sync()
        backup_to_telegram("Edited Customer: " + customer.name)
        flash('Customer updated successfully!', 'success')
        return redirect(url_for('main.index'))
        
    return render_template('customer_form.html', customer=customer, directors=directors)

@main.route('/delete_customer/<int:id>', methods=['POST'])
def delete_customer(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.index'))

    customer = Customer.query.get_or_404(id)
    director = Director.query.get(customer.director_id)
    
    # Update Director Totals
    director.total_paid = sum(c.total_paid for c in director.customers if c.id != customer.id)
    director.total_due = sum(c.due_amount for c in director.customers if c.id != customer.id)

    db.session.delete(customer)
    db.session.commit()
    # Sync to Excel
    trigger_excel_sync()
    trigger_sync()
    backup_to_telegram("Deleted Customer")
    flash('Customer deleted!', 'success')
    return redirect(url_for('main.index'))

# --- Installment Management ---
@main.route('/installment/create', methods=['POST'])
def create_installment():
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.index'))
    
    name = request.form.get('name')
    amount_per_share = float(request.form.get('amount_per_share') or 0)
    
    if name and amount_per_share > 0:
        new_inst = Installment(name=name, amount_per_share=amount_per_share)
        db.session.add(new_inst)
        db.session.flush() # Get ID
        
        # Generate for all customers
        customers = Customer.query.all()
        for c in customers:
            total_amt = c.shares * amount_per_share
            if total_amt > 0:
                cust_inst = CustomerInstallment(
                    customer_id=c.id,
                    installment_id=new_inst.id,
                    total_amount=total_amt,
                    due_amount=total_amt
                )
                db.session.add(cust_inst)
            # Ensure totals are correct for this customer
            recalculate_customer_totals(c)
        
        db.session.commit()
        flash(f'Installment "{name}" created for all applicable customers.', 'success')
    else:
        flash('Invalid Installment Name or Amount.', 'danger')
        
    return redirect(url_for('main.index'))

@main.route('/installment/edit/<int:id>', methods=['POST'])
def edit_installment(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.index'))

    inst = Installment.query.get_or_404(id)
    new_name = request.form.get('name', '').strip()
    new_amount = float(request.form.get('amount_per_share') or 0)

    if not new_name or new_amount <= 0:
        flash('Invalid name or amount.', 'danger')
        return redirect(url_for('main.index'))

    inst.name = new_name
    inst.amount_per_share = new_amount

    # Recalculate all CustomerInstallment records for this installment
    for ci in inst.customer_installments:
        ci.total_amount = ci.customer.shares * new_amount
        ci.due_amount = ci.total_amount - ci.paid_amount

    db.session.flush()

    # Recalculate all affected customers
    affected_customers = set(ci.customer for ci in inst.customer_installments)
    for c in affected_customers:
        recalculate_customer_totals(c)

    # Recalculate all director dues using total_share
    total_rate_per_share = sum(i.amount_per_share for i in Installment.query.all())
    from models import Director as Dir
    for d in Dir.query.all():
        d.total_paid = sum(c.total_paid for c in d.customers)
        d.total_due = d.total_share * total_rate_per_share - d.total_paid

    db.session.commit()
    backup_to_telegram("Edited Installment")
    flash(f'Installment "{inst.name}" updated and all totals recalculated.', 'success')
    return redirect(url_for('main.index'))


@main.route('/installment/delete/<int:id>', methods=['POST'])
def delete_installment(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.index'))

    inst = Installment.query.get_or_404(id)
    inst_name = inst.name

    # Collect affected customers before deleting
    affected_customers = set(ci.customer for ci in inst.customer_installments)

    # Delete the installment (cascade deletes CustomerInstallment records via model)
    db.session.delete(inst)
    db.session.flush()

    # Recalculate customer totals now that installment is removed
    for c in affected_customers:
        recalculate_customer_totals(c)

    # Recalculate all director dues
    total_rate_per_share = sum(i.amount_per_share for i in Installment.query.all())
    from models import Director as Dir
    for d in Dir.query.all():
        d.total_paid = sum(c.total_paid for c in d.customers)
        d.total_due = d.total_share * total_rate_per_share - d.total_paid

    db.session.commit()
    backup_to_telegram("Deleted Installment")
    flash(f'Installment "{inst_name}" deleted and all totals recalculated.', 'success')
    return redirect(url_for('main.index'))

@main.route('/manage_transactions/<int:customer_id>', methods=['GET', 'POST'])
def manage_transactions(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.manage_transactions', customer_id=customer_id))

        date = request.form.get('date')
        amount = float(request.form.get('amount') or 0)
        installment_type = request.form.get('installment_type')
        cust_inst_id = request.form.get('customer_installment_id') or None
        transaction_id = request.form.get('transaction_id')
        remarks = request.form.get('remarks')
        payment_source = request.form.get('payment_source', 'cash')  # 'bank', 'petty_cash', or 'cash'
        
        # Payment source specific fields
        bank_id = request.form.get('bank_id') or None
        bank_name = request.form.get('bank_name', '')
        cheque_no = request.form.get('cheque_no', '')
        bank_narration = request.form.get('bank_narration', '')
        bank_remarks = request.form.get('bank_remarks', '')
        petty_cash_desc = request.form.get('petty_cash_desc', f'Payment from {customer.name}')
        petty_cash_category = request.form.get('petty_cash_category', 'Customer Payment')
        
        # Merge remarks: bank_remarks takes priority when bank is selected
        if payment_source == 'bank' and bank_remarks:
            remarks = bank_remarks
        
        # Handle Images
        images = []
        if 'evidence' in request.files:
            files = request.files.getlist('evidence')
            for file in files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    images.append(filename)
        
        # Determine bank_name to store on transaction
        if payment_source == 'bank' and bank_id:
            selected_bank = Bank.query.get(bank_id)
            if selected_bank:
                bank_name = selected_bank.bank_name
        elif payment_source == 'petty_cash':
            bank_name = 'Petty Cash'
        
        new_tx = Transaction(
            date=date,
            amount=amount,
            installment_type=installment_type,
            bank_name=bank_name,
            transaction_id=transaction_id,
            remarks=remarks,
            customer_id=customer_id,
            customer_installment_id=cust_inst_id,
            images=','.join(images)
        )
        db.session.add(new_tx)
        
        # Update Customer Totals
        customer.total_paid += amount
        customer.due_amount = customer.total_price - customer.total_paid
        
        # Update Director Totals
        director = Director.query.get(customer.director_id)
        director.total_paid = sum(c.total_paid for c in director.customers)
        director.total_due = sum(c.due_amount for c in director.customers)

        # Update Specific Installment if selected
        if cust_inst_id:
            cust_inst = CustomerInstallment.query.get(cust_inst_id)
            if cust_inst:
                cust_inst.paid_amount += amount
                cust_inst.due_amount = cust_inst.total_amount - cust_inst.paid_amount
                # Mirror installment name if not set
                if not new_tx.installment_type:
                    new_tx.installment_type = cust_inst.installment.name

        # Handle Payment Source: update bank balance or petty cash
        if payment_source == 'bank' and bank_id:
            selected_bank = Bank.query.get(bank_id)
            if selected_bank:
                # Calculate running balance
                last_tx = BankTransaction.query.filter_by(bank_id=selected_bank.id).order_by(BankTransaction.id.desc()).first()
                running_balance = (last_tx.balance if last_tx else 0) + amount
                bank_tx = BankTransaction(
                    date=date,
                    cheque_no=cheque_no or None,
                    ref_no=transaction_id or None,
                    narration=bank_narration or f'Customer Payment - {customer.name} ({customer.customer_id})',
                    transaction_details=installment_type or 'Customer Payment',
                    credit=amount,
                    debit=0,
                    balance=running_balance,
                    bank_id=selected_bank.id
                )
                db.session.add(bank_tx)
        elif payment_source == 'petty_cash':
            pc_entry = PettyCash(
                date=date,
                description=petty_cash_desc or f'Customer Payment - {customer.name}',
                category=petty_cash_category or 'Customer Payment',
                type='Income',
                amount=amount
            )
            db.session.add(pc_entry)
        
        db.session.commit()

        # Recalculate everything
        recalculate_customer_totals(customer)
        db.session.commit()

        trigger_excel_sync()
        trigger_sync()
        backup_to_telegram("Added Transaction for Customer: " + customer.name)
        flash('Transaction Added!', 'success')
        return redirect(url_for('main.manage_transactions', customer_id=customer_id))
        
    transactions = Transaction.query.filter_by(customer_id=customer_id).all()
    # Fetch active installments for this customer
    customer_installments = CustomerInstallment.query.filter_by(customer_id=customer_id).all()
    banks = Bank.query.filter_by(status='Active').all()
    # Seed categories if empty
    if PettyCashCategory.query.count() == 0:
        defaults = ["Bank", "Customer Payment", "Entertainment", "Food", "Maintenance",
                    "Marketing", "Office", "Repair", "Salary", "Stationery", "Transport",
                    "Travel", "Utility"]
        for d in defaults:
            db.session.add(PettyCashCategory(name=d))
        db.session.commit()
    petty_cash_categories = [c.name for c in PettyCashCategory.query.order_by(PettyCashCategory.name).all()]

    return render_template('customer_transactions.html', 
                         customer=customer, 
                         transactions=transactions, 
                         customer_installments=customer_installments,
                         banks=banks,
                         petty_cash_categories=petty_cash_categories)

@main.route('/delete_transaction/<int:id>', methods=['GET', 'POST'])
def delete_transaction(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        tx = Transaction.query.get(id)
        if tx:
             return redirect(url_for('main.manage_transactions', customer_id=tx.customer_id))
        return redirect(url_for('main.index'))

    tx = Transaction.query.get_or_404(id)
    customer_id = tx.customer_id
    customer = Customer.query.get(customer_id)
    
    # Revert Installment if associated
    if tx.customer_installment_id:
        ci = CustomerInstallment.query.get(tx.customer_installment_id)
        if ci:
            ci.paid_amount -= tx.amount
            ci.due_amount = ci.total_amount - ci.paid_amount
    
    db.session.delete(tx)
    db.session.commit()
    
    # Final Recalculation
    recalculate_customer_totals(customer)
    db.session.commit()
    
    trigger_excel_sync()
    trigger_sync()
    backup_to_telegram("Deleted Transaction for: " + customer.name)
    flash('Transaction Deleted!', 'warning')
    return redirect(url_for('main.manage_transactions', customer_id=customer_id))

@main.route('/transaction/edit/<int:id>', methods=['POST'])
def edit_transaction_details(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        # We need customer_id to redirect
        tx = Transaction.query.get(id)
        if tx:
            # Revert to manage page if possible
            return redirect(url_for('main.manage_transactions', customer_id=tx.customer_id))
        return redirect(url_for('main.index'))

    tx = Transaction.query.get_or_404(id)
    customer = Customer.query.get(tx.customer_id)
    
    # 1. Revert Old Amount from Customer Totals
    customer.total_paid -= tx.amount
    
    # 2. Update Transaction Data
    tx.date = request.form.get('date')
    tx.amount = float(request.form.get('amount') or 0)
    tx.installment_type = request.form.get('installment_type')
    tx.bank_name = request.form.get('bank_name')
    tx.transaction_id = request.form.get('transaction_id')
    tx.remarks = request.form.get('remarks')
    
    # 3. Handle New Images (Append)
    if 'evidence' in request.files:
        files = request.files.getlist('evidence')
        new_images = []
        for file in files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                new_images.append(filename)
        
        if new_images:
            current_images = tx.images.split(',') if tx.images else []
            updated_images = current_images + new_images
            tx.images = ','.join(updated_images)
            
    # 4. Apply New Amount to Customer Totals
    customer.total_paid += tx.amount
    customer.due_amount = customer.total_price - customer.total_paid
    
    db.session.commit()
    trigger_excel_sync()
    trigger_sync()
    backup_to_telegram("Edited Transaction")
    flash('Transaction Updated!', 'success')
    return redirect(url_for('main.manage_transactions', customer_id=customer.id))


# --- Petty Cash Routes ---
@main.route('/petty_cash', methods=['GET', 'POST'])
def manage_petty_cash():
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.manage_petty_cash'))

        date = request.form.get('date')
        description = request.form.get('description')
        category = request.form.get('category')
        type = request.form.get('type')
        amount = float(request.form.get('amount') or 0)
        
        # Handle Evidence Files
        images = []
        if 'evidence' in request.files:
            files = request.files.getlist('evidence')
            for file in files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    # Optional: Add timestamp/UUID to filename to prevent collisions?
                    # For now keeping it simple as per previous pattern
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    images.append(filename)
        
        new_entry = PettyCash(
            date=date,
            description=description,
            category=category,
            type=type,
            amount=amount,
            images=','.join(images)
        )
        db.session.add(new_entry)
        db.session.commit()
        trigger_excel_sync()
        trigger_sync()
        backup_to_telegram("Added Petty Cash: " + description)
        flash('Petty Cash Entry Added!', 'success')
        return redirect(url_for('main.manage_petty_cash'))
        
    # Filter Logic
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    filter_category = request.args.get('category')
    
    query = PettyCash.query
    
    if start_date:
        query = query.filter(PettyCash.date >= start_date)
    if end_date:
        query = query.filter(PettyCash.date <= end_date)
    if filter_category and filter_category != 'All':
        query = query.filter(PettyCash.category == filter_category)
        
    entries = query.order_by(PettyCash.date.desc()).all()

    # Use managed PettyCashCategory table; seed defaults if empty
    if PettyCashCategory.query.count() == 0:
        defaults = ["Bank", "Customer Payment", "Entertainment", "Food", "Maintenance",
                    "Marketing", "Office", "Repair", "Salary", "Stationery", "Transport",
                    "Travel", "Utility"]
        for d in defaults:
            db.session.add(PettyCashCategory(name=d))
        db.session.commit()

    available_categories = [c.name for c in PettyCashCategory.query.order_by(PettyCashCategory.name).all()]

    total_income = sum(e.amount for e in entries if e.type == 'Income')
    total_expense = sum(e.amount for e in entries if e.type == 'Expense')
    current_balance = total_income - total_expense
    
    pc_categories = PettyCashCategory.query.order_by(PettyCashCategory.name).all()
    return render_template('petty_cash.html', entries=entries, 
                         total_income=total_income, 
                         total_expense=total_expense, 
                         current_balance=current_balance,
                         available_categories=available_categories,
                         pc_categories=pc_categories)

# --- Petty Cash Category CRUD ---
@main.route('/petty_cash/category/add', methods=['POST'])
def add_petty_cash_category():
    name = request.form.get('name', '').strip()
    if name:
        existing = PettyCashCategory.query.filter_by(name=name).first()
        if not existing:
            db.session.add(PettyCashCategory(name=name))
            db.session.commit()
            flash(f'Category "{name}" added!', 'success')
        else:
            flash(f'Category "{name}" already exists.', 'warning')
    return redirect(url_for('main.manage_petty_cash'))

@main.route('/petty_cash/category/edit/<int:id>', methods=['POST'])
def edit_petty_cash_category(id):
    cat = PettyCashCategory.query.get_or_404(id)
    new_name = request.form.get('name', '').strip()
    if new_name and new_name != cat.name:
        old_name = cat.name
        cat.name = new_name
        # Also update all existing PettyCash entries with this category
        PettyCash.query.filter_by(category=old_name).update({'category': new_name})
        db.session.commit()
        flash(f'Category renamed to "{new_name}".', 'success')
    return redirect(url_for('main.manage_petty_cash'))

@main.route('/petty_cash/category/delete/<int:id>', methods=['POST'])
def delete_petty_cash_category(id):
    cat = PettyCashCategory.query.get_or_404(id)
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    flash(f'Category "{name}" deleted.', 'info')
    return redirect(url_for('main.manage_petty_cash'))

@main.route('/petty_cash/categories', methods=['GET'])
def get_petty_cash_categories():
    """JSON endpoint for category list (used by customer_transactions form)."""
    cats = [c.name for c in PettyCashCategory.query.order_by(PettyCashCategory.name).all()]
    from flask import jsonify
    return jsonify(cats)

@main.route('/petty_cash/export')
def export_petty_cash_report():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    filter_category = request.args.get('category')
    
    query = PettyCash.query
    
    if start_date:
        query = query.filter(PettyCash.date >= start_date)
    if end_date:
        query = query.filter(PettyCash.date <= end_date)
    if filter_category and filter_category != 'All':
        query = query.filter(PettyCash.category == filter_category)
        
    entries = query.order_by(PettyCash.date.desc()).all()
    
    try:
        data = []
        for e in entries:
            data.append({
                'Date': e.date,
                'Description': e.description,
                'Category': e.category,
                'Type': e.type,
                'Income': e.amount if e.type == 'Income' else 0,
                'Expense': e.amount if e.type == 'Expense' else 0,
                'Images': e.images
            })
            
        df = pd.DataFrame(data)
        
        # Calculate totals for the report
        total_income = df['Income'].sum() if not df.empty else 0
        total_expense = df['Expense'].sum() if not df.empty else 0
        
        # Append Total Row
        if not df.empty:
            df.loc['Total'] = pd.Series(dtype='float64')
            df.at['Total', 'Description'] = 'TOTAL'
            df.at['Total', 'Income'] = total_income
            df.at['Total', 'Expense'] = total_expense
            df.at['Total', 'Category'] = f'Balance: {total_income - total_expense}'
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Petty_Cash_Report', index=False)
            # Polish width
            worksheet = writer.sheets['Petty_Cash_Report']
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

        output.seek(0)
        return send_file(output, download_name="Petty_Cash_Report.xlsx", as_attachment=True)
    except Exception as e:
        from telegram_utils import log_debug
        log_debug(f"Excel Export Error (Petty Cash): {e}")
        import traceback
        log_debug(traceback.format_exc())
        flash(f"Error exporting Excel: {e}", "danger")
        return redirect(url_for('main.manage_petty_cash'))

@main.route('/delete_petty_cash/<int:id>', methods=['POST'])
def delete_petty_cash(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.manage_petty_cash'))

    entry = PettyCash.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    trigger_excel_sync()
    trigger_sync()
    backup_to_telegram("Deleted Petty Cash")
    flash('Entry Deleted!', 'info')
    return redirect(url_for('main.manage_petty_cash'))

@main.route('/petty_cash/invoice/<int:id>')
def invoice_view(id):
    entry = PettyCash.query.get_or_404(id)
    return render_template('invoice.html', entry=entry, now=datetime.now())

@main.route('/petty_cash/edit/<int:id>', methods=['POST'])
def edit_petty_cash(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.manage_petty_cash'))

    entry = PettyCash.query.get_or_404(id)
    
    entry.date = request.form.get('date')
    entry.description = request.form.get('description')
    entry.category = request.form.get('category')
    entry.type = request.form.get('type')
    entry.amount = float(request.form.get('amount') or 0)
    
    # Handle New Evidence Files (Append to existing?)
    # For simplicity, if new files are uploaded, we append them.
    if 'evidence' in request.files:
        files = request.files.getlist('evidence')
        new_images = []
        for file in files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                new_images.append(filename)
        
        if new_images:
            current_images = entry.images.split(',') if entry.images else []
            updated_images = current_images + new_images
            entry.images = ','.join(updated_images)
            
    db.session.commit()
    trigger_excel_sync()
    trigger_sync()
    backup_to_telegram("Edited Petty Cash")
    flash('Entry Updated Successfully!', 'success')
    return redirect(url_for('main.manage_petty_cash'))

@main.route('/report/download')
def download_report():
    # Generate a summary report
    # Group by Director, Sum Collection (Total Paid), Outstanding (Due Amount)
    
    directors = Director.query.all()
    report_data = []
    
    try:
        grand_total_collection = 0
        grand_total_due = 0
        
        for d in directors:
            d_collection = sum(c.total_paid for c in d.customers)
            d_due = sum(c.due_amount for c in d.customers)
            
            grand_total_collection += d_collection
            grand_total_due += d_due
            
            report_data.append({
                'Director': d.name,
                'Total Collection': d_collection,
                'Total Outstanding Dues': d_due
            })
            
        # Append Grand Total
        report_data.append({
            'Director': 'GRAND TOTAL',
            'Total Collection': grand_total_collection,
            'Total Outstanding Dues': grand_total_due
        })
        
        df = pd.DataFrame(report_data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Summary_Report', index=False)
            
            # Polish width
            worksheet = writer.sheets['Summary_Report']
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

        output.seek(0)
        
        return send_file(output, download_name="Summary_Report.xlsx", as_attachment=True)
    except Exception as e:
        from telegram_utils import log_debug
        log_debug(f"Excel Export Error (Summary Report): {e}")
        import traceback
        log_debug(traceback.format_exc())
        flash(f"Error exporting Excel: {e}", "danger")
        return redirect(url_for('main.index'))

# --- Excel Helper ---
def format_excel_width(writer, sheet_name):
    """Helper to auto-adjust column width for Excel sheets."""
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

# --- New Customer Reports ---

def save_and_open_excel(output_bytes, filename):
    """
    Saves an Excel BytesIO to the user's Documents/NexusRiverView folder
    and opens it automatically. This works inside pywebview where send_file downloads don't work.
    Returns (saved_path, error_msg).
    """
    import os, subprocess
    try:
        docs_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'NexusRiverView')
        os.makedirs(docs_dir, exist_ok=True)
        save_path = os.path.join(docs_dir, filename)
        with open(save_path, 'wb') as f:
            f.write(output_bytes.read())
        os.startfile(save_path)  # Opens with Excel
        return save_path, None
    except Exception as e:
        return None, str(e)

@main.route('/report/customers/all')
def download_all_customers_report():
    from telegram_utils import log_debug
    try:
        customers = Customer.query.join(Director).order_by(Director.name, Customer.customer_id).all()
        if not customers:
            log_debug("WARNING: Customer.query.join(Director) returned 0 customers. Checking without join...")
            customers = Customer.query.order_by(Customer.customer_id).all()
        
        log_debug(f"Export All: Found {len(customers)} customers.")
        
        # Check total counts
        all_c = Customer.query.count()
        all_d = Director.query.count()
        log_debug(f"Total in DB: Customers={all_c}, Directors={all_d}")
        installments = Installment.query.order_by(Installment.id).all()
        inst_names = [inst.name for inst in installments]
        data = []
        for c in customers:
            # Build installment lookup
            ci_map = {ci.installment_id: ci for ci in c.installments}
            row = {
                'Director Name': c.director.name if c.director else '',
                'Customer ID': c.customer_id,
                'Customer Name': c.name,
                'Phone': c.phone,
                'Father Name': c.father_name,
                'Mother Name': c.mother_name,
                'DOB': c.dob,
                'Religion': c.religion,
                'Profession': c.profession,
                'NID No': c.nid_no,
                'Present Address': c.present_address,
                'Permanent Address': c.permanent_address,
                'Plot No': c.plot_no,
                'Shares': int(c.shares) if c.shares == int(c.shares) else c.shares,
            }
            # Add per-installment columns
            for inst in installments:
                ci = ci_map.get(inst.id)
                row[f'{inst.name} (Total)'] = ci.total_amount if ci else 0
                row[f'{inst.name} (Paid)'] = ci.paid_amount if ci else 0
                row[f'{inst.name} (Due)'] = ci.due_amount if ci else 0
            row['Total Price'] = c.total_price
            row['Total Paid'] = c.total_paid
            row['Due Amount'] = c.due_amount
            data.append(row)

        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='All_Customers', index=False)
            format_excel_width(writer, 'All_Customers')
        output.seek(0)
        filename = f"All_Customers_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path, err = save_and_open_excel(output, filename)
        if err:
            flash(f"Export failed: {err}", "danger")
        else:
            flash(f"Exported! File saved to Documents/NexusRiverView/{filename}", "success")
        return redirect(url_for('main.index'))
    except Exception as e:
        from telegram_utils import log_debug
        log_debug(f"Excel Export Error (All Customers): {e}")
        import traceback
        log_debug(traceback.format_exc())
        flash(f"Error exporting Excel: {e}", "danger")
        return redirect(url_for('main.index'))

@main.route('/report/director/<int:id>/customers')
def download_director_customers_report(id):
    director = Director.query.get_or_404(id)
    customers = director.customers
    
    try:
        installments = Installment.query.order_by(Installment.id).all()
        data = []
        for c in customers:
            ci_map = {ci.installment_id: ci for ci in c.installments}
            row = {
                'Customer ID': c.customer_id,
                'Customer Name': c.name,
                'Phone': c.phone,
                'Father Name': c.father_name,
                'Mother Name': c.mother_name,
                'DOB': c.dob,
                'Religion': c.religion,
                'Profession': c.profession,
                'NID No': c.nid_no,
                'Present Address': c.present_address,
                'Permanent Address': c.permanent_address,
                'Plot No': c.plot_no,
                'Shares': int(c.shares) if c.shares == int(c.shares) else c.shares,
            }
            for inst in installments:
                ci = ci_map.get(inst.id)
                row[f'{inst.name} (Total)'] = ci.total_amount if ci else 0
                row[f'{inst.name} (Paid)'] = ci.paid_amount if ci else 0
                row[f'{inst.name} (Due)'] = ci.due_amount if ci else 0
            row['Total Price'] = c.total_price
            row['Total Paid'] = c.total_paid
            row['Due Amount'] = c.due_amount
            data.append(row)
            
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Customers', index=False)
            format_excel_width(writer, 'Customers')
        output.seek(0)
        filename = f"Director_{secure_filename(director.name)}_Customers_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path, err = save_and_open_excel(output, filename)
        if err:
            flash(f"Export failed: {err}", "danger")
        else:
            flash(f"Exported! File saved to Documents/NexusRiverView/{filename}", "success")
        return redirect(url_for('main.index'))
    except Exception as e:
        from telegram_utils import log_debug
        log_debug(f"Excel Export Error (Director Customers): {e}")
        import traceback
        log_debug(traceback.format_exc())
        flash(f"Error exporting Excel: {e}", "danger")
        return redirect(url_for('main.index'))

@main.route('/report/customer/<int:id>')
def download_individual_customer_report(id):
    c = Customer.query.get_or_404(id)
    
    # 1. Profile Data
    profile_data = [{
        'Field': 'Customer ID', 'Value': c.customer_id},
        {'Field': 'Name', 'Value': c.name},
        {'Field': 'Director', 'Value': c.director.name},
        {'Field': 'Phone', 'Value': c.phone},
        {'Field': 'Father Name', 'Value': c.father_name},
        {'Field': 'Mother Name', 'Value': c.mother_name},
        {'Field': 'DOB', 'Value': c.dob},
        {'Field': 'Religion', 'Value': c.religion},
        {'Field': 'Profession', 'Value': c.profession},
        {'Field': 'NID No', 'Value': c.nid_no},
        {'Field': 'Present Address', 'Value': c.present_address},
        {'Field': 'Permanent Address', 'Value': c.permanent_address},
        {'Field': 'Plot No', 'Value': c.plot_no},
        {'Field': 'Total Price', 'Value': c.total_price},
        {'Field': 'Down Payment', 'Value': c.down_payment},
        {'Field': 'Monthly Installment', 'Value': c.monthly_installment},
        {'Field': 'Total Paid', 'Value': c.total_paid},
        {'Field': 'Due Amount', 'Value': c.due_amount}
    ]
    df_profile = pd.DataFrame(profile_data)
    
    # 2. Transactions Data
    tx_data = []
    for tx in c.transactions:
        tx_data.append({
            'Date': tx.date,
            'Amount': tx.amount,
            'Installment Type': tx.installment_type,
            'Bank Name': tx.bank_name,
            'Transaction ID': tx.transaction_id,
            'Remarks': tx.remarks
        })
    df_tx = pd.DataFrame(tx_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_profile.to_excel(writer, sheet_name='Profile', index=False)
        format_excel_width(writer, 'Profile')
        df_tx.to_excel(writer, sheet_name='Transactions', index=False)
        format_excel_width(writer, 'Transactions')
    output.seek(0)
    filename = f"Customer_{secure_filename(c.name)}_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    path, err = save_and_open_excel(output, filename)
    if err:
        flash(f"Export failed: {err}", "danger")
    else:
        flash(f"Exported! File saved to Documents/NexusRiverView/{filename}", "success")
    return redirect(url_for('main.manage_transactions', customer_id=c.id))

# --- Bank Management Routes ---
@main.route('/banks', methods=['GET', 'POST'])
def manage_banks():
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.manage_banks'))

        # Add New Bank
        new_bank = Bank(
            bank_name=request.form.get('bank_name'),
            branch=request.form.get('branch'),
            account_holder_name=request.form.get('account_holder_name'),
            joint_name=request.form.get('joint_name'),
            fhp=request.form.get('fhp'),
            address=request.form.get('address'),
            city=request.form.get('city'),
            phone=request.form.get('phone'),
            customer_id=request.form.get('customer_id'),
            account_no=request.form.get('account_no'),
            prev_account_no=request.form.get('prev_account_no'),
            account_type=request.form.get('account_type'),
            currency=request.form.get('currency'),
            status=request.form.get('status')
        )
        db.session.add(new_bank)
        db.session.commit()
        trigger_excel_sync()
        backup_to_telegram("Added Bank: " + request.form.get('bank_name'))
        flash('Bank Account Added!', 'success')
        return redirect(url_for('main.manage_banks'))
        
    banks = Bank.query.all()
    return render_template('banks.html', banks=banks)

@main.route('/bank/edit/<int:id>', methods=['POST'])
def edit_bank(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.manage_banks'))

    bank = Bank.query.get_or_404(id)
    
    bank.bank_name = request.form.get('bank_name')
    bank.branch = request.form.get('branch')
    bank.account_holder_name = request.form.get('account_holder_name')
    bank.joint_name = request.form.get('joint_name')
    bank.fhp = request.form.get('fhp')
    bank.address = request.form.get('address')
    bank.city = request.form.get('city')
    bank.phone = request.form.get('phone')
    bank.customer_id = request.form.get('customer_id')
    bank.account_no = request.form.get('account_no')
    bank.prev_account_no = request.form.get('prev_account_no')
    bank.account_type = request.form.get('account_type')
    bank.currency = request.form.get('currency')
    bank.status = request.form.get('status')
    
    db.session.commit()
    trigger_excel_sync()
    backup_to_telegram("Edited Bank: " + bank.bank_name)
    flash('Bank Account Updated!', 'success')
    return redirect(url_for('main.manage_banks'))

@main.route('/bank/delete/<int:id>', methods=['POST'])
def delete_bank(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.manage_banks'))

    bank = Bank.query.get_or_404(id)
    db.session.delete(bank)
    db.session.commit()
    trigger_excel_sync()
    backup_to_telegram("Deleted Bank: " + bank.bank_name)
    flash('Bank Account Deleted!', 'warning')
    return redirect(url_for('main.manage_banks'))

@main.route('/bank/<int:id>/ledger', methods=['GET', 'POST'])
def bank_ledger(id):
    bank = Bank.query.get_or_404(id)
    
    # Force recompute on view to ensure existing data is corrected
    recompute_bank_balances(id)
    
    if request.method == 'POST':
        if not verify_password():
            flash('Invalid Admin Password!', 'danger')
            return redirect(url_for('main.bank_ledger', id=id))

        date = request.form.get('date')
        cheque_no = request.form.get('cheque_no')
        ref_no = request.form.get('ref_no')
        narration = request.form.get('narration')
        transaction_details = request.form.get('transaction_details')
        tx_type = request.form.get('tx_type')
        if tx_type == 'credit':
            credit = float(request.form.get('credit') or 0)
            debit = 0.0
        else:
            debit = float(request.form.get('debit') or 0)
            credit = 0.0
        
        # Convert YYYY-MM-DD input to DD-MM-YYYY storage
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            date = date_obj.strftime('%d-%m-%Y')
        except ValueError:
             # Already in format or invalid? keep as is
             pass

        new_tx = BankTransaction(
            date=date,
            cheque_no=cheque_no,
            ref_no=ref_no,
            narration=narration,
            transaction_details=transaction_details,
            debit=debit,
            credit=credit,
            balance=0,
            bank=bank
        )

        db.session.add(new_tx)
        db.session.commit()
        
        # Recompute Balances
        recompute_bank_balances(id)
        
        trigger_excel_sync()
        backup_to_telegram("Added Bank Ledger Tx")
        flash('Transaction Added to Ledger!', 'success')
        return redirect(url_for('main.bank_ledger', id=id))
        
    transactions = BankTransaction.query.filter_by(bank_id=id).all()
    
    # Sort in Python to handle Date Parsing correctly
    # DB Date is String, format DD-MM-YYYY preferred
    def parse_tx_date(tx):
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(tx.date, fmt)
            except ValueError:
                pass
        return datetime.min # Fallback

    transactions.sort(key=lambda x: (parse_tx_date(x), x.id), reverse=True)
    
    # --- Date Filter Logic ---
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    if start_date_str or end_date_str:
        filtered_transactions = []
        
        # Convert filter inputs (YYYY-MM-DD -> datetime)
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None
        
        for tx in transactions:
            try:
                # Use helper or direct parse
                tx_date = parse_tx_date(tx)
                
                # Apply Filter
                if start_date and tx_date < start_date:
                    continue
                if end_date and tx_date > end_date:
                    continue
                
                filtered_transactions.append(tx)
            except ValueError:
                filtered_transactions.append(tx)
                
        transactions = filtered_transactions

    return render_template('bank_ledger.html', bank=bank, transactions=transactions, start_date=start_date_str, end_date=end_date_str)

def recompute_bank_balances(bank_id):
    """
    Recalculates the running balance for all transactions of a specific bank.
    Sorts by Date (asc) and then ID (asc).
    Handles mixed date formats (DD-MM-YYYY vs YYYY-MM-DD).
    """
    transactions = BankTransaction.query.filter_by(bank_id=bank_id).all()
    
    def parse_date(date_str):
        # Prioritize DD-MM-YYYY
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                pass
        return datetime.min

    # Sort transactions (Oldest First for Calculation)
    transactions.sort(key=lambda x: (parse_date(x.date), x.id))
    
    running_balance = 0.0
    for tx in transactions:
        running_balance += (tx.credit - tx.debit)
        tx.balance = running_balance
        
    db.session.commit()

@main.route('/bank/transaction/delete/<int:id>', methods=['POST'])
def delete_bank_transaction(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        # We need bank_id to redirect
        tx = BankTransaction.query.get(id)
        if tx:
            return redirect(url_for('main.bank_ledger', id=tx.bank_id))
        return redirect(url_for('main.manage_banks'))

    tx = BankTransaction.query.get_or_404(id)
    bank_id = tx.bank_id
    
    db.session.delete(tx)
    db.session.commit()
    
    recompute_bank_balances(bank_id)
    
    trigger_excel_sync()
    backup_to_telegram("Deleted Bank Tx: " + (tx.narration or str(id)))
    flash('Transaction Deleted & Balances Recomputed!', 'warning')
    return redirect(url_for('main.bank_ledger', id=bank_id))

@main.route('/bank/transaction/edit/<int:id>', methods=['POST'])
def edit_bank_transaction(id):
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        tx = BankTransaction.query.get(id)
        if tx:
            return redirect(url_for('main.bank_ledger', id=tx.bank_id))
        return redirect(url_for('main.manage_banks'))

    tx = BankTransaction.query.get_or_404(id)
    bank_id = tx.bank_id
    
    # Update Data
    tx.date = request.form.get('date')
    tx.cheque_no = request.form.get('cheque_no')
    tx.ref_no = request.form.get('ref_no')
    tx.narration = request.form.get('narration')
    tx.transaction_details = request.form.get('transaction_details')
    tx_type = request.form.get('tx_type')
    if tx_type == 'credit':
        tx.credit = float(request.form.get('credit') or 0)
        tx.debit = 0.0
    else:
        tx.debit = float(request.form.get('debit') or 0)
        tx.credit = 0.0
    
    # Save first to establish new values
    db.session.commit()
    
    recompute_bank_balances(bank_id)
    
    trigger_excel_sync()
    backup_to_telegram("Edited Bank Tx: " + (tx.narration or str(id)))
    flash('Transaction Updated & Balances Recomputed!', 'success')
    return redirect(url_for('main.bank_ledger', id=bank_id))

@main.route('/bank/<int:id>/export')
def export_bank_ledger(id):
    bank = Bank.query.get_or_404(id)
    # Raw query: no sorting
    transactions = BankTransaction.query.filter_by(bank_id=id).all()
    
    from sync_manager import sync_manager
    data = [sync_manager._model_to_dict('bank_transaction', tx) for tx in transactions]
        
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = 'Ledger'
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        # No formatting/auto-width as requested
        
    safe_name = secure_filename(bank.bank_name) or "Bank"
    filename = f"Bank_Ledger_{safe_name}.xlsx"
    
    # Optional: Save a copy to the data directory for GUI users
    try:
        data_dir = current_app.config.get('DATA_FOLDER', '.')
        disk_path = os.path.join(data_dir, filename)
        with open(disk_path, 'wb') as f:
            f.write(output.getvalue())
        from telegram_utils import log_debug
        log_debug(f"Bank Ledger saved to disk: {disk_path}")
    except Exception as e:
        print(f"Failed to save disk backup: {e}")

    output.seek(0)
    return send_file(
        output, 
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        download_name=filename, 
        as_attachment=True
    )

@main.route('/report/bank/all')
def export_all_bank_data():
    from sync_manager import sync_manager
    banks = Bank.query.all()
    bank_transactions = BankTransaction.query.all()

    banks_data = [sync_manager._model_to_dict('bank', b) for b in banks]
    tx_data = [sync_manager._model_to_dict('bank_transaction', tx) for tx in bank_transactions]

    df_banks = pd.DataFrame(banks_data)
    df_tx = pd.DataFrame(tx_data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_banks.to_excel(writer, sheet_name='Banks', index=False)
        df_tx.to_excel(writer, sheet_name='Bank_Transactions', index=False)

    # Optional: Save a copy to the data directory
    filename = "All_Bank_Data_Raw.xlsx"
    try:
        data_dir = current_app.config.get('DATA_FOLDER', '.')
        disk_path = os.path.join(data_dir, filename)
        with open(disk_path, 'wb') as f:
            f.write(output.getvalue())
        from telegram_utils import log_debug
        log_debug(f"All Bank Data saved to disk: {disk_path}")
    except Exception as e:
        print(f"Failed to save disk backup: {e}")

    output.seek(0)
    return send_file(
        output, 
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        download_name=filename, 
        as_attachment=True
    )

# --- Settings & Restore ---
@main.route('/settings')
def settings():
    # List available backups
    backups = []
    backup_dir = os.path.join(current_app.root_path, 'backups')
    if os.path.exists(backup_dir):
        files = sorted(os.listdir(backup_dir), reverse=True)
        for f in files:
            if f.endswith('.xlsx'):
                backups.append(f)
    return render_template('settings.html', backups=backups)

@main.route('/settings/restore', methods=['POST'])
def restore_data():
    if 'backup_file' in request.files:
        file = request.files['backup_file']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            success, msg = restore_from_excel(filepath)
            os.remove(filepath) # Clean up temp file
            
            if success:
                flash('System successfully restored from upload!', 'success')
            else:
                flash(f'Restore failed: {msg}', 'danger')
                
    elif 'backup_filename' in request.form:
        # Restore from internal backup
        filename = request.form.get('backup_filename')
        filepath = os.path.join(current_app.root_path, 'backups', filename)
        if os.path.exists(filepath):
            success, msg = restore_from_excel(filepath)
            if success:
                flash(f'System restored from {filename}', 'success')
            else:
                flash(f'Restore failed: {msg}', 'danger')
        else:
            flash('Backup file not found.', 'danger')
            
    return redirect(url_for('main.settings'))


@main.route('/sync', methods=['GET', 'POST'])
def sync_resolution():
    from sync_manager import sync_manager
    mismatch_details = current_app.config.get('SYNC_MISMATCH')
    
    if not mismatch_details:
        flash('No sync mismatch detected.', 'info')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        choice = request.form.get('choice')
        if choice == 'sheet_to_db':
            success, msg = sync_manager.restore_db_from_sheets()
            if success:
                flash('Local database restored from Google Sheets!', 'success')
                current_app.config['SYNC_MISMATCH'] = None
            else:
                flash(f'Sync failed: {msg}', 'danger')
        elif choice == 'db_to_sheet':
            success, msg = sync_manager.sync_to_sheets()
            if success:
                flash('Google Sheets updated with local data!', 'success')
                current_app.config['SYNC_MISMATCH'] = None
            else:
                flash(f'Sync failed: {msg}', 'danger')
        
        return redirect(url_for('main.index'))

    return render_template('sync_resolution.html', details=mismatch_details)

@main.before_app_request
def check_sync_mismatch():
    # Only redirect to /sync if mismatch exists and it's not the /sync or static route
    if current_app.config.get('SYNC_MISMATCH') and \
       request.endpoint not in ['main.sync_resolution', 'main.uploaded_file', 'static']:
        return redirect(url_for('main.sync_resolution'))

# --- Notifications / Logs ---
@main.route('/notifications')
def notifications():
    from telegram_utils import get_log_path
    log_file = get_log_path()
    logs = ""
    if os.path.exists(log_file):
        try:
            # Read the last 500 lines for performance
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                logs = "".join(lines[-500:])
        except Exception as e:
            logs = f"Error reading logs: {e}"
    
    return render_template('notifications.html', logs=logs)

@main.route('/clear_logs', methods=['POST'])
def clear_logs():
    if not verify_password():
        flash('Invalid Admin Password!', 'danger')
        return redirect(url_for('main.notifications'))
        
    from telegram_utils import get_log_path
    log_file = get_log_path()
    try:
        if os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("") # Clear
        flash('Logs cleared successfully.', 'success')
    except Exception as e:
        flash(f'Failed to clear logs: {e}', 'danger')
        
    return redirect(url_for('main.notifications'))

# --- AI Assistant ---
@main.route('/ai_assistant')
def ai_assistant():
    return render_template('ai_assistant.html')

@main.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@main.route('/api/chat', methods=['POST'])
def api_ai_chat():
    from ai_chat import chat_with_db
    data = request.get_json()
    if not data or 'message' not in data:
        return {"error": "No message provided"}, 400
        
    user_message = data['message']
    history = data.get('history', [])
    
    try:
        reply = chat_with_db(user_message, chat_history=history)
        return {"reply": reply}
    except Exception as e:
        from telegram_utils import log_debug
        log_debug(f"AI Route Error: {e}")
        return {"error": str(e)}, 500

# --- Global Error Handler ---
@main.app_errorhandler(Exception)
def handle_exception(e):
    from telegram_utils import log_debug
    from flask import request, jsonify
    import traceback
    
    error_details = traceback.format_exc()
    log_debug(f"Unhandled Exception in {request.path}: {e}\n{error_details}")
    
    # If this is an API route, return JSON instead of a redirect
    if request.path.startswith('/api/'):
        return jsonify({
            'error': str(e),
            'type': type(e).__name__
        }), 500
        
    flash("An unexpected error occurred. Please check the Notifications log for details.", "danger")
    # Redirect to index, which is usually safe
    try:
        return redirect(url_for('main.index'))
    except:
        return "A critical error occurred.", 500

