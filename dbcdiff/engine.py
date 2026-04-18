"""
dbcdiff.engine
--------------
Core diff engine.  Compares two cantools Database objects and returns a flat
list of DiffEntry records describing every detected difference.

File-A / File-B terminology is used throughout (no "old" / "new").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from dbcdiff.protocol import (
    CANProtocol, detect_protocol,
    extract_j1939_pgn, extract_j1939_sa, extract_j1939_priority,
)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

class Severity(IntEnum):
    METADATA   = 1   # cosmetic: comment, unit, sender name
    FUNCTIONAL = 2   # run-time impact: scale, offset, cycle time
    BREAKING   = 3   # bus-level impact: bit position, DLC, frame-id

    def label(self) -> str:          # e.g. "Metadata"
        return self.name.capitalize()


ADDED   = "added"
REMOVED = "removed"
CHANGED = "changed"
RENAME  = "renamed"


# ---------------------------------------------------------------------------
# DiffEntry
# ---------------------------------------------------------------------------

@dataclass
class DiffEntry:
    entity:   str                       # "message", "signal", "node", …
    kind:     str                       # ADDED | REMOVED | CHANGED
    severity: Severity
    path:     str                       # dot-separated location
    value_a:  Any = None                # value in File A
    value_b:  Any = None                # value in File B
    detail:   str = ""
    protocol: str = ""                  # detected protocol label

    def as_dict(self) -> dict:
        return {
            "entity":   self.entity,
            "kind":     self.kind,
            "severity": self.severity.label(),
            "path":     self.path,
            "value_a":  _jsonable(self.value_a),
            "value_b":  _jsonable(self.value_b),
            "detail":   self.detail,
            "protocol": self.protocol,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool, type(None))):
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(i) for i in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(vv) for k, vv in v.items()}
    return str(v)


def _dbc_attr_dict(obj) -> dict:
    """Return {attr_name: value} from a cantools object's DBC specifics."""
    try:
        spec = obj.dbc
        if spec is None:
            return {}
        attrs = spec.attributes or {}
        return {k: v.value for k, v in attrs.items()}
    except AttributeError:
        return {}


def _msg_key(m) -> tuple:
    return (m.frame_id, m.is_extended_frame)


def _sig_key(s) -> str:
    return s.name


# ---------------------------------------------------------------------------
# Field maps (lambda getters)
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
    "scale":      lambda s: s.scale,
    "offset":     lambda s: s.offset,
    "minimum":    lambda s: s.minimum,
    "maximum":    lambda s: s.maximum,
    "is_float":   lambda s: s.is_float,
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


# ---------------------------------------------------------------------------
# Low-level field comparator
# ---------------------------------------------------------------------------

def _compare_fields(entity: str, path_prefix: str, obj_a, obj_b,
                    field_groups: list[tuple[dict, Severity]],
                    protocol: str = "") -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    for field_map, severity in field_groups:
        for fname, getter in field_map.items():
            try:
                val_a = getter(obj_a)
                val_b = getter(obj_b)
            except Exception:
                continue
            if val_a != val_b:
                entries.append(DiffEntry(
                    entity=entity,
                    kind=CHANGED,
                    severity=severity,
                    path=f"{path_prefix}.{fname}",
                    value_a=val_a,
                    value_b=val_b,
                    protocol=protocol,
                ))
    return entries


# ---------------------------------------------------------------------------
# J1939 specialised diff
# ---------------------------------------------------------------------------

