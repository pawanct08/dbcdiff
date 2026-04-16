"""
engine.py – Core diff engine for dbcdiff.

Compares two cantools Database objects and returns a list of DiffEntry
records, each tagged with a Severity level.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Severity levels (also used as CI exit-code contributors)
# ---------------------------------------------------------------------------

class Severity(enum.IntEnum):
    IDENTICAL  = 0   # no change at all
    METADATA   = 1   # comment / unit / sender / receiver label changes
    FUNCTIONAL = 2   # scale / offset / min / max / send_type / cycle_time
    BREAKING   = 3   # frame_id / dlc / bit-layout changes


ADDED   = "ADDED"
REMOVED = "REMOVED"
CHANGED = "CHANGED"


# ---------------------------------------------------------------------------
# DiffEntry – single change record
# ---------------------------------------------------------------------------

@dataclass
class DiffEntry:
    entity: str          # e.g. "message", "signal", "node", "attribute", "envvar"
    kind: str            # ADDED | REMOVED | CHANGED
    severity: Severity
    path: str            # human-readable location, e.g. "EngineStatus.RPM.scale"
    old_value: Any = None
    new_value: Any = None
    detail: str = ""     # free-text extra context

    def as_dict(self) -> dict:
        return {
            "entity":    self.entity,
            "kind":      self.kind,
            "severity":  self.severity.name,
            "path":      self.path,
            "old_value": _jsonable(self.old_value),
            "new_value": _jsonable(self.new_value),
            "detail":    self.detail,
        }


def _jsonable(v: Any) -> Any:
    """Convert value to something JSON-serialisable."""
    if isinstance(v, enum.Enum):
        return v.name
    if isinstance(v, (list, tuple)):
        return [_jsonable(i) for i in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items()}
    return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dbc_attr_dict(dbc_specifics) -> dict:
    """Extract BA_ attributes from a DbcSpecifics object into a plain dict."""
    if dbc_specifics is None:
        return {}
    attrs = {}
    try:
        for k, v in dbc_specifics.attributes.items():
            attrs[k] = v.value if hasattr(v, "value") else v
    except AttributeError:
        pass
    return attrs


def _msg_key(msg) -> tuple:
    """Unique key for a message."""
    return (msg.frame_id, msg.is_extended_frame)


def _sig_key(sig) -> str:
    return sig.name


# ---------------------------------------------------------------------------
# Field-level comparers
# ---------------------------------------------------------------------------

_MSG_BREAKING = {
    "frame_id":          lambda m: m.frame_id,
    "dlc":               lambda m: m.length,         # cantools uses .length
    "is_extended_frame": lambda m: m.is_extended_frame,
    "is_fd":             lambda m: m.is_fd,
}

_MSG_FUNCTIONAL = {
    "send_type":  lambda m: m.send_type,
    "cycle_time": lambda m: m.cycle_time,
}

_MSG_METADATA = {
    "name":    lambda m: m.name,
    "senders": lambda m: sorted(m.senders or []),
    "comment": lambda m: m.comment,
}

_SIG_BREAKING = {
    "start":      lambda s: s.start,
    "length":     lambda s: s.length,
    "byte_order": lambda s: str(s.byte_order),
    "is_signed":  lambda s: s.is_signed,
}

_SIG_FUNCTIONAL = {
    "scale":   lambda s: s.scale,
    "offset":  lambda s: s.offset,
    "minimum": lambda s: s.minimum,
    "maximum": lambda s: s.maximum,
    "is_float": lambda s: s.is_float,
    "multiplexer_ids": lambda s: sorted(s.multiplexer_ids or [])
                                  if s.multiplexer_ids else None,
    "is_multiplexer":  lambda s: s.is_multiplexer,
}

_SIG_METADATA = {
    "unit":      lambda s: s.unit,
    "comment":   lambda s: s.comment,
    "receivers": lambda s: sorted(s.receivers or []),
    "choices":   lambda s: {str(k): v for k, v in s.choices.items()}
                            if s.choices else None,
}


def _compare_fields(entity: str, path_prefix: str, old_obj, new_obj,
                    field_groups: list[tuple[dict, Severity]]) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    for field_map, severity in field_groups:
        for fname, getter in field_map.items():
            try:
                old_v = getter(old_obj)
                new_v = getter(new_obj)
            except Exception:
                continue
            if old_v != new_v:
                entries.append(DiffEntry(
                    entity=entity,
                    kind=CHANGED,
                    severity=severity,
                    path=f"{path_prefix}.{fname}",
                    old_value=old_v,
                    new_value=new_v,
                ))
    return entries


# ---------------------------------------------------------------------------
# Main diff function
# ---------------------------------------------------------------------------

def diff_databases(db_old, db_new) -> list[DiffEntry]:
    """
    Compare two cantools Database objects.
    Returns a list of DiffEntry records sorted by severity (descending).
    """
    entries: list[DiffEntry] = []

    entries.extend(_diff_nodes(db_old, db_new))
    entries.extend(_diff_messages(db_old, db_new))
    entries.extend(_diff_db_attributes(db_old, db_new))
    entries.extend(_diff_envvars(db_old, db_new))

    entries.sort(key=lambda e: -e.severity)
    return entries


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def _diff_nodes(db_old, db_new) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    old_nodes = {n.name: n for n in (db_old.nodes or [])}
    new_nodes = {n.name: n for n in (db_new.nodes or [])}

    for name in sorted(old_nodes.keys() - new_nodes.keys()):
        entries.append(DiffEntry("node", REMOVED, Severity.FUNCTIONAL,
                                  f"node.{name}", old_value=name))

    for name in sorted(new_nodes.keys() - old_nodes.keys()):
        entries.append(DiffEntry("node", ADDED, Severity.FUNCTIONAL,
                                  f"node.{name}", new_value=name))

    for name in sorted(old_nodes.keys() & new_nodes.keys()):
        o, n = old_nodes[name], new_nodes[name]
        if o.comment != n.comment:
            entries.append(DiffEntry("node", CHANGED, Severity.METADATA,
                                      f"node.{name}.comment",
                                      old_value=o.comment, new_value=n.comment))
        # BA_ attributes on nodes
        entries.extend(_diff_attributes("node", f"node.{name}",
                                         _dbc_attr_dict(o.dbc),
                                         _dbc_attr_dict(n.dbc)))
    return entries


# ---------------------------------------------------------------------------
# Messages & Signals
# ---------------------------------------------------------------------------

def _diff_messages(db_old, db_new) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    old_msgs = {_msg_key(m): m for m in db_old.messages}
    new_msgs = {_msg_key(m): m for m in db_new.messages}

    for key in sorted(old_msgs.keys() - new_msgs.keys()):
        m = old_msgs[key]
        entries.append(DiffEntry("message", REMOVED, Severity.FUNCTIONAL,
                                  f"message.{m.name}(0x{m.frame_id:X})",
                                  old_value=m.name))

    for key in sorted(new_msgs.keys() - old_msgs.keys()):
        m = new_msgs[key]
        entries.append(DiffEntry("message", ADDED, Severity.FUNCTIONAL,
                                  f"message.{m.name}(0x{m.frame_id:X})",
                                  new_value=m.name))

    for key in sorted(old_msgs.keys() & new_msgs.keys()):
        old_m, new_m = old_msgs[key], new_msgs[key]
        prefix = f"message.{old_m.name}(0x{old_m.frame_id:X})"

        # Message-level field comparison
        entries.extend(_compare_fields(
            "message", prefix, old_m, new_m,
            [
                (_MSG_BREAKING,    Severity.BREAKING),
                (_MSG_FUNCTIONAL,  Severity.FUNCTIONAL),
                (_MSG_METADATA,    Severity.METADATA),
            ]
        ))

        # BA_ attributes on message
        entries.extend(_diff_attributes(
            "attribute", prefix,
            _dbc_attr_dict(old_m.dbc),
            _dbc_attr_dict(new_m.dbc),
        ))

        # Signals
        entries.extend(_diff_signals(prefix, old_m, new_m))

    return entries


def _diff_signals(msg_prefix: str, old_m, new_m) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    old_sigs = {_sig_key(s): s for s in old_m.signals}
    new_sigs = {_sig_key(s): s for s in new_m.signals}

    for name in sorted(old_sigs.keys() - new_sigs.keys()):
        entries.append(DiffEntry("signal", REMOVED, Severity.FUNCTIONAL,
                                  f"{msg_prefix}.{name}", old_value=name))

    for name in sorted(new_sigs.keys() - old_sigs.keys()):
        entries.append(DiffEntry("signal", ADDED, Severity.FUNCTIONAL,
                                  f"{msg_prefix}.{name}", new_value=name))

    for name in sorted(old_sigs.keys() & new_sigs.keys()):
        old_s, new_s = old_sigs[name], new_sigs[name]
        prefix = f"{msg_prefix}.{name}"

        entries.extend(_compare_fields(
            "signal", prefix, old_s, new_s,
            [
                (_SIG_BREAKING,    Severity.BREAKING),
                (_SIG_FUNCTIONAL,  Severity.FUNCTIONAL),
                (_SIG_METADATA,    Severity.METADATA),
            ]
        ))

        # BA_ attributes on signal
        entries.extend(_diff_attributes(
            "attribute", prefix,
            _dbc_attr_dict(old_s.dbc),
            _dbc_attr_dict(new_s.dbc),
        ))

    return entries


# ---------------------------------------------------------------------------
# Attribute helper
# ---------------------------------------------------------------------------

def _diff_attributes(entity: str, path_prefix: str,
                      old_attrs: dict, new_attrs: dict) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    all_keys = sorted(old_attrs.keys() | new_attrs.keys())
    for k in all_keys:
        if k not in old_attrs:
            entries.append(DiffEntry(entity, ADDED, Severity.METADATA,
                                      f"{path_prefix}[{k}]",
                                      new_value=new_attrs[k]))
        elif k not in new_attrs:
            entries.append(DiffEntry(entity, REMOVED, Severity.METADATA,
                                      f"{path_prefix}[{k}]",
                                      old_value=old_attrs[k]))
        elif old_attrs[k] != new_attrs[k]:
            entries.append(DiffEntry(entity, CHANGED, Severity.METADATA,
                                      f"{path_prefix}[{k}]",
                                      old_value=old_attrs[k],
                                      new_value=new_attrs[k]))
    return entries


# ---------------------------------------------------------------------------
# DB-level attributes (BA_DEF_ / BA_ globals)
# ---------------------------------------------------------------------------

def _diff_db_attributes(db_old, db_new) -> list[DiffEntry]:
    try:
        old_a = _dbc_attr_dict(db_old.dbc)
        new_a = _dbc_attr_dict(db_new.dbc)
    except AttributeError:
        return []
    return _diff_attributes("attribute", "db", old_a, new_a)


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

def _diff_envvars(db_old, db_new) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    try:
        old_ev = {e.name: e for e in (db_old.dbc.environment_variables
                                       if db_old.dbc else [])}
        new_ev = {e.name: e for e in (db_new.dbc.environment_variables
                                       if db_new.dbc else [])}
    except AttributeError:
        return []

    for name in sorted(old_ev.keys() - new_ev.keys()):
        entries.append(DiffEntry("envvar", REMOVED, Severity.FUNCTIONAL,
                                  f"envvar.{name}", old_value=name))
    for name in sorted(new_ev.keys() - old_ev.keys()):
        entries.append(DiffEntry("envvar", ADDED, Severity.FUNCTIONAL,
                                  f"envvar.{name}", new_value=name))
    # Full field diff for shared envvars could be added here
    return entries


# ---------------------------------------------------------------------------
# Convenience: max severity from a list of entries
# ---------------------------------------------------------------------------

def max_severity(entries: list[DiffEntry]) -> Severity:
    if not entries:
        return Severity.IDENTICAL
    return Severity(max(e.severity for e in entries))
