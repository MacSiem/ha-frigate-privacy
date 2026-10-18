"""Actual HA registration and entity-service authority, with synthetic targets."""
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from custom_components.ha_frigate_privacy.const import DOMAIN
from tests_ha.test_frontend import _setup


async def test_late_camera_adds_native_entities_with_unknown_deadline_and_guarded_actions(hass: HomeAssistant, hass_admin_user):
    # HA assigns owner rights to the first user of an empty auth store.
    # Seed the normal administrator before creating the household member.
    assert hass_admin_user.is_admin
    entry=await _setup(hass)
    source=MockConfigEntry(domain="frigate",data={},unique_id="synthetic-frigate")
    source.add_to_hass(hass)
    registry=er.async_get(hass)
    target=registry.async_get_or_create("switch","frigate","synthetic_front_detect",suggested_object_id="synthetic_front_detect",config_entry=source)
    hass.states.async_set(target.entity_id,"on",{"friendly_name":"Synthetic Front Detection"})
    await hass.async_block_till_done()
    entities=er.async_entries_for_config_entry(registry,entry.entry_id)
    own={item.unique_id:item for item in entities}
    assert len([item for item in entities if item.domain=="button"])==3
    assert len([item for item in entities if item.domain=="switch"])==1
    assert len([item for item in entities if item.domain=="sensor"])==2
    deadline=own[f"{DOMAIN}_synthetic_front_privacy_until"]
    assert hass.states.get(deadline.entity_id).state=="unknown"
    assert hass.states.get(own[f"{DOMAIN}_last_outcome"].entity_id).state=="unknown"
    button=own[f"{DOMAIN}_synthetic_front_privacy_15_minutes"]
    assert button.device_id==deadline.device_id
    member=await hass.auth.async_create_user("Synthetic household")
    assert not member.is_admin
    before=await hass.data[DOMAIN]["storage"].async_get_state()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("button","press",{"entity_id":button.entity_id},blocking=True,context=Context(user_id=member.id))
    assert await hass.data[DOMAIN]["storage"].async_get_state()==before
    # No new entity may duplicate on another ordinary state event.
    hass.states.async_set(target.entity_id,"off")
    await hass.async_block_till_done()
    assert len(er.async_entries_for_config_entry(registry,entry.entry_id))==len(entities)
    assert await hass.config_entries.async_unload(entry.entry_id)
