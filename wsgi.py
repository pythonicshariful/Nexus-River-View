import sys
import os

# Add the application directory to the Python path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

from app import create_app

# Create the Flask application instance
application = create_app()

if __name__ == "__main__":
    application.run()
