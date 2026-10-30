---
name: document-reading
description: How to read the documents a BA brings with BRIDGE - Excel workbooks, Word documents, PDFs, PowerPoint decks, emails, saved web pages, CSV and text - as Markdown, and keep one as a work item's input; how to cite a place in one; and how to read an image or a scanned page yourself and keep what it shows. Use when a BA gives, attaches or points to a file, or a work item starts from one.
metadata:
  version: 0.1.0
  owner: ba-team
---

# Reading documents

BRIDGE turns a document into Markdown you can read. Every command below goes through the launcher,
`.github/bridge-kit/bin/bridge-kit`. Run each command on its own, never in a loop, a pipe or a chain: tool approvals
match a command by how it starts. Name the file by the path the BA gives, or by its path in the workspace.

## 1. Which command reads what

| The BA wants | Run |
|---|---|
| To know what a document says, before keeping it | `bridge-kit doc read <file>` |
| A document kept for a work item | `bridge-kit inputs add <file> --work-item <id>`, then read the input it names |
| Only some sheets of a workbook | `--sheet <name>`, once for each sheet, on either command |
| A long sheet in full (by default a table of over 500 rows shows its first 200) | `--rows all`, or `--rows <n>` |
| A sheet of real records: what its columns are, not what's in them | `--headers-only` |
| A PDF made of tables, whose columns run together | `--layout` |
| An image, or a scanned page | Read it yourself: section 4 |

It reads Excel (`.xlsx`, `.xlsm`), Word (`.docx`), PDF, PowerPoint (`.pptx`), emails (`.eml`), saved web pages
(`.html`, `.htm`), CSV and TSV, and text and Markdown. Keeping a document makes `work/<id>/inputs/NN-<name>.md`; from
then on read that file, not the original or the chat.

## 2. What the Markdown keeps, and how to cite it

Cite every point you take from a document by where it is, so the BA can find it:

| Document | What you get | Cite |
|---|---|---|
| Excel, CSV | Each sheet a table under its heading row; each row's number, each column's letter (`Rule (C)`); rows above the table listed | `Mapping!C12`, or the sheet, row 12 |
| Word | Headings with their numbers, lists with their labels, `Table N:` with row numbers | Section 3.2, Table 2 row 4 |
| PDF | Each page under `## Page N`, with its own label when it has another | Page 7 (labelled 5) |
| PowerPoint | Each slide under `## Slide N: <title>`, its speaker notes under it | Slide 4 |
| Email | From, to, date and subject, then its body | The email of 27 October from Anna Example |

What BRIDGE marks, and what you do with it:

- **Struck-through text**, `~~like this~~`: often a row or a rule that was dropped. Don't take it as current; ask the
  BA if it matters.
- **Coloured cells and text** (listed under a sheet's table): they mean something only the BA knows, unless the sheet
  has a legend. Ask.
- **Hidden** sheets, rows and columns, marked `(hidden)`: read, but say when you rely on one.
- **Comments**, `[comment N]` and the list at the end: often open questions. Say which bear on your work.
- **Tracked changes** in Word, shown as if accepted and listed at the end: ask the BA whether they stand.
- **Formulas**, listed under a sheet's table: a formula may be the BA's rule.
- **Footnotes**, `[^N]`, listed at the end.

## 3. Pass the warnings on

`doc read` prints its warnings after the Markdown, as `Warning:` lines; `inputs add` prints them too and keeps them in
the input's header, under `warnings`. Tell the BA each one that bears on the work, in your own words. Most of all:

- **Personal data**: values that look like email addresses, IBANs or card numbers, by column, page or slide. Never
  repeat the values. Ask the BA whether the input may be kept, or to add it again with `--headers-only`.
- **Pages or slides with no text**, and **images**: section 4.
- **Attachments** of an email: `inputs add` adds each one it reads as an input of its own, listed under the email,
  and says which it didn't add and why.

## 4. Images and scanned pages

BRIDGE can't read an image; you can, when your chat takes images. In VS Code, open the image file; in the Copilot
CLI, attach its path; a PDF can be read the same way. If you can't see images here, ask the BA to attach it to the
chat or to tell you what it shows.

Where images come from:

- A file the BA gives (`.png`, `.jpg`, `.gif`, `.webp`).
- Images in a document, marked `[Image N: <alt text>]`. Keeping the document puts them in the folder its input's
  header names under `images:`, as `image-N.<ext>`. Read only those that bear on the work.
- A PDF's pages with no text: a scan, or pictures.

Write down what it shows:

- every piece of text in it, exactly as written;
- a table as a Markdown table;
- a diagram's boxes and arrows as a list: `Upstream → Collector: nightly file`;
- `[unreadable]` where you can't read it.

Nothing guessed and nothing explained: what it shows, not what it means. Write it to `.work/tmp/<image's name>.md`,
then keep it with the image:

```text
.github/bridge-kit/bin/bridge-kit inputs add <image> --work-item <id> --description .work/tmp/<image's name>.md --by <your name>
```

For a scanned PDF, add the PDF the same way, its description saying which page shows what. Tell the BA to check your
description before the input is committed: it's your reading, not the document's text.

## 5. When it fails

The commands say why in one line:

- **Exit 1: the file can't be read.** An old format (`.doc`, `.xls`, `.ppt`: save it as `.docx`, `.xlsx`, `.pptx`),
  an Outlook message (`.msg`: save it from Outlook as HTML or Text Only), a file locked by a password or a
  sensitivity label (save a copy without it), or one that isn't what its extension says. Show the BA the line and
  wait for the file.
- **Exit 2: a wrong work item, file or description.** Correct it and run the command again.

## 6. Never

- **Never open an Office file, a PDF or an email with a file-reading tool or a script**, and never unzip or convert
  one with another tool: read it only through BRIDGE. Images are the exception: you read those yourself.
- **Never rewrite an input or paste a document's text into another file**: refer to the input by its path.
- **Never repeat personal data** from a document in the chat or in what you write.
- **Never commit an input the BA hasn't looked at**: a document may hold data that mustn't be committed.
