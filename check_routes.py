from app import create_app

app = create_app()
print("\n--- Registered Routes ---")
for rule in app.url_map.iter_rules():
    print(f"{rule.endpoint}: {rule}")
print("------------------------\n")
