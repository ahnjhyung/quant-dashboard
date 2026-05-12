from data_collectors.supabase_manager import SupabaseManager
import json

db = SupabaseManager()
latest = db.get_latest_macro()
print("Latest Macro Data Keys:", list(latest.keys()))
for k, v in latest.items():
    if v['current'] is None:
        print(f"MISSING: {k} -> {v}")
    else:
        print(f"FOUND: {k} -> {v}")