def _diff_j1939_fields(ma, mb, msg_name: str, protocol: str,
                        out: list[DiffEntry]) -> None:
    """Compare J1939 decoded fields (PGN, SA, Priority) for 29-bit messages."""
    if not (getattr(ma, "is_extended_frame", False) and
            getattr(mb, "is_extended_frame", False)):
        return

    checks = [
        ("pgn",      extract_j1939_pgn,      Severity.BREAKING),
        ("sa",       extract_j1939_sa,        Severity.FUNCTIONAL),
        ("priority", extract_j1939_priority,   Severity.METADATA),
    ]
    for field_name, extractor, severity in checks:
        try:
            va = extractor(ma.frame_id)
            vb = extractor(mb.frame_id)
        except Exception:
            continue
        if va != vb:
            out.append(DiffEntry(
                entity="j1939",
                kind=CHANGED,
                severity=severity,
                path=f"message.{msg_name}.{field_name}",
                value_a=va,
                value_b=vb,
                protocol=protocol,
            ))


# ---------------------------------------------------------------------------
# Cross-message signal rename resolution (post-pass)
# ---------------------------------------------------------------------------

def _parse_msg_name_from_path(path: str) -> str:
    """Extract 'MsgName' from a path like 'message.MsgName(0xXX).SigName'."""
    if not path.startswith("message."):
        return ""
    rest = path[len("message."):]
    paren_pos = rest.find("(")
    return rest[:paren_pos] if paren_pos >= 0 else rest.split(".")[0]


def _resolve_cross_message_signal_renames(
        entries: list[DiffEntry], db_a, db_b, protocol: str) -> list[DiffEntry]:
    """Post-pass: upgrade REMOVED+ADDED signal pairs that share fingerprints but
    live in *different* messages to a single RENAME entry.

    Within-message renames are already handled by _diff_signals(). This pass
    only promotes cross-message cases that fall through as plain REMOVED+ADDED.
    """
    sig_by_key_a: dict[tuple, object] = {
        (m.name, s.name): s for m in db_a.messages for s in m.signals
    }
    sig_by_key_b: dict[tuple, object] = {
        (m.name, s.name): s for m in db_b.messages for s in m.signals
    }

    removed_sig: list[DiffEntry] = []
    added_sig:   list[DiffEntry] = []
    other:       list[DiffEntry] = []

    for e in entries:
        if e.entity == "signal" and e.kind == REMOVED:
            removed_sig.append(e)
        elif e.entity == "signal" and e.kind == ADDED:
            added_sig.append(e)
        else:
            other.append(e)

    fp_to_removed_e: dict[tuple, DiffEntry] = {}
    for e in removed_sig:
        msg_name = _parse_msg_name_from_path(e.path)
        sig_name = e.value_a or ""
        sig_obj = sig_by_key_a.get((msg_name, sig_name))
        if sig_obj is not None:
            fp = _sig_fingerprint(sig_obj)
            if fp not in fp_to_removed_e:
                fp_to_removed_e[fp] = e

    matched_removed: set[int] = set()
    matched_added:   set[int] = set()
    rename_entries:  list[DiffEntry] = []

    for e in added_sig:
        msg_name = _parse_msg_name_from_path(e.path)
        sig_name = e.value_b or ""
        sig_obj = sig_by_key_b.get((msg_name, sig_name))
        if sig_obj is not None:
            fp = _sig_fingerprint(sig_obj)
            if fp in fp_to_removed_e:
                e_removed = fp_to_removed_e.pop(fp)
                matched_removed.add(id(e_removed))
                matched_added.add(id(e))
                old_msg = _parse_msg_name_from_path(e_removed.path)
                new_msg = _parse_msg_name_from_path(e.path)
                rename_entries.append(DiffEntry(
                    entity="signal",
                    kind=RENAME,
                    severity=Severity.METADATA,
                    path=e_removed.path,
                    value_a=f"{old_msg}.{e_removed.value_a}",
                    value_b=f"{new_msg}.{e.value_b}",
                    detail=(f"moved {e_removed.value_a!r} from {old_msg!r} "
                            f"→ {e.value_b!r} in {new_msg!r}"),
                    protocol=protocol,
                ))

    result = other
    result.extend(e for e in removed_sig if id(e) not in matched_removed)
    result.extend(e for e in added_sig   if id(e) not in matched_added)
    result.extend(rename_entries)
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compare_databases(db_a, db_b,
                      path_a: str = "File A",
                      path_b: str = "File B",
                      baud_rate: int = 500_000) -> list[DiffEntry]:
    """
    Compare two cantools Database objects.

    Parameters
    ----------
    db_a, db_b  : cantools.database.Database
    path_a, path_b : human-readable labels used in summary entries

    Returns
    -------
    List of DiffEntry records, sorted by severity (descending).
    """
    entries: list[DiffEntry] = []

    proto_a = detect_protocol(db_a)
    proto_b = detect_protocol(db_b)

    # Report protocol mismatch as a functional difference
    if proto_a != proto_b:
        entries.append(DiffEntry(
            entity="database",
            kind=CHANGED,
            severity=Severity.FUNCTIONAL,
            path="db.protocol",
            value_a=proto_a.value,
            value_b=proto_b.value,
            detail=f"{path_a} uses {proto_a.value}, {path_b} uses {proto_b.value}",
            protocol=f"{proto_a.value} / {proto_b.value}",
        ))

    # Use File-A protocol label for individual entries (dominant file)
    proto_label = proto_a.value

    entries.extend(_diff_nodes(db_a, db_b, proto_label))
    entries.extend(_diff_messages(db_a, db_b, proto_label, baud_rate=baud_rate))
    entries.extend(_diff_db_attributes(db_a, db_b))
    entries.extend(_diff_envvars(db_a, db_b))

    entries = _resolve_cross_message_signal_renames(entries, db_a, db_b, proto_label)
    entries = _expand_choices_diff(entries)
    entries.sort(key=lambda e: -e.severity)
    return entries


