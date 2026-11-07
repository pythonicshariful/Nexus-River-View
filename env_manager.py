import os
import sys
import json
import requests
import datetime

def get_env_file_path():
    """
    Returns the path to the active .env file.
    Creates an empty one if it doesn't already exist.
    """
    # 1. If NEXUS_DATA_PATH is set, check if a .env exists there
    custom_data_dir = os.environ.get('NEXUS_DATA_PATH')
    
    # 2. Base directory of project or executable
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    env_path = os.path.join(base_dir, '.env')
    
    # If not found but data dir has one, use that
    if not os.path.exists(env_path) and custom_data_dir and os.path.exists(os.path.join(custom_data_dir, '.env')):
        return os.path.join(custom_data_dir, '.env')

    # If neither exists, ensure empty .env is created in base_dir
    if not os.path.exists(env_path):
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write("# Nexus River View Environment Configuration\n")
        except Exception:
            pass

    return env_path


def read_env_file():
    """
    Reads the .env file and returns:
    - raw_content (str): Full text of the .env file
    - env_dict (dict): Parsed key-value pairs
    """
    env_path = get_env_file_path()
    raw_content = ""
    env_dict = {}

    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                raw_content = f.read()
                
            for line in raw_content.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                if '=' in stripped:
                    key, val = stripped.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    # Strip quotes if present
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    env_dict[key] = val
        except Exception as e:
            print(f"Error reading .env file: {e}")

    # Fallback/merge known environment variables currently active in os.environ
    known_keys = [
        'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
        'GEMINI_API_KEY', 'AION_API_KEY', 'AION_MODEL',
        'COMPANY_NAME', 'COMPANY_ADDRESS',
        'ADMIN_PASSWORD', 'NEXUS_DATA_PATH'
    ]
    for k in known_keys:
        if k not in env_dict and os.environ.get(k):
            env_dict[k] = os.environ.get(k)

    return raw_content, env_dict


def save_env_file(env_dict, raw_content=None):
    """
    Saves environment variables to .env and immediately updates os.environ.
    If raw_content is provided, writes raw_content directly.
    """
    env_path = get_env_file_path()
    
    if raw_content is not None:
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(raw_content)
                
            # Re-parse to update os.environ
            for line in raw_content.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    k, v = stripped.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ[k] = v
            return True, "Environment variables saved successfully from raw editor!"
        except Exception as e:
            return False, f"Failed to save raw .env: {e}"

    # Formatted write from dict
    try:
        # Categorize keys
        telegram_keys = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
        ai_keys = ['GEMINI_API_KEY', 'AION_API_KEY', 'AION_MODEL']
        company_keys = ['COMPANY_NAME', 'COMPANY_ADDRESS']
        system_keys = ['ADMIN_PASSWORD', 'NEXUS_DATA_PATH']
        
        all_categorized = set(telegram_keys + ai_keys + company_keys + system_keys)
        custom_keys = [k for k in env_dict.keys() if k not in all_categorized]

        lines = [
            "# =====================================================",
            "# NEXUS RIVER VIEW — SYSTEM ENVIRONMENT CONFIGURATION",
            f"# Last Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# =====================================================\n"
        ]

        # Telegram
        lines.append("# --- Telegram Bot & Backup Alerts ---")
        for k in telegram_keys:
            val = env_dict.get(k, '')
            lines.append(f"{k}={val}")
        lines.append("")

        # AI (Gemini + Aion Labs)
        lines.append("# --- AI APIs (Aion Labs primary, Google Gemini fallback) ---")
        for k in ai_keys:
            val = env_dict.get(k, '')
            lines.append(f"{k}={val}")
        lines.append("")

        # Company
        lines.append("# --- Company & Print Profile ---")
        for k in company_keys:
            val = env_dict.get(k, '')
            lines.append(f"{k}={val}")
        lines.append("")

        # System
        lines.append("# --- Security & System ---")
        for k in system_keys:
            val = env_dict.get(k, '')
            lines.append(f"{k}={val}")
        lines.append("")

        # Custom
        if custom_keys:
            lines.append("# --- Custom / Additional Variables ---")
            for k in custom_keys:
                val = env_dict.get(k, '')
                lines.append(f"{k}={val}")
            lines.append("")

        output_text = "\n".join(lines)
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(output_text)

        # Update running os.environ in-memory
        for k, v in env_dict.items():
            if v is not None:
                os.environ[k] = str(v)

        return True, "Environment configuration saved and applied successfully!"
    except Exception as e:
        return False, f"Failed to save .env file: {e}"


