import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not set in environment. Copy .env.example to .env and fill it in.")

genai.configure(api_key=API_KEY)

print("🔍 Checking available models for your API key...\n")

try:
    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"✅ Available: {m.name}")
            print(f"   Description: {m.description}")
            print("-" * 40)
except Exception as e:
    print(f"❌ Error: {e}")
