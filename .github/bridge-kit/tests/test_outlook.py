"""Outlook messages (`.msg`) as Markdown: written here by a compound-file writer of our own (fixtures/msg.py), made-up
content only. Its headers, its bodies, its attachments and an attached message, read as any email is; one with only an
RTF body refused."""

from datetime import datetime, timezone

import pytest

from bridge_kit.cli import main
from bridge_kit.documents import DocumentError, read_document
from bridge_kit.markdown import read_markdown
from fixtures.msg import msg

SENT = datetime(2026, 10, 27, 14, 30, tzinfo=timezone.utc)
SCREENSHOT = b"\x89PNG\r\n\x1a\n" + b"\x01" * 5000


def reply(path, **fields):
    defaults = dict(subject="Re: VAT numbers from the upstream", sender=("Anna Example", "anna.example@example.com"),
                    to=[("Bo Example", "bo@example.com")], cc=[("BA team", "ba-team@example.com")], date=SENT,
                    text="Hi Bo,\n\nThey send VAT numbers with spaces; trim them.\n")
    return msg(path, **{**defaults, **fields})


def test_a_message_reads_as_an_email(tmp_path):
    document = read_document(reply(tmp_path / "reply.msg"))

    assert (document.kind, document.title) == ("email", "Re: VAT numbers from the upstream")
    assert document.markdown == (
        "# Re: VAT numbers from the upstream\n\n"
        "`reply.msg`: an email.\n\n"
        "From: Anna Example <anna.example@example.com>\n"
        "To: Bo Example <bo@example.com>\n"
        "Cc: BA team <ba-team@example.com>\n"
        "Date: Tue, 27 Oct 2026 14:30:00 +0000\n"
        "Subject: Re: VAT numbers from the upstream\n\n"
        "Hi Bo,\n\n"
        "They send VAT numbers with spaces; trim them.\n")


def test_its_attachments_and_an_attached_message(tmp_path):
    path = reply(tmp_path / "reply.msg", attachments=[("rough.csv", b"Field,Rule\nvatNo,trim\n", "text/csv", None),
                                                      ("spec.pdf", b"%PDF-1.4" + b"\x00" * 5000, "application/pdf",
                                                       None)],
                 embedded=[dict(subject="Spec v2", sender=("Upstream team", "up@example.com"),
                                text="The spec is attached.\n")])

    document = read_document(path)

    assert list(document.attachments) == ["rough.csv", "spec.pdf", "Spec v2.eml"]
    assert document.attachments["spec.pdf"] == b"%PDF-1.4" + b"\x00" * 5000  # from the sectors, not the mini stream
    assert b"Subject: Spec v2" in document.attachments["Spec v2.eml"]


def test_an_html_body_with_a_pasted_screenshot(tmp_path):
    path = reply(tmp_path / "reply.msg", text="Their screen: [cid:shot1]",
                 html="<p>Their screen:</p><img src='cid:shot1' alt='The upstream screen'>",
                 attachments=[("image001.png", SCREENSHOT, "image/png", "shot1")])

    document = read_document(path)

    assert "Their screen:\n\n[Image 1: The upstream screen]" in document.markdown
    assert document.images == {"image-1.png": SCREENSHOT} and document.attachments == {}


def test_an_exchange_address_is_left_out(tmp_path):
    path = reply(tmp_path / "reply.msg", sender=("Anna Example", "/O=EXAMPLE/OU=EXCHANGE/CN=RECIPIENTS/CN=ANNA"))

    assert 'From: "Anna Example"\n' in read_document(path).markdown  # a name alone, as an email header writes it


@pytest.mark.parametrize("content, message", [
    (b"not a compound file", "reply.msg isn't an Outlook message inside"),
])
def test_what_isn_t_a_message_is_refused(tmp_path, content, message):
    (tmp_path / "reply.msg").write_bytes(content)

    with pytest.raises(DocumentError, match=message):
        read_document(tmp_path / "reply.msg")


def test_a_message_with_only_an_rtf_body_is_refused(tmp_path):
    with pytest.raises(DocumentError, match="reply.msg has only a rich-text .RTF. body, which bridge-kit doesn't read: "
                                            r"save it from Outlook as HTML \(.htm\)"):
        read_document(reply(tmp_path / "reply.msg", text=None, rtf_only=True))


def test_a_message_kept_as_an_input_with_its_attachments(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "ba-repo"
    (repo / ".github" / "bridge-kit").mkdir(parents=True)
    monkeypatch.setenv("BRIDGE_KIT_REPO_ROOT", str(repo))
    path = reply(tmp_path / "reply.msg", attachments=[("rough.csv", b"Field,Rule\nvatNo,trim\n", "text/csv", None)])

    assert main(["inputs", "add", str(path), "--work-item", "REQ-341"]) == 0

    assert capsys.readouterr().out == ("Added work/REQ-341/inputs/01-reply.md: Re: VAT numbers from the upstream\n"
                                       "  Added work/REQ-341/inputs/02-rough.md: rough, attached to it\n")
    header = read_markdown((repo / "work/REQ-341/inputs/01-reply.md").read_text(encoding="utf-8")).front_matter
    assert (header["kind"], header["source"], header["raw"]) == ("email", "file:reply.msg",
                                                                 ".work/sources/REQ-341/01-reply.msg")
