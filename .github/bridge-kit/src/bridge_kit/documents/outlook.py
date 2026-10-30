"""Outlook messages (`.msg`), on olefile: classic Outlook drags an email out as one. A `.msg` is a compound file of the
message's properties, one stream each (MS-OXMSG); the few bridge-kit needs are read into Python's own email message,
which `mail.py` then reads as it reads any email.

- The subject, the sender (name and SMTP address), the recipients (to and cc, by their recipient type), the date it
  was sent; the text body, the HTML one, or both.
- Attachments: a file's name, type and bytes; an image the HTML shows (`cid:`) as pasted into the body; an attached
  message as an email of its own.
- A message with only a rich-text (RTF) body is refused: Outlook saves it as HTML, which bridge-kit reads.
"""

from __future__ import annotations

import mimetypes
import struct
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from pathlib import Path

from bridge_kit.documents import Document, DocumentError, Options

SENT, DELIVERED = 0x00390040, 0x0E060040  # PR_CLIENT_SUBMIT_TIME, PR_MESSAGE_DELIVERY_TIME
RECIPIENT_TYPE, ATTACH_METHOD = 0x0C150003, 0x37050003
EMBEDDED = 5  # an attached message


def read_msg(path: Path, options: Options) -> Document:
    import olefile

    from bridge_kit.documents.mail import _email

    try:
        if not olefile.isOleFile(str(path)):
            raise DocumentError(f"{path.name} isn't an Outlook message inside")
        with olefile.OleFileIO(str(path)) as ole:
            message = _message(ole, [], top=True, name=path.name)
    except DocumentError:
        raise
    except Exception as e:  # a broken compound file raises any of a dozen kinds
        raise DocumentError(f"{path.name} can't be read as an Outlook message ({type(e).__name__}): save it again "
                            "from Outlook, or as HTML (.htm)") from None
    return _email(message, path, options)


def _message(ole, prefix: list[str], top: bool, name: str) -> EmailMessage:
    def stream(entry: str, under: list[str] | None = None) -> bytes | None:
        path = (prefix if under is None else under) + [entry]
        return ole.openstream(path).read() if ole.exists("/".join(path)) else None

    def text(prop: str, under: list[str] | None = None) -> str | None:
        for kind, codec in (("001F", "utf-16-le"), ("001E", "cp1252")):
            data = stream(f"__substg1.0_{prop}{kind}", under)
            if data is not None:
                return data.decode(codec, errors="replace").rstrip("\x00")
        return None

    properties = _properties(stream("__properties_version1.0"), 32 if top else 24)
    message = EmailMessage()
    message["Subject"] = text("0037") or ""
    sender = _address(text("0C1A"), text("5D01") or text("0C1F"))
    if sender:
        message["From"] = sender
    recipients = {1: [], 2: []}
    for storage in _children(ole, prefix, "__recip_version1.0_#"):
        kind = _number(_properties(stream("__properties_version1.0", storage), 8).get(RECIPIENT_TYPE))
        if kind in recipients and (found := _address(text("3001", storage), text("39FE", storage)
                                                     or text("3003", storage))):
            recipients[kind].append(found)
    for header, kind, shown in (("To", 1, "0E04"), ("Cc", 2, "0E03")):
        found = ", ".join(recipients[kind]) or text(shown)
        if found:
            message[header] = found
    sent = properties.get(SENT) or properties.get(DELIVERED)
    if sent:
        message["Date"] = format_datetime(_filetime(sent))

    plain = text("1000")
    raw = stream("__substg1.0_10130102")
    html = _decoded(raw) if raw is not None else text("1013")
    if plain is None and html is None and stream("__substg1.0_10090102") is not None:
        raise DocumentError(f"{name} has only a rich-text (RTF) body, which bridge-kit doesn't read: save it from "
                            "Outlook as HTML (.htm)")
    if plain is not None:
        message.set_content(plain)
        if html is not None:
            message.add_alternative(html, subtype="html")
    elif html is not None:
        message.set_content(html, subtype="html")
    else:
        message.set_content("")

    for storage in _children(ole, prefix, "__attach_version1.0_#"):
        method = _number(_properties(stream("__properties_version1.0", storage), 8).get(ATTACH_METHOD))
        if method == EMBEDDED:
            message.add_attachment(_message(ole, storage + ["__substg1.0_3701000D"], top=False, name=name))
            continue
        data = stream("__substg1.0_37010102", storage)
        if data is None:
            continue  # an attachment by reference or an OLE object: nothing to keep
        filename = text("3707", storage) or text("3704", storage) or "attachment"
        mime = text("370E", storage) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        maintype, _, subtype = mime.partition("/")
        cid = text("3712", storage)
        body = message.get_body(("html",))
        if cid and body is not None and f"cid:{cid}" in (html or ""):
            body.add_related(data, maintype, subtype or "octet-stream", cid=f"<{cid}>", filename=filename)
        else:
            message.add_attachment(data, maintype, subtype or "octet-stream", filename=filename)
    return message


def _address(name: str | None, address: str | None) -> str:
    """"Name <address>", or the name alone when the address is none, or an Exchange name (`/O=…`), not an email's."""
    if address and not address.startswith("/"):
        return formataddr((name or "", address))
    return name or ""


def _children(ole, prefix: list[str], start: str) -> list[list[str]]:
    """The storages directly under `prefix` whose names start so, in order."""
    found = {tuple(path[:len(prefix) + 1]) for path in ole.listdir(streams=True, storages=True)
             if len(path) > len(prefix) and path[:len(prefix)] == prefix and path[len(prefix)].startswith(start)}
    return [list(path) for path in sorted(found)]


def _properties(data: bytes | None, header: int) -> dict[int, bytes]:
    """A property stream's fixed-size values, by their tag: 16 bytes each after the header."""
    if not data:
        return {}
    return {struct.unpack("<I", data[i:i + 4])[0]: data[i + 8:i + 16] for i in range(header, len(data) - 15, 16)}


def _number(value: bytes | None) -> int | None:
    return struct.unpack("<i", value[:4])[0] if value else None


def _filetime(value: bytes) -> datetime:
    ticks = int.from_bytes(value, "little")  # 100 nanoseconds since 1601
    return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)


def _decoded(data: bytes) -> str:
    try:
        return data.decode("utf-8").rstrip("\x00")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace").rstrip("\x00")
