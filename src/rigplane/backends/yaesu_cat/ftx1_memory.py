"""Native FTX-1 memory read operations; no additional CAT connection or writes.

Authority: Yaesu FTX-1 CAT Operation Reference Manual 2508-C pp. 19-21.
Read-only MR and MT only. No serial owner, writes, memory recall, or PTT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Ftx1MemoryRecord",
    "parse_ftx1_memory_reply",
    "parse_ftx1_tag_reply",
    "read_ftx1_memory",
    "read_ftx1_memory_tag",
]

# The manual's intersecting normal-memory range is 00001-00099:
# MC and MT define up to 00099, whereas MR also mentions up to 00999.
# Start conservatively with the range all three agree on.
_MIN_CHANNEL = 1
_MAX_CHANNEL = 99
_MR = re.compile(
    r"^MR(?P<chan>[0-9]{5})(?P<freq>[0-9]{9})"
    r"(?P<sign>[+-])(?P<offset>[0-9]{4})"
    r"(?P<rx>[01])(?P<tx>[01])"
    r"(?P<mode>[1-9A-FHI])(?P<state>[01235])"
    r"(?P<tone>[0-5])00(?P<shift>[012]);?$"
)
_MT = re.compile(r"^MT(?P<chan>[0-9]{5})(?P<tag>[ -:<-~]{0,12});?$")


@dataclass(frozen=True, slots=True)
class Ftx1MemoryRecord:
    """Confirmed MR observation, not a local PC preset or write acknowledgement."""

    channel: int
    frequency_hz: int
    mode_code: str
    clarifier_offset_hz: int
    rx_clar_enabled: bool
    tx_clar_enabled: bool
    memory_state: int
    tone_mode: int
    repeater_shift: int


def _normal_channel(channel: int) -> str:
    if type(channel) is not int or not (_MIN_CHANNEL <= channel <= _MAX_CHANNEL):
        raise ValueError(
            "FTX-1 ordinary memory channel must be an integer from 1 to 99; "
            "PMS, QMB, 5 MHz and emergency memories require separate support"
        )
    return f"{channel:05d}"


def parse_ftx1_memory_reply(reply: str, *, channel: int) -> Ftx1MemoryRecord:
    """Validate the complete 30-character Yaesu MR answer before exposing state."""
    expected = _normal_channel(channel)
    if not isinstance(reply, str):
        raise ValueError("FTX-1 MR response must be text")
    matched = _MR.fullmatch(reply)
    if matched is None:
        raise ValueError("FTX-1 MR malformed, missing or rejected; memory is UNKNOWN")
    m = matched.groupdict()
    if m["chan"] != expected:
        raise ValueError("FTX-1 MR returned a different memory channel")
    freq = int(m["freq"])
    if not 30_000 <= freq <= 470_000_000:
        raise ValueError("FTX-1 MR memory frequency outside documented radio domain")
    offset = int(m["offset"])
    if offset > 9990:
        raise ValueError("FTX-1 MR clarifier offset outside documented 0..9990 Hz")
    clar = offset * (-1 if m["sign"] == "-" else 1)
    return Ftx1MemoryRecord(
        channel=channel,
        frequency_hz=freq,
        mode_code=m["mode"],
        clarifier_offset_hz=clar,
        rx_clar_enabled=m["rx"] == "1",
        tx_clar_enabled=m["tx"] == "1",
        memory_state=int(m["state"]),
        tone_mode=int(m["tone"]),
        repeater_shift=int(m["shift"]),
    )


def parse_ftx1_tag_reply(reply: str, *, channel: int) -> str:
    """Validate an MT response; names are radio-observed printable ASCII."""
    expected = _normal_channel(channel)
    if not isinstance(reply, str):
        raise ValueError("FTX-1 MT response must be text")
    matched = _MT.fullmatch(reply)
    if matched is None or matched.group("chan") != expected:
        raise ValueError("FTX-1 MT malformed or wrong-channel response")
    return matched.group("tag").rstrip()


async def read_ftx1_memory(radio: Any, channel: int) -> Ftx1MemoryRecord:
    """Use the ALREADY OPEN RigPlane transport and profile-backed MR read."""
    chan = _normal_channel(channel)
    # This is intentionally backend-owned code. VSS clients must call a
    # public RigPlane facade, NEVER open the CAT port or call _query directly.
    fields = await radio._query("get_memory_channel", chan=chan)
    # Reconstruct the exact response from the parser's typed fields so the
    # same strict validations apply to both the fake and real transport.
    raw = (
        f'MR{fields["chan"]}{fields["freq"]:09d}'
        f'{fields["sign"]}{fields["offset"]:04d}'
        f'{fields["rx"]}{fields["tx"]}{fields["mode"]}'
        f'{fields["state"]}{fields["tone"]}00{fields["shift"]};'
    )
    return parse_ftx1_memory_reply(raw, channel=channel)


async def read_ftx1_memory_tag(radio: Any, channel: int) -> str:
    """Read MT via the existing exchange-gated owner; MT tags vary in length."""
    chan = _normal_channel(channel)
    # The stock RigPlane CAT parser has no variable-length ASCII tag field.
    # Use the profile's read template and existing serialized transport;
    # do not create a second serial session or write a CAT command.
    from rigplane.backends.yaesu_cat.parser import format_command

    spec = radio._get_spec("get_memory_tag")
    if spec.read is None:
        raise ValueError("FTX-1 memory tag read is not declared in active profile")
    reply = await radio._transport.query(format_command(spec.read, chan=chan))
    return parse_ftx1_tag_reply(reply, channel=channel)
