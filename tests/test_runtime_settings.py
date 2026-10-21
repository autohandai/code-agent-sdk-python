"""Provider settings must reach runtime construction, without changing saved config."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autohand_sdk.rpc_client import RPCClient
from autohand_sdk.runtime_settings import build_runtime_settings
from autohand_sdk.transport import Transport, TransportOptions
from autohand_sdk.types import FeatureFlagSettings, ProviderConfigError, SDKConfig


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("anthropic", {"apiKey": "key", "baseUrl": "https://fixture.test"}),
        ("openai", {"apiKey": "key", "authMode": "api-key", "baseUrl": "https://fixture.test"}),
        ("xai", {"apiKey": "key", "authMode": "api-key", "baseUrl": "https://fixture.test"}),
        ("azure", {"apiKey": "key", "authMethod": "api-key", "baseUrl": "https://fixture.test"}),
        (
            "bedrock",
            {"apiKey": "key", "authMode": "bedrock-api-key", "endpoint": "https://fixture.test"},
        ),
        ("vertexai", {"authToken": "key", "endpoint": "fixture.test"}),
    ],
)
def test_native_provider_fields(provider: str, expected: dict[str, object]) -> None:
    """Verify native provider fields."""
    assert build_runtime_settings(
        TransportOptions(provider=provider, api_key="key", base_url="https://fixture.test")
    ) == {provider: expected}


def test_preserves_saved_account_defaults_and_literal_ids() -> None:
    """Verify preserves saved account defaults and literal ids."""
    assert build_runtime_settings(TransportOptions(provider="autohandai")) == {}
    assert build_runtime_settings(
        TransportOptions(provider="custom:my.provider", api_key="key")
    ) == {"customProviders": {"my.provider": {"apiKey": "key"}}}
    assert build_runtime_settings(
        TransportOptions(provider="extension:my.provider:model", model="fixture")
    ) == {"extensionProviders": {"extension:my.provider:model": {"model": "fixture"}}}


def test_preserves_false_null_arrays_and_input() -> None:
    """Verify preserves false null arrays and input."""
    raw = {
        "openai": {"headers": {"x-fixture": "yes"}},
        "features": {"usageV2": True},
        "customProviders": {"fixture": {"models": ["one", None]}},
    }
    opts = TransportOptions(
        provider="openai", api_key="new", features={"usageV2": False}, run_settings=raw
    )
    result = build_runtime_settings(opts)
    assert result["openai"] == {
        "headers": {"x-fixture": "yes"},
        "apiKey": "new",
        "authMode": "api-key",
    }
    assert result["features"] == {"usageV2": False}
    assert raw["features"] == {"usageV2": True}
    assert result["customProviders"] == raw["customProviders"]


@pytest.mark.parametrize("value", [float("nan"), object(), {"__proto__": {"bad": True}}])
def test_invalid_json_is_structured(value: object) -> None:
    """Verify invalid json is structured."""
    with pytest.raises(ProviderConfigError):
        build_runtime_settings(
            TransportOptions(run_settings={"customProviders": {"fixture": {"value": [value]}}})
        )


@pytest.mark.parametrize(
    "value", ["http://fixture.test", "https://user:secret@fixture.test", "https://fixture.test/v1"]
)
def test_vertex_origin_is_validated(value: str) -> None:
    """Verify vertex origin is validated."""
    with pytest.raises(ProviderConfigError, match="Vertex endpoint"):
        build_runtime_settings(TransportOptions(provider="vertexai", base_url=value))


def test_sdk_options_are_forwarded_before_startup() -> None:
    """Verify sdk options are forwarded before startup."""
    client = RPCClient(
        SDKConfig(
            provider="openai",
            api_key="key",
            features=FeatureFlagSettings(usage_v2=False),
            run_settings={"openai": {"model": "saved"}},
            openai_auth_mode="api-key",
        )
    )
    options = client._build_transport_options()
    assert build_runtime_settings(options) == {
        "features": {"usageV2": False},
        "openai": {"apiKey": "key", "authMode": "api-key", "model": "saved"},
    }


@pytest.mark.asyncio
async def test_credentials_require_provider_before_discovery() -> None:
    """Verify credentials require provider before discovery."""
    transport = Transport(TransportOptions(api_key="secret"))
    with patch.object(transport, "_detect_cli_binary") as discover:
        with pytest.raises(ProviderConfigError):
            await transport.start()
        discover.assert_not_called()


@pytest.mark.asyncio
async def test_envelope_is_private_environment_not_argv() -> None:
    """Verify envelope is private environment not argv."""
    process = MagicMock()
    process.wait = AsyncMock(return_value=0)
    process.stdin.wait_closed = AsyncMock()
    process.returncode = None
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(return_value=b"")
    transport = Transport(
        TransportOptions(
            cli_path="/fixture/autohand",
            provider="anthropic",
            api_key="secret",
            features={"usageV2": False},
        )
    )
    with patch(
        "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process
    ) as spawn:
        await transport.start()
        args = spawn.call_args.args
        assert "--sdk-settings-version" in args
        assert "secret" not in args
        assert json.loads(spawn.call_args.kwargs["env"]["AUTOHAND_RUN_SETTINGS"]) == {
            "anthropic": {"apiKey": "secret"},
            "features": {"usageV2": False},
        }
        await transport.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (
            TransportOptions(session_id="saved", persist_session=True),
            ["--sdk-session-reference", "saved"],
        ),
        (
            TransportOptions(session_path="/saved/path", resume=True),
            ["--sdk-session-reference", "/saved/path"],
        ),
        (TransportOptions(continue_session=True), ["--sdk-resume-last"]),
        (TransportOptions(fork="saved", session_id="saved"), ["--fork", "saved"]),
    ],
)
async def test_current_session_arguments(options: TransportOptions, expected: list[str]) -> None:
    """Translate legacy SDK session options to the current RPC startup contract."""
    options.cli_path = "/fixture/autohand"
    process = MagicMock()
    process.returncode = None
    process.wait = AsyncMock(return_value=0)
    process.stdin.wait_closed = AsyncMock()
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(return_value=b"")
    transport = Transport(options)
    with patch(
        "asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process
    ) as spawn:
        await transport.start()
        assert list(spawn.call_args.args[1:]) == ["--mode", "rpc", *expected]
        await transport.stop()


@pytest.mark.parametrize("provider", ["autohandai", "openai", "azure", "openrouter", "vertexai"])
def test_credentials_can_be_inherited_from_saved_cli_config(provider: str) -> None:
    """Let the CLI validate complete provider settings after loading saved config."""
    client = RPCClient(SDKConfig(provider=provider))
    assert client._build_transport_options().provider == provider
