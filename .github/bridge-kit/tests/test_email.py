"""Emails as Markdown, and their attachments as inputs of their own: emails built with Python's email package, made-up
content only. Its headers, its text or its HTML with a pasted screenshot, quoted replies, attachments listed and added,
an image or an unknown kind not added."""

from email.message import EmailMessage

import pytest

from bridge_kit.cli import main
from bridge_kit.documents import DocumentError, read_document
from bridge_kit.markdown import read_markdown

SCREENSHOT = b"\x89PNG\r\n\x1a\n" + b"\x01" * 5000
ICON = b"\x89PNG\r\n\x1a\n" + b"\x02" * 100


def email(subject: str = "Re: VAT numbers from the upstream", text: str | None = None, html: str | None = None,
          related: dict | None = None) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Anna Example <anna.example@example.com>"
    message["To"] = "Bo Example <bo@example.com>"
    message["Cc"] = "ba-team@example.com"
    message["Date"] = "Tue, 27 Oct 2026 14:30:00 +0000"
    message["Subject"] = subject
    if text is not None:
        message.set_content(text)
    if html is not None:
        if text is None:
            message.set_content(html, subtype="html")
        else:
            message.add_alternative(html, subtype="html")
        body = message.get_body(("html",))
        for cid, data in (related or {}).items():
            body.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>")
    return message


def save(tmp_path, message: EmailMessage, name: str = "reply.eml"):
    path = tmp_path / name
    path.write_bytes(bytes(message))
    return path


def test_a_plain_email_reads_with_its_headers_and_quoted_reply(tmp_path):
    message = email(text="Hi Bo,\n\nThey send VAT numbers with spaces; trim them.\n\n> On 26 Oct, Bo wrote:\n"
                         "> Do they send spaces?\n")

    document = read_document(save(tmp_path, message))

    assert (document.kind, document.title) == ("email", "Re: VAT numbers from the upstream")
    assert document.markdown == (
        "# Re: VAT numbers from the upstream\n\n"
        "`reply.eml`: an email.\n\n"
        "From: Anna Example <anna.example@example.com>\n"
        "To: Bo Example <bo@example.com>\n"
        "Cc: ba-team@example.com\n"
        "Date: Tue, 27 Oct 2026 14:30:00 +0000\n"
        "Subject: Re: VAT numbers from the upstream\n\n"
        "Hi Bo,\n\n"
        "They send VAT numbers with spaces; trim them.\n\n"
        "> On 26 Oct, Bo wrote:\n"
        "> Do they send spaces?\n")
    assert document.warnings == []  # the headers' addresses aren't counted


def test_the_html_is_read_when_it_shows_a_pasted_screenshot(tmp_path):
    html = ("<p>Hi Bo,</p><p>Their screen, below:</p><img src='cid:shot1' alt='The upstream screen'>"
            "<p>Write to <a href='mailto:ops@example.com'>ops</a>.</p><img src='cid:logo'>")
    message = email(text="Hi Bo,\n\nTheir screen, below: [cid:shot1]\n", html=html,
                    related={"shot1": SCREENSHOT, "logo": ICON})

    document = read_document(save(tmp_path, message))

    assert document.markdown.endswith(
        "Subject: Re: VAT numbers from the upstream\n\n"
        "Hi Bo,\n\n"
        "Their screen, below:\n\n"
        "[Image 1: The upstream screen]\n\n"
        "Write to [ops](mailto:ops@example.com).\n\n"
        "## Images\n\n"
        "- Image 1: `image-1.png`: The upstream screen\n")
    assert document.images == {"image-1.png": SCREENSHOT}  # the icon, under 4 KB, is left out
    assert document.warnings == [
        "Its body has values that look like personal data (1 email address): check before committing it",
        "reply.eml has 1 image(s) in its body, which bridge-kit can't read: each is marked [Image N]; bridge-kit "
        "inputs add keeps them, for an agent to describe any that matters"]


def test_an_html_only_email(tmp_path):
    document = read_document(save(tmp_path, email(html="<p>Only <b>HTML</b> here.</p>")))

    assert document.markdown.endswith("Subject: Re: VAT numbers from the upstream\n\nOnly HTML here.\n")