# Backwards-compatibility alias
def diff_databases(db_old, db_new) -> list[DiffEntry]:
    return compare_databases(db_old, db_new)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def _diff_nodes(db_a, db_b, protocol: str = "") -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    nodes_a = {n.name: n for n in (db_a.nodes or [])}
    nodes_b = {n.name: n for n in (db_b.nodes or [])}

    for name in sorted(nodes_a.keys() - nodes_b.keys()):
        entries.append(DiffEntry("node", REMOVED, Severity.BREAKING,
                                  f"node.{name}", value_a=name,
                                  protocol=protocol))

    for name in sorted(nodes_b.keys() - nodes_a.keys()):
        entries.append(DiffEntry("node", ADDED, Severity.FUNCTIONAL,
                                  f"node.{name}", value_b=name,
                                  protocol=protocol))

    for name in sorted(nodes_a.keys() & nodes_b.keys()):
        na, nb = nodes_a[name], nodes_b[name]
        if na.comment != nb.comment:
            entries.append(DiffEntry("node", CHANGED, Severity.METADATA,
                                      f"node.{name}.comment",
                                      value_a=na.comment, value_b=nb.comment,
                                      protocol=protocol))
        entries.extend(_diff_attributes("node", f"node.{name}",
                                         _dbc_attr_dict(na),
                                         _dbc_attr_dict(nb),
                                         protocol=protocol))
    return entries


# ---------------------------------------------------------------------------
# Messages & Signals
# ---------------------------------------------------------------------------

