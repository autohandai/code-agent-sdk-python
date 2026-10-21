"""Lossless packet access alongside typed notifications."""

from __future__ import annotations

from typing import Any

import pytest

from autohand_sdk import Agent, AutohandSDK
from autohand_sdk.transport import Transport


@pytest.mark.parametrize("payload", [{"type": "progress", "future": False}, [1, None, False], None])
def test_observers_preserve_shapes_and_do_not_replace_handlers(payload: Any) -> None:
    """Isolate observer failures and mutations from raw and typed delivery."""
    transport = Transport()
    packets = []
    typed = []

    def failing(_packet: Any) -> None:
        raise ValueError("observer failure")

    def mutating(packet: Any) -> None:
        if isinstance(packet.params, list):
            packet.params.append("changed")

    transport.on_notification("autohand.pipe.output", typed.append)
    transport.observe_notifications(failing)
    transport.observe_notifications(mutating)
    remove = transport.observe_notifications(packets.append)
    transport._handle_rpc_message({"method": "autohand.pipe.output", "params": payload})
    assert packets[0].method == "autohand.pipe.output"
    assert packets[0].params == payload
    assert len(typed) == 1
    remove()
    transport._handle_rpc_message({"method": "autohand.pipe.output", "params": payload})
    assert len(packets) == 1


@pytest.mark.asyncio
async def test_unknown_arrays_survive_typed_stream_and_sdk_rebuild() -> None:
    """Retain exact unknown JSON and subscriptions when skills recreate the client."""
    sdk = AutohandSDK()
    packets = []
    remove = Agent.from_sdk(sdk).on_notification(packets.append)
    sdk.skills = ["typescript"]
    client = sdk._client
    assert client is not None and client._transport is not None
    payload = [1, None, False]
    client._transport._handle_rpc_message({"method": "autohand.future", "params": payload})
    event = client._event_queue.get_nowait()
    assert event == {"type": "unknown_notification", "method": "autohand.future", "params": payload}
    assert packets[0].params == payload
    remove()
    client._transport._handle_rpc_message({"method": "autohand.future", "params": None})
    assert len(packets) == 1


@pytest.mark.asyncio
async def test_unsupported_option_fails_before_launch() -> None:
    """Reject obsolete SDK switches before attempting to execute the CLI."""
    from autohand_sdk.transport import TransportOptions

    transport = Transport(TransportOptions(cli_path="/does-not-exist", auto_save_interval=30))
    with pytest.raises(ValueError, match="unsupported by the current CLI"):
        await transport.start()


def test_ephemeral_configuration_reaches_transport() -> None:
    """Keep persistence automatic unless ephemeral mode is explicitly requested."""
    from autohand_sdk.rpc_client import RPCClient
    from autohand_sdk.types import SDKConfig

    assert RPCClient(SDKConfig(ephemeral=True))._build_transport_options().ephemeral is True
    assert RPCClient(SDKConfig())._build_transport_options().ephemeral is False
