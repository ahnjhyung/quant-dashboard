"""
Notion Dashboard Bridge
=======================
Guidance and helper for exposing local Streamlit to Notion Embeds.
"""

import os
import subprocess
import platform

def get_tunnel_command():
    """Returns the command to start a local tunnel."""
    # Choice 1: Cloudflared (Recommended for stability and no-auth)
    # Choice 2: ngrok (Requires account)
    
    # We'll suggest using cloudflared as it's free and easy for quick embeds
    return "npx -y localtunnel --port 8501"

def print_notion_guide():
    print("="*50)
    print("🚀 NOTION EMBED GUIDE")
    print("="*50)
    print("1. Start your Streamlit app: `streamlit run app.py`")
    print("2. In a NEW terminal, run: " + get_tunnel_command())
    print("3. Copy the 'your url is: https://...' link.")
    print("4. Go to your Notion page (" + "https://www.notion.so/2f59d833cbff803e80d2f4f6ef7b0d65" + ")")
    print("5. Type `/embed` and paste the link.")
    print("="*50)

if __name__ == "__main__":
    print_notion_guide()
