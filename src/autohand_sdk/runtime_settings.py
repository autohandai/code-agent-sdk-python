"""Run-only CLI settings, applied before provider and session construction."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from pydantic import JsonValue

from autohand_sdk.types import ProviderConfigError

MAX_SETTINGS_DEPTH = 256

if TYPE_CHECKING:
    from autohand_sdk.transport import TransportOptions


def _json_copy(value: object, ancestors: set[int] | None = None, depth: int = 0) -> JsonValue:
    if depth > MAX_SETTINGS_DEPTH:
        raise ProviderConfigError("Run settings exceed the maximum nesting depth")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if type(value) not in (dict, list):
        raise ProviderConfigError("Run settings must contain plain JSON values")
    ancestors = set() if ancestors is None else ancestors
    identity = id(value)
    if identity in ancestors:
        raise ProviderConfigError("Run settings must not contain cycles")
    ancestors.add(identity)
    try:
        if isinstance(value, list):
            return [_json_copy(item, ancestors, depth + 1) for item in value]
        result: dict[str, JsonValue] = {}
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str) or key in ("__proto__", "prototype", "constructor"):
                raise ProviderConfigError("Run settings contain an unsafe setting path")
            result[key] = _json_copy(item, ancestors, depth + 1)
        return result
    finally:
        ancestors.remove(identity)


def _merge(target: dict[str, JsonValue], source: dict[str, JsonValue]) -> None:
    for key, value in source.items():
        existing = target.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            _merge(existing, value)
        else:
            target[key] = value


def _vertex_endpoint(value: str) -> str:
    try:
        url = urlsplit(value if "://" in value else "https://" + value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.port is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("Invalid origin")
        return url.hostname
    except ValueError:
        raise ProviderConfigError("Vertex endpoint must be an HTTPS origin or hostname") from None


def build_runtime_settings(options: TransportOptions) -> dict[str, JsonValue]:
    """Copy JSON settings and map explicit options to native CLI provider fields."""
    settings = cast(dict[str, JsonValue], _json_copy(options.run_settings or {}))
    if options.features is not None:
        _merge(settings, {"features": _json_copy(options.features)})
    provider_options = (
        options.api_key,
        options.base_url,
        options.port,
        options.autohand_ai_plan,
        options.openai_auth_mode,
        options.chatgpt_access_token,
        options.chatgpt_account_id,
        options.azure_auth_method,
        options.azure_tenant_id,
        options.azure_client_id,
        options.azure_client_secret,
        options.azure_resource_name,
        options.azure_deployment_name,
        options.azure_api_version,
    )
    provider = options.provider
    if provider is None:
        if any(value is not None for value in provider_options):
            raise ProviderConfigError(
                "A provider is required for provider credentials and settings"
            )
        return settings
    section: dict[str, JsonValue] = {}
    if options.model is not None:
        section["model"] = options.model
    if options.api_key is not None:
        section["authToken" if provider == "vertexai" else "apiKey"] = options.api_key
        if provider in ("autohandai", "openai", "xai"):
            section["authMode"] = "api-key"
        elif provider == "azure":
            section["authMethod"] = "api-key"
        elif provider == "bedrock":
            section["authMode"] = "bedrock-api-key"
    if options.base_url is not None:
        field = "endpoint" if provider in ("vertexai", "bedrock") else "baseUrl"
        section[field] = (
            _vertex_endpoint(options.base_url) if provider == "vertexai" else options.base_url
        )
    elif options.port is not None and provider in ("ollama", "llamacpp", "mlx"):
        section["baseUrl"] = f"http://localhost:{options.port}"
    if provider == "autohandai":
        existing = settings.get("autohandai")
        if options.autohand_ai_plan is not None:
            section["plan"] = options.autohand_ai_plan
        elif (options.api_key is not None or options.base_url is not None) and not (
            isinstance(existing, dict) and "plan" in existing
        ):
            section["plan"] = "cloud"
    if provider == "openai":
        section.update(
            {
                key: value
                for key, value in (
                    ("authMode", options.openai_auth_mode),
                    ("chatgptAccessToken", options.chatgpt_access_token),
                    ("chatgptAccountId", options.chatgpt_account_id),
                )
                if value is not None
            }
        )
    if provider == "azure":
        section.update(
            {
                key: value
                for key, value in (
                    ("authMethod", options.azure_auth_method),
                    ("tenantId", options.azure_tenant_id),
                    ("clientId", options.azure_client_id),
                    ("clientSecret", options.azure_client_secret),
                    ("resourceName", options.azure_resource_name),
                    ("deploymentName", options.azure_deployment_name),
                    ("apiVersion", options.azure_api_version),
                )
                if value is not None
            }
        )
    if section:
        overlay: dict[str, JsonValue]
        if provider.startswith("custom:"):
            overlay = {"customProviders": {provider[len("custom:") :]: section}}
        elif provider.startswith("extension:"):
            overlay = {"extensionProviders": {provider: section}}
        else:
            overlay = {provider: section}
        _merge(settings, overlay)
    return settings


def needs_runtime_settings(options: TransportOptions) -> bool:
    """Use the versioned envelope for settings not supported by legacy hosted env."""
    return (
        options.features is not None
        or options.run_settings is not None
        or (
            options.provider is not None
            and options.provider != "autohandai"
            and any(
                value is not None
                for value in (
                    options.api_key,
                    options.base_url,
                    options.port,
                    options.openai_auth_mode,
                    options.chatgpt_access_token,
                    options.chatgpt_account_id,
                    options.azure_auth_method,
                    options.azure_tenant_id,
                    options.azure_client_id,
                    options.azure_client_secret,
                    options.azure_resource_name,
                    options.azure_deployment_name,
                    options.azure_api_version,
                )
            )
        )
    )
