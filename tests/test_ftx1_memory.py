"""FTX-1 memory MR/MT tests: no RF, no serial port, no memory writes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rigplane.backends.yaesu_cat.ftx1_memory import (
    parse_ftx1_memory_reply,
    parse_ftx1_tag_reply,
)
from rigplane.backends.yaesu_cat.radio import YaesuCatRadio
from rigplane.rig_loader import load_rig

_RIGS = Path(__file__).parents[1] / "rigs"
# Direct FTX-1 MR observation recorded in Hamlib/Hamlib PR #2035.
_MR = "MR00001007050000+020010110000;"


@pytest.fixture
def radio():
    rig = YaesuCatRadio("/dev/null", profile=load_rig(_RIGS / "ftx1.toml"))
    rig._transport._connected = True
    rig._transport.query = AsyncMock(return_value=_MR.rstrip(";"))
    rig._transport.write = AsyncMock()
    return rig


@pytest.mark.asyncio
async def test_actual_profile_parser_and_public_memory_reader(radio):
    entry = await radio.get_memory_channel(1)
    assert entry.channel == 1
    assert entry.frequency_hz == 7_050_000
    assert entry.mode_code == "1"
    assert entry.clarifier_offset_hz == 200
    assert entry.rx_clar_enabled is True
    assert entry.tx_clar_enabled is False
    assert entry.memory_state == 1
    radio._transport.query.assert_awaited_once_with("MR00001;")
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_profile_and_public_memory_tag_reader(radio):
    radio._transport.query.return_value = "MT00001K4VSS       "
    assert await radio.get_memory_tag(1) == "K4VSS"
    radio._transport.query.assert_awaited_once_with("MT00001;")
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_radio_rejects_or_does_not_reply_no_fabricated_memory(radio):
    for frame in ("?;", "MR", "MR00002" + _MR[7:-1]):
        radio._transport.query.return_value = frame
        with pytest.raises((ValueError, Exception)) as exc:
            await radio.get_memory_channel(1)
        assert exc.value is not None
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_channel_never_accepted(radio):
    radio._transport.query.return_value = _MR.replace("MR00001", "MR00002").rstrip(";")
    with pytest.raises(ValueError, match="different memory channel"):
        await radio.get_memory_channel(1)
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_tag_rejects_embedded_control_or_wrong_channel(radio):
    for raw in ("?;", "MT00002K4VSS", "MT00001ABC\nDEF", "MT00001" + "X" * 13):
        radio._transport.query.return_value = raw
        with pytest.raises(ValueError):
            await radio.get_memory_tag(1)
    radio._transport.write.assert_not_awaited()


def test_format_does_not_accept_extra_or_invalid_fields():
    for raw in (
        _MR[:-2],
        _MR.replace("MR00001", "MR00002"),
        _MR.replace("+0200", "10200"),
        _MR.replace("+0200", "+9999"),
        "?;",
        "",
    ):
        with pytest.raises(ValueError):
            parse_ftx1_memory_reply(raw, channel=1)
    for raw in ("MT00001abc;def;", "MT00001" + "A" * 13, "MT00002name"):
        with pytest.raises(ValueError):
            parse_ftx1_tag_reply(raw, channel=1)


@pytest.mark.parametrize("bad", [0, 100, -1, True, 1.5, "1", None])
@pytest.mark.asyncio
async def test_reject_invalid_memory_channel_without_cat(radio, bad):
    with pytest.raises(ValueError):
        await radio.get_memory_channel(bad)
    radio._transport.query.assert_not_awaited()
    radio._transport.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_memory_write_and_recall_still_fail_closed(radio):
    with pytest.raises(NotImplementedError):
        await radio.memory_write()
    with pytest.raises(NotImplementedError):
        await radio.memory_to_vfo(1)
    radio._transport.write.assert_not_awaited()
