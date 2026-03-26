import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import streamlit as st

def _get(key, default=""):
    """Read from Streamlit secrets first, then env vars."""
    # 1. Try st.secrets (Streamlit Cloud)
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    # 2. Try environment variable
    val = os.environ.get(key)
    if val:
        return val
    return default

# API Keys
OPENAI_API_KEY = _get("OPENAI_API_KEY")
TAVILY_API_KEY = _get("TAVILY_API_KEY")

# Neo4j
NEO4J_URI = _get("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = _get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = _get("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = _get("NEO4J_DATABASE", "neo4j")

# OpenAI
OPENAI_MODEL = _get("OPENAI_MODEL", "gpt-4o")

# Warn if keys are missing
if not TAVILY_API_KEY or not OPENAI_API_KEY:
    st.error(
        "⚠️ **Missing API keys!** Go to App Settings → Secrets and add:\n\n"
        "```\nTAVILY_API_KEY = \"your-key\"\nOPENAI_API_KEY = \"your-key\"\n"
        "NEO4J_URI = \"your-uri\"\nNEO4J_USER = \"neo4j\"\nNEO4J_PASSWORD = \"your-password\"\n```"
    )
    st.stop()
