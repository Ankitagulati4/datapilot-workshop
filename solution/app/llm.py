"""Pluggable LLM factory.

Default: Groq (free, fast). Switch model via GROQ_MODEL in .env.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()


def get_llm(temperature: float = 0.0):
    """Return a configured ChatGroq instance."""
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get a free key at "
            "https://console.groq.com/keys and put it in your .env file."
        )
    return ChatGroq(model=model, temperature=temperature, api_key=api_key)
