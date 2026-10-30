"""Outlook messages (`.msg`) written by hand, for the reader's tests: a compound file (MS-CFB, version 3) holding a
message's property streams (MS-OXMSG), only the ones bridge-kit reads. The reader is checked against this writer, so the
first real `.msg` a BA brings is the check that both read the format as Outlook writes it.

    msg(path, subject="Re: VAT", sender=("Anna Example", "anna@example.com"), to=[("Bo", "bo@example.com")],
        text="Hello", html="<p>Hello</p>", attachments=[("rough.csv", b"...", "text/csv", None)])
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone

SECTOR, MINI, CUTOFF = 512, 64, 4096
FREE, END, FATSECT, NONE = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF


def _utf16(text: str) -> bytes:
    return text.encode("utf-16-le")


def _filetime(when: datetime) -> bytes:
    delta = when - datetime(1601, 1, 1, tzinfo=timezone.utc)
    return (int(delta.total_seconds()) * 10_000_000 + delta.microseconds * 10).to_bytes(8, "little")


def _properties(header: int, entries: list[tuple[int, bytes]]) -> bytes:
    """A property stream: its header's bytes, then 16 bytes a property: its tag, flags, and 8 bytes of value."""
    return b"\x00" * header + b"".join(struct.pack("<II", tag, 2) + value.ljust(8, b"\x00") for tag, value in entries)


def message(subject: str = "", sender: tuple[str, str] | None = None, to: list | None = None, cc: list | None = None,
            date: datetime | None = None, text: str | None = None, html: str | None = None, rtf_only: bool = False,
            attachments: list | None = None, embedded: list | None = None, top: bool = True) -> dict:
    """A message's storage: its streams by name, and its recipients' and attachments' storages."""
    found: dict = {"__substg1.0_0037001F": _utf16(subject)}
    if sender:
        found["__substg1.0_0C1A001F"], found["__substg1.0_5D01001F"] = _utf16(sender[0]), _utf16(sender[1])
    if text is not None:
        found["__substg1.0_1000001F"] = _utf16(text)
    if html is not None:
        found["__substg1.0_10130102"] = html.encode("utf-8")
    if rtf_only:
        found["__substg1.0_10090102"] = b"LZFu-compressed RTF, which bridge-kit doesn't read"
    entries = [(0x00390040, _filetime(date))] if date else []
    found["__properties_version1.0"] = _properties(32 if top else 24, entries)
    for n, (kind, (name, address)) in enumerate([(1, r) for r in to or []] + [(2, r) for r in cc or []]):
        found[f"__recip_version1.0_#{n:08X}"] = {
            "__substg1.0_3001001F": _utf16(name), "__substg1.0_39FE001F": _utf16(address),
            "__properties_version1.0": _properties(8, [(0x0C150003, struct.pack("<I", kind))])}
    n = 0
    for name, data, mime, cid in attachments or []:
        storage = {"__substg1.0_3707001F": _utf16(name), "__substg1.0_37010102": data,
                   "__substg1.0_370E001F": _utf16(mime), "__properties_version1.0": _properties(8, [
                       (0x37050003, struct.pack("<I", 1))])}
        if cid:
            storage["__substg1.0_3712001F"] = _utf16(cid)
        found[f"__attach_version1.0_#{n:08X}"] = storage
        n += 1
    for inner in embedded or []:
        found[f"__attach_version1.0_#{n:08X}"] = {
            "__properties_version1.0": _properties(8, [(0x37050003, struct.pack("<I", 5))]),
            "__substg1.0_3701000D": message(**inner, top=False)}
        n += 1
    return found


def msg(path, **fields) -> object:
    path.write_bytes(compound(message(**fields)))
    return path


