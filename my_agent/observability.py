"""Agent 365 Observability bootstrap for the existing Google ADK/Gemini agent.

This module adds Microsoft **Agent 365 Observability** to the agent WITHOUT
modifying ``agent.py``. It configures the Microsoft OpenTelemetry distro
(``microsoft-opentelemetry``) to export OpenTelemetry traces to the Agent 365
observability service using a **standard-app service-to-service (S2S)** identity
(MSAL client credentials).

Google ADK has no Agent 365 auto-instrumentation extension, so telemetry is not
captured automatically. Wrap each agent invocation in your serving/runtime layer
with :func:`observe_agent_run` to emit an ``InvokeAgent`` span. ``agent.py`` and
the ``root_agent`` definition stay exactly as they are.

Configuration is read from environment variables so no secrets live in code:

    AGENT365_TENANT_ID                    Entra tenant ID.
    AGENT365_OBSERVABILITY_CLIENT_ID      Standard (telemetry) app client ID.
                                          Also used as the {agentId} in the
                                          Agent 365 export URL.
    AGENT365_OBSERVABILITY_CLIENT_SECRET  Standard app client secret.
    AGENT365_OBSERVABILITY_ENABLED        Set to "false" to force-disable.

The ``CONNECTIONS__SERVICE_CONNECTION__SETTINGS__{TENANTID,CLIENTID,CLIENTSECRET}``
variables (Agent 365 convention) are also accepted as fallbacks.

If the SDK is not installed or the identity is not configured, this module
degrades to a no-op so the agent keeps running unchanged.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

# Agent 365 Observability resource. App-only (S2S) tokens use the /.default form.
_OBSERVABILITY_RESOURCE_APP_ID = "9b975845-388f-4429-889e-eab1ef63949c"
_OBSERVABILITY_S2S_SCOPE = f"api://{_OBSERVABILITY_RESOURCE_APP_ID}/.default"

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "my-adk-agent")
_SERVICE_NAMESPACE = os.getenv("AGENT365_SERVICE_NAMESPACE", "ai.agents")

_init_lock = threading.Lock()
_initialized = False
_enabled = False

# Reused ConfidentialClientApplication so MSAL's built-in token cache is honored.
_cca = None
_cca_lock = threading.Lock()


def _config() -> Optional[Tuple[str, str, str]]:
    """Return (tenant_id, client_id, client_secret) if fully configured."""
    tenant = os.getenv("AGENT365_TENANT_ID") or os.getenv(
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID"
    )
    client_id = os.getenv("AGENT365_OBSERVABILITY_CLIENT_ID") or os.getenv(
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID"
    )
    client_secret = os.getenv("AGENT365_OBSERVABILITY_CLIENT_SECRET") or os.getenv(
        "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET"
    )
    if tenant and client_id and client_secret:
        return tenant, client_id, client_secret
    return None


def _token_resolver(agent_id: str, tenant_id: str) -> Optional[str]:
    """Sync callable (agent_id, tenant_id) -> bearer token for the A365 exporter.

    Mints an app-only token for the Agent 365 observability resource using MSAL
    client credentials. MSAL caches tokens internally, so this is safe to call
    on every export.
    """
    global _cca
    cfg = _config()
    if not cfg:
        return None
    cfg_tenant, client_id, client_secret = cfg
    try:
        with _cca_lock:
            if _cca is None:
                from msal import ConfidentialClientApplication

                _cca = ConfidentialClientApplication(
                    client_id=client_id,
                    authority=f"https://login.microsoftonline.com/{cfg_tenant}",
                    client_credential=client_secret,
                )
        result = _cca.acquire_token_for_client(scopes=[_OBSERVABILITY_S2S_SCOPE])
        if result and "access_token" in result:
            return result["access_token"]
    except Exception:
        # Never let telemetry auth break the agent.
        return None
    return None


def init_observability() -> bool:
    """Initialize Agent 365 Observability. Idempotent; returns True if enabled.

    No-op (returns False) when disabled, unconfigured, or the SDK is missing.
    """
    global _initialized, _enabled
    with _init_lock:
        if _initialized:
            return _enabled
        _initialized = True

        if os.getenv("AGENT365_OBSERVABILITY_ENABLED", "").strip().lower() in (
            "false",
            "0",
            "no",
        ):
            return False

        if _config() is None:
            return False

        try:
            from microsoft.opentelemetry import use_microsoft_opentelemetry
            from opentelemetry.sdk.resources import Resource
        except Exception:
            # microsoft-opentelemetry not installed -> stay a no-op.
            return False

        use_microsoft_opentelemetry(
            enable_a365=True,
            a365_token_resolver=_token_resolver,
            a365_use_s2s_endpoint=True,
            a365_enable_observability_exporter=True,
            resource=Resource.create(
                {
                    "service.name": _SERVICE_NAME,
                    "service.namespace": _SERVICE_NAMESPACE,
                }
            ),
        )
        _enabled = True
        return True


@contextmanager
def observe_agent_run(
    user_message: str,
    *,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> Iterator[object]:
    """Wrap a single agent invocation in an Agent 365 ``InvokeAgent`` span.

    Usage from your serving/runtime layer (NOT agent.py)::

        from my_agent.observability import observe_agent_run

        with observe_agent_run(user_text, session_id=sid) as scope:
            response = run_the_agent(user_text)
            if scope is not None:
                scope.record_response(response)

    Yields the active scope (or ``None`` when observability is disabled) so the
    caller can record the response. ``BaggageBuilder`` sets tenant_id/agent_id;
    without them the exporter silently drops spans.
    """
    if not _enabled:
        yield None
        return

    cfg = _config()
    if cfg is None:
        yield None
        return
    tenant_id, agent_id, _ = cfg

    try:
        from microsoft.opentelemetry.a365.core import (
            AgentDetails,
            BaggageBuilder,
            CallerDetails,
            InvokeAgentScope,
            InvokeAgentScopeDetails,
            Request,
            UserDetails,
        )
    except Exception:
        yield None
        return

    agent = AgentDetails(
        agent_id=agent_id, agent_name=_SERVICE_NAME, tenant_id=tenant_id
    )
    caller = None
    if user_id or user_email:
        caller = CallerDetails(
            user_details=UserDetails(user_id=user_id, user_email=user_email)
        )

    with BaggageBuilder().tenant_id(tenant_id).agent_id(agent_id).build():
        with InvokeAgentScope.start(
            request=Request(
                content=user_message,
                session_id=session_id,
                conversation_id=conversation_id,
            ),
            scope_details=InvokeAgentScopeDetails(),
            agent_details=agent,
            caller_details=caller,
        ) as scope:
            yield scope
