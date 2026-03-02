import urllib.request
try:
    response = urllib.request.urlopen("http://127.0.0.1:5000/installments", timeout=2)
    print("Status:", response.status)
except Exception as e:
    print("Error:", e)
