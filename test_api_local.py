from app import create_app
import traceback
import sys

# Instantiate the Proxy App
proxy = create_app()

# Manually invoke the WSGI application layer
from werkzeug.test import Client
from werkzeug.wrappers import Response

client = Client(proxy, Response)

print("Pinging /api/profiles...")
try:
    response = client.get('/api/profiles')
    print("Status:", response.status)
    print("Data:", response.get_data(as_text=True))
except Exception as e:
    print("EXCEPTION CAUGHT DIRECTLY:")
    traceback.print_exc()

print("Pinging /api/add_profile...")
try:
    response = client.post('/api/add_profile', json={'profile_key': 'ShopnoBilash', 'name': 'ShopnoBilash', 'sheet_id': '12EvfR0SResxmfyF4eKh-vJsu0F4pUYGAeOY8eJIiB_A'})
    print("Status:", response.status)
    print("Data:", response.get_data(as_text=True))
except Exception as e:
    print("EXCEPTION CAUGHT DIRECTLY:")
    traceback.print_exc()
