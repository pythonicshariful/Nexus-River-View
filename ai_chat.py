import os
import json
from google import genai
from google.genai import types
from database import db
from models import (Director, Customer, Transaction, PettyCash, Bank, BankTransaction, 
                    Party, PartyLedger, Voucher, ContraEntry, Employee, Attendance, Leave, 
                    Salary, ChartOfAccounts, JournalEntry, JournalLine)
from telegram_utils import log_debug
import datetime

# Create the client once
# It will automatically pick up GEMINI_API_KEY from the environment
def get_ai_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return None
    try:
        return genai.Client()
    except Exception as e:
        log_debug(f"Failed to initialize Gemini Client: {e}")
        return None

# --- Database Read Tools ---

def query_database(model_name: str, limit: int = 10, offset: int = 0) -> str:
    """
    Query the Nexus River View database.
    
    Args:
        model_name: The table to query. Allowed values: 'director', 'customer', 'transaction', 'petty_cash', 'bank', 'bank_transaction'.
        limit: Maximum number of records to return. Max is 50.
        offset: Number of records to skip.
    """
    models = {
        'director': Director,
        'customer': Customer,
        'transaction': Transaction,
        'petty_cash': PettyCash,
        'bank': Bank,
        'bank_transaction': BankTransaction,
        'party': Party,
        'party_ledger': PartyLedger,
        'voucher': Voucher,
        'contra': ContraEntry,
        'employee': Employee,
        'attendance': Attendance,
        'leave': Leave,
        'salary': Salary,
        'coa': ChartOfAccounts,
        'journal_entry': JournalEntry,
        'journal_line': JournalLine
    }
    
    model_name = model_name.lower()
    if model_name not in models:
        return json.dumps({"error": f"Invalid model_name. Allowed: {list(models.keys())}"})
    
    limit = min(limit, 50) # Cap at 50 to prevent huge context
    model = models[model_name]
    
    try:
        from sync_manager import sync_manager
        records = model.query.offset(offset).limit(limit).all()
        data = [sync_manager._model_to_dict(model_name, r) for r in records]
        return json.dumps(data)
    except Exception as e:
        log_debug(f"AI DB Query Error: {e}")
        return json.dumps({"error": str(e)})