def _diff_messages(db_a, db_b, protocol: str = "", baud_rate: int = 500_000) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    msgs_a = {_msg_key(m): m for m in db_a.messages}
    msgs_b = {_msg_key(m): m for m in db_b.messages}

    # --- Message rename detection ---
    # A message is "renamed" when its DLC + signal-geometry fingerprint matches
    # across a removed↔added pair with different names (same frame_id already
    # implies matching — here we handle messages removed from one frame_id and
    # a structurally-identical new message added at a different frame_id).
    removed_keys = sorted(msgs_a.keys() - msgs_b.keys())
    added_keys   = sorted(msgs_b.keys() - msgs_a.keys())

    fp_to_removed_key: dict[tuple, tuple] = {}
    for key in removed_keys:
        fp = _msg_fingerprint(msgs_a[key])
        if fp not in fp_to_removed_key:
            fp_to_removed_key[fp] = key

    rename_removed_keys: set[tuple] = set()
    rename_added_keys:   set[tuple] = set()

    for key in added_keys:
        fp = _msg_fingerprint(msgs_b[key])
        if fp in fp_to_removed_key:
            old_key = fp_to_removed_key.pop(fp)
            rename_removed_keys.add(old_key)
            rename_added_keys.add(key)
            ma_r = msgs_a[old_key]
            mb_a = msgs_b[key]
            entries.append(DiffEntry(
                entity="message",
                kind=RENAME,
                severity=Severity.METADATA,
                path=f"message.{ma_r.name}(0x{ma_r.frame_id:X})",
                value_a=ma_r.name,
                value_b=mb_a.name,
                detail=f"renamed {ma_r.name!r} → {mb_a.name!r}",
                protocol=protocol,
            ))

    for key in removed_keys:
        if key in rename_removed_keys:
            continue
        m = msgs_a[key]
        entries.append(DiffEntry("message", REMOVED, Severity.BREAKING,
                                  f"message.{m.name}(0x{m.frame_id:X})",
                                  value_a=m.name, protocol=protocol))

    for key in added_keys:
        if key in rename_added_keys:
            continue
        m = msgs_b[key]
        entries.append(DiffEntry("message", ADDED, Severity.FUNCTIONAL,
                                  f"message.{m.name}(0x{m.frame_id:X})",
                                  value_b=m.name, protocol=protocol))

    for key in sorted(msgs_a.keys() & msgs_b.keys()):
        ma, mb = msgs_a[key], msgs_b[key]
        prefix = f"message.{ma.name}(0x{ma.frame_id:X})"

        msg_fields = _compare_fields(
            "message", prefix, ma, mb,
            [
                (_MSG_BREAKING,    Severity.BREAKING),
                (_MSG_FUNCTIONAL,  Severity.FUNCTIONAL),
                (_MSG_METADATA,    Severity.METADATA),
            ],
            protocol=protocol,
        )
        for _ent in msg_fields:
            if (_ent.kind == CHANGED
                    and _ent.path == f"{prefix}.cycle_time"
                    and _ent.value_a and _ent.value_b):
                try:
                    ct_a, ct_b = float(_ent.value_a), float(_ent.value_b)
                    if ct_a > 0 and ct_b > 0:
                        overhead = 67 if ma.is_extended_frame else 47
                        frame_bits = overhead + ma.length * 8
                        load_a = frame_bits / (ct_a * 1e-3) / baud_rate * 100
                        load_b = frame_bits / (ct_b * 1e-3) / baud_rate * 100
                        _ent.detail = (
                            f"bus_load {load_a:.3f}% → {load_b:.3f}%"
                            f"  (Δ{load_b - load_a:+.3f}%  @ {baud_rate // 1000}kbps)"
                        )
                except (TypeError, ZeroDivisionError, ValueError):
                    pass
        entries.extend(msg_fields)

        # J1939 extended decode
        _diff_j1939_fields(ma, mb, ma.name, protocol, entries)

        entries.extend(_diff_attributes(
            "attribute", prefix,
            _dbc_attr_dict(ma),
            _dbc_attr_dict(mb),
            protocol=protocol,
        ))

        entries.extend(_diff_signals(prefix, ma, mb, protocol))

    return entries


def _signals_overlap(sig, other_signals) -> bool:
    """Return True if *sig* bit range overlaps any signal in *other_signals*."""
    def _bit_set(s) -> set:
        return set(range(s.start, s.start + s.length))
    sig_bits = _bit_set(sig)
    return any(sig_bits & _bit_set(o) for o in other_signals)


def _sig_fingerprint(s) -> tuple:
    """Return a geometry-and-scaling fingerprint used for rename detection.

    Two signals with identical fingerprints but different names are treated as
    a *rename* rather than a removal + addition.
    """
    return (
        s.start,
        s.length,
        str(s.byte_order),
        s.is_signed,
        s.scale,
        s.offset,
    )


