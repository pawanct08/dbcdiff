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
