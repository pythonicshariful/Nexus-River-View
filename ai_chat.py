"""
Nexus River View — AI Assistant (Aion Labs, with Gemini fallback)

The assistant answers questions about the live SQLite database using
tool calling: the model can inspect the schema (get_database_schema)
and run READ-ONLY SELECT queries (execute_read_query). It can never
write to the database:

- queries are validated (single SELECT/PRAGMA statement only)
- the SQLite connection itself is opened in read-only mode
- the `user.password_hash` column is blocked in schema and queries

Primary provider: Aion Labs (OpenAI-compatible API)
    AION_API_KEY   - required for the Aion path (set in Settings / .env)
    AION_MODEL     - optional, default "aion-labs/aion-3.0-mini"
    AION_BASE_URL  - optional, default "https://api.aionlabs.ai/v1"

Fallback: if AION_API_KEY is not set but GEMINI_API_KEY is, the legacy
Gemini implementation is used so existing installs keep working.
"""
import os
import re
import json
import sqlite3
import sys

import requests
from flask import current_app
from telegram_utils import log_debug

# Database path is typically C:\NRV\nexus.db or read from env
db_path = os.environ.get('NEXUS_DATA_PATH', 'C:\\NRV')
DB_FILE = os.path.join(db_path, 'nexus.db')

AION_DEFAULT_MODEL = 'aion-labs/aion-3.0-mini'
AION_DEFAULT_BASE_URL = 'https://api.aionlabs.ai/v1'
# Aion sits behind Cloudflare, which rejects default Python HTTP
# user-agents (HTTP 403 / error 1010) — send a browser-like UA.
AION_USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/126.0 Safari/537.36')
MAX_TOOL_ROUNDS = 6
MAX_RESULT_CHARS = 15000


def get_db_file():
    # 1. Try active Flask current_app context
    try:
        if current_app:
            path = current_app.config.get('DATABASE_PATH')
            if path:
                return path
    except Exception:
        pass

    # 2. Static resolution fallback (same as app.py logic)
    data_dir = os.environ.get('NEXUS_DATA_PATH')
    if getattr(sys, 'frozen', False):
        if not data_dir or data_dir == '.':
            base_path = os.path.dirname(sys.executable)
            data_dir = base_path
    else:
        if not data_dir or data_dir == '.':
            data_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.abspath(data_dir)

    return os.path.join(data_dir, 'nexus.db')


def _connect_readonly():
    """Open the database strictly read-only (writes are impossible)."""
    path = get_db_file()
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------- tools

def get_database_schema() -> str:
    """Returns the SQLite schema of the database (tables and columns).

    The password_hash column is redacted — credential material is never
    exposed to the model.
    """
    try:
        conn = _connect_readonly()
        cursor = conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        schema_info = []
        for name, sql in tables:
            if name != 'sqlite_sequence' and sql:
                lines = [ln for ln in sql.splitlines()
                         if 'password_hash' not in ln.lower()]
                # Collapse whitespace — the schema is sent to the model
                # on many questions, so keep it compact to save tokens.
                compact = ' '.join(' '.join(lines).split())
                schema_info.append(f"Table: {name} — {compact}")
        conn.close()
        return "\n\n".join(schema_info)
    except Exception as e:
        return json.dumps({"error": str(e)})


_WRITE_KEYWORDS = re.compile(
    r'\b(insert|update|delete|drop|alter|attach|detach|vacuum|reindex|'
    r'replace|create|truncate|grant|revoke)\b', re.IGNORECASE)


def execute_read_query(query: str) -> str:
    """Executes a single read-only SELECT query and returns rows as JSON.

    Only SELECT (or PRAGMA table_info) is allowed, only one statement,
    no password_hash access. A LIMIT is added when the model omits one.
    """
    q = (query or '').strip()
    # Single statement only
    q_single = q.rstrip(';').strip()
    if ';' in q_single:
        return json.dumps({"error": "Only a single query is allowed."})
    q = q_single

    lower = q.lower()
    if not (lower.startswith('select') or lower.startswith('pragma')):
        return json.dumps({"error": "Only SELECT or PRAGMA queries are allowed."})
    if 'password_hash' in lower:
        return json.dumps({"error": "Access to password hashes is not allowed."})
    if _WRITE_KEYWORDS.search(q):
        return json.dumps({"error": "Write operations are not allowed."})

    try:
        conn = _connect_readonly()
        cursor = conn.cursor()

        if lower.startswith('select') and 'limit' not in lower:
            q += " LIMIT 100"

        cursor.execute(q)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()

        out = json.dumps(results, default=str)
        if len(out) > MAX_RESULT_CHARS:
            out = out[:MAX_RESULT_CHARS] + \
                f'... [truncated: {len(results)} rows total, showing a prefix]'
        return out
    except Exception as e:
        return json.dumps({"error": str(e)})


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": ("Get the database schema: every table and its "
                            "columns. Call this first when you are unsure "
                            "about exact table or column names."),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_read_query",
            "description": ("Run a single read-only SQLite SELECT query "
                            "against the Nexus River View database and get "
                            "the rows back as JSON. Use this to fetch the "
                            "real data needed to answer the user."),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "One SELECT statement, e.g. "
                                       "\"SELECT COUNT(*) AS n FROM customer\"",
                    }
                },
                "required": ["query"],
            },
        },
    },
]

