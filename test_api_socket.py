import urllib.request
import json
import traceback

data = json.dumps({'profile_key': 'socket_test', 'name': 'Socket Test', 'sheet_id': '12EvfR0SResxmfyF4eKh-vJsu0F4pUYGAeOY8eJIiB_A'}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:5000/api/add_profile', data=data, headers={'Content-Type': 'application/json'})

try:
    response = urllib.request.urlopen(req)
    print("Status:", response.status)
    print("Data:", response.read().decode('utf-8'))
except Exception as e:
    print("EXCEPTION:")
    traceback.print_exc()
