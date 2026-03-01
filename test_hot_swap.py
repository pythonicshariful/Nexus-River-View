from werkzeug.serving import run_simple
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import threading
import time
import requests
import os

def create_isolated_app(profile_name, db_name):
    app = Flask(profile_name)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_name}'
    db = SQLAlchemy(app)
    
    class User(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String)
        
    with app.app_context():
        db.create_all()
        if not User.query.first():
            db.session.add(User(name=f"User_of_{profile_name}"))
            db.session.commit()
            
    @app.route('/')
    def index():
        return f"Hello from {profile_name}. User is {User.query.first().name}"
        
    @app.route('/switch/<new_profile>')
    def switch(new_profile):
        # We need a way to tell the proxy to switch
        app.config['SWITCH_CALLBACK'](new_profile)
        return jsonify({"status": "switched to " + new_profile})
        
    return app

class ProfileProxy:
    def __init__(self):
        self.apps = {}
        self.active = None
        
    def add_app(self, name, app):
        self.apps[name] = app
        # Inject callback
        app.config['SWITCH_CALLBACK'] = self.switch_profile
        if not self.active:
            self.active = name
            
    def switch_profile(self, name):
        if name in self.apps:
            self.active = name
            
    def __call__(self, environ, start_response):
        app = self.apps[self.active]
        return app(environ, start_response)

if __name__ == '__main__':
    proxy = ProfileProxy()
    proxy.add_app('profile1', create_isolated_app('profile1', 'test1.db'))
    proxy.add_app('profile2', create_isolated_app('profile2', 'test2.db'))
    
    def run_server():
        run_simple('127.0.0.1', 5001, proxy)
        
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(1)
    
    print("Test Profile 1:", requests.get('http://127.0.0.1:5001/').text)
    
    print("Switching...", requests.get('http://127.0.0.1:5001/switch/profile2').json())
    
    print("Test Profile 2:", requests.get('http://127.0.0.1:5001/').text)
    
    try:
        os.remove('test1.db')
        os.remove('test2.db')
    except:
        pass
