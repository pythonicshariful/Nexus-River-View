import urllib.request
import urllib.error
try:
    print(urllib.request.urlopen("http://127.0.0.1:5000/api/profiles").read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print(e.read().decode("utf-8"))