SYSTEM_INSTRUCTION = (
    "You are a helpful AI Accounting Assistant for 'Nexus River View'. "
    "You have full READ access to their SQLite database through two tools. "
    "For ANY question about data, counts, amounts, people, payments or "
    "reports you MUST use the tools to fetch the real data — first "
    "'get_database_schema' if you are unsure about table/column names, "
    "then 'execute_read_query' with precise SELECT queries (use SUM, "
    "COUNT, GROUP BY etc. instead of fetching raw rows when possible). "
    "Never invent or guess numbers. If a query returns an error, fix the "
    "query and try again. "
    "Currency is BDT (Taka, ৳). Dates in most tables are text strings. "
    "The user may write in Bengali or English — always respond in the "
    "same language they used. Keep answers clear and concise, and show "
    "the key figures you found.\n\n"
    "CHART GENERATION CAPABILITY:\n"
    "You can display charts (bar, pie, line, doughnut) directly to the "
    "user in their chat. If the user asks for a chart, graph, "
    "visualization, or if a summary report would benefit from a visual "
    "breakdown, you MUST output a JSON block inside a ```chart code "
    "block. The format must be exactly like this:\n"
    "```chart\n"
    "{\n"
    "  \"type\": \"bar\", // or 'pie', 'line', 'doughnut'\n"
    "  \"title\": \"Chart Title\",\n"
    "  \"labels\": [\"Label A\", \"Label B\", ...],\n"
    "  \"data\": [12000, 34000, ...],\n"
    "  \"label\": \"Legend Label\" // optional\n"
    "}\n"
    "```\n"
    "Output ONLY valid JSON within the chart code block. Keep text "
    "explanations outside of the code block."
)


