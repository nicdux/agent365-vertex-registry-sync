# Load environment variables from a local .env file if python-dotenv is present.
# Optional convenience; if the package is missing the agent still runs unchanged.
try:  # pragma: no cover - best-effort only
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:
    pass

from . import agent
from .observability import init_observability

# Instrument the existing agent with Agent 365 Observability.
# No-op when the identity is not configured or the SDK is not installed, so it
# never changes the agent's behavior.
init_observability()
