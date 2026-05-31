import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

print("--- Inspecting Models ---")
try:
    for model in client.models.list():
        # Dump model details to find the correct naming convention
        print(f"Name: {model.name} | Methods: {getattr(model, 'supported_methods', 'Unknown')}")
except Exception as e:
    print(f"Error: {e}")
