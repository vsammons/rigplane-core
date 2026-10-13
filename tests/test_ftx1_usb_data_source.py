"""Yaesu FTX-1 digital MOD SOURCE hardware contract — no radio or RF access."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rigplane.backends.yaesu_cat.radio import YaesuCatRadio
from rigplane.exceptions import CommandError
from rigplane.rig_loader import load_rig

RIG_DIR = Path(__file__).parents[1] / "rigs"


@pytest.fixture
def radio() -> YaesuCatRadio:
    radio = YaesuCatRadio("/dev/null", profile=load_rig(RIG_DIR / "ftx1.toml"))
    radio._transport._connected = True
    radio._transport.query = AsyncMock()
    radio._transport.write = AsyncMock()
    return radio


@pytest.mark.asyncio
async def test_real_ftx1_usb_data_menu_readback(radio):
    for code, expected in [
        ("0", "MIC"), ("1", "USB"), ("2", "Bluetooth"), ("3", "AUTO")
    ]:
        radio._transport.query.return_value = f"EX010413{code}"
        assert await radio.get_data_mod_source() == expected
        radio._transport.query.assert_awaited_with("EX010413;")
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_usb_when_already_selected_has_zero_cat_writes(radio):
    radio._transport.query.return_value = "EX0104131"
    assert await radio.ensure_data_mod_source_usb() == "USB"
    assert radio._transport.query.await_count == 2
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_usb_from_microphone_requires_exact_readback(radio):
    radio._transport.query.side_effect = ["EX0104130", "EX0104131"]
    assert await radio.ensure_data_mod_source_usb() == "USB"
    assert radio._transport.query.await_count == 2
    radio._transport.write.assert_awaited_once_with("EX0104131;")


@pytest.mark.asyncio
async def test_no_success_claim_after_unconfirmed_write(radio):
    radio._transport.query.side_effect = ["EX0104130", "EX0104130"]
    with pytest.raises(CommandError, match="not confirmed"):
        await radio.ensure_data_mod_source_usb()
    radio._transport.write.assert_awaited_once_with("EX0104131;")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["?;", "", "EX0104134", "EX0104141",
                                  "EX010413", "MD0C", "EX01041311"])
async def test_unknown_or_rejected_response_fails_closed_without_write(radio, bad):
    radio._transport.query.return_value = bad.rstrip(";")
    with pytest.raises(Exception):
        await radio.ensure_data_mod_source_usb()
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_failure_does_not_fake_a_verified_state(radio):
    radio._transport.query.return_value = "EX0104130"
    radio._transport.write.side_effect = OSError("radio rejected")
    with pytest.raises(OSError):
        await radio.ensure_data_mod_source_usb()
    assert radio._transport.query.await_count == 1


@pytest.mark.asyncio
async def test_malformed_query_cannot_be_interpreted_as_usb(radio):
    radio._transport.query.return_value = "EX010413X"
    with pytest.raises(CommandError):
        await radio.get_data_mod_source()
    radio._transport.write.assert_not_awaited()


def test_profile_is_explicit_and_separate_from_operating_mode(radio):
    cmds = radio._config.commands
    assert cmds["get_data_mod_source"].read == "EX010413;"
    assert cmds["set_data_mod_source"].write == "EX010413{src};"
    assert cmds["get_mode"].read == "MD0;"
    assert cmds["set_mode"].write == "MD0{mode};"
