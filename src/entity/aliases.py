"""Explicit alias mapping for deterministic entity resolution.

Mapping raw alias strings (after stripping whitespace) to their canonical name.
All keys are stored in their original form (case‑insensitive handling is done
in the resolver).
"""

# Example aliases - extend as needed.
ALIAS_MAP = {
    "Open AI": "OpenAI",
    "OpenAI Inc.": "OpenAI",
    "OpenAI, Inc.": "OpenAI",
    "OpenAI Inc": "OpenAI",
    # Add more aliases here
}