def _msg_fingerprint(m) -> tuple:
    """Return a fingerprint for message rename detection: (dlc, frozenset of signal fingerprints).

    Two messages with identical fingerprints but different names are treated as
    a *rename* rather than a removal + addition.
    """
    sigs_fp = frozenset(_sig_fingerprint(s) for s in m.signals)
    return (m.length, sigs_fp)


def _diff_signals(msg_prefix: str, ma, mb, protocol: str = "") -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    sigs_a = {_sig_key(s): s for s in ma.signals}
    sigs_b = {_sig_key(s): s for s in mb.signals}

    removed_names = sorted(sigs_a.keys() - sigs_b.keys())
    added_names   = sorted(sigs_b.keys() - sigs_a.keys())

    # ------------------------------------------------------------------
    # Rename detection: match removed↔added signals by geometry fingerprint.
    # If a removed signal shares (start, length, byte_order, is_signed,
    # scale, offset) with an added signal, it's a rename — emit a single
    # RENAME entry instead of REMOVED + ADDED.
    # ------------------------------------------------------------------
    fp_to_removed: dict[tuple, str] = {}
    for name in removed_names:
        fp = _sig_fingerprint(sigs_a[name])
        # First match wins; if two removed signals share a fingerprint we
        # cannot determine which was renamed, so keep only the first.
        if fp not in fp_to_removed:
            fp_to_removed[fp] = name

    renamed_removed: set[str] = set()
    renamed_added:   set[str] = set()

    for add_name in added_names:
        fp = _sig_fingerprint(sigs_b[add_name])
        if fp in fp_to_removed:
            old_name = fp_to_removed.pop(fp)   # consume so it's not reused
            renamed_removed.add(old_name)
            renamed_added.add(add_name)
            entries.append(DiffEntry(
                entity="signal",
                kind=RENAME,
                severity=Severity.METADATA,
                path=f"{msg_prefix}.{old_name}",
                value_a=old_name,
                value_b=add_name,
                detail=f"renamed {old_name!r} → {add_name!r}",
                protocol=protocol,
            ))

    # Emit plain REMOVED for signals that weren't matched to a rename
    for name in removed_names:
        if name in renamed_removed:
            continue
        sev = (
            Severity.BREAKING
            if _signals_overlap(sigs_a[name], sigs_b.values())
            else Severity.FUNCTIONAL
        )
        entries.append(DiffEntry("signal", REMOVED, sev,
                                  f"{msg_prefix}.{name}", value_a=name,
                                  protocol=protocol))

    # Emit plain ADDED for signals that weren't matched to a rename
    for name in added_names:
        if name in renamed_added:
            continue
        entries.append(DiffEntry("signal", ADDED, Severity.FUNCTIONAL,
                                  f"{msg_prefix}.{name}", value_b=name,
                                  protocol=protocol))

    for name in sorted(sigs_a.keys() & sigs_b.keys()):
        sa, sb = sigs_a[name], sigs_b[name]
        prefix = f"{msg_prefix}.{name}"

        entries.extend(_compare_fields(
            "signal", prefix, sa, sb,
            [
                (_SIG_BREAKING,    Severity.BREAKING),
                (_SIG_FUNCTIONAL,  Severity.FUNCTIONAL),
                (_SIG_METADATA,    Severity.METADATA),
            ],
            protocol=protocol,
        ))

        entries.extend(_diff_attributes(
            "attribute", prefix,
            _dbc_attr_dict(sa),
            _dbc_attr_dict(sb),
            protocol=protocol,
        ))

    return entries


# ---------------------------------------------------------------------------
# Attribute helper
# ---------------------------------------------------------------------------

