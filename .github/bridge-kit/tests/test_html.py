"""HTML pages as Markdown: a saved wiki page, a table of data and a table for layout, images from a data URL and from
beside a page Outlook saved, charsets. Made-up content only."""

import base64

import pytest

from bridge_kit.documents import read_document
from bridge_kit.documents.html import to_markdown
from bridge_kit.documents import Options

PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64


def page(tmp_path, body: str, name: str = "page.html", head: str = "<title>Onboarding checklist</title>",
         encoding: str = "utf-8"):
    path = tmp_path / name
    path.write_bytes(f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>".encode(encoding))
    return path


def test_a_saved_wiki_page_reads_as_markdown(tmp_path):
    body = ("<script>track()</script><style>p { color: red }</style>"
            "<h1>Onboarding an upstream</h1><p>Before the &amp; first   run:<br>check its spec.</p>"
            "<ol start='3'><li>Get the spec jar<ul><li>From Nexus</li><li>Its <a href='https://example.com/v2'>v2"
            "</a></li></ul></li><li>Ask about <s>dates</s> time zones</ol>"
            "<h2>Notes</h2><blockquote><p>Dates are UTC.</p><p>Always.</p></blockquote>"
            "<pre>vatNo  -> trim\nctry   -> lookup</pre><hr><div hidden>internal</div>"
            "<p style='display: none'>also hidden</p><p>Write to <a href='mailto:team@example.com'>"
            "team@example.com</a></p>")

    document = read_document(page(tmp_path, body))

    assert (document.kind, document.title) == ("html", "Onboarding checklist")
    assert document.markdown == (
        "# Onboarding checklist\n\n"
        "`page.html`: an HTML page.\n\n"
        "## Onboarding an upstream\n\n"
        "Before the & first run:\ncheck its spec.\n\n"
        "- 3. Get the spec jar\n"
        "  - From Nexus\n"
        "  - Its [v2](https://example.com/v2)\n"
        "- 4. Ask about ~~dates~~ time zones\n\n"
        "### Notes\n\n"
        "> Dates are UTC.\n\n"
        "> Always.\n\n"
        "```\nvatNo  -> trim\nctry   -> lookup\n```\n\n"
        "---\n\n"
        "Write to team@example.com\n")
    assert document.warnings == ["Its text has values that look like personal data (1 email address): check before "
                                 "committing it"]


def test_a_table_of_data_is_a_table_and_one_for_layout_is_its_cells(tmp_path):
    body = ("<table><tr><td><p>Hello Bo,</p><p>The rules:</p>"
            "<table><tr><th>Field</th><th>Rule</th><th>Notes</th></tr>"
            "<tr><td rowspan='2'>vatNo</td><td colspan='2'>trim | upper</td></tr>"
            "<tr><td>no spaces</td><td>ISO</td></tr></table></td></tr>"
            "<tr><td>Regards, Anna</td></tr></table>")

    text = read_document(page(tmp_path, body)).markdown

    assert text.endswith(
        "`page.html`: an HTML page.\n\n"
        "Hello Bo,\n\n"
        "The rules:\n\n"
        "Table 1:\n\n"
        "| Row | Field | Rule | Notes |\n"
        "|---|---|---|---|\n"
        "| 2 | vatNo | trim \\| upper | trim \\| upper |\n"
        "| 3 | vatNo | no spaces | ISO |\n\n"
        "Regards, Anna\n")


def test_images_from_a_data_url_and_beside_a_page_outlook_saved(tmp_path):
    (tmp_path / "reply_files").mkdir()
    (tmp_path / "reply_files" / "image001.png").write_bytes(PNG)
    (tmp_path / "secret.png").write_bytes(PNG + b"other")
    data = base64.b64encode(PNG + b"data").decode()
    body = (f"<p><img src='reply_files/image001.png' alt='The upstream screen'></p>"
            f"<p><img src='data:image/png;base64,{data}'></p>"
            "<p><img src='https://example.com/logo.png' alt='Logo'><img src='https://example.com/pixel.gif'></p>"
            "<p><img src='../secret.png' alt='Outside'><img src='reply_files/image001.png' alt='Again'></p>")

    document = read_document(page(tmp_path / "reply_files" / ".." , body, name="reply.htm"))

    assert ("[Image 1: The upstream screen]\n\n[Image 2]\n\n[Image: Logo]\n\n[Image: Outside] [Image 1: Again]\n\n"
            "## Images\n\n- Image 1: `image-1.png`: The upstream screen\n- Image 2: `image-2.png`\n") in (
        document.markdown)
    assert document.images == {"image-1.png": PNG, "image-2.png": PNG + b"data"}


def test_a_page_s_declared_charset_and_one_that_isn_t_utf_8(tmp_path):
    declared = page(tmp_path, "<p>Café règles</p>", name="declared.htm",
                    head='<meta http-equiv="Content-Type" content="text/html; charset=windows-1252">',
                    encoding="cp1252")
    undeclared = page(tmp_path, "<p>Café</p>", name="undeclared.htm", head="", encoding="cp1252")

    assert "Café règles" in read_document(declared).markdown and read_document(declared).warnings == []
    assert read_document(undeclared).warnings == ["undeclared.htm isn't UTF-8: read as Windows-1252, so check its "
                                                  "accented letters"]


@pytest.mark.parametrize("head, body, title", [
    ("", "<h2>Ways of working</h2><p>Tuesdays</p>", "Ways of working"),
    ("", "<p>Tuesdays</p>", "notes"),
])
def test_a_title_from_the_first_heading_or_the_file_s_name(tmp_path, head, body, title):
    assert read_document(page(tmp_path, body, name="notes.html", head=head)).title == title


def test_unclosed_paragraphs_and_items_still_break_where_they_should():
    markdown, _, _ = to_markdown("<p>One<p>Two<ul><li>a<li>b</ul>Three", Options())

    assert markdown == "One\n\nTwo\n\n- a\n- b\n\nThree"
