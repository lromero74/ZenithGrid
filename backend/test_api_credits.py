"""Test script to check API credit endpoints for AI providers"""
import os
from anthropic import Anthropic

# Test Anthropic (if API key is available)
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
if anthropic_key:
    print("Testing Anthropic API...")
    try:
        client = Anthropic(api_key=anthropic_key)
        # Anthropic doesn't have a direct credits endpoint
        # We can only see usage in the dashboard
        print("Anthropic: No programmatic credits API available")
        print("Users must check: https://console.anthropic.com/settings/usage")
    except Exception as e:
        print(f"Anthropic error: {e}")
else:
    print("No Anthropic API key found")

print("\n" + "="*60 + "\n")

# Test Google Gemini
gemini_key = os.getenv("GEMINI_API_KEY", "")
if gemini_key:
    print("Testing Google Gemini API...")
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        # Gemini free tier has no credits API
        # Users must check: https://aistudio.google.com/app/apikey
        print("Gemini: No programmatic credits API available")
        print("Users must check: https://aistudio.google.com/app/apikey")
    except Exception as e:
        print(f"Gemini error: {e}")
else:
    print("No Gemini API key found")

print("\nConclusion: Most AI providers don't expose credit balance via API.")
print("Best approach: Show links to billing dashboards instead.")