def _diff_attributes(entity: str, path_prefix: str,
                      attrs_a: dict, attrs_b: dict,
                      protocol: str = "") -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    all_keys = sorted(attrs_a.keys() | attrs_b.keys())
    for k in all_keys:
        if k not in attrs_a:
            entries.append(DiffEntry(entity, ADDED, Severity.METADATA,
                                      f"{path_prefix}[{k}]",
                                      value_b=attrs_b[k], protocol=protocol))
        elif k not in attrs_b:
            entries.append(DiffEntry(entity, REMOVED, Severity.METADATA,
                                      f"{path_prefix}[{k}]",
                                      value_a=attrs_a[k], protocol=protocol))
        elif attrs_a[k] != attrs_b[k]:
            entries.append(DiffEntry(entity, CHANGED, Severity.METADATA,
                                      f"{path_prefix}[{k}]",
                                      value_a=attrs_a[k],
                                      value_b=attrs_b[k],
                                      protocol=protocol))
    return entries


# ---------------------------------------------------------------------------
# DB-level attributes (BA_DEF_ / BA_ globals)
# ---------------------------------------------------------------------------

def _diff_db_attributes(db_a, db_b) -> list[DiffEntry]:
    try:
        attrs_a = _dbc_attr_dict(db_a)
        attrs_b = _dbc_attr_dict(db_b)
    except AttributeError:
        return []
    return _diff_attributes("attribute", "db", attrs_a, attrs_b)


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------

def _diff_envvars(db_a, db_b) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    try:
        ev_a = {e.name: e for e in (db_a.dbc.environment_variables
                                     if db_a.dbc else [])}
        ev_b = {e.name: e for e in (db_b.dbc.environment_variables
                                     if db_b.dbc else [])}
    except AttributeError:
        return []

    for name in sorted(ev_a.keys() - ev_b.keys()):
        entries.append(DiffEntry("envvar", REMOVED, Severity.FUNCTIONAL,
                                  f"envvar.{name}", value_a=name))
    for name in sorted(ev_b.keys() - ev_a.keys()):
        entries.append(DiffEntry("envvar", ADDED, Severity.FUNCTIONAL,
                                  f"envvar.{name}", value_b=name))
    return entries


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def max_severity(entries: list[DiffEntry]) -> Optional[Severity]:
    if not entries:
        return None
    return Severity(max(e.severity for e in entries))


# ---------------------------------------------------------------------------
# Value-table semantic diff  (Feature #4)
# ---------------------------------------------------------------------------

def _expand_choices_diff(entries: list[DiffEntry]) -> list[DiffEntry]:
    """Expand raw CHANGED .choices entries into per-key ADDED/REMOVED/CHANGED rows."""
    result: list[DiffEntry] = []
    for e in entries:
        if (e.kind == CHANGED
                and e.path.endswith(".choices")
                and isinstance(e.value_a, dict)
                and isinstance(e.value_b, dict)):
            all_keys = sorted(
                e.value_a.keys() | e.value_b.keys(),
                key=lambda x: int(x) if str(x).lstrip("-").isdigit() else x,
            )
            for k in all_keys:
                va = e.value_a.get(k)
                vb = e.value_b.get(k)
                if va is None:
                    result.append(DiffEntry(e.entity, ADDED, e.severity,
                                            f"{e.path}[{k}]",
                                            value_b=vb, protocol=e.protocol))
                elif vb is None:
                    result.append(DiffEntry(e.entity, REMOVED, e.severity,
                                            f"{e.path}[{k}]",
                                            value_a=va, protocol=e.protocol))
                elif va != vb:
                    result.append(DiffEntry(e.entity, CHANGED, e.severity,
                                            f"{e.path}[{k}]",
                                            value_a=va, value_b=vb,
                                            protocol=e.protocol))
                # identical keys are silently dropped (no diff)
        else:
            result.append(e)
    return result


# ---------------------------------------------------------------------------
# Three-way merge diff  (Feature #1)
# ---------------------------------------------------------------------------

@dataclass
class ThreeWayResult:
    """Three-way CAN database diff (base vs branch_a vs branch_b)."""
    only_in_a: list[DiffEntry]
    only_in_b: list[DiffEntry]
    conflict:  list[DiffEntry]
    common:    list[DiffEntry]


