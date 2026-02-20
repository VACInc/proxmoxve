"""Tests for Proxmox VE HA select entities."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proxmoxve import DOMAIN
from custom_components.proxmoxve.const import (
    CONF_LXC,
    CONF_QEMU,
    CONF_REALM,
    COORDINATORS,
    PROXMOX_CLIENT,
    ProxmoxHAState,
    ProxmoxType,
)
from custom_components.proxmoxve.coordinator import ProxmoxHACoordinator
from custom_components.proxmoxve.models import ProxmoxHAResourceData
from custom_components.proxmoxve.select import (
    PROXMOX_SELECT_HA_STATE,
    ProxmoxHASelectEntity,
    async_setup_entry,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _build_config_entry() -> MockConfigEntry:
    """Return a mock config entry for select entity tests."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test",
        data={
            CONF_HOST: "192.168.10.101",
            CONF_PORT: 8006,
            CONF_USERNAME: "root",
            CONF_PASSWORD: "secret",
            CONF_REALM: "pam",
            CONF_VERIFY_SSL: True,
            CONF_QEMU: ["101", "102"],
            CONF_LXC: ["100", "200"],
        },
    )


def _build_ha_resource(
    sid: str,
    vmid: int,
    state: str = ProxmoxHAState.STARTED.value,
) -> ProxmoxHAResourceData:
    """Build HA coordinator resource data."""
    return ProxmoxHAResourceData(
        sid=sid,
        type=sid.split(":")[0],
        vmid=vmid,
        state=state,
        group=None,
        status=None,
        request_state=None,
        max_relocate=None,
        max_restart=None,
        digest=None,
    )


def _build_select_entity(
    hass: HomeAssistant,
    state: str = ProxmoxHAState.STARTED.value,
) -> tuple[ProxmoxHASelectEntity, ProxmoxHACoordinator, MagicMock]:
    """Build a Proxmox HA select entity with mocked dependencies."""
    config_entry = _build_config_entry()
    coordinator = ProxmoxHACoordinator(
        hass=hass,
        proxmox=MagicMock(),
        config_entry=config_entry,
    )
    coordinator.data = {"vm:101": _build_ha_resource("vm:101", 101, state)}
    coordinator.last_update_success = True

    proxmox_client = MagicMock()
    proxmox_client.get_api_client.return_value = object()

    entity = ProxmoxHASelectEntity(
        ha_coordinator=coordinator,
        info_device=DeviceInfo(
            identifiers={(DOMAIN, "test-device")},
            name="VM test",
        ),
        description=PROXMOX_SELECT_HA_STATE,
        unique_id="test_unique_id",
        proxmox_client=proxmox_client,
        sid="vm:101",
    )
    entity.hass = hass
    return entity, coordinator, proxmox_client


async def test_async_setup_entry_creates_entities_for_ha_resources(
    hass: HomeAssistant,
) -> None:
    """Test setup creates select entities only for HA-managed VM/CT resources."""
    config_entry = _build_config_entry()

    coordinator_ha = ProxmoxHACoordinator(
        hass=hass,
        proxmox=MagicMock(),
        config_entry=config_entry,
    )
    coordinator_ha.data = {
        "vm:101": _build_ha_resource("vm:101", 101),
        "ct:100": _build_ha_resource("ct:100", 100),
    }

    config_entry.runtime_data = {
        COORDINATORS: {
            f"{ProxmoxType.Resources}_ha": coordinator_ha,
            f"{ProxmoxType.QEMU}_101": SimpleNamespace(
                data=SimpleNamespace(name="vm-test-101", node="pve")
            ),
            f"{ProxmoxType.LXC}_100": SimpleNamespace(
                data=SimpleNamespace(name="ct-test-100", node="pve")
            ),
        },
        PROXMOX_CLIENT: MagicMock(),
    }

    entities: list[ProxmoxHASelectEntity] = []
    await async_setup_entry(hass, config_entry, entities.extend)

    assert len(entities) == 2
    assert {entity.unique_id for entity in entities} == {
        f"{config_entry.entry_id}_101_ha_state",
        f"{config_entry.entry_id}_100_ha_state",
    }
    assert {entity.current_option for entity in entities} == {"started"}


async def test_async_select_option_updates_state(
    hass: HomeAssistant,
) -> None:
    """Test changing HA state performs PUT call and refreshes coordinator."""
    entity, coordinator, proxmox_client = _build_select_entity(hass)
    coordinator.async_request_refresh = AsyncMock()

    with patch("custom_components.proxmoxve.select.put_api") as put_mock:
        await entity.async_select_option(ProxmoxHAState.STOPPED.value)

    put_mock.assert_called_once_with(
        proxmox_client.get_api_client.return_value,
        "cluster/ha/resources/vm:101",
        state=ProxmoxHAState.STOPPED.value,
    )
    coordinator.async_request_refresh.assert_awaited_once()


async def test_async_select_option_rejects_invalid_state(
    hass: HomeAssistant,
) -> None:
    """Test invalid HA state option raises HomeAssistantError."""
    entity, _, _ = _build_select_entity(hass)

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("invalid_state")
