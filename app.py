from flask import Flask, request, redirect, url_for
from flask_login import LoginManager
from database import db
from routes import main
import os
import sys
import logging
from dotenv import load_dotenv

# Load .env — works both in dev mode and when bundled as a PyInstaller exe
if getattr(sys, 'frozen', False):
    # Running as compiled exe: .env is extracted to the temp _MEIPASS folder
    _env_path = os.path.join(sys._MEIPASS, '.env')
else:
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path)

# Setup Logging
def setup_logging(data_dir):
    log_file = os.path.join(data_dir, 'nexus_startup.log')
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def create_app():
    # precise determination of data_dir path
    data_dir = os.environ.get('NEXUS_DATA_PATH')
    if not data_dir:
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
            data_dir = base_path
        else:
            # Fallback for dev mode
            data_dir = os.path.dirname(os.path.abspath(__file__))
            
    # Ensure data_dir exists before setting up logging
    os.makedirs(data_dir, exist_ok=True)
            
    # Ensure data_dir exists before setting up logging
    os.makedirs(data_dir, exist_ok=True)
    
    logger = setup_logging(data_dir)
    logger.info(f"Application starting with data_dir: {data_dir}")

    if getattr(sys, 'frozen', False):
        # When running as EXE, resources are in sys._MEIPASS
        template_folder = os.path.join(sys._MEIPASS, 'templates')
        static_folder = os.path.join(sys._MEIPASS, 'static')
        app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    else:
        app = Flask(__name__)

    # DB Path
    db_path = os.path.join(data_dir, 'nexus.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['DATA_FOLDER'] = data_dir 
    app.config['DATABASE_PATH'] = db_path 
    app.config['SECRET_KEY'] = 'dev-key-nexus-river-view'
    
    # Load Admin Config
    external_config_path = os.path.join(data_dir, 'admin_config.json')
    bundled_config_path = os.path.join(app.root_path, 'admin_config.json')
    
    config_loaded = False
    if os.path.exists(external_config_path):
        try:
            import json
            with open(external_config_path, 'r') as f:
                config = json.load(f)
                app.config['ADMIN_PASSWORD'] = config.get('ADMIN_PASSWORD', '1234')
            config_loaded = True
        except:
             pass 
    
    # Auto-generate if missing in data_dir
    if not config_loaded:
        default_password = '1234'
        if os.path.exists(bundled_config_path):
             try:
                import json
                with open(bundled_config_path, 'r') as f:
                    config = json.load(f)
                    default_password = config.get('ADMIN_PASSWORD', '1234')
             except:
                  pass
        
        try:
            import json
            with open(external_config_path, 'w') as f:
                json.dump({"ADMIN_PASSWORD": default_password}, f)
            app.config['ADMIN_PASSWORD'] = default_password
        except Exception as e:
            logger.error(f"Failed to auto-create config: {e}")
            app.config['ADMIN_PASSWORD'] = default_password 
            
    if 'ADMIN_PASSWORD' not in app.config:
        app.config['ADMIN_PASSWORD'] = '1234'

    # Upload Folder
    app.config['UPLOAD_FOLDER'] = os.path.join(data_dir, 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    db.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'main.login'
    login_manager.init_app(app)

    from models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
        
    app.register_blueprint(main)
    
    # Startup Sync & DB Check (Run in background thread to prevent GUI/Startup hang)
    from sync_manager import sync_manager
    
    def run_startup_sync(app_to_sync, logger_to_use, db_path_to_use):
        with app_to_sync.app_context():
            # Ensure tables exist
            try:
                db.create_all()
                logger_to_use.info("Database tables verified/created.")
                
                # Check for default admin
                from models import User
                if not User.query.filter_by(username='admin').first():
                    admin = User(username='admin')
                    # Get password from config
                    pwd = app_to_sync.config.get('ADMIN_PASSWORD', '1234')
                    admin.set_password(pwd)
                    db.session.add(admin)
                    db.session.commit()
                    logger_to_use.info("Default admin user created.")
            except Exception as e:
                logger_to_use.error(f"Failed to initialize database tables or create admin: {e}")

            if not os.path.exists(db_path_to_use) or os.path.getsize(db_path_to_use) == 0:
                logger_to_use.info("Database missing. Attempting recovery from Google Sheets...")
                try:
                    success, msg = sync_manager.restore_db_from_sheets()
                    if success:
                        logger_to_use.info("Database restored from Google Sheets.")
                    else:
                        logger_to_use.error(f"Recovery failed: {msg}")
                except Exception as e:
                    logger_to_use.error(f"Recovery hang/error: {e}")
            else:
                try:
                    logger_to_use.info("Verifying sync status with Google Sheets (Background)...")
                    status, details = sync_manager.check_for_mismatches()
                    if status == "mismatch":
                        app_to_sync.config['SYNC_MISMATCH'] = details
                        logger_to_use.warning(f"Sync Mismatch Detected: {details}")
                    elif status == "empty_sheets":
                        logger_to_use.info("Google Sheets is empty. Initializing with local data...")
                        sync_manager.sync_to_sheets()
                except Exception as e:
                    logger_to_use.error(f"Sync verification skipped due to error: {e}")

    @app.context_processor
    def inject_company_settings():
        company_name = "Company Name"
        company_address = ""
        settings_path = os.path.join(data_dir, 'company_settings.json')
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    settings_data = json.load(f)
                    company_name = settings_data.get('company_name', company_name)
                    company_address = settings_data.get('company_address', company_address)
            except Exception:
                pass
        return dict(global_company_name=company_name, global_company_address=company_address)

    import threading
    sync_thread = threading.Thread(target=run_startup_sync, args=(app, logger, db_path))
    sync_thread.daemon = True
    sync_thread.start()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5001, use_reloader=True)