def compare_three_way(db_base, db_a, db_b,
                      path_base: str = "Base",
                      path_a:    str = "Branch A",
                      path_b:    str = "Branch B",
                      baud_rate: int = 500_000) -> ThreeWayResult:
    """Three-way diff: changes in each branch relative to a shared base."""
    entries_a = compare_databases(db_base, db_a, path_base, path_a,
                                  baud_rate=baud_rate)
    entries_b = compare_databases(db_base, db_b, path_base, path_b,
                                  baud_rate=baud_rate)

    idx_a = {(e.path, e.kind): e for e in entries_a}
    idx_b = {(e.path, e.kind): e for e in entries_b}
    keys_a, keys_b = set(idx_a), set(idx_b)

    only_a   = sorted([idx_a[k] for k in keys_a - keys_b], key=lambda e: e.path)
    only_b   = sorted([idx_b[k] for k in keys_b - keys_a], key=lambda e: e.path)
    common:   list[DiffEntry] = []
    conflict: list[DiffEntry] = []

    for k in sorted(keys_a & keys_b):
        ea, eb = idx_a[k], idx_b[k]
        if ea.value_b == eb.value_b:
            common.append(ea)
        else:
            conflict.extend([ea, eb])

    return ThreeWayResult(only_a, only_b, conflict, common)


# ---------------------------------------------------------------------------
# Bus-load analysis  (Timing Analysis tab)
# ---------------------------------------------------------------------------

#: Supported baud rates displayed in the UI dropdown
BAUD_RATES: dict[str, int] = {
    "125k":  125_000,
    "250k":  250_000,
    "500k":  500_000,
    "1M":  1_000_000,
    "2M":  2_000_000,   # CAN FD
}


def compute_bus_load(db, baud_rate: int) -> list[dict]:
    """Return per-message bus-load records sorted by load% descending.

    Skips messages with no cycle time (periodic load cannot be estimated).

    Frame-bit count uses standard CAN overhead formulas:
      * Standard (11-bit ID):  47 bits + 8×DLC
      * Extended / FD (29-bit): 67 bits + 8×DLC
    """
    results: list[dict] = []
    for m in db.messages:
        if not m.cycle_time or m.cycle_time <= 0:
            continue  # aperiodic / event-triggered — skip
        is_ext = m.is_extended_frame or getattr(m, "is_fd", False)
        overhead = 67 if is_ext else 47
        frame_bits = overhead + 8 * m.length
        cycle_s = m.cycle_time / 1000.0               # ms → s
        load_pct = (frame_bits / baud_rate) / cycle_s * 100.0
        results.append({
            "name":        m.name,
            "frame_id":    m.frame_id,
            "dlc":         m.length,
            "cycle_ms":    m.cycle_time,
            "frame_bits":  frame_bits,
            "load_pct":    load_pct,
            "is_extended": is_ext,
        })
    results.sort(key=lambda r: r["load_pct"], reverse=True)
    return results


def compute_bus_load_delta(
    db_a, db_b, baud_rate: int
) -> list[dict]:
    """Return per-message load delta between two DBCs.

    Each entry includes ``load_pct_a``, ``load_pct_b``, and ``delta``
    (positive = load increased in db_b).  Messages present in only one DB
    are included with the absent side set to ``None``.
    """
    def _load_map(db) -> dict[str, float]:
        return {r["name"]: r["load_pct"] for r in compute_bus_load(db, baud_rate)}

    map_a = _load_map(db_a)
    map_b = _load_map(db_b)
    all_names = sorted(map_a.keys() | map_b.keys())

    results: list[dict] = []
    for name in all_names:
        la = map_a.get(name)
        lb = map_b.get(name)
        delta = (lb or 0.0) - (la or 0.0)
        results.append({
            "name":       name,
            "load_pct_a": la,
            "load_pct_b": lb,
            "delta":      delta,
        })
    results.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return results
