"""Emails (`.eml`), on Python's own email package.

- From, to, cc, date and subject, then the body: its text part, as written, with its quoted replies; or its HTML
  (`html.py`) when there's no text part, or when the HTML shows images the text part can't (a screenshot pasted
  into the email).
- Images pasted into the body kept as the email's images, marked `[Image N]` where they are; those under 4 KB
  (signatures' icons, tracking pixels) left out.
- Attachments listed, and kept apart (`Document.attachments`), an attached email as `.eml`: `bridge-kit inputs add`
  adds each one it reads as an input of its own.
- The addresses in its headers aren't counted as personal data: an email has them by nature. Its body's are.
"""

from __future__ import annotations

import mimetypes
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

from bridge_kit.documents import Document, DocumentError, Options, personal
from bridge_kit.documents.html import IMAGE_TYPES, Images, data_url, to_markdown

HEADERS = ("From", "To", "Cc", "Date", "Subject")
SMALLEST = 4 * 1024  # a pasted image under this many bytes is an icon or a tracking pixel


def read_email(path: Path, options: Options) -> Document:
    try:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    except Exception as e:  # the parser is lenient; what it can't parse at all isn't an email
        raise DocumentError(f"{path.name} can't be read as an email ({type(e).__name__})") from None
    if not any(message.get(header) for header in HEADERS):
        raise DocumentError(f"{path.name} has no From, To, Date or Subject: it isn't an email inside")
    return _email(message, path, options)


def _email(message: EmailMessage, path: Path, options: Options) -> Document:
    images = Images()
    pasted = {_cid(part): part for part in message.walk()
              if part.get("Content-ID") and part.get_content_maintype() == "image"}
    used: set[str] = set()

    def image(src: str, alt: str) -> str | None:
        if src.lower().startswith("cid:"):
            part = pasted.get(src[4:].strip("<>"))
            if part is None:
                return f"[Image: {alt}]" if alt else None
            used.add(src[4:].strip("<>"))
            data = part.get_payload(decode=True) or b""
            suffix = IMAGE_TYPES.get(part.get_content_subtype().lower())
            if len(data) < SMALLEST or suffix is None:
                return None
            return images.add(data, suffix, alt)
        if found := data_url(src):
            return images.add(*found, alt)
        return f"[Image: {alt}]" if alt else None

    warnings: list[str] = []
    plain = message.get_body(("plain",))
    html = message.get_body(("html",))
    html_text = _text(html) if html is not None else ""
    if html is not None and (plain is None or re.search(r"""src\s*=\s*["']?cid:""", html_text, re.IGNORECASE)):
        body, _, found = to_markdown(html_text, options, image)
        warnings += [w.replace("Its text", "Its body", 1) for w in found]
    elif plain is not None:
        body = "\n".join(line.rstrip() for line in _text(plain).replace("\r\n", "\n").split("\n")).strip()
        if warning := personal.warning("Its body", [body]):
            warnings.append(warning)
    else:
        body = ""

    attachments: dict[str, bytes] = {}
    listed = []
    for n, part in enumerate(message.iter_attachments(), 1):
        if _cid(part) in used or (part.get_content_disposition() == "inline" and part.get_content_maintype() == "image"
                                  and not part.get_filename()):
            continue  # shown in the body, or an unnamed one pasted in and not shown
        name, data = _attachment(part, n)
        name = _unique(name, attachments)
        attachments[name] = data
        listed.append(f"- `{name}` ({part.get_content_type()}, {_size(len(data))})")

    subject = " ".join(str(message.get("Subject") or "").split())
    title = subject or path.stem
    lines = [f"# {title}", "", f"`{path.name}`: an email" + (f", with {len(attachments)} attachment(s)"
                                                            if attachments else "") + ".", ""]
    lines += [f"{header}: {' '.join(str(message.get(header)).split())}" for header in HEADERS if message.get(header)]
    lines += ["", body or "_No text in its body._"]
    if listed:
        lines += ["", "## Attachments", ""] + listed
    if images.lines:
        lines += ["", "## Images", ""] + images.lines
    if attachments:
        warnings.insert(0, f"{path.name} has {len(attachments)} attachment(s), listed at the end: bridge-kit inputs "
                           "add adds each it reads as an input of its own")
    if images.files:
        warnings.append(f"{path.name} has {len(images.files)} image(s) in its body, which bridge-kit can't read: each "
                        "is marked [Image N]; bridge-kit inputs add keeps them, for an agent to describe any that "
                        "matters")
    return Document("email", title, "\n".join(lines).rstrip() + "\n", warnings, images.files, attachments)


def _text(part: EmailMessage) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeError):  # a charset Python doesn't know, or text that isn't in it
        return (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")


def _cid(part: EmailMessage) -> str:
    return str(part.get("Content-ID") or "").strip().strip("<>")


def _attachment(part: EmailMessage, n: int) -> tuple[str, bytes]:
    if part.get_content_type() == "message/rfc822":
        attached = part.get_content()
        subject = re.sub(r"[^\w .-]+", "", str(attached.get("Subject") or "")).strip()[:60]
        return f"{subject or f'attached-email-{n}'}.eml", attached.as_bytes(policy=policy.default)
    name = Path(str(part.get_filename() or "")).name  # a name only, never a path
    if not name:
        name = f"attachment-{n}{mimetypes.guess_extension(part.get_content_type()) or ''}"
    data = part.get_payload(decode=True)
    if data is None:
        content = part.get_content()
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    return name, data


def _unique(name: str, taken: dict) -> str:
    stem, suffix = Path(name).stem, Path(name).suffix
    found, n = name, 1
    while found in taken:
        n += 1
        found = f"{stem}-{n}{suffix}"
    return found


def _size(n: int) -> str:
    return f"{n} bytes" if n < 1024 else f"{n // 1024} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"