def test_telegram_message(bot_token=None, chat_id=None, custom_text=None):
    """
    Tests sending a message to Telegram.
    Returns (success: bool, detail: str)
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        return False, "Bot Token is missing. Please enter your Telegram Bot Token."
    if not chat:
        return False, "Chat ID is missing. Please enter your Telegram Chat ID."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    text = custom_text or (
        f"✅ *Nexus River View — Telegram Test Successful!*\n\n"
        f"🤖 *Bot Connection:* Active & Verified\n"
        f"💬 *Chat ID:* `{chat}`\n"
        f"⏰ *Timestamp:* {timestamp}\n\n"
        f"Your Telegram notification and database backup pipeline is ready to use!"
    )

    payload = {
        "chat_id": chat,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        res_data = response.json()
        if response.status_code == 200 and res_data.get("ok"):
            return True, f"Telegram message sent successfully to Chat ID: {chat}!"
        
        # Analyze error description
        error_desc = res_data.get("description", "Unknown Telegram error.")
        if "chat not found" in error_desc.lower():
            hint = "Chat ID not found. Ensure you have clicked 'Start' in the bot or added the bot to your channel/group with admin permissions."
        elif "unauthorized" in error_desc.lower():
            hint = "Bot Token is invalid. Please verify the token copied from @BotFather."
        elif "bot was blocked by the user" in error_desc.lower():
            hint = "The bot was blocked by the user. Please unblock the bot in Telegram."
        else:
            hint = error_desc

        return False, f"Telegram API Error: {hint}"
    except requests.exceptions.RequestException as e:
        return False, f"Network/Connection Error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def test_telegram_backup_document(bot_token=None, chat_id=None):
    """
    Tests sending a small test backup document to Telegram.
    Returns (success: bool, detail: str)
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat:
        return False, "Both Bot Token and Chat ID are required to test backup uploads."

    # Look for existing nexus.db or create a small test file
    from telegram_utils import get_cert_path
    db_path = None
    try:
        from flask import current_app
        if current_app:
            db_path = current_app.config.get('DATABASE_PATH')
    except Exception:
        pass

    if not db_path or not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), 'nexus.db')

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    caption = f"🚀 Nexus River View — Test Backup Document Upload\nTime: {timestamp}"

    try:
        cert = get_cert_path()
        if os.path.exists(db_path):
            with open(db_path, 'rb') as f:
                files = {'document': ('nexus_test_backup.db', f, 'application/octet-stream')}
                data = {'chat_id': chat, 'caption': caption}
                response = requests.post(url, data=data, files=files, verify=cert, timeout=25)
        else:
            # Send sample text file if db not found
            test_content = b"Nexus River View Database Backup Test Verification File\n"
            files = {'document': ('test_backup_check.txt', test_content, 'text/plain')}
            data = {'chat_id': chat, 'caption': caption}
            response = requests.post(url, data=data, files=files, verify=cert, timeout=25)

        res_data = response.json()
        if response.status_code == 200 and res_data.get("ok"):
            return True, f"Backup document uploaded and received successfully in Telegram (Chat ID: {chat})!"
        
        return False, f"Telegram API Error: {res_data.get('description', 'Upload failed.')}"
    except Exception as e:
        return False, f"Backup upload test failed: {e}"


def test_gemini_api(api_key=None):
    """
    Tests the Google Gemini API key by making a lightweight request.
    Returns (success: bool, detail: str)
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or key == "YOUR_GEMINI_API_KEY_HERE":
        return False, "Gemini API Key is missing. Please provide your Google Gemini API Key."

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            model_count = len(models)
            return True, f"Google Gemini API Key is valid and active! ({model_count} models accessible)"
        else:
            try:
                err_data = response.json()
                msg = err_data.get('error', {}).get('message', response.text)
            except Exception:
                msg = response.text
            return False, f"Gemini API Error ({response.status_code}): {msg}"
    except requests.exceptions.RequestException as e:
        return False, f"Gemini API connection error: {e}"
    except Exception as e:
        return False, f"Error testing Gemini key: {e}"


def test_aion_api(api_key=None, model=None):
    """
    Tests an Aion Labs API key with a tiny authenticated chat request.
    (GET /v1/models is public, so it cannot validate a key — a minimal
    chat completion is the reliable check. Costs a few tokens.)
    Returns (success: bool, detail: str)
    """
    key = (api_key or os.environ.get("AION_API_KEY", "")).strip()
    if not key or key == "YOUR_AION_API_KEY_HERE":
        return False, "Aion API Key is missing. Please provide your Aion Labs API Key."

    model_id = (model or os.environ.get("AION_MODEL", "")).strip() or "aion-labs/aion-3.0-mini"
    base_url = (os.environ.get("AION_BASE_URL", "")).strip() or "https://api.aionlabs.ai/v1"
    url = base_url.rstrip('/') + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        # Cloudflare rejects default Python user-agents (403 / error 1010)
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0 Safari/537.36"),
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 200,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return True, f"Aion Labs API Key is valid and active! (model: {model_id})"
        if response.status_code == 401:
            return False, "Aion API Error (401): Invalid API key."
        if response.status_code == 429:
            return False, "Aion API Error (429): Rate limit / daily quota reached — the key itself may be valid."
        try:
            err = response.json()
            msg = err.get('detail') or err.get('error', {}).get('message', response.text[:200])
        except Exception:
            msg = response.text[:200]
        return False, f"Aion API Error ({response.status_code}): {msg}"
    except requests.exceptions.RequestException as e:
        return False, f"Aion API connection error: {e}"
    except Exception as e:
        return False, f"Error testing Aion key: {e}"
