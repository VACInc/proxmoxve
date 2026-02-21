"""Tests for Proxmox device info helpers."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proxmoxve import DOMAIN, device_info
from custom_components.proxmoxve.const import COORDINATORS, ProxmoxType


def test_device_info_node_uses_fallback_model_when_data_missing(hass) -> None:
    """Node device info should not fail when node coordinator has no data."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "prox.vacinc.us",
            CONF_PORT: 8006,
        },
    )
    config_entry.runtime_data = {
        COORDINATORS: {
            f"{ProxmoxType.Node}_vacmoxtwo": SimpleNamespace(data=None),
        }
    }

    info = device_info(
        hass=hass,
        config_entry=config_entry,
        api_category=ProxmoxType.Node,
        node="vacmoxtwo",
    )

    assert info["model"] == "Node"
    assert info["name"] == "Node vacmoxtwo"