def compound(root: dict) -> bytes:
    """A compound file holding the storage `root`: streams under 4096 bytes in the mini stream, the rest in sectors."""
    entries: list[dict] = [{"name": "Root Entry", "type": 5, "children": []}]

    def add(storage: dict, index: int) -> None:
        for name, value in storage.items():
            entries.append({"name": name, "type": 1 if isinstance(value, dict) else 2,
                            "data": None if isinstance(value, dict) else value, "children": []})
            entries[index]["children"].append(len(entries) - 1)
            if isinstance(value, dict):
                add(value, len(entries) - 1)

    add(root, 0)
    mini, mini_fat, big = bytearray(), [], []
    for entry in entries:
        data = entry.get("data")
        if data is None:
            continue
        if len(data) < CUTOFF:
            start, count = len(mini) // MINI, max(1, -(-len(data) // MINI))
            entry["start"] = start if data else END
            mini += data.ljust(count * MINI, b"\x00") if data else b""
            mini_fat += [start + i + 1 for i in range(count - 1)] + [END] if data else []
        else:
            big.append(entry)
    directory_sectors = -(-len(entries) * 128 // SECTOR)
    mini_fat_sectors = -(-len(mini_fat) * 4 // SECTOR) if mini_fat else 0
    mini_sectors = -(-len(mini) // SECTOR)
    big_sectors = [-(-len(e["data"]) // SECTOR) for e in big]
    used = directory_sectors + mini_fat_sectors + mini_sectors + sum(big_sectors)
    fat_sectors = 1
    while fat_sectors * (SECTOR // 4) < used + fat_sectors:
        fat_sectors += 1

    fat: list[int] = [FATSECT] * fat_sectors
    def chain(count: int) -> int:
        start = len(fat)
        fat.extend([start + i + 1 for i in range(count - 1)] + [END])
        return start

    first_directory = chain(directory_sectors)
    first_mini_fat = chain(mini_fat_sectors) if mini_fat_sectors else END
    entries[0]["start"] = chain(mini_sectors) if mini_sectors else END
    entries[0]["size"] = len(mini)
    for entry, count in zip(big, big_sectors):
        entry["start"] = chain(count)
    fat += [FREE] * (fat_sectors * (SECTOR // 4) - len(fat))

    for entry in entries:  # each storage's children as a balanced tree, in the format's order
        children = sorted(entry["children"], key=lambda i: (len(entries[i]["name"]), entries[i]["name"].upper()))

        def tree(nodes: list[int]) -> int:
            if not nodes:
                return NONE
            middle = len(nodes) // 2
            entries[nodes[middle]]["left"], entries[nodes[middle]]["right"] = tree(nodes[:middle]), tree(
                nodes[middle + 1:])
            return nodes[middle]

        entry["child"] = tree(children)

    def directory_entry(entry: dict | None) -> bytes:
        if entry is None:
            return b"\x00" * 64 + struct.pack("<HBBIII", 0, 0, 0, NONE, NONE, NONE) + b"\x00" * 36 + \
                struct.pack("<IQ", 0, 0)
        name = _utf16(entry["name"]) + b"\x00\x00"
        size = entry.get("size", len(entry.get("data") or b""))
        start = entry.get("start", END) if entry["type"] != 1 else 0
        return (name.ljust(64, b"\x00") + struct.pack("<HBBIII", len(name), entry["type"], 1, entry.get("left", NONE),
                                                      entry.get("right", NONE), entry.get("child", NONE))
                + b"\x00" * 36 + struct.pack("<IQ", start, size))

    directory = b"".join(directory_entry(e) for e in entries)
    directory += directory_entry(None) * ((directory_sectors * SECTOR - len(directory)) // 128)
    header = (bytes.fromhex("d0cf11e0a1b11ae1") + b"\x00" * 16 + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6)
              + b"\x00" * 6 + struct.pack("<IIIIIIIII", 0, fat_sectors, first_directory, 0, CUTOFF, first_mini_fat,
                                          mini_fat_sectors, END, 0)
              + struct.pack("<109I", *(list(range(fat_sectors)) + [FREE] * (109 - fat_sectors))))
    body = struct.pack(f"<{len(fat)}I", *fat) + directory
    if mini_fat_sectors:
        body += struct.pack(f"<{len(mini_fat)}I", *mini_fat).ljust(mini_fat_sectors * SECTOR, b"\xff")
    body += bytes(mini).ljust(mini_sectors * SECTOR, b"\x00")
    for entry, count in zip(big, big_sectors):
        body += entry["data"].ljust(count * SECTOR, b"\x00")
    return header + body
