"""
dbcdiff.protocol
~~~~~~~~~~~~~~~~
Protocol detection and J1939 helpers.

Supported protocols
-------------------
- Basic CAN   (11-bit IDs, standard frame, ≤8 bytes)
- CAN FD      (ISO 11898-7, up to 64 bytes, optional BRS/ESI)
- J1939       (SAE, 29-bit extended IDs, PGN/SA/Priority structure)
- CAN XL      (ISO 11898-6, up to 2048 bytes – heuristic flag only)
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid circular at runtime
    import cantools.database


class CANProtocol(str, Enum):
    """Named protocol identifiers returned by :func:`detect_protocol`."""

    BASIC_CAN = "Basic CAN"
    CAN_FD = "CAN FD"
    J1939 = "J1939"
    CAN_XL = "CAN XL"
    UNKNOWN = "Unknown"


# ──────────────────────────────────────────────────────────────────────────────
# J1939 bit-field helpers (29-bit extended frame layout)
# ──────────────────────────────────────────────────────────────────────────────
# Bit layout of a 29-bit J1939 frame ID:
#   Bits 28-26 : Priority     (3 bits)
#   Bit  25    : Reserved
#   Bit  24    : Data Page    (DP)
#   Bits 23-16 : PGN high byte (PDU Format / PF)
#   Bits 15- 8 : PGN low byte  (PDU Specific / PS) — destination SA if PF < 240
#   Bits  7- 0 : Source Address (SA)

def extract_j1939_priority(frame_id: int) -> int:
    """Return the 3-bit Priority field from a J1939 29-bit frame ID."""
    return (frame_id >> 26) & 0x07


def extract_j1939_pgn(frame_id: int) -> int:
    """Return the Parameter Group Number (PGN) from a J1939 29-bit frame ID.

    For PDU1 (PF < 240) the PDU Specific byte encodes the destination address
    and is *not* part of the PGN; it is zeroed in the returned value.
    For PDU2 (PF >= 240) the byte is part of the PGN.
    """
    pf = (frame_id >> 8) & 0xFF   # PDU Format
    dp = (frame_id >> 24) & 0x01  # Data Page
    if pf < 0xF0:  # PDU1 — destination SA, not PGN
        return (dp << 17) | (pf << 8)
    # PDU2 — full PGN including PS
    ps = (frame_id >> 0) & 0xFF   # actually bits 15-8 after SA removed
    # Reconstruct: DP(1), Reserved(1), PF(8), PS(8)
    return (dp << 17) | (pf << 8) | ps


def extract_j1939_sa(frame_id: int) -> int:
    """Return the Source Address (SA) byte from a J1939 29-bit frame ID."""
    return frame_id & 0xFF


# ──────────────────────────────────────────────────────────────────────────────
# Protocol detection
# ──────────────────────────────────────────────────────────────────────────────
_J1939_DB_ATTR_KEYS = frozenset({
    "J1939PGN", "J1939SA", "J1939SystemInstance", "J1939BAMTickTime",
    "SPN", "SystemSignalLongSymbol",  # common Kvaser / CANdb++ J1939 attrs
    "GenSigSendType",  # used by some J1939 exporters
})

_CAN_XL_ATTR_KEYS = frozenset({
    "CANXL", "CAN_XL", "CanXlAF",  # heuristic — no universal standard yet
})


def detect_protocol(db: "cantools.database.Database") -> CANProtocol:
    """Heuristically determine the CAN protocol used in *db*.

    Detection priority
    ------------------
    1. **CAN XL** — any message with ``is_fd`` AND SDU type hint attrs, or
       explicit CANXL database attribute.
    2. **CAN FD** — any message has ``is_fd == True`` or payload > 8 bytes.
    3. **J1939**  — majority of messages use 29-bit extended IDs and the
       database has known J1939 attribute keys, OR all extended IDs with
       well-formed PGN structure.
    4. **Basic CAN** — fallback.
    """
    messages = list(db.messages)
    if not messages:
        return CANProtocol.UNKNOWN

    # ── CAN XL heuristic ────────────────────────────────────────────────────
    db_attr_keys: set[str] = set()
    try:
        if db.dbc and db.dbc.attributes:
            db_attr_keys = set(db.dbc.attributes.keys())
    except Exception:
        pass

    if db_attr_keys & _CAN_XL_ATTR_KEYS:
        return CANProtocol.CAN_XL

    # ── CAN FD ──────────────────────────────────────────────────────────────
    if any(getattr(m, "is_fd", False) or m.length > 8 for m in messages):
        return CANProtocol.CAN_FD

    # ── J1939 ───────────────────────────────────────────────────────────────
    # Check database-level attributes first (most reliable)
    if db_attr_keys & _J1939_DB_ATTR_KEYS:
        return CANProtocol.J1939

    # Check message-level attributes
    for msg in messages:
        try:
            msg_attr_keys = set()
            if msg.dbc and msg.dbc.attributes:
                msg_attr_keys = set(msg.dbc.attributes.keys())
            if msg_attr_keys & _J1939_DB_ATTR_KEYS:
                return CANProtocol.J1939
        except Exception:
            pass

    # Check structural signature: all extended IDs → likely J1939
    extended = [m for m in messages if m.is_extended_frame]
    if len(extended) == len(messages) and len(messages) >= 2:
        # Validate PGN structure: SA byte should vary, PGN part should be
        # recognisable (PF != 0 for most real messages)
        pgns = {extract_j1939_pgn(m.frame_id) for m in extended}
        if len(pgns) > 1 or any(extract_j1939_sa(m.frame_id) != 0 for m in extended):
            return CANProtocol.J1939

    return CANProtocol.BASIC_CAN


def protocol_summary(db: "cantools.database.Database") -> dict:
    """Return a dict with key protocol facts about *db* for display / logging."""
    proto = detect_protocol(db)
    msgs  = list(db.messages)
    sigs  = sum(len(m.signals) for m in msgs)
    nodes = len(db.nodes) if db.nodes else 0
    result = {
        "protocol": proto.value,
        "messages": len(msgs),
        "signals":  sigs,
        "nodes":    nodes,
    }
    if proto == CANProtocol.J1939:
        pgns = {extract_j1939_pgn(m.frame_id) for m in msgs if m.is_extended_frame}
        result["unique_pgns"] = len(pgns)
    return result
