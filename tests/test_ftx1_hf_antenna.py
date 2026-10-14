"""FTX-1 Optima manufacturer's EX030701-04, native public API, NO radio."""
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from rigplane.backends.yaesu_cat.radio import YaesuCatRadio
from rigplane.exceptions import CommandError
from rigplane.rig_loader import load_rig

@pytest.fixture
def radio():
    rig=YaesuCatRadio("/dev/null", profile=load_rig(Path(__file__).parents[1]/"rigs"/"ftx1.toml"))
    rig._transport._connected=True
    rig._transport.query=AsyncMock()
    rig._transport.write=AsyncMock()
    return rig

@pytest.mark.asyncio
async def test_hf_radio_antenna_live_readback(radio):
    for p4 in (0,1):
        radio._transport.query.return_value=f"EX030704{p4}"
        assert await radio.get_hf_antenna()==p4
        radio._transport.query.assert_awaited_with("EX030704;")
    radio._transport.write.assert_not_awaited()

@pytest.mark.asyncio
async def test_write_is_only_yaesu_hf_antenna_menu_p4(radio):
    await radio.set_hf_antenna(1)
    radio._transport.write.assert_awaited_once_with("EX0307041;")
    radio._transport.write.reset_mock()
    await radio.set_hf_antenna(0)
    radio._transport.write.assert_awaited_once_with("EX0307040;")

@pytest.mark.asyncio
async def test_reject_invalid_before_any_cat_write(radio):
    for value in (-1,2,True,False,"1",None,1.0):
        with pytest.raises(CommandError):
            await radio.set_hf_antenna(value)
    radio._transport.write.assert_not_awaited()

@pytest.mark.asyncio
async def test_read_selected_antenna_tuner_modes_and_ant2_rx_rule(radio):
    for ant in (0,1):
        for p4 in range(4):
            radio._transport.query.return_value=f"EX03070{ant+1}{p4}"
            assert await radio.get_hf_antenna_tuner_type(ant)==p4
            radio._transport.query.assert_awaited_with(f"EX03070{ant+1};")
    for p4 in range(3):
        radio._transport.query.return_value=f"EX030703{p4}"
        assert await radio.get_ant2_operation()==p4
        radio._transport.query.assert_awaited_with("EX030703;")
    radio._transport.write.assert_not_awaited()

@pytest.mark.asyncio
async def test_failed_cat_read_never_succeeds(radio):
    for bad in ("", "?", "EX0307042", "EX030704", "EX0307021"):
        radio._transport.query.return_value=bad
        with pytest.raises(Exception):
            await radio.get_hf_antenna()
    radio._transport.write.assert_not_awaited()

def test_profile_enumerates_exact_yaesu_commands(radio):
    c=radio._config.commands
    assert c["get_hf_antenna"].read=="EX030704;"
    assert c["set_hf_antenna"].write=="EX030704{ant};"
    assert c["get_tuner_type_ant1"].read=="EX030701;"
    assert c["get_tuner_type_ant2"].read=="EX030702;"
    assert c["get_ant2_operation"].read=="EX030703;"
