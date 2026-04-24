"""dbcdiff.protocol — per-message CAN protocol classification."""


def classify_protocol(msg) -> str:
    """Return the CAN protocol variant for a message."""
    # CAN XL: check BusType attribute in DBC specifics
    try:
        if msg.dbc and msg.dbc.attributes:
            bus = msg.dbc.attributes.get('BusType')
            if bus and 'XL' in str(bus.value).upper():
                return 'CAN XL'
    except Exception:
        pass

    # CAN FD: is_fd flag or DLC > 8
    if getattr(msg, 'is_fd', False):
        return 'CAN FD'
    if msg.length > 8:
        return 'CAN FD'

    # J1939: 29-bit extended frame with PGN structure
    # PGN occupies bits 8-25 of the 29-bit ID; SA (low byte) <= 253
    if msg.is_extended_frame:
        pgn = (msg.frame_id >> 8) & 0x3FFFF
        sa = msg.frame_id & 0xFF
        if pgn <= 0xFFFF and sa <= 253:
            return 'J1939'

    # Standard CAN 2.0A (11-bit) or 2.0B (29-bit non-J1939)
    return 'CAN 2.0'


def classify_subtype(msg) -> str:
    """Return Cyclic / Event / Muxed / Unknown."""
    if msg.is_multiplexed():
        return 'Muxed'
    try:
        st = msg.dbc.attributes.get('GenMsgSendType')
        if st:
            v = str(st.value)
            if 'Cyclic' in v:
                return 'Cyclic'
            if 'Event' in v:
                return 'Event'
    except Exception:
        pass
    return 'Cyclic' if msg.cycle_time else 'Event'
