"""
Nexus River View — REST API v1
==============================

A JSON API over the existing accounting engine, intended for the Android client
(and any future integrations). It reuses the same business logic as the web
routes — `process_voucher_financials`, `process_transaction_financials`,
`process_contra_financials`, `post_journal_entry`, `recalculate_customer_totals`,
the report builders in `logic.py` — so the mobile client cannot create books
that the web app would not.

Auth
----
`POST /api/v1/auth/login` returns a bearer token (signed with the app SECRET_KEY,
valid 7 days). Every other endpoint expects `Authorization: Bearer <token>`.

Destructive endpoints additionally require the administrator password, supplied
either as the `X-Admin-Password` header or as `admin_password` in the JSON body —
mirroring the web app's confirmation modal.

Money
-----
All monetary values are JSON numbers with 2-decimal precision, derived from
`Decimal`. Clients should parse them as BigDecimal/Decimal, not float.

Registration
------------
`app.py` registers this blueprint and `routes.py` exempts `/api/` from the
session-login redirect (see `global_request_processor`).
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
import os

from flask import Blueprint, current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from database import db
from models import (
    Attendance, Bank, BankTransaction, ChartOfAccounts, ContraEntry, Customer,
    CustomerInstallment, Director, Employee, Installment, JournalEntry,
    JournalLine, Leave, Party, PartyCategory, PartyLedger, PettyCash,
    PettyCashCategory, Salary, Todo, Transaction, User, Voucher,
)

api = Blueprint('api', __name__, url_prefix='/api/v1')

TOKEN_MAX_AGE = 7 * 24 * 3600  # 7 days


# ======================================================================
# Helpers — serialization
# ======================================================================

def _f(value):
    """Decimal/None → JSON-safe float with 2-decimal rounding."""
    if value is None:
        return 0.0
    try:
        return float(Decimal(str(value)).quantize(Decimal('0.01')))
    except (InvalidOperation, ValueError):
        return 0.0


def _dt(value):
    return value.isoformat() if value else None


def _qs_flag(name, default=False):
    raw = request.args.get(name)
    if raw is None:
        return default
    return raw.lower() in ('1', 'true', 'yes', 'on')


# ======================================================================
# Helpers — responses
# ======================================================================

def ok(data, meta=None, status=200):
    body = {'data': data}
    if meta is not None:
        body['meta'] = meta
    return jsonify(body), status


def created(data, status=201):
    return ok(data, status=status)


def error(message, status=400, **extra):
    body = {'error': {'message': message, 'status': status}}
    body['error'].update(extra)
    return jsonify(body), status


def paginate(query, serializer, default_per_page=50):
    page = max(1, request.args.get('page', 1, type=int) or 1)
    per_page = request.args.get('per_page', default_per_page, type=int) or default_per_page
    per_page = min(max(1, per_page), 200)
    total = query.order_by(None).count()
    rows = query.limit(per_page).offset((page - 1) * per_page).all()
    return ok(
        [serializer(row) for row in rows],
        meta={
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page,
        },
    )


# ======================================================================
# Helpers — authentication
# ======================================================================

def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='nrv-api-v1')


def _issue_token(user):
    return _serializer().dumps({'uid': user.id, 'v': 1})


def require_api(view):
    """Require a valid bearer token; put the user on `g.api_user`."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return error('Missing bearer token', 401, code='unauthenticated')
        token = header[7:].strip()
        try:
            payload = _serializer().loads(token, max_age=TOKEN_MAX_AGE)
        except SignatureExpired:
            return error('Token expired — sign in again', 401, code='token_expired')
        except BadSignature:
            return error('Invalid token', 401, code='invalid_token')

        user = db.session.get(User, payload.get('uid'))
        if not user:
            return error('User no longer exists', 401, code='invalid_token')
        g.api_user = user
        return view(*args, **kwargs)
    return wrapper


def _admin_password_ok():
    candidate = request.headers.get('X-Admin-Password')
    if not candidate and request.is_json:
        candidate = (request.get_json(silent=True) or {}).get('admin_password')
    if not candidate:
        return False
    user = getattr(g, 'api_user', None)
    if user and user.check_password(candidate):
        return True
    return candidate == current_app.config.get('ADMIN_PASSWORD')


