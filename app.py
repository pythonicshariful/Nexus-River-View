from flask import Flask, request
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
            
    logger = setup_logging(data_dir)
    logger.info("Application starting...")

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
    app.register_blueprint(main)
    
    with app.app_context():
        db.create_all()
        # Startup Sync Check
        from sync_manager import sync_manager
        
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            logger.info("Database missing. Attempting recovery from Google Sheets...")
            success, msg = sync_manager.restore_db_from_sheets()
            if success:
                logger.info("Database restored from Google Sheets.")
            else:
                logger.error(f"Recovery failed: {msg}")
        else:
            status, details = sync_manager.check_for_mismatches()
            if status == "mismatch":
                app.config['SYNC_MISMATCH'] = details
                logger.warning(f"Sync Mismatch Detected: {details}")
            elif status == "empty_sheets":
                logger.info("Google Sheets is empty. Initializing with local data...")
                sync_manager.sync_to_sheets()
                
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5000, use_reloader=True)