def _history_to_messages(chat_history):
    """Convert stored history to OpenAI-style messages.

    Accepts both the web UI's Gemini-style format
    {'role': 'user'|'model', 'parts': [{'text': ...}]} and plain
    OpenAI-style {'role': ..., 'content': ...} entries.
    """
    messages = []
    for msg in (chat_history or [])[-6:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get('role')
        if role == 'model':
            role = 'assistant'
        if role not in ('user', 'assistant'):
            continue
        text = msg.get('content') or ''
        if not text and msg.get('parts'):
            try:
                text = msg['parts'][0].get('text', '')
            except Exception:
                text = ''
        if text:
            messages.append({"role": role, "content": str(text)})
    return messages


# ---------------------------------------------------------------- Aion

def _aion_config():
    api_key = (os.environ.get('AION_API_KEY') or '').strip()
    if not api_key or api_key == 'YOUR_AION_API_KEY_HERE':
        return None
    return {
        'api_key': api_key,
        'model': (os.environ.get('AION_MODEL') or '').strip() or AION_DEFAULT_MODEL,
        'base_url': ((os.environ.get('AION_BASE_URL') or '').strip()
                     or AION_DEFAULT_BASE_URL).rstrip('/'),
    }


def _run_tool(name, arguments):
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
    except Exception:
        args = {}
    if name == 'get_database_schema':
        return get_database_schema()
    if name == 'execute_read_query':
        return execute_read_query(args.get('query', ''))
    return json.dumps({"error": f"Unknown tool: {name}"})


def _chat_with_aion(prompt, chat_history, cfg):
    url = cfg['base_url'] + '/chat/completions'
    headers = {
        'Authorization': f"Bearer {cfg['api_key']}",
        'Content-Type': 'application/json',
        'User-Agent': AION_USER_AGENT,
    }
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    messages += _history_to_messages(chat_history)
    messages.append({"role": "user", "content": prompt})

    for _round in range(MAX_TOOL_ROUNDS):
        payload = {
            'model': cfg['model'],
            'messages': messages,
            'tools': TOOLS,
            'tool_choice': 'auto',
            'max_tokens': 2000,
            'temperature': 0.2,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=110)
        except requests.exceptions.RequestException as e:
            return f"Sorry, I could not reach the Aion AI service. ({e})"

        if resp.status_code == 401:
            return ("Aion API key is invalid. Please check AION_API_KEY "
                    "in Settings.")
        if resp.status_code == 429:
            detail = ''
            try:
                detail = resp.json().get('error', {}).get('message', '')
            except Exception:
                pass
            if 'daily' in detail.lower():
                return ("Aion daily free-token limit is over for today "
                        f"({detail}) It resets tomorrow — or add balance "
                        "to the Aion account for uninterrupted use.")
            return ("Aion rate limit reached. Please wait a minute and "
                    "try again.")
        if resp.status_code != 200:
            log_debug(f"Aion API error {resp.status_code}: {resp.text[:300]}")
            return (f"Sorry, the Aion AI service returned an error "
                    f"(HTTP {resp.status_code}). Please try again.")

        data = resp.json()
        try:
            message = data['choices'][0]['message']
        except Exception:
            log_debug(f"Aion unexpected response: {str(data)[:300]}")
            return "Sorry, I received an unexpected response from the AI."

        tool_calls = message.get('tool_calls') or []
        if tool_calls:
            # Record the assistant's tool-call turn, then run each tool
            messages.append({
                "role": "assistant",
                "content": message.get('content') or '',
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                fn = (call.get('function') or {})
                result = _run_tool(fn.get('name', ''), fn.get('arguments', '{}'))
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get('id', ''),
                    "content": result,
                })
            continue

        content = (message.get('content') or '').strip()
        if content:
            return content
        # Reasoning consumed the whole budget without a visible answer;
        # ask once more, without tools, for the final text.
        messages.append({"role": "user",
                         "content": "Now give the final answer in plain text."})
        payload['tools'] = []
        payload.pop('tool_choice', None)
        try:
            resp2 = requests.post(url, headers=headers, json={
                'model': cfg['model'], 'messages': messages,
                'max_tokens': 1500, 'temperature': 0.2,
            }, timeout=110)
            text2 = resp2.json()['choices'][0]['message'].get('content', '').strip()
            if text2:
                return text2
        except Exception as e:
            log_debug(f"Aion final-answer retry failed: {e}")
        return "Sorry, the AI could not produce an answer. Please ask again."

    return ("Sorry, I needed too many database lookups for that question. "
            "Please ask something more specific.")


# ---------------------------------------------------------------- Gemini fallback

def _chat_with_gemini(prompt, chat_history):
    """Legacy Gemini path — used only when AION_API_KEY is not set."""
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return ("AI is not configured. Please set AION_API_KEY in "
                "Settings (Aion Labs).")

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return ("AI is not configured. Please set AION_API_KEY in "
                "Settings (Aion Labs).")
    try:
        client = genai.Client()
    except Exception as e:
        log_debug(f"Failed to initialize Gemini Client: {e}")
        return "Gemini API key is missing or invalid. Please check your .env file."

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[get_database_schema, execute_read_query],
        )
        contents = []
        for msg in _history_to_messages(chat_history):
            role = 'model' if msg['role'] == 'assistant' else 'user'
            contents.append(types.Content(
                role=role, parts=[types.Part.from_text(text=msg['content'])]))
        chat = client.chats.create(model='gemini-2.5-flash',
                                   config=config, history=contents)
        return chat.send_message(prompt).text
    except Exception as e:
        log_debug(f"AI Chat Error (Gemini fallback): {e}")
        return f"Sorry, I encountered an error communicating with the AI. Error: {e}"


# ---------------------------------------------------------------- entry point

def chat_with_db(prompt: str, chat_history: list = None) -> str:
    """Answer a user question, using DB tools via the configured AI."""
    if chat_history is None:
        chat_history = []

    cfg = _aion_config()
    if cfg:
        try:
            return _chat_with_aion(prompt, chat_history, cfg)
        except Exception as e:
            log_debug(f"AI Chat Error (Aion): {e}")
            return f"Sorry, I encountered an error communicating with the AI. Error: {str(e)}"

    return _chat_with_gemini(prompt, chat_history)
