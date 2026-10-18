from flask import Flask, request, redirect, url_for
from flask_login import LoginManager
from database import db
from routes import main
from api import api as api_blueprint
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
    
    if getattr(sys, 'frozen', False):
        if not data_dir or data_dir == '.':
            base_path = os.path.dirname(sys.executable)
            data_dir = base_path
    else:
        if not data_dir or data_dir == '.':
            data_dir = os.path.dirname(os.path.abspath(__file__))
        # Resolve any relative paths to absolute
        data_dir = os.path.abspath(data_dir)
            
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
    
    # Load Admin Config from Environment
    app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', '1234')

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
    app.register_blueprint(api_blueprint)
    # Database Initialization CLI Command
    @app.cli.command("init-db")
    def init_db_command():
        """Creates the database tables and default admin."""
        with app.app_context():
            try:
                db.create_all()
                print("Database tables verified/created.")
                
                # Seed Chart of Accounts
                from logic import seed_chart_of_accounts
                seed_chart_of_accounts()
                print("Chart of Accounts seeded.")
                
                # Check for default admin
                from models import User
                if not User.query.filter_by(username='admin').first():
                    admin = User(username='admin')
                    # Get password from config
                    pwd = app.config.get('ADMIN_PASSWORD', '1234')
                    admin.set_password(pwd)
                    db.session.add(admin)
                    db.session.commit()
                    print("Default admin user created.")
            except Exception as e:
                print(f"Failed to initialize database tables or create admin: {e}")

    @app.context_processor
    def inject_company_settings():
        company_name = os.environ.get('COMPANY_NAME', 'Company Name')
        company_address = os.environ.get('COMPANY_ADDRESS', '')
        return dict(global_company_name=company_name, global_company_address=company_address)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5001, debug=True, use_reloader=True)
