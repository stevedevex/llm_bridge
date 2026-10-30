"""The templates a BA fills in: the impact analysis's example reads as the package check reads impact.md; the test case
template's header fits its schema, and its example follows it (its sections, and only the data it defines)."""

import json
import re

import yaml
from conftest import KIT

from bridge_kit.markdown import read_markdown
from bridge_kit.schema import problems
from bridge_kit.validators.package import load_impact

TEMPLATES = KIT.parents[1] / "templates"
TEST_CASE = (TEMPLATES / "test-case.md").read_text(encoding="utf-8")
EXAMPLE = (TEMPLATES / "test-case.example.md").read_text(encoding="utf-8")
SCHEMA = json.loads((TEMPLATES / "test-case.schema.json").read_text(encoding="utf-8"))


def test_the_impact_template_s_example_reads_as_impact_md_does(tmp_path):
    text = (TEMPLATES / "impact.md").read_text(encoding="utf-8")
    example = text.split("````markdown\n", 1)[1].split("\n````", 1)[0]
    (tmp_path / "impact.md").write_text(example, encoding="utf-8")

    impact = load_impact(tmp_path / "impact.md")

    assert list(impact.components) == ["<a component, as architecture/components.yaml names it>"]
    assert impact.cited == {"mappings/upstream-1/get-customer.md", "work/REQ-101/model-change.md"}
    assert impact.questions is not None


def template_sections() -> list[tuple[str, bool]]:
    """The body's sections as the template's table gives them: (heading, required)."""
    table = next(t for s in read_markdown(TEST_CASE).sections if s.heading == "Body" for t in s.tables)
    return [(re.fullmatch(r"`## (.+)`", cells[1]).group(1), cells[2] in ("Yes", "Empty to approve"))
            for _, cells in table.rows]


def test_the_test_case_template_s_header_fits_its_schema():
    header = TEST_CASE.split("```yaml\n---\n", 1)[1].split("\n---\n```", 1)[0]

    assert problems(yaml.safe_load(header), SCHEMA) == []


def test_the_schema_refuses_a_case_that_proves_nothing():
    header = read_markdown(EXAMPLE).front_matter

    assert problems({**header, "verifies": []}, SCHEMA) == ["verifies needs at least 1 item(s)"]
    assert problems({**header, "environment": "prod"}, SCHEMA) == ["environment must be one of dev, sit"]


def test_the_example_fits_the_schema_and_has_the_template_s_sections_in_order():
    document = read_markdown(EXAMPLE)
    headings = [s.heading for s in document.sections if s.heading]
    order = [heading for heading, _ in template_sections()]

    assert problems(document.front_matter, SCHEMA) == []
    assert headings == [h for h in order if h in headings]
    assert {h for h, required in template_sections() if required} <= set(headings)


def test_the_example_names_only_data_it_defines():
    document = read_markdown(EXAMPLE)
    table = document.section("Test data").tables[0]
    defined = {re.fullmatch(r"`\{(.+)\}`", cells[0]).group(1) for _, cells in table.rows}
    body = EXAMPLE.split("\n---\n", 1)[1]  # after the header

    assert set(re.findall(r"\{([a-z][a-z0-9-]*)\}", body)) == defined


def test_a_case_is_a_draft_while_it_has_open_questions():
    document = read_markdown(EXAMPLE)
    questions = " ".join(text for _, text in document.section("Open questions").paragraphs)

    assert document.front_matter["status"] == "draft" or questions == "None."
    assert questions != "None."  # the example shows why it isn't approved yet
