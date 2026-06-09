import os
import json
import sqlite3
import datetime
from google import genai
from google.genai import types
from telegram_utils import log_debug

# Database path is typically C:\NRV\nexus.db or read from env
db_path = os.environ.get('NEXUS_DATA_PATH', 'C:\\NRV')
DB_FILE = os.path.join(db_path, 'nexus.db')

def get_ai_client():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return None
    try:
        return genai.Client()
    except Exception as e:
        log_debug(f"Failed to initialize Gemini Client: {e}")
        return None

def get_database_schema() -> str:
    """Returns the SQLite schema of the database to understand what tables and columns exist."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        schema_info = []
        for name, sql in tables:
            if name != 'sqlite_sequence' and sql:
                schema_info.append(f"Table: {name}\nSchema:\n{sql}")
        conn.close()
        return "\n\n".join(schema_info)
    except Exception as e:
        return json.dumps({"error": str(e)})

def execute_read_query(query: str) -> str:
    """Executes a SELECT SQL query against the database and returns the results. ONLY use this to read data. The query must start with SELECT."""
    if not query.strip().lower().startswith("select") and not query.strip().lower().startswith("pragma"):
        return json.dumps({"error": "Only SELECT or PRAGMA queries are allowed."})
    
    try:
        conn = sqlite3.connect(DB_FILE)
        # Use row factory to get dict-like objects
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Add LIMIT to prevent massive responses if not present
        if "limit" not in query.lower():
            query += " LIMIT 50"
            
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Convert rows to dicts
        results = [dict(row) for row in rows]
        conn.close()
        
        return json.dumps(results, default=str) # Handle dates and decimals
    except Exception as e:
        return json.dumps({"error": str(e)})

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
        "You have full read access to their SQLite database via SQL queries. "
        "Always use 'get_database_schema' first if you are unsure about the exact table names or columns. "
        "Use 'execute_read_query' to fetch the data you need to answer the user's question. "
        "When referencing currency, note that it is BDT (Taka). "
        "The user may write in Bengali or English — always respond in the same language they used. "
        "Never invent data. Execute the required queries to find out."
    )

    try:
        model_id = 'gemini-2.5-flash'
        
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[get_database_schema, execute_read_query]
        )

        # Build contents from history securely
        contents = []
        recent_history = chat_history[-6:] if chat_history else []
        for msg in recent_history:
             if isinstance(msg, dict) and 'role' in msg and 'parts' in msg:
                 role = msg['role']
                 # Ensure role is valid ('user' or 'model')
                 if role not in ['user', 'model']: continue
                 text_val = msg['parts'][0].get('text', '') if msg['parts'] else ''
                 if not text_val: continue
                 
                 contents.append(
                     types.Content(role=role, parts=[types.Part.from_text(text=text_val)])
                 )
        
        chat = client.chats.create(
            model=model_id,
            config=config,
            history=contents
        )
        
        response = chat.send_message(prompt)
        return response.text

    except Exception as e:
        log_debug(f"AI Chat Error: {e}")
        return f"Sorry, I encountered an error communicating with the AI. Error logic: {str(e)}"
