import os
import requests
from dotenv import load_dotenv
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

response = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
)

models = response.json().get("data", [])

# Filter only free models
free_models = [m for m in models if ":free" in m["id"]]

print(f"\n✅ {len(free_models)} FREE models available on your OpenRouter account:\n")
for m in sorted(free_models, key=lambda x: x["id"]):
    print(f"  {m['id']}")