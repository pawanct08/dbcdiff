def classify_message(msg) -> str:
    """Return CAN message sub-type for display."""
    if msg.is_multiplexed():
        return "Muxed"

    send_type = ""
    try:
        send_type = msg.dbc.attributes.get("GenMsgSendType", None)
        if send_type:
            send_type = send_type.value
    except Exception:
        pass

    if send_type == "Event":
        return "Event"
    if send_type == "Cyclic":
        return "Cyclic"
    return "CAN 2.0"


def classify_subtype(msg) -> str:
    """Return message send sub-type: Muxed / Event / Cyclic / —."""
    if msg.is_multiplexed():
        return "Muxed"

    send_type = ""
    try:
        send_type = msg.dbc.attributes.get("GenMsgSendType", None)
        if send_type:
            send_type = send_type.value
    except Exception:
        pass

    if send_type == "Event":
        return "Event"
    if send_type == "Cyclic":
        return "Cyclic"
    return "—"


def classify_protocol(msg) -> str:
    """Return bus protocol: CAN FD / J1939 / CAN 2.0."""
    try:
        if getattr(msg, "is_fd", False):
            return "CAN FD"
        # J1939 uses 29-bit extended PGN-based IDs (≥ 0x18000000)
        if getattr(msg, "is_extended_id", False) and msg.frame_id >= 0x18000000:
            return "J1939"
    except Exception:
        pass
    return "CAN 2.0"
