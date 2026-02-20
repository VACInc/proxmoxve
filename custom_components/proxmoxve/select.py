"""Select entities for Proxmox VE HA resource state management."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.exceptions import HomeAssistantError
from proxmoxer.core import ResourceException
from requests.exceptions import ConnectTimeout

from . import device_info
from .api import ProxmoxClient, put_api
from .const import (
    CONF_LXC,
    CONF_QEMU,
    COORDINATORS,
    LOGGER,
    PROXMOX_CLIENT,
    ProxmoxHAState,
    ProxmoxType,
)
from .entity import ProxmoxEntity, ProxmoxEntityDescription

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import ProxmoxHACoordinator


@dataclass(frozen=True, kw_only=True)
class ProxmoxSelectEntityDescription(ProxmoxEntityDescription, SelectEntityDescription):
    """Class describing Proxmox select entities."""


PROXMOX_SELECT_HA_STATE: Final[ProxmoxSelectEntityDescription] = (
    ProxmoxSelectEntityDescription(
        key="ha_state",
        icon="mdi:shield-sync",
        name="HA state",
        translation_key="ha_state",
        options=[state.value for state in ProxmoxHAState],
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for HA-managed resources."""
    selects: list[ProxmoxHASelectEntity] = []

    coordinators = config_entry.runtime_data[COORDINATORS]
    proxmox_client = config_entry.runtime_data[PROXMOX_CLIENT]

    ha_coordinator: ProxmoxHACoordinator | None = coordinators.get(
        f"{ProxmoxType.Resources}_ha"
    )
    if ha_coordinator is None or ha_coordinator.data is None:
        return

    ha_resources = ha_coordinator.data

    for vm_id in config_entry.data[CONF_QEMU]:
        sid = f"vm:{vm_id}"
        if sid not in ha_resources:
            continue
        if f"{ProxmoxType.QEMU}_{vm_id}" not in coordinators:
            continue

        selects.append(
            ProxmoxHASelectEntity(
                ha_coordinator=ha_coordinator,
                info_device=device_info(
                    hass=hass,
                    config_entry=config_entry,
                    api_category=ProxmoxType.QEMU,
                    resource_id=vm_id,
                ),
                description=PROXMOX_SELECT_HA_STATE,
                unique_id=f"{config_entry.entry_id}_{vm_id}_ha_state",
                proxmox_client=proxmox_client,
                sid=sid,
            )
        )

    for ct_id in config_entry.data[CONF_LXC]:
        sid = f"ct:{ct_id}"
        if sid not in ha_resources:
            continue
        if f"{ProxmoxType.LXC}_{ct_id}" not in coordinators:
            continue

        selects.append(
            ProxmoxHASelectEntity(
                ha_coordinator=ha_coordinator,
                info_device=device_info(
                    hass=hass,
                    config_entry=config_entry,
                    api_category=ProxmoxType.LXC,
                    resource_id=ct_id,
                ),
                description=PROXMOX_SELECT_HA_STATE,
                unique_id=f"{config_entry.entry_id}_{ct_id}_ha_state",
                proxmox_client=proxmox_client,
                sid=sid,
            )
        )

    async_add_entities(selects)


class ProxmoxHASelectEntity(ProxmoxEntity, SelectEntity):
    """A select entity for managing Proxmox HA resource state."""

    entity_description: ProxmoxSelectEntityDescription

    def __init__(
        self,
        ha_coordinator: ProxmoxHACoordinator,
        info_device: DeviceInfo,
        description: ProxmoxSelectEntityDescription,
        unique_id: str,
        proxmox_client: ProxmoxClient,
        sid: str,
    ) -> None:
        """Create the select entity for HA state management."""
        super().__init__(ha_coordinator, unique_id, description)

        self._attr_device_info = info_device
        self._proxmox_client = proxmox_client
        self._sid = sid

    @property
    def current_option(self) -> str | None:
        """Return the current HA state."""
        if self.coordinator.data is None:
            return None
        resource = self.coordinator.data.get(self._sid)
        if resource is None:
            return None
        return resource.state

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._sid in self.coordinator.data
        )

    async def async_select_option(self, option: str) -> None:
        """Set the HA state for this resource."""
        if option not in [state.value for state in ProxmoxHAState]:
            msg = f"Invalid HA state: {option}"
            raise HomeAssistantError(msg)

        proxmox = self._proxmox_client.get_api_client()
        api_path = f"cluster/ha/resources/{self._sid}"

        try:
            await self.hass.async_add_executor_job(
                partial(put_api, proxmox, api_path, state=option)
            )
        except ResourceException as error:
            msg = f"Failed to set HA state for {self._sid} to {option}: {error}"
            raise HomeAssistantError(msg) from error
        except ConnectTimeout as error:
            msg = f"Timeout setting HA state for {self._sid}: {error}"
            raise HomeAssistantError(msg) from error

        LOGGER.debug("Set HA state for %s to %s", self._sid, option)

        # Refresh coordinator to pick up the new state
        await self.coordinator.async_request_refresh()
