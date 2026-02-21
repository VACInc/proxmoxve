"""Tests for Proxmox HA coordinator behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from homeassistant.const import CONF_HOST
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.proxmoxve.coordinator as coordinator_module
from custom_components.proxmoxve import DOMAIN
from custom_components.proxmoxve.const import (
    CONF_LXC,
    CONF_QEMU,
    CONF_REALM,
)
from custom_components.proxmoxve.coordinator import ProxmoxHACoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _build_config_entry() -> MockConfigEntry:
    """Return a mock config entry for coordinator tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "192.168.10.101",
            CONF_REALM: "pam",
            CONF_QEMU: ["101"],
            CONF_LXC: ["100"],
        },
    )


async def test_ha_coordinator_returns_empty_on_optional_endpoint_failure(
    hass: HomeAssistant,
    monkeypatch,
) -> None:
    """HA coordinator should not fail if optional HA endpoint is unavailable."""

    def _raise_update_failed(*_args: object, **_kwargs: object) -> None:
        msg = "HA manager not configured"
        raise UpdateFailed(msg)

    monkeypatch.setattr(coordinator_module, "poll_api", _raise_update_failed)

    coordinator = ProxmoxHACoordinator(
        hass=hass,
        proxmox=MagicMock(),
        config_entry=_build_config_entry(),
    )

    await coordinator.async_refresh()

    assert coordinator.data == {}
    assert coordinator.last_update_success


async def test_ha_coordinator_handles_dict_payload(
    hass: HomeAssistant,
    monkeypatch,
) -> None:
    """HA coordinator should accept payloads wrapped in a dict data key."""

    def _payload(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "data": [
                {"sid": "vm:101", "state": "started"},
                {"sid": "ct:100", "state": "stopped"},
                {"sid": "node:abc", "state": "started"},
                "unexpected-item",
            ]
        }

    monkeypatch.setattr(coordinator_module, "poll_api", _payload)

    coordinator = ProxmoxHACoordinator(
        hass=hass,
        proxmox=MagicMock(),
        config_entry=_build_config_entry(),
    )

    await coordinator.async_refresh()

    assert sorted(coordinator.data) == ["ct:100", "vm:101"]
    assert coordinator.data["vm:101"].state == "started"
    assert coordinator.data["ct:100"].state == "stopped"
    assert coordinator.last_update_success


async def test_ha_coordinator_still_raises_auth_failures(
    hass: HomeAssistant,
    monkeypatch,
) -> None:
    """HA coordinator must keep auth failures as unsuccessful updates."""

    def _raise_auth_failed(*_args: object, **_kwargs: object) -> None:
        raise ConfigEntryAuthFailed

    monkeypatch.setattr(coordinator_module, "poll_api", _raise_auth_failed)

    config_entry = _build_config_entry()
    config_entry.async_start_reauth = MagicMock()

    coordinator = ProxmoxHACoordinator(
        hass=hass,
        proxmox=MagicMock(),
        config_entry=config_entry,
    )

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    config_entry.async_start_reauth.assert_called_once_with(hass)