def get_database_summary() -> str:
    """
    Get a high-level summary of the database counts and totals across the entire company.
    """
    try:
        summary = {
            "counts": {
                "directors": db.session.query(Director).count(),
                "customers": db.session.query(Customer).count(),
                "parties": db.session.query(Party).count(),
                "employees": db.session.query(Employee).count(),
                "journal_entries": db.session.query(JournalEntry).count()
            },
            "financials": {
                "total_project_value": db.session.query(db.func.sum(Customer.total_price)).scalar() or 0,
                "total_collection": db.session.query(db.func.sum(Customer.total_paid)).scalar() or 0,
                "total_due": db.session.query(db.func.sum(Customer.due_amount)).scalar() or 0,
                "cash_in_hand": 0, # Calculated below
                "bank_balance": 0 # Calculated below
            },
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Petty Cash
        pc_in = db.session.query(db.func.sum(PettyCash.amount)).filter(PettyCash.type == 'Income').scalar() or 0
        pc_out = db.session.query(db.func.sum(PettyCash.amount)).filter(PettyCash.type == 'Expense').scalar() or 0
        summary["financials"]["cash_in_hand"] = pc_in - pc_out
        
        # Bank
        bank_in = db.session.query(db.func.sum(BankTransaction.credit)).scalar() or 0
        bank_out = db.session.query(db.func.sum(BankTransaction.debit)).scalar() or 0
        summary["financials"]["bank_balance"] = bank_in - bank_out
        
        return json.dumps(summary)
    except Exception as e:
         log_debug(f"AI DB Summary Error: {e}")
         return json.dumps({"error": str(e)})

def search_parties(query: str) -> str:
    """
    Find specific suppliers, contractors, or individual parties.
    """
    try:
        from sqlalchemy import or_
        results = Party.query.filter(
            or_(
                Party.name.ilike(f"%{query}%"),
                Party.phone.ilike(f"%{query}%"),
                Party.category.ilike(f"%{query}%")
            )
        ).limit(10).all()
        
        data = []
        for p in results:
            data.append({
                "name": p.name,
                "category": p.category,
                "balance": p.current_balance
            })
        return json.dumps(data)
    except Exception as e:
        log_debug(f"AI Party Search Error: {e}")
        return json.dumps({"error": str(e)})

def get_accounting_status() -> str:
    """
    Get the Trial Balance and Profit/Loss summary.
    """
    try:
        from logic import get_trial_balance, get_profit_loss
        tb = get_trial_balance()
        pl = get_profit_loss()
        return json.dumps({
            "trial_balance_status": "Balanced" if tb['total_debit'] == tb['total_credit'] else "Unbalanced",
            "net_profit": pl['net_profit'],
            "total_revenue": pl['total_revenue'],
            "total_expenses": pl['total_expenses']
        })
    except Exception as e:
        log_debug(f"AI Accounting Error: {e}")
        return json.dumps({"error": str(e)})

def search_customers(query: str) -> str:
    """
    Find specific customers by name, phone number, plot number, or Customer ID.
    Use this to answer questions like 'How much does Ariful owe?' or 'Find customer AI-01'.
    """
    try:
        from sqlalchemy import or_
        results = Customer.query.filter(
            or_(
                Customer.name.ilike(f"%{query}%"),
                Customer.phone.ilike(f"%{query}%"),
                Customer.customer_id.ilike(f"%{query}%"),
                Customer.plot_no.ilike(f"%{query}%")
            )
        ).limit(10).all()
        
        if not results:
            return json.dumps({"message": "No customers found matching that query."})
            
        data = []
        for c in results:
            data.append({
                "id": c.id,
                "customer_id": c.customer_id,
                "name": c.name,
                "phone": c.phone,
                "plot_no": c.plot_no,
                "shares": c.shares,
                "total_price": c.total_price,
                "total_paid": c.total_paid,
                "due_amount": c.due_amount,
                "director": c.director.name if c.director else "Unknown"
            })
        return json.dumps(data)
    except Exception as e:
        log_debug(f"AI Search Error: {e}")
        return json.dumps({"error": str(e)})

def search_directors(query: str) -> str:
    """
    Find specific directors by name or phone number and return their financial summary.
    Use this to answer questions like 'How much does Anowar Khan owe?' or 'What is director Azad\'s due?'
    """
    try:
        from sqlalchemy import or_
        from models import Installment
        results = Director.query.filter(
            or_(
                Director.name.ilike(f"%{query}%"),
                Director.phone.ilike(f"%{query}%")
            )
        ).limit(5).all()

        if not results:
            return json.dumps({"message": f"No director found matching '{query}'."})

        total_rate = sum(inst.amount_per_share for inst in Installment.query.all())

        data = []
        for d in results:
            total_expected = d.total_share * total_rate
            data.append({
                "name": d.name,
                "phone": d.phone,
                "total_shares": d.total_share,
                "total_expected_taka": total_expected,
                "total_paid_taka": d.total_paid,
                "total_due_taka": d.total_due,
                "customers": [{"name": c.name, "paid": c.total_paid, "due": c.due_amount} for c in d.customers]
            })
        return json.dumps(data)
    except Exception as e:
        log_debug(f"AI Director Search Error: {e}")
        return json.dumps({"error": str(e)})

def get_bank_balances() -> str:
    """
    Get the current balance of all bank accounts in the system.
    """
    try:
        banks = Bank.query.all()
        balances = []
        for b in banks:
            total_credit = db.session.query(db.func.sum(BankTransaction.credit)).filter_by(bank_id=b.id).scalar() or 0.0
            total_debit = db.session.query(db.func.sum(BankTransaction.debit)).filter_by(bank_id=b.id).scalar() or 0.0
            balances.append({
                "bank_name": b.bank_name,
                "account_holder_name": b.account_holder_name,
                "account_no": b.account_no,
                "current_balance": total_credit - total_debit
            })
        return json.dumps(balances)
    except Exception as e:
        log_debug(f"AI Bank Balance Error: {e}")
        return json.dumps({"error": str(e)})

def get_petty_cash_summary() -> str:
    """
    Get the summary of the petty cash account (total received, total spent, and current balance).
    """
    try:
        transactions = PettyCash.query.all()
        total_in = sum(t.amount for t in transactions if t.type == 'Income')
        total_out = sum(t.amount for t in transactions if t.type == 'Expense')
        balance = total_in - total_out
        
        summary = {
            "total_received": total_in,
            "total_spent": total_out,
            "current_balance": balance
        }
        return json.dumps(summary)
    except Exception as e:
        log_debug(f"AI Petty Cash Error: {e}")
        return json.dumps({"error": str(e)})

# --- AI Interaction Loop ---

def chat_with_db(prompt: str, chat_history: list = None) -> str:
    """
    Sends a query to Gemini with tools to query the database.
    """
    client = get_ai_client()
    if not client:
        return "Gemini API key is missing or invalid. Please check your .env file."

    if chat_history is None:
         chat_history = []

    system_instruction = (
        "You are a helpful AI Accounting Assistant for 'Nexus River View'. "
        "You have read-only access to their SQLite database. "
        "Use 'search_directors' when asked about a director's dues, paid amount, or financial status. "
        "Use 'search_customers' to find specific customers when asked about personal dues or balances. "
        "Use 'get_database_summary' for company-wide totals. "
        "When referencing currency, note that it is BDT (Taka). "
        "The user may write in Bengali or English — always respond in the same language they used. "
        "If you don't know the answer, use the tools to find out. "
        "Never invent data. Present financial information clearly."
    )

    try:
        # Create a chat session. GenAI SDK manages tool calling automatically in chat sessions if tools are passed.
        # But for fine-grained control or specific model versions, we can pass tools to the model config.
        
        # We will use gemini-2.5-flash as the fast, standard tool-calling model
        model_id = 'gemini-2.5-flash'
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            # Pass our python functions directly as tools
            tools=[query_database, get_database_summary, search_customers, search_directors, 
                   search_parties, get_bank_balances, get_petty_cash_summary, get_accounting_status],
        )

        # Build contents from history securely
        # Gemini is very strict about history. It needs alternating User -> Model -> User -> Model
        # Since we don't save the raw backend tool interactions to the frontend localStorage, 
        # we simplify the history: we treat past interactions purely as text conversation.
        # To save tokens, we only keep the last 6 messages (3 full conversation turns).
        contents = []
        recent_history = chat_history[-6:] if chat_history else []
        for msg in recent_history:
             if isinstance(msg, dict) and 'role' in msg and 'parts' in msg:
                 role = msg['role']
                 # Ensure role is valid ('user' or 'model')
                 if role not in ['user', 'model']: continue
                 text_val = msg['parts'][0].get('text', '') if msg['parts'] else ''
                 if not text_val: continuepyt
                 
                 contents.append(
                     types.Content(role=role, parts=[types.Part.from_text(text=text_val)])
                 )
        
        # Add the latest user prompt
        contents.append(
             types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        )

        # Call the model
        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )
        
        return response.text

    except Exception as e:
        log_debug(f"AI Chat Error: {e}")
        return f"Sorry, I encountered an error communicating with the AI. Error logic: {str(e)}"
