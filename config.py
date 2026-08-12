"""
config.py
---------
One shared helper for reading configuration from either source, so every
module (database.py, ai_engine.py) resolves settings the same way:

1. Streamlit Cloud "Secrets" (st.secrets) — used when deployed
2. Local .env file (os.getenv) — used when running on your Mac

This means the exact same code works locally and once deployed, with no
branching logic scattered around the app.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def get_config(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass  # st.secrets not available (no secrets.toml, or not in a Streamlit context)
    return os.getenv(key, default)