def with_attachments() -> EmailMessage:
    message = email(text="The files are attached.\n")
    message.add_attachment(b"Field,Rule\nvatNo,trim\n", maintype="text", subtype="csv",
                           filename="../../rough mapping.csv")
    forwarded = email(subject="Spec v2", text="The spec is attached.\n")
    message.add_attachment(forwarded)
    message.add_attachment(SCREENSHOT, maintype="image", subtype="png", filename="whiteboard.png")
    message.add_attachment(b"PK\x03\x04", maintype="application", subtype="zip", filename="bundle.zip")
    return message


def test_attachments_are_listed_and_kept_apart(tmp_path):
    document = read_document(save(tmp_path, with_attachments()))

    listed = document.markdown.split("## Attachments\n\n")[1].splitlines()
    assert [line.split(" (")[0] for line in listed] == [
        "- `rough mapping.csv`", "- `Spec v2.eml`", "- `whiteboard.png`", "- `bundle.zip`"]  # a name, never a path
    assert (listed[0], listed[2]) == ("- `rough mapping.csv` (text/csv, 22 bytes)", "- `whiteboard.png` (image/png, 4 KB)")
    assert list(document.attachments) == ["rough mapping.csv", "Spec v2.eml", "whiteboard.png", "bundle.zip"]
    assert document.warnings[0] == ("reply.eml has 4 attachment(s), listed at the end: bridge-kit inputs add adds each "
                                    "it reads as an input of its own")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    return repo


def test_an_email_s_attachments_become_inputs_of_their_own(tmp_path, repo, capsys):
    path = save(tmp_path, with_attachments())

    assert main(["inputs", "add", str(path), "--work-item", "REQ-341"]) == 0

    out = capsys.readouterr().out
    assert out == (
        "Added work/REQ-341/inputs/01-reply.md: Re: VAT numbers from the upstream\n"
        "  Added work/REQ-341/inputs/02-rough-mapping.md: rough mapping, attached to it\n"
        "  Added work/REQ-341/inputs/03-spec-v2.md: Spec v2, attached to it\n"
        "  Not added: whiteboard.png is an image: read it, then add it with --description and --by, from "
        ".work/sources/REQ-341/01-reply-attachments/whiteboard.png\n"
        "  Not added: bridge-kit doesn't read .zip files: it reads .csv, .docx, .eml, .gif, .htm, .html, .jpeg, .jpg, "
        ".markdown, .md, .msg, .pdf, .png, .pptx, .tsv, .txt, .webp, .xlsm, .xlsx\n")
    email_header = read_markdown((repo / "work/REQ-341/inputs/01-reply.md").read_text(encoding="utf-8")).front_matter
    assert email_header["attachments"] == ".work/sources/REQ-341/01-reply-attachments"
    for file in ("02-rough-mapping.md", "03-spec-v2.md"):
        header = read_markdown((repo / "work/REQ-341/inputs" / file).read_text(encoding="utf-8")).front_matter
        assert header["attached_to"] == "work/REQ-341/inputs/01-reply.md"

    assert main(["inputs", "add", str(path), "--work-item", "REQ-341"]) == 0
    assert capsys.readouterr().out == "Already there, unchanged: work/REQ-341/inputs/01-reply.md\n"


def test_emails_attached_three_deep_stop_there(tmp_path, repo, capsys):
    message = email(subject="Level 0", text="Zero\n")
    inner = email(subject="Level 1", text="One\n")
    deeper = email(subject="Level 2", text="Two\n")
    deeper.add_attachment(email(subject="Level 3", text="Three\n"))
    inner.add_attachment(deeper)
    message.add_attachment(inner)

    assert main(["inputs", "add", str(save(tmp_path, message)), "--work-item", "REQ-341"]) == 0

    assert capsys.readouterr().out == (
        "Added work/REQ-341/inputs/01-reply.md: Level 0\n"
        "  Added work/REQ-341/inputs/02-level-1.md: Level 1, attached to it\n"
        "    Added work/REQ-341/inputs/03-level-2.md: Level 2, attached to it\n"
        "      Not added: Level 3.eml is attached three emails deep: add it yourself, from "
        ".work/sources/REQ-341/03-level-2-attachments/Level 3.eml\n")


def test_a_file_with_no_email_headers_is_refused(tmp_path):
    path = tmp_path / "notes.eml"
    path.write_text("Just some notes, not an email.\n", encoding="utf-8")

    with pytest.raises(DocumentError, match="notes.eml has no From, To, Date or Subject: it isn't an email inside"):
        read_document(path)
