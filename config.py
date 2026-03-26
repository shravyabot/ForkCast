import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import streamlit as st

def _get(key, default=""):
    """Read from Streamlit secrets first, then env vars."""
    try:
        val = st.secrets.get(key, None)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)

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