def require_admin_password(view):
    """Mirror the web app's confirmation modal for destructive actions."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not _admin_password_ok():
            return error(
                'Administrator password required. Send X-Admin-Password or admin_password.',
                403,
                code='admin_password_required',
            )
        return view(*args, **kwargs)
    return wrapper


def _body():
    return request.get_json(silent=True) or {}


def _get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        return None
    return obj


def _not_found(what):
    return error(f'{what} not found', 404, code='not_found')


# ======================================================================
# Helpers — serializers
# ======================================================================

def _user_dict(user):
    return {
        'id': user.id,
        'username': user.username,
        'is_admin': bool(user.is_admin),
    }


def _director_dict(d):
    assigned = sum(Decimal(str(c.shares or 0)) for c in d.customers)
    return {
        'id': d.id,
        'name': d.name,
        'phone': d.phone,
        'bank_name': d.bank_name,
        'total_share': _f(d.total_share),
        'assigned_shares': _f(assigned),
        'available_shares': _f(Decimal(str(d.total_share or 0)) - assigned),
        'total_paid': _f(d.total_paid),
        'total_due': _f(d.total_due),
        'customer_count': len(d.customers or []),
        'payment_history': d.payment_history,
        'updated_at': _dt(d.updated_at),
    }


def _customer_dict(c, detail=False):
    data = {
        'id': c.id,
        'customer_id': c.customer_id,
        'name': c.name,
        'phone': c.phone,
        'plot_no': c.plot_no,
        'director_id': c.director_id,
        'director_name': c.director.name if c.director else None,
        'shares': _f(c.shares),
        'total_price': _f(c.total_price),
        'down_payment': _f(c.down_payment),
        'monthly_installment': _f(c.monthly_installment),
        'total_paid': _f(c.total_paid),
        'due_amount': _f(c.due_amount),
        'updated_at': _dt(c.updated_at),
    }
    if detail:
        data.update({
            'father_name': c.father_name,
            'mother_name': c.mother_name,
            'dob': c.dob,
            'religion': c.religion,
            'profession': c.profession,
            'nid_no': c.nid_no,
            'present_address': c.present_address,
            'permanent_address': c.permanent_address,
            'installments': [_customer_installment_dict(ci) for ci in c.installments],
        })
    return data


def _transaction_dict(t):
    return {
        'id': t.id,
        'customer_id': t.customer_id,
        'date': t.date,
        'amount': _f(t.amount),
        'installment_type': t.installment_type,
        'customer_installment_id': t.customer_installment_id,
        'bank_id': t.bank_id,
        'bank_name': t.bank_name,
        'transaction_id': t.transaction_id,
        'remarks': t.remarks,
        'payment_method': t.payment_method,
        'images': [i for i in (t.images or '').split(',') if i],
        'voucher_id': t.voucher_id,
        'updated_at': _dt(t.updated_at),
    }


def _customer_installment_dict(ci):
    return {
        'id': ci.id,
        'customer_id': ci.customer_id,
        'installment_id': ci.installment_id,
        'installment_name': ci.installment.name if ci.installment else None,
        'total_amount': _f(ci.total_amount),
        'paid_amount': _f(ci.paid_amount),
        'due_amount': _f(ci.due_amount),
    }


def _installment_dict(i):
    return {
        'id': i.id,
        'name': i.name,
        'amount_per_share': _f(i.amount_per_share),
        'created_at': _dt(i.created_at),
        'total_expected': _f(i.total_expected),
        'total_collected': _f(i.total_collected),
        'total_due': _f(i.total_due),
        'customer_count': len(i.customer_installments or []),
    }


def _party_dict(p):
    return {
        'id': p.id,
        'name': p.name,
        'category': p.category,
        'phone': p.phone,
        'address': p.address,
        'current_balance': _f(p.current_balance),
        'updated_at': _dt(p.updated_at),
    }


def _party_ledger_dict(e):
    return {
        'id': e.id,
        'party_id': e.party_id,
        'date': e.date,
        'description': e.description,
        'bill_amount': _f(e.bill_amount),
        'paid_amount': _f(e.paid_amount),
        'balance': _f(e.balance),
        'reference': e.reference,
        'voucher_id': e.voucher_id,
        'created_at': _dt(e.created_at),
    }


def _petty_cash_dict(e):
    return {
        'id': e.id,
        'date': e.date,
        'description': e.description,
        'category': e.category,
        'type': e.type,
        'amount': _f(e.amount),
        'images': [i for i in (e.images or '').split(',') if i],
        'voucher_id': e.voucher_id,
        'contra_entry_id': e.contra_entry_id,
        'transaction_id': e.transaction_id,
        'updated_at': _dt(e.updated_at),
    }


def _bank_dict(b):
    data = b.to_dict()
    data['balance'] = _f(
        sum(Decimal(str(t.credit or 0)) - Decimal(str(t.debit or 0)) for t in b.transactions)
    )
    data['coa_account_code'] = b.coa_account_code
    return data


def _bank_tx_dict(t):
    data = t.to_dict()
    data['debit'] = _f(t.debit)
    data['credit'] = _f(t.credit)
    data['balance'] = _f(t.balance)
    return data


def _voucher_dict(v):
    return {
        'id': v.id,
        'voucher_no': v.voucher_no,
        'type': v.type,
        'date': v.date,
        'payment_date': v.payment_date,
        'party_id': v.party_id,
        'party_name': v.party_obj.name if v.party_obj else None,
        'customer_id': v.customer_id,
        'customer_name': v.customer_obj.name if v.customer_obj else None,
        'description': v.description,
        'total_amount': _f(v.total_amount),
        'amount_paid': _f(v.amount_paid),
        'due_amount': _f(v.due_amount),
        'payment_percentage': _f(v.payment_percentage),
        'payment_method': v.payment_method,
        'bank_id': v.bank_id,
        'bank_name': v.bank_obj.bank_name if v.bank_obj else None,
        'debit_account_code': v.debit_account_code,
        'credit_account_code': v.credit_account_code,
        'category': v.category,
        'notes': v.notes,
        'attachment': v.attachment,
        'is_payment': bool(v.is_payment),
        'created_at': _dt(v.created_at),
        'updated_at': _dt(v.updated_at),
    }


def _contra_dict(c):
    return {
        'id': c.id,
        'contra_no': c.contra_no,
        'date': c.date,
        'from_account': c.from_account,
        'to_account': c.to_account,
        'bank_id': c.bank_id,
        'bank_name': c.bank_obj.bank_name if c.bank_obj else None,
        'amount': _f(c.amount),
        'description': c.description,
        'cheque_no': c.cheque_no,
        'attachments': [a for a in (c.attachments or '').split(',') if a],
        'created_at': _dt(c.created_at),
    }


def _coa_dict(a):
    return {
        'account_code': a.account_code,
        'account_name': a.account_name,
        'account_type': a.account_type,
        'account_category': a.account_category,
        'normal_balance': a.normal_balance,
        'is_control_account': bool(a.is_control_account),
        'is_system': bool(a.is_system),
        'parent_code': a.parent_code,
        'description': a.description,
    }


def _journal_dict(je, with_lines=True):
    data = {
        'id': je.id,
        'entry_number': je.entry_number,
        'entry_date': je.entry_date.isoformat() if je.entry_date else None,
        'reference_type': je.reference_type,
        'reference_id': je.reference_id,
        'description': je.description,
        'posted_by': je.posted_by,
        'posted_at': _dt(je.posted_at),
        'is_posted': bool(je.is_posted),
        'is_reversed': bool(je.is_reversed),
        'reversal_entry_id': je.reversal_entry_id,
        'voucher_id': je.voucher_id,
        'total_debit': _f(sum(Decimal(str(l.debit_amount or 0)) for l in je.lines)),
        'total_credit': _f(sum(Decimal(str(l.credit_amount or 0)) for l in je.lines)),
    }
    if with_lines:
        data['lines'] = [
            {
                'id': l.id,
                'account_code': l.account_code,
                'account_name': l.account_name,
                'debit_amount': _f(l.debit_amount),
                'credit_amount': _f(l.credit_amount),
                'narration': l.narration,
                'party_type': l.party_type,
                'party_id': l.party_id,
            }
            for l in je.lines
        ]
    return data


def _employee_dict(e):
    return {
        'id': e.id,
        'employee_id': e.employee_id,
        'name': e.name,
        'designation': e.designation,
        'department': e.department,
        'joining_date': e.joining_date,
        'phone': e.phone,
        'net_salary': _f(e.net_salary),
        'leave_allocations': {
            'casual': e.cl_total,
            'medical': e.ml_total,
            'festival': e.fl_total,
            'earned': e.el_total,
        },
    }


def _attendance_dict(a):
    return {
        'id': a.id,
        'employee_id': a.employee_id,
        'employee_name': a.employee.name if a.employee else None,
        'date': a.date,
        'in_time': a.in_time,
        'out_time': a.out_time,
        'status': a.status,
        'working_hours': round(a.working_hours or 0.0, 2),
        'notes': a.notes,
    }


def _leave_dict(l):
    return {
        'id': l.id,
        'employee_id': l.employee_id,
        'employee_name': l.employee.name if l.employee else None,
        'leave_type': l.leave_type,
        'from_date': l.from_date,
        'to_date': l.to_date,
        'total_days': l.total_days,
        'status': l.status,
        'reason': l.reason,
        'created_at': _dt(l.created_at),
    }


def _salary_dict(s):
    return {
        'id': s.id,
        'employee_id': s.employee_id,
        'employee_name': s.employee.name if s.employee else None,
        'month': s.month,
        'year': s.year,
        'net_salary': _f(s.net_salary),
        'working_days': s.working_days,
        'present_days': s.present_days,
        'absent_days': s.absent_days,
        'leave_days': s.leave_days,
        'late_days': s.late_days,
        'off_days': s.off_days,
        'per_day_salary': _f(s.per_day_salary),
        'deduction': _f(s.deduction),
        'mobile_bill': _f(s.mobile_bill),
        'bonus': _f(s.bonus),
        'final_salary': _f(s.final_salary),
        'status': s.status,
        'payment_date': s.payment_date,
    }


def _todo_dict(t):
    return {
        'id': t.id,
        'task': t.task,
        'category': t.category,
        'due_date': t.due_date,
        'due_time': t.due_time,
        'is_completed': bool(t.is_completed),
        'created_at': _dt(t.created_at),
    }


# ======================================================================
# Health & meta
# ======================================================================

@api.get('/health')
def health():
    return ok({'status': 'ok', 'time': datetime.utcnow().isoformat() + 'Z'})


@api.get('/meta')
def meta():
    return ok({
        'company': {
            'name': current_app.config.get('COMPANY_NAME')
            or os.environ.get('COMPANY_NAME', 'Nexus River View'),
            'currency_symbol': '৳',
            'currency_code': 'BDT',
        },
        'enums': {
            'voucher_types': ['Debit', 'Credit'],
            'payment_methods': ['Cash', 'Bank'],
            'payment_sources': ['cash', 'petty_cash', 'bank'],
            'account_types': ['Asset', 'Liability', 'Equity', 'Revenue', 'COGS', 'Expense'],
            'normal_balances': ['Debit', 'Credit'],
            'party_categories': [c.name for c in PartyCategory.query.order_by(PartyCategory.name)],
            'petty_cash_categories': [c.name for c in PettyCashCategory.query.order_by(PettyCashCategory.name)],
            'leave_types': ['CL', 'ML', 'FL', 'EL'],
            'leave_statuses': ['Approved', 'Pending', 'Rejected'],
            'attendance_statuses': ['Present', 'Absent', 'Late', 'Leave', 'Off Day'],
            'salary_statuses': ['Unpaid', 'Paid'],
            'transaction_installment_types': ['Booking', 'Down Payment', 'Installment', 'Full Payment', 'Other'],
        },
        'date_formats': {
            'api': 'YYYY-MM-DD',
            'bank_ledger_storage': 'DD-MM-YYYY',
        },
    })


# ======================================================================
# Auth
# ======================================================================

@api.post('/auth/login')
def login():
    body = _body()
    username = (body.get('username') or '').strip()
    password = body.get('password') or ''
    if not username or not password:
        return error('username and password are required', 422)

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return error('Invalid username or password', 401, code='invalid_credentials')

    return ok({
        'token': _issue_token(user),
        'token_type': 'Bearer',
        'expires_in': TOKEN_MAX_AGE,
        'user': _user_dict(user),
    })


@api.get('/auth/me')
@require_api
def me():
    return ok(_user_dict(g.api_user))


@api.post('/auth/refresh')
@require_api
def refresh():
    return ok({
        'token': _issue_token(g.api_user),
        'token_type': 'Bearer',
        'expires_in': TOKEN_MAX_AGE,
    })


# ======================================================================
# Dashboard
# ======================================================================

@api.get('/dashboard')
@require_api
def dashboard():
    from collections import defaultdict
    from sqlalchemy import func
    from datetime import date as date_cls
    import calendar

    total_milestone_rate = db.session.query(func.sum(Installment.amount_per_share)).scalar() or 0
    total_director_shares = db.session.query(func.sum(Director.total_share)).scalar() or 0
    payable = Decimal(str(total_director_shares)) * Decimal(str(total_milestone_rate))

    customers = Customer.query.all()
    paid = sum(Decimal(str(c.total_paid or 0)) for c in customers)
    due = Decimal(str(payable)) - Decimal(str(paid))

    bank_res = db.session.query(func.sum(BankTransaction.credit) - func.sum(BankTransaction.debit)).scalar()
    bank_balance = Decimal(str(bank_res)) if bank_res else Decimal('0')

    cash_in = db.session.query(func.sum(PettyCash.amount)).filter_by(type='Income').scalar()
    cash_out = db.session.query(func.sum(PettyCash.amount)).filter_by(type='Expense').scalar()
    cash_in_hand = Decimal(str(cash_in or 0)) - Decimal(str(cash_out or 0))

    parties = Party.query.all()
    party_due = sum(Decimal(str(p.current_balance or 0)) for p in parties if (p.current_balance or 0) > 0)
    party_advance = abs(sum(Decimal(str(p.current_balance or 0)) for p in parties if (p.current_balance or 0) < 0))

    income_by_month = defaultdict(float)
    expense_by_month = defaultdict(float)

    def month_key(raw):
        for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw, fmt).strftime('%Y-%m')
            except (ValueError, TypeError):
                continue
        return None

    for d, amount in db.session.query(Transaction.date, Transaction.amount).all():
        key = month_key(d)
        if key:
            income_by_month[key] += float(amount or 0)
    for d, credit, debit in db.session.query(BankTransaction.date, BankTransaction.credit, BankTransaction.debit).all():
        key = month_key(d)
        if key:
            income_by_month[key] += float(credit or 0)
            expense_by_month[key] += float(debit or 0)
    for d, type_, amount in db.session.query(PettyCash.date, PettyCash.type, PettyCash.amount).all():
        key = month_key(d)
        if key:
            if type_ == 'Income':
                income_by_month[key] += float(amount or 0)
            else:
                expense_by_month[key] += float(amount or 0)

    cursor = date_cls.today().replace(day=1)
    chart = []
    for _ in range(6):
        key = cursor.strftime('%Y-%m')
        chart.insert(0, {
            'label': calendar.month_name[cursor.month][:3] + ' ' + str(cursor.year)[2:],
            'income': round(income_by_month[key], 2),
            'expense': round(expense_by_month[key], 2),
        })
        cursor = (cursor.replace(year=cursor.year - 1, month=12)
                  if cursor.month == 1 else cursor.replace(month=cursor.month - 1))

    return ok({
        'project_value': _f(payable),
        'total_collected': _f(paid),
        'total_due': _f(due),
        'total_outstanding': _f(due),
        'bank_balance': _f(bank_balance),
        'cash_in_hand': _f(cash_in_hand),
        'payable_to_suppliers': _f(party_due),
        'advance_credit': _f(party_advance),
        'chart': chart,
        'counts': {
            'directors': Director.query.count(),
            'customers': Customer.query.count(),
            'parties': Party.query.count(),
            'open_vouchers_due': Voucher.query.filter(Voucher.due_amount > 0).count(),
        },
    })


# ======================================================================
# Directors
# ======================================================================

@api.get('/directors')
@require_api
def list_directors():
    query = Director.query.order_by(Director.name)
    return paginate(query, _director_dict)


@api.get('/directors/<int:director_id>')
@require_api
def get_director(director_id):
    d = _get_or_404(Director, director_id)
    if not d:
        return _not_found('Director')
    data = _director_dict(d)
    data['customers'] = [_customer_dict(c) for c in d.customers]
    return ok(data)


@api.post('/directors')
@require_api
@require_admin_password
def create_director():
    body = _body()
    if not (body.get('name') or '').strip():
        return error('name is required', 422)
    d = Director(
        name=body['name'].strip(),
        phone=body.get('phone'),
        bank_name=body.get('bank_name'),
        total_share=Decimal(str(body.get('total_share') or 0)),
        per_share_value=Decimal(str(body.get('per_share_value') or 0)),
        fair_cost=Decimal(str(body.get('fair_cost') or 0)),
        land_value_extra_share=Decimal(str(body.get('land_value_extra_share') or 0)),
        payment_history=body.get('payment_history'),
    )
    db.session.add(d)
    db.session.commit()
    return created(_director_dict(d))


@api.patch('/directors/<int:director_id>')
@require_api
@require_admin_password
def update_director(director_id):
    d = _get_or_404(Director, director_id)
    if not d:
        return _not_found('Director')
    body = _body()
    for field in ('name', 'phone', 'bank_name', 'payment_history'):
        if field in body:
            setattr(d, field, body[field])
    for field in ('total_share', 'per_share_value', 'fair_cost', 'land_value_extra_share'):
        if field in body:
            setattr(d, field, Decimal(str(body[field] or 0)))
    db.session.commit()
    return ok(_director_dict(d))


@api.delete('/directors/<int:director_id>')
@require_api
@require_admin_password
def delete_director(director_id):
    d = _get_or_404(Director, director_id)
    if not d:
        return _not_found('Director')
    if d.customers:
        return error('Cannot delete a director who still has customers', 409, code='has_dependents')
    db.session.delete(d)
    db.session.commit()
    return ok({'deleted': True, 'id': director_id})


# ======================================================================
# Customers
# ======================================================================

@api.get('/customers')
@require_api
def list_customers():
    query = Customer.query
    director_id = request.args.get('director_id', type=int)
    if director_id:
        query = query.filter(Customer.director_id == director_id)
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        query = query.filter(db.or_(
            Customer.name.ilike(like),
            Customer.customer_id.ilike(like),
            Customer.phone.ilike(like),
            Customer.plot_no.ilike(like),
        ))
    due_only = _qs_flag('due_only')
    if due_only:
        query = query.filter(Customer.due_amount > 0)
    query = query.order_by(Customer.director_id, Customer.customer_id)
    return paginate(query, _customer_dict)


@api.get('/customers/<int:customer_id>')
@require_api
def get_customer(customer_id):
    c = _get_or_404(Customer, customer_id)
    if not c:
        return _not_found('Customer')
    data = _customer_dict(c, detail=True)
    data['transactions'] = [_transaction_dict(t) for t in
                            sorted(c.transactions, key=lambda t: (t.date or '', t.id))]
    return ok(data)


@api.post('/customers')
@require_api
@require_admin_password
def create_customer():
    from logic import recalculate_customer_totals

    body = _body()
    director_id = body.get('director_id')
    director = db.session.get(Director, director_id) if director_id else None
    if not director:
        return error('A valid director_id is required', 422)

    shares = Decimal(str(body.get('shares') or 0))
    if shares > director.available_shares:
        return error(
            f'Director only has {director.available_shares} shares available',
            409,
            code='insufficient_shares',
        )

    customer_code = (body.get('customer_id') or '').strip()
    if not customer_code:
        last = Customer.query.filter_by(director_id=director.id).count()
        customer_code = f'{director.id}-{last + 1}'

    c = Customer(
        director_id=director.id,
        customer_id=customer_code,
        name=(body.get('name') or '').strip(),
        phone=body.get('phone'),
        plot_no=body.get('plot_no'),
        shares=shares,
        total_price=Decimal(str(body.get('total_price') or 0)),
        down_payment=Decimal(str(body.get('down_payment') or 0)),
        monthly_installment=Decimal(str(body.get('monthly_installment') or 0)),
        father_name=body.get('father_name'),
        mother_name=body.get('mother_name'),
        dob=body.get('dob'),
        religion=body.get('religion'),
        profession=body.get('profession'),
        nid_no=body.get('nid_no'),
        present_address=body.get('present_address'),
        permanent_address=body.get('permanent_address'),
    )
    if not c.name:
        return error('name is required', 422)

    db.session.add(c)
    db.session.flush()
    recalculate_customer_totals(c)
    return created(_customer_dict(c, detail=True))


@api.patch('/customers/<int:customer_id>')
@require_api
@require_admin_password
def update_customer(customer_id):
    from logic import recalculate_customer_totals
    c = _get_or_404(Customer, customer_id)
    if not c:
        return _not_found('Customer')

    body = _body()
    plain = ('name', 'phone', 'plot_no', 'father_name', 'mother_name', 'dob', 'religion',
             'profession', 'nid_no', 'present_address', 'permanent_address')
    for field in plain:
        if field in body:
            setattr(c, field, body[field])
    for field in ('shares', 'total_price', 'down_payment', 'monthly_installment'):
        if field in body:
            setattr(c, field, Decimal(str(body[field] or 0)))

    if 'director_id' in body and body['director_id'] != c.director_id:
        new_director = db.session.get(Director, body['director_id'])
        if not new_director:
            return error('A valid director_id is required', 422)
        c.director_id = new_director.id

    db.session.commit()
    recalculate_customer_totals(c)
    return ok(_customer_dict(c, detail=True))


@api.delete('/customers/<int:customer_id>')
@require_api
@require_admin_password
def delete_customer(customer_id):
    from logic import cleanup_journal_entries
    c = _get_or_404(Customer, customer_id)
    if not c:
        return _not_found('Customer')
    tx_ids = [t.id for t in c.transactions]
    for tx_id in tx_ids:
        cleanup_journal_entries(reference_id=f'TX-{tx_id}')
    db.session.delete(c)
    db.session.commit()
    return ok({'deleted': True, 'id': customer_id})


# ======================================================================
# Customer transactions
# ======================================================================

@api.get('/customers/<int:customer_id>/transactions')
@require_api
def list_customer_transactions(customer_id):
    c = _get_or_404(Customer, customer_id)
    if not c:
        return _not_found('Customer')
    rows = sorted(c.transactions, key=lambda t: (t.date or '', t.id), reverse=True)
    return ok([_transaction_dict(t) for t in rows], meta={'total': len(rows)})


@api.post('/customers/<int:customer_id>/transactions')
@require_api
@require_admin_password
def create_customer_transaction(customer_id):
    from logic import (
        journal_customer_booking, journal_customer_payment_bank,
        journal_customer_payment_cash, process_transaction_financials,
        recalculate_customer_totals,
    )

    c = _get_or_404(Customer, customer_id)
    if not c:
        return _not_found('Customer')

    body = _body()
    amount = Decimal(str(body.get('amount') or 0))
    if amount <= 0:
        return error('amount must be greater than zero', 422)
    when = body.get('date') or datetime.now().strftime('%Y-%m-%d')
    source = (body.get('payment_source') or 'cash').lower()
    if source not in ('cash', 'petty_cash', 'bank'):
        return error("payment_source must be cash, petty_cash or bank", 422)

    bank_id = body.get('bank_id')
    bank = db.session.get(Bank, bank_id) if (source == 'bank' and bank_id) else None
    if source == 'bank' and not bank:
        return error('bank_id is required when payment_source is bank', 422)

    images = body.get('images') or []
    if isinstance(images, str):
        images = [i for i in images.split(',') if i]

    tx = Transaction(
        date=when,
        amount=amount,
        installment_type=body.get('installment_type'),
        bank_name=bank.bank_name if bank else ('Petty Cash' if source == 'petty_cash' else ''),
        bank_id=bank.id if bank else None,
        transaction_id=body.get('transaction_id'),
        remarks=body.get('remarks'),
        payment_method=source.capitalize(),
        customer_id=c.id,
        customer_installment_id=body.get('customer_installment_id'),
        images=','.join(images),
    )
    db.session.add(tx)
    db.session.flush()

    if tx.customer_installment_id:
        ci = db.session.get(CustomerInstallment, tx.customer_installment_id)
        if ci and ci.customer_id == c.id:
            ci.paid_amount = Decimal(str(ci.paid_amount or 0)) + amount
            ci.due_amount = Decimal(str(ci.total_amount or 0)) - Decimal(str(ci.paid_amount or 0))
            if not tx.installment_type and ci.installment:
                tx.installment_type = ci.installment.name

    process_transaction_financials(tx.id, action='add', payment_source=source,
                                   bank_id=bank.id if bank else None)

    if tx.installment_type == 'Booking':
        journal_customer_booking(c, amount, when)
    elif bank and bank.coa_account_code:
        journal_customer_payment_bank(c, bank.coa_account_code, tx.installment_type,
                                      amount, tx.transaction_id or '', when)
    else:
        journal_customer_payment_cash(c, tx.installment_type, amount, when)

    db.session.commit()
    recalculate_customer_totals(c)
    return created(_transaction_dict(tx), status=201)


@api.delete('/transactions/<int:transaction_id>')
@require_api
@require_admin_password
def delete_transaction(transaction_id):
    from logic import (
        cleanup_journal_entries, process_transaction_financials,
        recalculate_customer_totals,
    )
    tx = _get_or_404(Transaction, transaction_id)
    if not tx:
        return _not_found('Transaction')

    customer = tx.customer
    process_transaction_financials(tx.id, action='delete')
    cleanup_journal_entries(reference_id=f'TX-{tx.id}')
    db.session.delete(tx)
    db.session.commit()

    if customer:
        recalculate_customer_totals(customer)
    return ok({'deleted': True, 'id': transaction_id})


# ======================================================================
# Installments
# ======================================================================

@api.get('/installments')
@require_api
def list_installments():
    rows = Installment.query.order_by(Installment.created_at).all()
    return ok([_installment_dict(i) for i in rows], meta={'total': len(rows)})


@api.get('/installments/<int:installment_id>')
@require_api
def get_installment(installment_id):
    i = _get_or_404(Installment, installment_id)
    if not i:
        return _not_found('Installment')
    data = _installment_dict(i)
    data['customer_installments'] = [
        _customer_installment_dict(ci) for ci in
        sorted(i.customer_installments, key=lambda x: x.customer.name if x.customer else '')
    ]
    return ok(data)


@api.post('/installments')
@require_api
@require_admin_password
def create_installment():
    from logic import recalculate_customer_totals
    body = _body()
    name = (body.get('name') or '').strip()
    amount = Decimal(str(body.get('amount_per_share') or 0))
    if not name:
        return error('name is required', 422)
    if amount <= 0:
        return error('amount_per_share must be greater than zero', 422)

    i = Installment(name=name, amount_per_share=amount)
    db.session.add(i)
    db.session.commit()

    for customer in Customer.query.all():
        recalculate_customer_totals(customer)
    return created(_installment_dict(i))


@api.patch('/installments/<int:installment_id>')
@require_api
@require_admin_password
def update_installment(installment_id):
    from logic import recalculate_customer_totals
    i = _get_or_404(Installment, installment_id)
    if not i:
        return _not_found('Installment')
    body = _body()
    if 'name' in body:
        i.name = (body['name'] or '').strip() or i.name
    if 'amount_per_share' in body:
        i.amount_per_share = Decimal(str(body['amount_per_share'] or 0))
    db.session.commit()

    for customer in Customer.query.all():
        recalculate_customer_totals(customer)
    return ok(_installment_dict(i))


@api.delete('/installments/<int:installment_id>')
@require_api
@require_admin_password
def delete_installment(installment_id):
    i = _get_or_404(Installment, installment_id)
    if not i:
        return _not_found('Installment')
    db.session.delete(i)
    db.session.commit()
    return ok({'deleted': True, 'id': installment_id})


# ======================================================================
# Parties & ledger
# ======================================================================

@api.get('/party-categories')
@require_api
def list_party_categories():
    rows = PartyCategory.query.order_by(PartyCategory.name).all()
    return ok([{'id': c.id, 'name': c.name} for c in rows])


@api.post('/party-categories')
@require_api
@require_admin_password
def create_party_category():
    name = (_body().get('name') or '').strip()
    if not name:
        return error('name is required', 422)
    if PartyCategory.query.filter_by(name=name).first():
        return error('Category already exists', 409, code='duplicate')
    c = PartyCategory(name=name)
    db.session.add(c)
    db.session.commit()
    return created({'id': c.id, 'name': c.name})


@api.get('/parties')
@require_api
def list_parties():
    query = Party.query
    category = request.args.get('category')
    if category:
        query = query.filter(Party.category == category)
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        query = query.filter(db.or_(Party.name.ilike(like), Party.phone.ilike(like)))
    return paginate(query.order_by(Party.name), _party_dict)


@api.get('/parties/<int:party_id>')
@require_api
def get_party(party_id):
    p = _get_or_404(Party, party_id)
    if not p:
        return _not_found('Party')
    data = _party_dict(p)
    data['ledger'] = [_party_ledger_dict(e) for e in
                      sorted(p.ledger_entries, key=lambda x: (x.date or '', x.id))]
    return ok(data)


@api.post('/parties')
@require_api
@require_admin_password
def create_party():
    body = _body()
    name, category = (body.get('name') or '').strip(), (body.get('category') or '').strip()
    if not name or not category:
        return error('name and category are required', 422)
    p = Party(name=name, category=category, phone=body.get('phone'), address=body.get('address'))
    db.session.add(p)
    db.session.commit()
    return created(_party_dict(p))


@api.patch('/parties/<int:party_id>')
@require_api
@require_admin_password
def update_party(party_id):
    p = _get_or_404(Party, party_id)
    if not p:
        return _not_found('Party')
    body = _body()
    for field in ('name', 'category', 'phone', 'address'):
        if field in body:
            setattr(p, field, body[field])
    db.session.commit()
    return ok(_party_dict(p))


@api.delete('/parties/<int:party_id>')
@require_api
@require_admin_password
def delete_party(party_id):
    p = _get_or_404(Party, party_id)
    if not p:
        return _not_found('Party')
    db.session.delete(p)
    db.session.commit()
    return ok({'deleted': True, 'id': party_id})


@api.post('/parties/<int:party_id>/ledger')
@require_api
@require_admin_password
def create_party_ledger_entry(party_id):
    from logic import recalculate_party_ledger_balances
    p = _get_or_404(Party, party_id)
    if not p:
        return _not_found('Party')

    body = _body()
    entry = PartyLedger(
        party_id=p.id,
        date=body.get('date') or datetime.now().strftime('%Y-%m-%d'),
        description=body.get('description'),
        bill_amount=Decimal(str(body.get('bill_amount') or 0)),
        paid_amount=Decimal(str(body.get('paid_amount') or 0)),
        reference=body.get('reference'),
    )
    db.session.add(entry)
    db.session.commit()
    recalculate_party_ledger_balances(p.id)
    db.session.refresh(entry)
    return created(_party_ledger_dict(entry))


@api.delete('/party-ledger/<int:entry_id>')
@require_api
@require_admin_password
def delete_party_ledger_entry(entry_id):
    from logic import recalculate_party_ledger_balances
    entry = _get_or_404(PartyLedger, entry_id)
    if not entry:
        return _not_found('Ledger entry')
    party_id = entry.party_id
    db.session.delete(entry)
    db.session.commit()
    recalculate_party_ledger_balances(party_id)
    return ok({'deleted': True, 'id': entry_id})


# ======================================================================
# Petty cash
# ======================================================================

@api.get('/petty-cash')
@require_api
def list_petty_cash():
    query = PettyCash.query
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    category = request.args.get('category')
    if start:
        query = query.filter(PettyCash.date >= start)
    if end:
        query = query.filter(PettyCash.date <= end)
    if category and category != 'All':
        query = query.filter(PettyCash.category == category)
    query = query.order_by(PettyCash.date.desc(), PettyCash.id.desc())

    rows = query.all()
    income = sum(Decimal(str(e.amount or 0)) for e in rows if e.type == 'Income')
    expense = sum(Decimal(str(e.amount or 0)) for e in rows if e.type == 'Expense')
    return paginate(query, _petty_cash_dict) if request.args.get('page') else ok(
        [_petty_cash_dict(e) for e in rows],
        meta={
            'total': len(rows),
            'total_income': _f(income),
            'total_expense': _f(expense),
            'balance': _f(income - expense),
        },
    )


@api.get('/petty-cash/categories')
@require_api
def list_petty_cash_categories():
    rows = PettyCashCategory.query.order_by(PettyCashCategory.name).all()
    return ok([{'id': c.id, 'name': c.name} for c in rows])


@api.post('/petty-cash')
@require_api
@require_admin_password
def create_petty_cash():
    from logic import journal_general_expense, journal_general_income

    body = _body()
    entry_type = body.get('type')
    amount = Decimal(str(body.get('amount') or 0))
    if entry_type not in ('Income', 'Expense'):
        return error("type must be 'Income' or 'Expense'", 422)
    if amount <= 0:
        return error('amount must be greater than zero', 422)
    if not (body.get('description') or '').strip():
        return error('description is required', 422)

    images = body.get('images') or []
    if isinstance(images, str):
        images = [i for i in images.split(',') if i]

    entry = PettyCash(
        date=body.get('date') or datetime.now().strftime('%Y-%m-%d'),
        description=body['description'].strip(),
        category=body.get('category') or 'General',
        type=entry_type,
        amount=amount,
        images=','.join(images),
    )
    db.session.add(entry)
    db.session.flush()

    if entry_type == 'Income':
        journal_general_income('4030', 'Cash', '1010', amount, f'PC-{entry.id}',
                               entry.category, entry.date)
    else:
        journal_general_expense('6230', 'Cash', '1010', amount, f'PC-{entry.id}',
                                entry.category, entry.date)

    db.session.commit()
    return created(_petty_cash_dict(entry))


@api.delete('/petty-cash/<int:entry_id>')
@require_api
@require_admin_password
def delete_petty_cash(entry_id):
    from logic import cleanup_journal_entries
    entry = _get_or_404(PettyCash, entry_id)
    if not entry:
        return _not_found('Petty cash entry')
    cleanup_journal_entries(reference_ids=[f'PC-{entry.id}'])
    db.session.delete(entry)
    db.session.commit()
    return ok({'deleted': True, 'id': entry_id})


# ======================================================================
# Banks
# ======================================================================

@api.get('/banks')
@require_api
def list_banks():
    rows = Bank.query.order_by(Bank.bank_name).all()
    return ok([_bank_dict(b) for b in rows], meta={'total': len(rows)})


@api.get('/banks/<int:bank_id>')
@require_api
def get_bank(bank_id):
    b = _get_or_404(Bank, bank_id)
    if not b:
        return _not_found('Bank')
    data = _bank_dict(b)
    data['transactions'] = [_bank_tx_dict(t) for t in
                            sorted(b.transactions, key=lambda t: (t.date or '', t.id), reverse=True)]
    return ok(data)


@api.post('/banks')
@require_api
@require_admin_password
def create_bank():
    body = _body()
    if not (body.get('bank_name') or '').strip():
        return error('bank_name is required', 422)
    if not (body.get('account_no') or '').strip():
        return error('account_no is required', 422)

    b = Bank(
        bank_name=body['bank_name'].strip(),
        branch=body.get('branch'),
        account_holder_name=body.get('account_holder_name'),
        joint_name=body.get('joint_name'),
        fhp=body.get('fhp'),
        address=body.get('address'),
        city=body.get('city'),
        phone=body.get('phone'),
        customer_id=body.get('customer_id'),
        account_no=body['account_no'].strip(),
        prev_account_no=body.get('prev_account_no'),
        account_type=body.get('account_type'),
        currency=body.get('currency') or 'BDT',
        status=body.get('status') or 'Active',
        coa_account_code=body.get('coa_account_code'),
    )
    db.session.add(b)
    db.session.commit()
    return created(_bank_dict(b))


@api.patch('/banks/<int:bank_id>')
@require_api
@require_admin_password
def update_bank(bank_id):
    b = _get_or_404(Bank, bank_id)
    if not b:
        return _not_found('Bank')
    body = _body()
    for field in ('bank_name', 'branch', 'account_holder_name', 'joint_name', 'fhp',
                  'address', 'city', 'phone', 'customer_id', 'account_no', 'prev_account_no',
                  'account_type', 'currency', 'status', 'coa_account_code'):
        if field in body:
            setattr(b, field, body[field])
    db.session.commit()
    return ok(_bank_dict(b))


@api.delete('/banks/<int:bank_id>')
@require_api
@require_admin_password
def delete_bank(bank_id):
    b = _get_or_404(Bank, bank_id)
    if not b:
        return _not_found('Bank')
    db.session.delete(b)
    db.session.commit()
    return ok({'deleted': True, 'id': bank_id})


@api.post('/banks/<int:bank_id>/transactions')
@require_api
@require_admin_password
def create_bank_transaction(bank_id):
    from logic import recompute_bank_balances
    b = _get_or_404(Bank, bank_id)
    if not b:
        return _not_found('Bank')

    body = _body()
    tx_type = (body.get('tx_type') or '').lower()
    if tx_type not in ('credit', 'debit'):
        return error("tx_type must be 'credit' or 'debit'", 422)

    raw_date = body.get('date') or datetime.now().strftime('%Y-%m-%d')
    try:
        stored_date = datetime.strptime(raw_date, '%Y-%m-%d').strftime('%d-%m-%Y')
    except ValueError:
        stored_date = raw_date  # already DD-MM-YYYY

    amount = Decimal(str(body.get('amount') or body.get(tx_type) or 0))
    if amount <= 0:
        return error('amount must be greater than zero', 422)

    tx = BankTransaction(
        date=stored_date,
        cheque_no=body.get('cheque_no'),
        ref_no=body.get('ref_no'),
        narration=body.get('narration'),
        transaction_details=body.get('transaction_details'),
        category=body.get('category'),
        debit=amount if tx_type == 'debit' else Decimal('0'),
        credit=amount if tx_type == 'credit' else Decimal('0'),
        balance=Decimal('0'),
        bank_id=b.id,
    )
    db.session.add(tx)
    db.session.commit()
    recompute_bank_balances(b.id)
    db.session.refresh(tx)
    return created(_bank_tx_dict(tx))


@api.delete('/bank-transactions/<int:tx_id>')
@require_api
@require_admin_password
def delete_bank_transaction(tx_id):
    from logic import recompute_bank_balances
    tx = _get_or_404(BankTransaction, tx_id)
    if not tx:
        return _not_found('Bank transaction')
    bank_id = tx.bank_id
    db.session.delete(tx)
    db.session.commit()
    recompute_bank_balances(bank_id)
    return ok({'deleted': True, 'id': tx_id})


# ======================================================================
# Vouchers
# ======================================================================

@api.get('/vouchers')
@require_api
def list_vouchers():
    query = Voucher.query
    v_type = request.args.get('type')
    if v_type in ('Debit', 'Credit'):
        query = query.filter(Voucher.type == v_type)
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    if start:
        query = query.filter(Voucher.date >= start)
    if end:
        query = query.filter(Voucher.date <= end)
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        query = query.filter(db.or_(
            Voucher.voucher_no.ilike(like),
            Voucher.description.ilike(like),
            Voucher.category.ilike(like),
        ))
    return paginate(query.order_by(Voucher.date.desc(), Voucher.id.desc()), _voucher_dict)


@api.get('/vouchers/next-number')
@require_api
def voucher_next_number():
    from logic import generate_voucher_number
    v_type = request.args.get('type', 'Debit')
    if v_type not in ('Debit', 'Credit'):
        return error("type must be 'Debit' or 'Credit'", 422)
    return ok({'voucher_no': generate_voucher_number(v_type)})


@api.get('/vouchers/<int:voucher_id>')
@require_api
def get_voucher(voucher_id):
    v = _get_or_404(Voucher, voucher_id)
    if not v:
        return _not_found('Voucher')
    return ok(_voucher_dict(v))


@api.post('/vouchers')
@require_api
@require_admin_password
def create_voucher():
    from logic import generate_voucher_number, process_voucher_financials

    body = _body()
    v_type = body.get('type')
    if v_type not in ('Debit', 'Credit'):
        return error("type must be 'Debit' or 'Credit'", 422)

    total = Decimal(str(body.get('total_amount') or 0))
    paid = Decimal(str(body.get('amount_paid') or 0))
    if total <= 0:
        return error('total_amount must be greater than zero', 422)
    if paid < 0 or paid > total:
        return error('amount_paid must be between 0 and total_amount', 422)

    method = body.get('payment_method') or 'Cash'
    if method not in ('Cash', 'Bank'):
        return error("payment_method must be 'Cash' or 'Bank'", 422)
    if method == 'Bank' and not body.get('bank_id'):
        return error('bank_id is required for bank payments', 422)

    v = Voucher(
        voucher_no=body.get('voucher_no') or generate_voucher_number(v_type),
        type=v_type,
        date=body.get('date') or datetime.now().strftime('%Y-%m-%d'),
        payment_date=body.get('payment_date') or body.get('date')
        or datetime.now().strftime('%Y-%m-%d'),
        party_id=body.get('party_id') or None,
        customer_id=body.get('customer_id') or None,
        description=body.get('description'),
        total_amount=total,
        amount_paid=paid,
        due_amount=total - paid,
        payment_percentage=(paid / total * 100) if total else Decimal('0'),
        payment_method=method,
        bank_id=body.get('bank_id') or None,
        category=body.get('category'),
        notes=body.get('notes'),
        debit_account_code=body.get('debit_account_code'),
        credit_account_code=body.get('credit_account_code'),
        is_payment=bool(body.get('is_payment')),
    )
    db.session.add(v)
    db.session.commit()

    success, message = process_voucher_financials(v.id, action='add')
    db.session.refresh(v)
    if not success:
        return error(message, 500, code='posting_failed', voucher=_voucher_dict(v))
    return created(_voucher_dict(v), status=201)


@api.patch('/vouchers/<int:voucher_id>')
@require_api
@require_admin_password
def update_voucher(voucher_id):
    from logic import process_voucher_financials

    v = _get_or_404(Voucher, voucher_id)
    if not v:
        return _not_found('Voucher')

    body = _body()
    for field in ('voucher_no', 'date', 'payment_date', 'description', 'category',
                  'notes', 'debit_account_code', 'credit_account_code'):
        if field in body:
            setattr(v, field, body[field])
    for field in ('party_id', 'customer_id', 'bank_id'):
        if field in body:
            setattr(v, field, body[field] or None)
    if 'total_amount' in body:
        v.total_amount = Decimal(str(body['total_amount'] or 0))
    if 'amount_paid' in body:
        v.amount_paid = Decimal(str(body['amount_paid'] or 0))
    if 'payment_method' in body:
        v.payment_method = body['payment_method']
    if 'is_payment' in body:
        v.is_payment = bool(body['is_payment'])

    v.due_amount = Decimal(str(v.total_amount or 0)) - Decimal(str(v.amount_paid or 0))
    v.payment_percentage = (
        Decimal(str(v.amount_paid or 0)) / Decimal(str(v.total_amount))
        * 100
    ) if Decimal(str(v.total_amount or 0)) else Decimal('0')

    db.session.commit()
    success, message = process_voucher_financials(v.id, action='edit')
    db.session.refresh(v)
    if not success:
        return error(message, 500, code='posting_failed')
    return ok(_voucher_dict(v))


@api.delete('/vouchers/<int:voucher_id>')
@require_api
@require_admin_password
def delete_voucher(voucher_id):
    from logic import process_voucher_financials
    v = _get_or_404(Voucher, voucher_id)
    if not v:
        return _not_found('Voucher')
    process_voucher_financials(v.id, action='delete')
    db.session.delete(v)
    db.session.commit()
    return ok({'deleted': True, 'id': voucher_id})


# ======================================================================
# Contra entries
# ======================================================================

@api.get('/contras')
@require_api
def list_contras():
    query = ContraEntry.query
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    if start:
        query = query.filter(ContraEntry.date >= start)
    if end:
        query = query.filter(ContraEntry.date <= end)
    return paginate(query.order_by(ContraEntry.date.desc(), ContraEntry.id.desc()), _contra_dict)


@api.get('/contras/next-number')
@require_api
def contra_next_number():
    from logic import generate_contra_number
    return ok({'contra_no': generate_contra_number()})


@api.post('/contras')
@require_api
@require_admin_password
def create_contra():
    from logic import generate_contra_number, process_contra_financials

    body = _body()
    from_acc = body.get('from_account')
    to_acc = body.get('to_account')
    if from_acc not in ('Cash', 'Bank') or to_acc not in ('Cash', 'Bank'):
        return error("from_account and to_account must be 'Cash' or 'Bank'", 422)
    if from_acc == to_acc:
        return error('from_account and to_account must differ', 422)

    amount = Decimal(str(body.get('amount') or 0))
    if amount <= 0:
        return error('amount must be greater than zero', 422)

    c = ContraEntry(
        contra_no=body.get('contra_no') or generate_contra_number(),
        date=body.get('date') or datetime.now().strftime('%Y-%m-%d'),
        from_account=from_acc,
        to_account=to_acc,
        bank_id=body.get('bank_id') or None,
        amount=amount,
        description=body.get('description'),
        cheque_no=body.get('cheque_no'),
        debit_account_code=body.get('debit_account_code'),
        credit_account_code=body.get('credit_account_code'),
    )
    db.session.add(c)
    db.session.commit()
    success, message = process_contra_financials(c.id, action='add')
    if not success:
        return error(message, 500, code='posting_failed')
    db.session.refresh(c)
    return created(_contra_dict(c))


@api.delete('/contras/<int:contra_id>')
@require_api
@require_admin_password
def delete_contra(contra_id):
    from logic import process_contra_financials
    c = _get_or_404(ContraEntry, contra_id)
    if not c:
        return _not_found('Contra entry')
    process_contra_financials(c.id, action='delete')
    db.session.delete(c)
    db.session.commit()
    return ok({'deleted': True, 'id': contra_id})


# ======================================================================
# Chart of accounts & journal
# ======================================================================

@api.get('/accounts')
@require_api
def list_accounts():
    query = ChartOfAccounts.query
    account_type = request.args.get('type')
    if account_type:
        query = query.filter(ChartOfAccounts.account_type == account_type)
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        query = query.filter(db.or_(
            ChartOfAccounts.account_code.ilike(like),
            ChartOfAccounts.account_name.ilike(like),
        ))
    rows = query.order_by(ChartOfAccounts.account_code).all()
    return ok([_coa_dict(a) for a in rows], meta={'total': len(rows)})


@api.post('/accounts')
@require_api
@require_admin_password
def create_account():
    body = _body()
    required = ('account_code', 'account_name', 'account_type', 'account_category', 'normal_balance')
    missing = [f for f in required if not (body.get(f) or '').strip()]
    if missing:
        return error(f'Missing fields: {", ".join(missing)}', 422)
    if db.session.get(ChartOfAccounts, body['account_code']):
        return error('Account code already exists', 409, code='duplicate')

    a = ChartOfAccounts(
        account_code=body['account_code'].strip(),
        account_name=body['account_name'].strip(),
        account_type=body['account_type'],
        account_category=body['account_category'],
        normal_balance=body['normal_balance'],
        parent_code=body.get('parent_code') or None,
        description=body.get('description'),
        is_system=False,
    )
    db.session.add(a)
    db.session.commit()
    return created(_coa_dict(a))


@api.delete('/accounts/<string:code>')
@require_api
@require_admin_password
def delete_account(code):
    a = db.session.get(ChartOfAccounts, code)
    if not a:
        return _not_found('Account')
    if a.is_system:
        return error('System accounts cannot be deleted', 409, code='system_account')
    if a.journal_lines:
        return error('Account has journal activity and cannot be deleted', 409, code='has_activity')
    if a.children:
        return error('Account has child accounts', 409, code='has_children')
    db.session.delete(a)
    db.session.commit()
    return ok({'deleted': True, 'account_code': code})


@api.get('/journal')
@require_api
def list_journal():
    query = JournalEntry.query
    reference_type = request.args.get('reference_type')
    if reference_type:
        query = query.filter(JournalEntry.reference_type == reference_type)
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    if start:
        query = query.filter(JournalEntry.entry_date >= start)
    if end:
        query = query.filter(JournalEntry.entry_date <= end)
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        query = query.filter(db.or_(
            JournalEntry.entry_number.ilike(like),
            JournalEntry.description.ilike(like),
        ))
    return paginate(query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()),
                    _journal_dict)


@api.get('/journal/<int:entry_id>')
@require_api
def get_journal_entry(entry_id):
    je = _get_or_404(JournalEntry, entry_id)
    if not je:
        return _not_found('Journal entry')
    return ok(_journal_dict(je))


@api.post('/journal/<int:entry_id>/reverse')
@require_api
@require_admin_password
def reverse_journal_entry(entry_id):
    from logic import journal_reversal
    je = _get_or_404(JournalEntry, entry_id)
    if not je:
        return _not_found('Journal entry')
    if je.is_reversed:
        return error('Entry is already reversed', 409, code='already_reversed')
    reversal = journal_reversal(je.id)
    if not reversal:
        return error('Could not create reversal', 500)
    return created(_journal_dict(reversal))


# ======================================================================
# Reports
# ======================================================================

@api.get('/reports/trial-balance')
@require_api
def report_trial_balance():
    from logic import get_trial_balance
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    data = get_trial_balance(start, end)
    return ok({
        'as_of': data['today_date'],
        'accounts': [
            {
                'account_code': row['code'],
                'account_name': row['name'],
                'debit': _f(row['debit']),
                'credit': _f(row['credit']),
                'is_control_account': row['is_control'],
            }
            for row in data['accounts']
        ],
        'total_debit': _f(data['total_debit']),
        'total_credit': _f(data['total_credit']),
        'balanced': data['total_debit'] == data['total_credit'],
    })


@api.get('/reports/profit-loss')
@require_api
def report_profit_loss():
    from logic import get_profit_loss
    data = get_profit_loss(request.args.get('start_date'), request.args.get('end_date'))
    return ok({
        'as_of': data['today_date'],
        'revenue': [{'account_name': r.account_name, 'balance': _f(r.balance)} for r in data['revenues']],
        'total_revenue': _f(data['total_revenue']),
        'cogs': [{'account_name': c.account_name, 'balance': _f(c.balance)} for c in data['cogs']],
        'total_cogs': _f(data['total_cogs']),
        'gross_profit': _f(data['gross_profit']),
        'expenses': [{'account_name': e.account_name, 'balance': _f(e.balance)} for e in data['expenses']],
        'total_expenses': _f(data['total_expenses']),
        'net_profit': _f(data['net_profit']),
    })


@api.get('/reports/balance-sheet')
@require_api
def report_balance_sheet():
    from logic import get_balance_sheet
    data = get_balance_sheet(request.args.get('as_of_date'))
    return ok({
        'as_of': data['today_date'],
        'assets': [{'category': a.account_category, 'account_name': a.account_name,
                    'balance': _f(a.balance)} for a in data['assets']],
        'total_assets': _f(data['total_assets']),
        'liabilities': [{'category': l.account_category, 'account_name': l.account_name,
                         'balance': _f(l.balance)} for l in data['liabilities']],
        'total_liabilities': _f(data['total_liabilities']),
        'equity': [{'category': e.account_category, 'account_name': e.account_name,
                    'balance': _f(e.balance)} for e in data['equity']],
        'net_profit': _f(data['net_profit']),
        'total_equity': _f(data['total_equity']),
    })


@api.get('/reports/cash-bank-flow')
@require_api
def report_cash_bank_flow():
    from logic import get_cash_bank_flow_data
    start = request.args.get('start_date') or datetime.now().replace(day=1).strftime('%Y-%m-%d')
    end = request.args.get('end_date') or datetime.now().strftime('%Y-%m-%d')
    data = get_cash_bank_flow_data(start, end)
    return ok({
        'start_date': data['start_date'],
        'end_date': data['end_date'],
        'opening_cash': _f(data['opening_cash']),
        'opening_bank': _f(data['total_opening_bank']),
        'opening_total': _f(data['total_opening']),
        'transactions': [
            {
                'date': t['date'],
                'source': t['source'],
                'bank_name': t['bank_name'],
                'description': t['description'],
                'category': t['category'],
                'reference': t['ref'],
                'cash_in': _f(t['cash_in']),
                'cash_out': _f(t['cash_out']),
                'bank_in': _f(t['bank_in']),
                'bank_out': _f(t['bank_out']),
            }
            for t in data['transactions']
        ],
        'total_cash_in': _f(data['total_cash_in']),
        'total_cash_out': _f(data['total_cash_out']),
        'total_bank_in': _f(data['total_bank_in']),
        'total_bank_out': _f(data['total_bank_out']),
        'closing_cash': _f(data['closing_cash']),
        'closing_bank': _f(data['total_closing_bank']),
        'closing_total': _f(data['total_closing']),
    })


@api.get('/reports/money-flow')
@require_api
def report_money_flow():
    from logic import get_monthly_in_out_report
    rows = get_monthly_in_out_report()
    return ok([
        {
            'month': r['month'],
            'month_raw': r['month_raw'],
            'cash_in': _f(r['cash_in']),
            'cash_out': _f(r['cash_out']),
            'bank_in': _f(r['bank_in']),
            'bank_out': _f(r['bank_out']),
            'total_in': _f(r['total_in']),
            'total_out': _f(r['total_out']),
            'net_flow': _f(r['net_flow']),
        }
        for r in rows
    ])


@api.get('/reports/daily-cash')
@require_api
def report_daily_cash():
    from logic import get_daily_cash_report
    target = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    data = get_daily_cash_report(target)
    return ok({
        'date': target,
        'transactions': [_petty_cash_dict(t) for t in data['transactions']],
        'previous_cash': _f(data['prev_cash']),
        'current_cash': _f(data['today_cash']),
        'previous_bank': _f(data['prev_bank']),
        'current_bank': _f(data['today_bank']),
    })


# ======================================================================
# Employees
# ======================================================================

@api.get('/employees')
@require_api
def list_employees():
    query = Employee.query
    term = (request.args.get('q') or '').strip()
    if term:
        like = f'%{term}%'
        query = query.filter(db.or_(Employee.name.ilike(like), Employee.employee_id.ilike(like)))
    rows = query.all()
    rows.sort(key=lambda e: int(e.employee_id) if str(e.employee_id).isdigit() else 0)
    return ok([_employee_dict(e) for e in rows], meta={'total': len(rows)})


@api.post('/employees')
@require_api
@require_admin_password
def create_employee():
    body = _body()
    employee_code = (body.get('employee_id') or '').strip()
    name = (body.get('name') or '').strip()
    if not employee_code or not name:
        return error('employee_id and name are required', 422)
    if Employee.query.filter_by(employee_id=employee_code).first():
        return error('Employee ID already exists', 409, code='duplicate')

    e = Employee(
        employee_id=employee_code,
        name=name,
        designation=body.get('designation'),
        department=body.get('department'),
        joining_date=body.get('joining_date'),
        phone=body.get('phone'),
        net_salary=Decimal(str(body.get('net_salary') or 0)),
        cl_total=int(body.get('cl_total') or 10),
        ml_total=int(body.get('ml_total') or 14),
        fl_total=int(body.get('fl_total') or 0),
        el_total=int(body.get('el_total') or 0),
    )
    db.session.add(e)
    db.session.commit()
    return created(_employee_dict(e))


@api.patch('/employees/<int:employee_id>')
@require_api
@require_admin_password
def update_employee(employee_id):
    e = _get_or_404(Employee, employee_id)
    if not e:
        return _not_found('Employee')
    body = _body()
    for field in ('name', 'designation', 'department', 'joining_date', 'phone'):
        if field in body:
            setattr(e, field, body[field])
    if 'net_salary' in body:
        e.net_salary = Decimal(str(body['net_salary'] or 0))
    for field in ('cl_total', 'ml_total', 'fl_total', 'el_total'):
        if field in body:
            setattr(e, field, int(body[field] or 0))
    db.session.commit()
    return ok(_employee_dict(e))


@api.delete('/employees/<int:employee_id>')
@require_api
@require_admin_password
def delete_employee(employee_id):
    e = _get_or_404(Employee, employee_id)
    if not e:
        return _not_found('Employee')
    db.session.delete(e)
    db.session.commit()
    return ok({'deleted': True, 'id': employee_id})


# ======================================================================
# Attendance
# ======================================================================

@api.get('/attendance')
@require_api
def list_attendance():
    query = Attendance.query
    on = request.args.get('date')
    if on:
        query = query.filter(Attendance.date == on)
    employee_id = request.args.get('employee_id', type=int)
    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)
    start = request.args.get('start_date')
    end = request.args.get('end_date')
    if start:
        query = query.filter(Attendance.date >= start)
    if end:
        query = query.filter(Attendance.date <= end)
    return paginate(query.order_by(Attendance.date.desc(), Attendance.id), _attendance_dict)


@api.post('/attendance')
@require_api
@require_admin_password
def mark_attendance():
    from routes import calculate_working_hours

    body = _body()
    day = body.get('date')
    records = body.get('records') or []
    if not day:
        return error('date is required (YYYY-MM-DD)', 422)
    if not isinstance(records, list) or not records:
        return error('records must be a non-empty list', 422)

    saved = []
    for rec in records:
        employee_id = rec.get('employee_id')
        status = rec.get('status')
        if not employee_id or not status:
            continue
        employee = db.session.get(Employee, employee_id)
        if not employee:
            continue

        in_time = rec.get('in_time')
        out_time = rec.get('out_time')
        if status in ('Absent', 'Leave', 'Off Day', 'FL'):
            in_time = out_time = None
        hours = calculate_working_hours(in_time, out_time) if in_time and out_time else 0.0

        existing = Attendance.query.filter_by(employee_id=employee.id, date=day).first()
        if existing:
            existing.status = status
            existing.in_time = in_time
            existing.out_time = out_time
            existing.working_hours = hours
            existing.notes = rec.get('notes')
            saved.append(existing)
        else:
            row = Attendance(employee_id=employee.id, date=day, status=status,
                             in_time=in_time, out_time=out_time,
                             working_hours=hours, notes=rec.get('notes'))
            db.session.add(row)
            saved.append(row)

    db.session.commit()
    return ok([_attendance_dict(a) for a in saved], meta={'saved': len(saved), 'date': day})


# ======================================================================
# Leaves
# ======================================================================

@api.get('/leaves')
@require_api
def list_leaves():
    query = Leave.query
    employee_id = request.args.get('employee_id', type=int)
    if employee_id:
        query = query.filter(Leave.employee_id == employee_id)
    status = request.args.get('status')
    if status:
        query = query.filter(Leave.status == status)
    return paginate(query.order_by(Leave.from_date.desc(), Leave.id.desc()), _leave_dict)


@api.post('/leaves')
@require_api
@require_admin_password
def create_leave():
    body = _body()
    employee_id = body.get('employee_id')
    if not employee_id or not db.session.get(Employee, employee_id):
        return error('a valid employee_id is required', 422)
    leave_type = body.get('leave_type')
    if leave_type not in ('CL', 'ML', 'FL', 'EL'):
        return error("leave_type must be one of CL, ML, FL, EL", 422)

    from_date, to_date = body.get('from_date'), body.get('to_date')
    if not from_date or not to_date:
        return error('from_date and to_date are required', 422)
    try:
        days = (datetime.strptime(to_date, '%Y-%m-%d')
                - datetime.strptime(from_date, '%Y-%m-%d')).days + 1
    except ValueError:
        return error('Dates must be YYYY-MM-DD', 422)
    if days < 1:
        return error('to_date must be on or after from_date', 422)

    leave = Leave(
        employee_id=employee_id,
        leave_type=leave_type,
        from_date=from_date,
        to_date=to_date,
        total_days=days,
        status=body.get('status') or 'Approved',
        reason=body.get('reason'),
    )
    db.session.add(leave)
    db.session.commit()
    return created(_leave_dict(leave))


@api.patch('/leaves/<int:leave_id>')
@require_api
@require_admin_password
def update_leave(leave_id):
    leave = _get_or_404(Leave, leave_id)
    if not leave:
        return _not_found('Leave')
    body = _body()
    if 'status' in body:
        leave.status = body['status']
    if 'reason' in body:
        leave.reason = body['reason']
    db.session.commit()
    return ok(_leave_dict(leave))


@api.delete('/leaves/<int:leave_id>')
@require_api
@require_admin_password
def delete_leave(leave_id):
    leave = _get_or_404(Leave, leave_id)
    if not leave:
        return _not_found('Leave')
    db.session.delete(leave)
    db.session.commit()
    return ok({'deleted': True, 'id': leave_id})


# ======================================================================
# Salary
# ======================================================================

@api.get('/salary')
@require_api
def list_salary():
    month = request.args.get('month')
    year = request.args.get('year')
    query = Salary.query
    if month:
        query = query.filter(Salary.month == month.zfill(2))
    if year:
        query = query.filter(Salary.year == str(year))
    return paginate(query.order_by(Salary.employee_id), _salary_dict)


@api.post('/salary/generate')
@require_api
@require_admin_password
def generate_salary():
    import calendar as pycal
    from logic import journal_payroll

    body = _body()
    month_year = body.get('month_year')  # 'YYYY-MM'
    if not month_year:
        month = str(body.get('month') or '').zfill(2)
        year = str(body.get('year') or '')
        if not month or not year:
            return error('month_year (YYYY-MM) or month+year is required', 422)
        month_year = f'{year}-{month}'

    try:
        year, monthstr = month_year.split('-')
        month_int = int(monthstr)
        total_days = pycal.monthrange(int(year), month_int)[1]
    except (ValueError, IndexError):
        return error('month_year must be YYYY-MM', 422)

    employee_ids = body.get('employee_ids')
    employees = (Employee.query.filter(Employee.id.in_(employee_ids)).all()
                 if employee_ids else Employee.query.all())
    if not employees:
        return error('No employees to process', 422)

    count = 0
    for emp in employees:
        start_date = f'{year}-{monthstr}-01'
        end_date = f'{year}-{monthstr}-{total_days:02d}'
        attendances = Attendance.query.filter(
            Attendance.employee_id == emp.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date,
        ).all()

        present = late = absent = leave_days = off = 0
        marked = set()
        for att in attendances:
            try:
                marked.add(datetime.strptime(att.date, '%Y-%m-%d').date())
            except (ValueError, TypeError):
                pass
            if att.status == 'Present':
                present += 1
            elif att.status == 'Late':
                late += 1
            elif att.status == 'Absent':
                absent += 1
            elif att.status == 'Leave':
                leave_days += 1
            elif att.status == 'Off Day':
                off += 1

        for day in range(1, total_days + 1):
            current = datetime(int(year), month_int, day).date()
            if current.weekday() == pycal.FRIDAY and current not in marked:
                off += 1

        effective_absent = absent + (late // 3)
        per_day = Decimal(str(emp.net_salary or 0)) / total_days if total_days else Decimal('0')
        deduction = per_day * effective_absent
        base = Decimal(str(emp.net_salary or 0)) - deduction

        existing = Salary.query.filter_by(employee_id=emp.id, month=monthstr, year=year).first()
        if existing:
            existing.net_salary = emp.net_salary
            existing.working_days = total_days
            existing.present_days = present + late
            existing.absent_days = absent
            existing.late_days = late
            existing.leave_days = leave_days
            existing.off_days = off
            existing.per_day_salary = per_day
            existing.deduction = deduction
            existing.final_salary = max(
                Decimal('0'), base + Decimal(str(existing.mobile_bill or 0))
                + Decimal(str(existing.bonus or 0)))
        else:
            db.session.add(Salary(
                employee_id=emp.id,
                month=monthstr,
                year=year,
                net_salary=emp.net_salary,
                working_days=total_days,
                present_days=present + late,
                absent_days=absent,
                leave_days=leave_days,
                late_days=late,
                off_days=off,
                per_day_salary=per_day,
                deduction=deduction,
                final_salary=max(Decimal('0'), base),
            ))
        count += 1

    db.session.commit()

    all_salaries = Salary.query.filter_by(year=year, month=monthstr).all()
    if all_salaries:
        gross = sum(Decimal(str(s.net_salary or 0)) for s in all_salaries)
        net = sum(Decimal(str(s.final_salary or 0)) for s in all_salaries)
        deductions = sum(Decimal(str(s.deduction or 0)) for s in all_salaries)
        journal_payroll(gross, net, deductions, monthstr, year)

    return ok([_salary_dict(s) for s in all_salaries], meta={'generated': count, 'month_year': month_year})


@api.post('/salary/<int:salary_id>/paid')
@require_api
@require_admin_password
def mark_salary_paid(salary_id):
    from logic import cleanup_journal_entries, journal_salary_payment
    s = _get_or_404(Salary, salary_id)
    if not s:
        return _not_found('Salary')
    if s.status == 'Paid':
        return error('Salary is already marked paid', 409, code='already_paid')

    s.status = 'Paid'
    s.payment_date = datetime.now().strftime('%Y-%m-%d')
    cleanup_journal_entries(reference_id=f'SAL-SAL-{s.id}')
    journal_salary_payment(s.employee, '1010', s.final_salary, f'SAL-{s.id}')
    db.session.commit()
    return ok(_salary_dict(s))


@api.post('/salary/<int:salary_id>/unpaid')
@require_api
@require_admin_password
def mark_salary_unpaid(salary_id):
    from logic import cleanup_journal_entries
    s = _get_or_404(Salary, salary_id)
    if not s:
        return _not_found('Salary')
    s.status = 'Unpaid'
    s.payment_date = None
    cleanup_journal_entries(reference_id=f'SAL-SAL-{s.id}')
    db.session.commit()
    return ok(_salary_dict(s))


# ======================================================================
# Todos (scoped to the authenticated user)
# ======================================================================

@api.get('/todos')
@require_api
def list_todos():
    query = Todo.query.filter_by(user_id=g.api_user.id)
    if _qs_flag('today'):
        query = query.filter(Todo.due_date == datetime.now().strftime('%Y-%m-%d'))
    if _qs_flag('open'):
        query = query.filter(Todo.is_completed.is_(False))
    return paginate(query.order_by(Todo.is_completed, Todo.due_date, Todo.id.desc()), _todo_dict)


@api.post('/todos')
@require_api
def create_todo():
    body = _body()
    task = (body.get('task') or '').strip()
    if not task:
        return error('task is required', 422)
    todo = Todo(
        task=task,
        category=body.get('category') or 'General',
        due_date=body.get('due_date'),
        due_time=body.get('due_time'),
        user_id=g.api_user.id,
    )
    db.session.add(todo)
    db.session.commit()
    return created(_todo_dict(todo))


@api.patch('/todos/<int:todo_id>')
@require_api
def update_todo(todo_id):
    todo = _get_or_404(Todo, todo_id)
    if not todo or todo.user_id != g.api_user.id:
        return _not_found('Todo')
    body = _body()
    for field in ('task', 'category', 'due_date', 'due_time'):
        if field in body:
            setattr(todo, field, body[field])
    if 'is_completed' in body:
        todo.is_completed = bool(body['is_completed'])
    db.session.commit()
    return ok(_todo_dict(todo))


@api.post('/todos/<int:todo_id>/toggle')
@require_api
def toggle_todo(todo_id):
    todo = _get_or_404(Todo, todo_id)
    if not todo or todo.user_id != g.api_user.id:
        return _not_found('Todo')
    todo.is_completed = not todo.is_completed
    db.session.commit()
    return ok(_todo_dict(todo))


@api.delete('/todos/<int:todo_id>')
@require_api
def delete_todo(todo_id):
    todo = _get_or_404(Todo, todo_id)
    if not todo or todo.user_id != g.api_user.id:
        return _not_found('Todo')
    db.session.delete(todo)
    db.session.commit()
    return ok({'deleted': True, 'id': todo_id})


# ======================================================================
# Error handling & CORS
# ======================================================================

@api.errorhandler(Exception)
def handle_api_exception(exc):
    from werkzeug.exceptions import HTTPException
    db.session.rollback()
    current_app.logger.exception('API error on %s %s', request.method, request.path)
    if isinstance(exc, HTTPException):
        return error(exc.description, exc.code or 500)
    return error(str(exc), 500, code='internal_error')


@api.after_request
def add_cors_headers(response):
    origin = current_app.config.get('API_CORS_ORIGIN', '*')
    response.headers.setdefault('Access-Control-Allow-Origin', origin)
    response.headers.setdefault('Access-Control-Allow-Headers',
                                'Authorization, Content-Type, X-Admin-Password')
    response.headers.setdefault('Access-Control-Allow-Methods',
                                'GET, POST, PATCH, DELETE, OPTIONS')
    return response
