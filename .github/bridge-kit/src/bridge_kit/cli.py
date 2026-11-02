"""The `bridge-kit` command line. Exit codes: 0 success, 1 a stop condition, 2 a usage error."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from bridge_kit.internal_model import InternalModel, ModelError


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridge-kit",
                                     description="bridge-kit: the commands behind the BA's AI agents.")
    commands = parser.add_subparsers(dest="command", required=True)

    gitlab = commands.add_parser("gitlab", help="Read GitLab's stories and wikis, in the projects and groups "
                                                "bridge-kit.yaml declares")
    gitlab_kinds = gitlab.add_subparsers(dest="kind", required=True)
    status = gitlab_kinds.add_parser("status", help="Who the token is, and whether each declared project, group and "
                                                    "wiki answers at its path")
    status.set_defaults(handler=_gitlab_status)
    issue = gitlab_kinds.add_parser("issue", help="Stories: GitLab issues")
    issue_actions = issue.add_subparsers(dest="action", required=True)
    get = issue_actions.add_parser("get", help="One story, with its comments and links when asked")
    get.add_argument("ref", help="REQ-101, <project>#101, its GitLab link, or 101 with --project")
    get.add_argument("--project", help="The declared project a bare number is in")
    get.add_argument("--notes", action="store_true", help="With its comments (GitLab's system notes left out)")
    get.add_argument("--links", action="store_true", help="With the stories it blocks, is blocked by, relates to")
    get.set_defaults(handler=_gitlab_issue_get)
    listing = issue_actions.add_parser("list", help="Stories in a declared project, latest updated first")
    listing.add_argument("--project", help="The declared project; by default default_project")
    listing.add_argument("--label", help="Labels, comma-separated: every one must be on the story")
    listing.add_argument("--milestone", help="The milestone's title")
    listing.add_argument("--state", choices=["opened", "closed", "all"], help="By default all")
    listing.add_argument("--search", help="Text in the title or description")
    listing.add_argument("--author", help="The author's username")
    listing.add_argument("--limit", type=int, default=50, help="At most this many (default 50)")
    listing.set_defaults(handler=_gitlab_issue_list)
    links = issue_actions.add_parser("links", help="The stories one blocks, is blocked by, or relates to")
    links.add_argument("ref", help="REQ-101, <project>#101, or its GitLab link")
    links.add_argument("--project", help="The declared project a bare number is in")
    links.set_defaults(handler=_gitlab_issue_links)
    epic = gitlab_kinds.add_parser("epic", help="Epics, where the GitLab tier has them")
    epic_actions = epic.add_subparsers(dest="action", required=True)
    epic_get = epic_actions.add_parser("get", help="An epic and its stories")
    epic_get.add_argument("group", help="The declared group")
    epic_get.add_argument("iid", type=int, help="The epic's number in the group")
    epic_get.set_defaults(handler=_gitlab_epic_get)
    wiki = gitlab_kinds.add_parser("wiki", help="A declared project's or group's wiki")
    wiki_actions = wiki.add_subparsers(dest="action", required=True)
    wiki_list = wiki_actions.add_parser("list", help="The wiki's pages")
    wiki_get = wiki_actions.add_parser("get", help="One page, as its Markdown")
    wiki_get.add_argument("slug", help="The page's slug, as wiki list shows it (e.g. onboarding/checklist)")
    wiki_search = wiki_actions.add_parser("search", help="Pages holding some text, with the lines that match")
    wiki_search.add_argument("text", help="The text to look for")
    for action, handler in ((wiki_list, _gitlab_wiki_list), (wiki_get, _gitlab_wiki_get),
                            (wiki_search, _gitlab_wiki_search)):
        action.add_argument("--wiki", help="The declared project or group; needed when more than one has a wiki")
        action.set_defaults(handler=handler)
    create = issue_actions.add_parser("create", help="Create a story in a read-write project: a dry run without --yes")
    create.add_argument("--project", required=True, help="The declared read-write project")
    create.add_argument("--title", required=True)
    create.add_argument("--description-file", type=Path, help="The description, a Markdown file")
    create.add_argument("--label", action="append", default=[], help="A label; may be repeated")
    create.set_defaults(handler=_gitlab_issue_create)
    update = issue_actions.add_parser("update", help="Update a story in a read-write project: a dry run without --yes")
    update.add_argument("ref", help="REQ-101, <project>#101, or its GitLab link")
    update.add_argument("--project", help="The declared project a bare number is in")
    update.add_argument("--title")
    update.add_argument("--description-file", type=Path, help="The new description, a Markdown file")
    update.add_argument("--label", action="append", help="Its labels, all of them; may be repeated")
    update.add_argument("--state", choices=["close", "reopen"])
    update.set_defaults(handler=_gitlab_issue_update)
    comment = issue_actions.add_parser("comment", help="Comment on a story: a dry run without --yes")
    comment.add_argument("ref", help="REQ-101, <project>#101, or its GitLab link")
    comment.add_argument("--project", help="The declared project a bare number is in")
    comment.add_argument("--body-file", type=Path, required=True, help="The comment, a Markdown file")
    comment.set_defaults(handler=_gitlab_issue_comment)
    link = issue_actions.add_parser("link", help="Link two stories, \"relates to\": a dry run without --yes")
    link.add_argument("ref", help="The story in a read-write project")
    link.add_argument("target", help="The story it relates to, in any declared project")
    link.add_argument("--project", help="The declared project a bare number is in")
    link.set_defaults(handler=_gitlab_issue_link)
    for writer in (create, update, comment, link):
        writer.add_argument("--yes", action="store_true", help="Write it: only once the BA has said so")
    for reader in (status, get, listing, links, epic_get, wiki_list, wiki_get, wiki_search, create, update, comment,
                   link):
        reader.add_argument("--json", action="store_true", help="Output JSON")

    payload = commands.add_parser("payload", help="Stored payloads from MongoDB, by request id, from dev or SIT only, "
                                                  "as bridge-kit.yaml declares")
    payload_actions = payload.add_subparsers(dest="action", required=True)
    payload_status = payload_actions.add_parser("status", help="The environment, and whether each declared collection "
                                                               "answers")
    payload_status.set_defaults(handler=_payload_status)
    payload_get = payload_actions.add_parser("get", help="One service's payload for a request, kept in .work/payloads/")
    payload_get.add_argument("service", help="A declared service, e.g. service-a-java")
    payload_get.add_argument("request_id", help="The request's UUID")
    payload_get.set_defaults(handler=_payload_get)
    payload_trace = payload_actions.add_parser("trace", help="The same request in every declared service, side by side")
    payload_trace.add_argument("request_id", help="The request's UUID")
    payload_trace.set_defaults(handler=_payload_trace)
    payload_check = payload_actions.add_parser("check", help="One payload against the internal model: fields it "
                                                             "doesn't have, required ones missing, nulls, types, "
                                                             "codes, formats")
    payload_check.add_argument("service", help="A declared service, e.g. service-a-java")
    payload_check.add_argument("request_id", help="The request's UUID")
    payload_check.set_defaults(handler=_payload_check)
    payload_profile = payload_actions.add_parser("profile", help="The shape across several payloads: per path, how "
                                                                 "often there and null, types, list sizes, codes seen")
    payload_profile.add_argument("service", help="A declared service, e.g. service-a-java")
    payload_profile.add_argument("request_ids", nargs="+", help="The requests' UUIDs")
    payload_profile.set_defaults(handler=_payload_profile)
    payload_raw = payload_actions.add_parser("raw", help="The raw upstream responses behind a request, per upstream "
                                                         "and operation, where a service keeps them")
    payload_raw.add_argument("request_id", help="The request's UUID")
    payload_raw.add_argument("upstream", nargs="?", help="Only this upstream's responses")
    payload_raw.set_defaults(handler=_payload_raw)
    for action in (payload_status, payload_get, payload_trace, payload_check, payload_profile, payload_raw):
        action.add_argument("--json", action="store_true", help="As JSON")

    workspace = commands.add_parser("workspace", help="The checkouts beside the BA repo")
    workspace_actions = workspace.add_subparsers(dest="action", required=True)
    workspace_scan = workspace_actions.add_parser("scan", help="Draft bridge-kit.yaml's workspace.repos from the "
                                                              "folders beside the BA repo, and what differs from it")
    workspace_scan.add_argument("folder", nargs="?", type=Path, help="The folder to scan; by default the BA repo's "
                                                                     "parent, where the repos sit side by side")
    workspace_scan.add_argument("--write", action="store_true", help="Add the repos bridge-kit.yaml doesn't declare, "
                                                                     "read-only; an entry it has is never changed")
    workspace_scan.add_argument("--json", action="store_true", help="Output JSON")
    workspace_scan.set_defaults(handler=_workspace_scan)

    tests = commands.add_parser("tests", help="A work item's test cases")
    tests_actions = tests.add_subparsers(dest="action", required=True)
    tests_coverage = tests_actions.add_parser("coverage", help="Which of a work item's acceptance criteria its test "
                                                               "cases verify, and the gaps")
    tests_coverage.add_argument("work_item", help="The work item, e.g. REQ-101")
    tests_coverage.add_argument("--json", action="store_true", help="Output JSON")
    tests_coverage.set_defaults(handler=_tests_coverage)

    inputs = commands.add_parser("inputs", help="A work item's inputs: what a BA brings, as Markdown with its source")
    inputs_actions = inputs.add_subparsers(dest="action", required=True)
    add = inputs_actions.add_parser("add", help="Add a source as the work item's next input, or say it's already there")
    add.add_argument("source", help="gitlab:<story> (REQ-101, <project>#101 or its link), wiki:<page slug>, or a "
                                    "file: a document, or an image with --description")
    add.add_argument("--work-item", required=True, help="The work item, e.g. REQ-102; its folder is made if needed")
    add.add_argument("--project", help="The declared project a bare story number is in")
    add.add_argument("--wiki", help="The declared project or group whose wiki the page is in")
    _document_options(add)
    add.add_argument("--description", help="For an image, or a PDF's pages without text: a file with what it shows, "
                                           "as read by an agent or the BA, or - for standard input")
    add.add_argument("--by", help="Who wrote the description: the agent's name, or the BA's")
    add.add_argument("--json", action="store_true", help="Output JSON")
    add.set_defaults(handler=_inputs_add)

    knowledge = commands.add_parser("knowledge", help="The component knowledge: the glossary of business terms, and "
                                                      "what the components' own teams have written down")
    knowledge_actions = knowledge.add_subparsers(dest="action", required=True)
    term = knowledge_actions.add_parser("term", help="What a business term means in the model: the glossary, the "
                                                     "model's fields, the profiles")
    term.add_argument("words", help="The business words, e.g. \"valuation date\"")
    term.add_argument("--json", action="store_true", help="Output JSON")
    term.set_defaults(handler=_knowledge_term)
    check = knowledge_actions.add_parser("check", help="Check the glossary: its shape, each term once, each data "
                                                       "element a path of the model")
    check.add_argument("--json", action="store_true", help="Output JSON")
    check.set_defaults(handler=_knowledge_check)
    show = knowledge_actions.add_parser("show", help="A component's own knowledge the catalog points to: its pointers, "
                                                     "or what one kind's point to")
    show.add_argument("component", help="The component, as architecture/components.yaml names it")
    show.add_argument("kind", nargs="?", help="glossary, lineage, anatomy, contracts, build-and-test, playbooks, "
                                              "privacy, versions, intake or other")
    show.add_argument("--json", action="store_true", help="Output JSON")
    show.set_defaults(handler=_knowledge_show)

    work = commands.add_parser("work", help="Work items")
    work_actions = work.add_subparsers(dest="action", required=True)
    work_status = work_actions.add_parser("status", help="Where a work item stands, from its files, and the next step")
    work_status.add_argument("work_item", help="The work item, e.g. REQ-101")
    work_status.add_argument("--json", action="store_true", help="Output JSON")
    work_status.set_defaults(handler=_work_status)

    stories = commands.add_parser("stories", help="A work item's user stories")
    stories_actions = stories.add_subparsers(dest="action", required=True)
    publish = stories_actions.add_parser("publish", help="Create the work item's approved stories as GitLab issues, "
                                                         "in each component's project: a dry run without --yes")
    publish.add_argument("work_item", help="The work item, e.g. REQ-101")
    publish.add_argument("--yes", action="store_true", help="Create them: only once the BA has said so")
    publish.add_argument("--maven-repo", type=Path, action="append", default=[],
                         help="A Maven repository folder holding the spec jars, for the package check; may be repeated")
    publish.add_argument("--repository", help="The Maven repository URL, for the package check")
    publish.add_argument("--json", action="store_true", help="Output JSON")
    publish.set_defaults(handler=_stories_publish)

    export = commands.add_parser("export", help="Write BRIDGE into another BA repo: the agents, prompts, skills, "
                                                "the kit, templates and formats; never that repo's own files")
    export.add_argument("--to", required=True, type=Path, help="The BA repo to write into, checked out")
    export.add_argument("--dry-run", action="store_true", help="List what it would write, and write nothing")
    export.add_argument("--force", action="store_true",
                        help="Overwrite the kit's files changed in that BA repo since the last export")
    export.add_argument("--json", action="store_true", help="Output JSON")
    export.set_defaults(handler=_export)

    components = commands.add_parser("components", help="The component catalog, architecture/components.yaml")
    components_actions = components.add_subparsers(dest="action", required=True)
    components_build = components_actions.add_parser(
        "build", help="Assemble the catalog from the components' profiles (architecture/components/): the diff, and "
                      "the file with --write")
    components_build.add_argument("--write", action="store_true", help="Write the catalog, when nothing's wrong")
    components_build.add_argument("--json", action="store_true", help="Output JSON")
    components_build.set_defaults(handler=_components_build)
    components_scan = components_actions.add_parser(
        "scan", help="Each declared checkout's own AI layer (.github: instructions, skills, agents, prompts), the kind "
                     "of knowledge each item holds, and the catalog's knowledge pointers it proposes or finds broken")
    components_scan.add_argument("component", nargs="?", help="Only this component")
    components_scan.add_argument("--write", action="store_true",
                                 help="Add the proposed pointers to each component the catalog has no knowledge for")
    components_scan.add_argument("--json", action="store_true", help="Output JSON")
    components_scan.set_defaults(handler=_components_scan)

    doc = commands.add_parser("doc", help="Documents a BA brings, as Markdown")
    doc_actions = doc.add_subparsers(dest="action", required=True)
    doc_read = doc_actions.add_parser("read", help="Print a document as Markdown, to look at it before keeping it")
    doc_read.add_argument("file", type=Path, help="Text, Markdown, CSV, TSV, Excel, Word, PDF, PowerPoint, HTML or "
                                                  "an email (.eml)")
    _document_options(doc_read)
    doc_read.add_argument("--json", action="store_true", help="Output JSON: the Markdown, its title and warnings")
    doc_read.set_defaults(handler=_doc_read)

    preflight = commands.add_parser("preflight", help="Check the environment and every declared checkout against "
                                                      "bridge-kit.yaml, before an agent acts on them")
    preflight.add_argument("--json", action="store_true", help="Output JSON")
    preflight.set_defaults(handler=_preflight)

    validate = commands.add_parser("validate", help="Run a validator")
    validate_kinds = validate.add_subparsers(dest="kind", required=True)
    mapping = validate_kinds.add_parser("mapping", help="Check mapping specs against FORMAT.md, the model and the spec")
    mapping.add_argument("files", nargs="+", type=Path, help="Mapping spec files")
    mapping.add_argument("--model", type=Path, help="The internal model's schemas folder; by default the model repo "
                                                    "bridge-kit.yaml names")
    mapping.add_argument("--maven-repo", type=Path, action="append", default=[],
                         help="A Maven repository folder holding the spec jars; may be repeated")
    mapping.add_argument("--json", action="store_true", help="Output JSON")
    mapping.set_defaults(handler=_validate_mapping)
    digest = validate_kinds.add_parser("digest", help="Check a spec digest's answers against the spec")
    digest.add_argument("files", nargs="+", type=Path, help="Spec digest files")
    digest.add_argument("--repository", help="The Nexus repository URL, when no mirror in settings.xml names it")
    digest.add_argument("--json", action="store_true", help="Output JSON")
    digest.set_defaults(handler=_validate_digest)
    request = validate_kinds.add_parser("request", help="Check a mapping request, the BA's input to the Mapping "
                                                        "Drafter")
    request.add_argument("files", nargs="+", type=Path, help="Mapping request files")
    request.add_argument("--model", type=Path, help="The internal model's schemas folder; by default the model repo "
                                                    "bridge-kit.yaml names")
    request.add_argument("--repository", help="The Nexus repository URL, when no mirror in settings.xml names it")
    request.add_argument("--json", action="store_true", help="Output JSON")
    request.set_defaults(handler=_validate_request)
    model = validate_kinds.add_parser("model", help="Check a change to the internal model: conventions, version, "
                                                    "example, merge request description and build")
    model.add_argument("work_item", help="The work item the change is for, e.g. REQ-101")
    model.add_argument("--no-build", action="store_true", help="Skip the model's build")
    model.add_argument("--json", action="store_true", help="Output JSON")
    model.set_defaults(handler=_validate_model)
    story = validate_kinds.add_parser("story", help="Check user stories against templates/story.md and the component "
                                                    "catalog, as one set")
    story.add_argument("paths", nargs="+", type=Path, help="Story files, or a folder of them (a work item's stories/)")
    story.add_argument("--json", action="store_true", help="Output JSON")
    story.set_defaults(handler=_validate_story)
    test_case = validate_kinds.add_parser("test-case", help="Check test cases against templates/test-case.md and the "
                                                            "stories they verify, as one set")
    test_case.add_argument("paths", nargs="+", type=Path, help="Test case files, or a folder of them (a work item's "
                                                               "tests/)")
    test_case.add_argument("--json", action="store_true", help="Output JSON")
    test_case.set_defaults(handler=_validate_test_case)
    impact = validate_kinds.add_parser("impact", help="Check a requirement's impact analysis, work/<id>/impact.md, "
                                                      "against templates/impact.md and the component catalog")
    impact.add_argument("work_item", help="The work item, e.g. REQ-101")
    impact.add_argument("--json", action="store_true", help="Output JSON")
    impact.set_defaults(handler=_validate_impact)
    package = validate_kinds.add_parser("package", help="Check a requirement package as a whole: every file's checks, "
                                                        "then that the files agree and every component has its "
                                                        "story, for the developers' implementable check")
    package.add_argument("work_item", help="The work item, e.g. REQ-101")
    package.add_argument("--maven-repo", type=Path, action="append", default=[],
                         help="A Maven repository folder holding the spec jars; may be repeated")
    package.add_argument("--repository", help="The Nexus repository URL, when no mirror in settings.xml names it")
    package.add_argument("--no-build", action="store_true", help="Skip the model's build")
    package.add_argument("--json", action="store_true", help="Output JSON")
    package.set_defaults(handler=_validate_package)

    change = commands.add_parser("model", help="Changes to the internal model")
    change_actions = change.add_subparsers(dest="kind", required=True)
    start = change_actions.add_parser("start", help="Start a change: record the model as it is now, as its base")
    start.add_argument("work_item", help="The work item the change is for, e.g. REQ-101")
    start.add_argument("--json", action="store_true", help="Output JSON")
    start.set_defaults(handler=_model_start)
    diff = change_actions.add_parser("diff", help="Compare the model with the change's base: every difference, "
                                                  "additive or breaking, the version it needs, and who it breaks")
    diff.add_argument("work_item", help="The work item the change is for")
    diff.add_argument("--json", action="store_true", help="Output JSON")
    diff.set_defaults(handler=_model_diff)
    profile = change_actions.add_parser("profile", help="The model's layout and conventions as its own files show "
                                                        "them, as a model: block for bridge-kit.yaml")
    profile.add_argument("checkout", nargs="?", type=Path, help="The model's checkout; by default the repo "
                                                                "bridge-kit.yaml names as model.repo")
    profile.add_argument("--json", action="store_true", help="Output JSON")
    profile.set_defaults(handler=_model_profile)

    spec = commands.add_parser("spec", help="Upstream specs")
    spec_actions = spec.add_subparsers(dest="kind", required=True)
    resolve = spec_actions.add_parser("resolve", help="Find and unpack an upstream spec, whatever form it's given in")
    resolve.add_argument("given", help="A file or folder, a URL, groupId:artifactId:version, a <dependency> or "
                                       "<artifactItem> block, or - to read pasted spec content from stdin")
    resolve.add_argument("--repository", help="The Nexus repository URL, when no mirror in settings.xml names it")
    resolve.add_argument("--pick", help="The spec to use when the input holds several")
    resolve.add_argument("--json", action="store_true", help="Output JSON")
    resolve.set_defaults(handler=_spec_resolve)
    digest = spec_actions.add_parser("digest", help="List every operation and field of an upstream spec, as a spec "
                                                    "digest for the Spec Explorer to write its answers into")
    digest.add_argument("given", help="Anything `bridge-kit spec resolve` takes")
    digest.add_argument("--upstream", required=True, help="The upstream's id, as mapping specs name it")
    digest.add_argument("--out", type=Path, help="The digest file to write; printed when left out")
    digest.add_argument("--force", action="store_true", help="Overwrite the digest file if it exists")
    digest.add_argument("--repository", help="The Nexus repository URL, when no mirror in settings.xml names it")
    digest.add_argument("--pick", help="The spec to use when the input holds several")
    digest.set_defaults(handler=_spec_digest)
    return parser


def _validate_mapping(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.validators.mapping import MappingValidator

    missing = [str(f) for f in [*args.files, *([args.model] if args.model else []), *args.maven_repo] if not f.exists()]
    if missing:
        print(f"Not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        validator = MappingValidator(InternalModel(args.model) if args.model else _config_model(), args.maven_repo)
    except (ConfigError, ModelError) as e:
        print(str(e), file=sys.stderr)
        return 2
    findings = [f for file in args.files for f in validator.validate(file)]
    return _print_findings(findings, args.files, args.json)


def _gitlab(args: argparse.Namespace, read) -> int:
    """Runs one GitLab read: `read(client, gitlab_config)` returns what to print, as text and as JSON."""
    from bridge_kit.auth import TokenError
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.gitlab import GitLab, GitLabError
    from bridge_kit.guard import GuardError

    try:
        config = load_config()
        if config.gitlab is None:
            raise ConfigError("bridge-kit.yaml declares no GitLab: add integrations.gitlab (see "
                              "bridge-kit.example.yaml)")
        text, data, code = read(GitLab(config.gitlab), config.gitlab)
    except (ConfigError, GuardError) as e:
        print(str(e), file=sys.stderr)
        return 2
    except (TokenError, GitLabError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2) if args.json else text, end="" if not args.json and text.endswith("\n") else "\n")
    return code


def _gitlab_status(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_status

    def read(client, _):
        text, data = read_status(client)
        return text, data, 0 if data["ok"] else 1

    return _gitlab(args, read)


def _gitlab_issue_get(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_issue

    return _gitlab(args, lambda client, _: (*read_issue(client, args.ref, args.project, args.notes, args.links), 0))


def _gitlab_issue_list(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_issue_list

    return _gitlab(args, lambda client, _: (*read_issue_list(client, args.project, args.label, args.milestone,
                                                             args.state, args.search, args.author, args.limit), 0))


def _gitlab_issue_links(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_links

    return _gitlab(args, lambda client, _: (*read_links(client, args.ref, args.project), 0))


def _payload(args: argparse.Namespace, read) -> int:
    """Runs one payload read: `read(payloads)` returns what to print, as text and as JSON, and the exit code."""
    from bridge_kit import audit
    from bridge_kit.auth import TokenError
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.payloads import PayloadError, Payloads, Refused

    call = f"payload {args.action}"
    arguments = {k: getattr(args, k) for k in ("service", "request_id", "request_ids", "upstream") if hasattr(args, k)}
    try:
        text, data, code = read(Payloads(load_config()))
    except (ConfigError, Refused) as e:
        audit.record("cli", call, arguments, False, str(e))
        print(str(e), file=sys.stderr)
        return 2
    except (TokenError, PayloadError) as e:
        audit.record("cli", call, arguments, False, str(e))
        print(str(e), file=sys.stderr)
        return 1
    audit.record("cli", call, arguments, True)
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else text,
          end="" if not args.json and text.endswith("\n") else "\n")
    return code


def _payload_status(args: argparse.Namespace) -> int:
    from bridge_kit.payloads import read_status

    def read(payloads):
        text, data = read_status(payloads)
        return text, data, 0 if data["ok"] else 1

    return _payload(args, read)


def _payload_get(args: argparse.Namespace) -> int:
    from bridge_kit.payloads import read_payload

    return _payload(args, lambda payloads: (*read_payload(payloads, args.service, args.request_id), 0))


def _payload_trace(args: argparse.Namespace) -> int:
    from bridge_kit.payloads import read_trace

    return _payload(args, lambda payloads: (*read_trace(payloads, args.request_id), 0))


def _payload_check(args: argparse.Namespace) -> int:
    from bridge_kit.payloads import read_check

    return _payload(args, lambda payloads: read_check(payloads, args.service, args.request_id))


def _payload_profile(args: argparse.Namespace) -> int:
    from bridge_kit.payloads import read_profile

    return _payload(args, lambda payloads: (*read_profile(payloads, args.service, args.request_ids), 0))


def _payload_raw(args: argparse.Namespace) -> int:
    from bridge_kit.payloads import read_raw

    return _payload(args, lambda payloads: (*read_raw(payloads, args.request_id, args.upstream), 0))


def _text_file(path: Path | None) -> str | None:
    from bridge_kit.gitlab import GitLabError

    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise GitLabError(f"Can't read {path}: {e.strerror}") from None


def _written(text: str, data: dict, dry_run: bool) -> tuple[str, dict, int]:
    return (text + ("Run it again with --yes once the BA has said so.\n" if dry_run else ""), data, 0)


def _gitlab_issue_create(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import write_create_issue

    return _gitlab(args, lambda client, _: _written(*write_create_issue(
        client, args.project, args.title, _text_file(args.description_file) or "", args.label, not args.yes),
        not args.yes))


def _gitlab_issue_update(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import write_update_issue

    return _gitlab(args, lambda client, _: _written(*write_update_issue(
        client, args.ref, args.project, args.title, _text_file(args.description_file), args.label, args.state,
        not args.yes), not args.yes))


def _gitlab_issue_comment(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import write_add_note

    return _gitlab(args, lambda client, _: _written(*write_add_note(
        client, args.ref, _text_file(args.body_file) or "", args.project, not args.yes), not args.yes))


def _gitlab_issue_link(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import write_link_issues

    return _gitlab(args, lambda client, _: _written(*write_link_issues(
        client, args.ref, args.target, args.project, not args.yes), not args.yes))


def _gitlab_epic_get(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_epic

    return _gitlab(args, lambda client, _: (*read_epic(client, args.group, args.iid), 0))


def _gitlab_wiki_list(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_wiki_list

    return _gitlab(args, lambda client, _: (*read_wiki_list(client, args.wiki), 0))


def _gitlab_wiki_get(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_wiki_page

    return _gitlab(args, lambda client, _: (*read_wiki_page(client, args.slug, args.wiki), 0))


def _gitlab_wiki_search(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import read_wiki_search

    return _gitlab(args, lambda client, _: (*read_wiki_search(client, args.text, args.wiki), 0))


def _optional_model():
    """The model bridge-kit.yaml declares, or None when there's no bridge-kit.yaml or no model to read."""
    from bridge_kit.config import ConfigError

    try:
        return _config_model()
    except (ConfigError, ModelError, OSError):
        return None


def _knowledge_term(args: argparse.Namespace) -> int:
    from bridge_kit.knowledge import find_term, format_found
    from bridge_kit.paths import repo_root

    from bridge_kit.component_knowledge import team_glossaries
    from bridge_kit.config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError:
        config = None
    found = find_term(args.words, repo_root(), _optional_model(), team_glossaries(repo_root(), config))
    print(json.dumps(found.to_dict(), indent=2) if args.json else format_found(args.words, found), end="")
    return 0


def _knowledge_show(args: argparse.Namespace) -> int:
    from bridge_kit.component_knowledge import show
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.paths import repo_root

    try:
        text, code = show(repo_root(), load_config(), args.component, args.kind)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps({"component": args.component, "kind": args.kind, "text": text}, indent=2) if args.json else text,
          end="" if not args.json else "\n")
    return code


def _components_scan(args: argparse.Namespace) -> int:
    from bridge_kit.component_knowledge import render, scan, write_proposed
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.paths import repo_root

    try:
        results = scan(repo_root(), load_config(), args.component)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    added = write_proposed(repo_root(), results) if args.write else []
    if args.json:
        print(json.dumps({"components": [r.to_dict() for r in results], "written": added}, indent=2))
    else:
        print(render(results), end="")
        if added:
            print(f"Added knowledge to {', '.join(added)} in architecture/components.yaml: review it")
    return 1 if any(r.broken for r in results) else 0


def _knowledge_check(args: argparse.Namespace) -> int:
    from bridge_kit.knowledge import GLOSSARY, check_glossary
    from bridge_kit.paths import repo_root

    model = _optional_model()
    findings = check_glossary(repo_root(), model)
    if model is None:
        print("The model isn't read (no bridge-kit.yaml, or its checkout isn't there): data elements aren't checked",
              file=sys.stderr)
    return _print_findings(findings, sorted((repo_root() / GLOSSARY).glob("*.yaml")), args.json)


def _work_status(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.paths import repo_root
    from bridge_kit.work_status import format_status, work_status

    try:
        model_repo = load_config().model_repo
    except ConfigError:
        model_repo = None  # the status reads files; the model's repo only names the model's component
    status = work_status(args.work_item, repo_root(), model_repo)
    print(json.dumps(status.to_dict(), indent=2) if args.json else format_status(status), end="")
    return 0


def _stories_publish(args: argparse.Namespace) -> int:
    from bridge_kit.auth import TokenError
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.gitlab import GitLab, GitLabError
    from bridge_kit.paths import repo_root
    from bridge_kit.publish import PublishError, publish
    from bridge_kit.validators.package import validate_package

    try:
        config = load_config()
        package = validate_package(args.work_item, repo_root(), config, args.maven_repo, args.repository, build=False)
        client = GitLab(config.gitlab) if args.yes and config.gitlab else None
        result = publish(args.work_item, repo_root(), config, client, dry_run=not args.yes, package_findings=package)
    except (ConfigError, ModelError) as e:
        print(str(e), file=sys.stderr)
        return 2
    except PublishError as e:
        print(str(e), file=sys.stderr)
        return 1
    except (TokenError, GitLabError) as e:
        print(f"{e}\nThe stories created before it have their ids in their files: run it again to go on.",
              file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    to_create = [p for p in result.planned if p.status != "created already"]
    if not to_create:
        print(f"Nothing to create: every story of {args.work_item} is created already.")
        return 0
    print(f"{'Would create' if result.dry_run else 'Created'} {len(to_create)} issue(s) for {args.work_item}:")
    for planned in result.planned:
        story = planned.story
        relates = ", ".join([str(story.header.get("parent")), *story.blocked_by])
        if planned.status == "created already":
            print(f"  {story.ref} {story.component}: {planned.id}, created already")
        elif result.dry_run:
            labels = ", ".join(str(label) for label in story.header.get("labels") or [])
            print(f"  {story.ref} {story.component} in {planned.project}: {story.header.get('title')} [{labels}]; "
                  f"relates to {relates}")
        else:
            print(f"  {story.ref} {story.component}: {planned.id}, {story.header.get('title')}")
    print("Run it again with --yes once the BA has said so." if result.dry_run else result.comment)
    return 0


def _export(args: argparse.Namespace) -> int:
    from bridge_kit.export import ExportError, export
    from bridge_kit.paths import repo_root

    try:
        result = export(repo_root(), args.to, args.dry_run, args.force)
    except ExportError as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 1 if result.stopped else 0
    for name, status in result.files.items():
        if status != "unchanged":
            print(f"{status:13} {name}")
    if result.stopped:
        print(f"Stopped, nothing written: {result.count('changed there')} of the kit's file(s) changed in "
              f"{result.target} since the last export. Bring each change to BRIDGE's repo and export again, or "
              "export with --force to overwrite them.", file=sys.stderr)
        return 1
    if result.gitignore != "unchanged":
        print(f"{result.gitignore:13} .gitignore: the kit's lines")
    counts = ", ".join(f"{result.count(s)} {s}" for s in ("new", "updated", "overwritten", "removed", "unchanged")
                       if s != "overwritten" or result.count(s))
    print(f"{'Would export' if args.dry_run else 'Exported'} {len(result.files)} file(s) from "
          f"{result.commit or 'a folder that isn\'t a git checkout'} to {result.target}: {counts}")
    if result.dirty:
        print("Warning: the kit's repo has changes not committed in the files it ships, so the commit recorded "
              "doesn't hold them", file=sys.stderr)
    return 0


def _config_model():
    """The internal model bridge-kit.yaml declares, read by its layout."""
    from bridge_kit.config import load_config
    from bridge_kit.internal_model import open_model

    config = load_config()
    return open_model(config.model.path, config.model_layout)


def _components_build(args: argparse.Namespace) -> int:
    from bridge_kit.components import CATALOG, build
    from bridge_kit.paths import repo_root

    repo = repo_root()
    built = build(repo)
    written = args.write and built.ok and built.text != built.current
    if written:
        (repo / CATALOG).parent.mkdir(parents=True, exist_ok=True)
        (repo / CATALOG).write_text(built.text, encoding="utf-8")
    if args.json:
        print(json.dumps({"ok": built.ok, "changed": built.text != built.current, "written": written,
                          "findings": [asdict(f) for f in built.findings], "diff": built.diff}, indent=2))
        return 0 if built.ok else 1
    for finding in built.findings:
        print(finding)
    if built.text == built.current:
        print(f"{CATALOG.as_posix()}: no change")
    else:
        print(built.diff, end="")
        print(f"Wrote {CATALOG.as_posix()}" if written else
              "Not written: fix the errors first" if args.write else "Not written: --write writes it")
    return 0 if built.ok else 1


def _document_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sheet", action="append", default=[], help="Only this sheet of a workbook; may be repeated")
    parser.add_argument("--rows", type=_rows, help="At most this many rows a table, or all; by default a table of "
                                                   "over 500 rows shows its first 200")
    parser.add_argument("--headers-only", action="store_true", help="A table's heading row only, for real records")
    parser.add_argument("--layout", action="store_true", help="A PDF's pages as laid out, keeping their tables' "
                                                              "columns")


def _rows(text: str) -> int | str:
    if text == "all":
        return text
    if text.isdigit() and int(text) > 0:
        return int(text)
    raise argparse.ArgumentTypeError(f"{text} isn't a number of rows, or all")


def _document_options_of(args: argparse.Namespace):
    from bridge_kit.documents import Options

    return Options(tuple(args.sheet), args.rows, args.headers_only, args.layout)


def _doc_read(args: argparse.Namespace) -> int:
    from bridge_kit.documents import DocumentError, read_document

    try:
        document = read_document(args.file, _document_options_of(args))
    except DocumentError as e:
        print(e, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(document.to_dict(), indent=2))
    else:
        print(document.markdown.rstrip("\n"))
        for warning in document.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _added_text(added) -> str:
    return {"added": f"Added {added.file}: {added.summary}",
            "unchanged": f"Already there, unchanged: {added.file}",
            "changed": f"Changed since {added.earlier}: added {added.file}"}[added.status]


def _inputs_add(args: argparse.Namespace) -> int:
    from bridge_kit.gitlab import render_issue, render_wiki_page
    from bridge_kit.guard import GuardError, issue_ref, wiki_ref
    from bridge_kit.inputs import InputError, add_input, content_hash, slug, work_folder
    from bridge_kit.paths import repo_root

    kind, _, ref = args.source.partition(":")
    if kind not in ("gitlab", "wiki") or not ref:
        return _inputs_add_file(args)

    def read(client, gitlab):
        try:
            work_folder(repo_root(), args.work_item, create=True)  # its id checked before anything is read
            if kind == "gitlab":
                story = issue_ref(gitlab, ref, args.project)
                issue, notes, links = client.issue(story), client.notes(story), client.links(story)
                added = add_input(repo_root(), args.work_item, "gitlab-issue", story.label,
                                  f"story-{slug(story.label)}", str(issue.get("updated_at") or ""),
                                  str(issue.get("title") or story.label), render_issue(story, issue, notes, links),
                                  {"issue": issue, "notes": notes, "links": links}, str(issue.get("web_url") or ""))
            else:
                wiki = wiki_ref(gitlab, args.wiki)
                page = client.wiki_page(wiki, ref)
                where = f"groups/{wiki.owner.path}" if wiki.is_group else wiki.owner.path
                added = add_input(repo_root(), args.work_item, "gitlab-wiki-page", f"{wiki.owner.name}:{ref}",
                                  f"wiki-{slug(ref)}", content_hash(str(page.get("content") or "")),
                                  str(page.get("title") or ref), render_wiki_page(wiki, page), page,
                                  f"{gitlab.url}/{where}/-/wikis/{ref}")
        except InputError as e:
            raise GuardError(str(e)) from None
        return _added_text(added) + "\n", added.to_dict(), 0

    return _gitlab(args, read)


def _inputs_add_file(args: argparse.Namespace) -> int:
    from bridge_kit.documents import DocumentError
    from bridge_kit.inputs import InputError, add_file
    from bridge_kit.paths import repo_root

    path = Path(args.source).expanduser()
    if not path.exists():
        print(f"{args.source} isn't a source bridge-kit reads: gitlab:<story>, wiki:<page slug>, or a file",
              file=sys.stderr)
        return 2
    try:
        description = None
        if args.description == "-":
            description = sys.stdin.read()
        elif args.description:
            description = Path(args.description).read_text(encoding="utf-8")
        added, document = add_file(repo_root(), args.work_item, path, _document_options_of(args), description,
                                   args.by)
    except (InputError, OSError) as e:
        print(e if isinstance(e, InputError) else f"Can't read the description: {e}", file=sys.stderr)
        return 2
    except DocumentError as e:
        print(e, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(added.to_dict(), indent=2))
        return 0
    _print_added(added)
    return 0


def _print_added(added, depth: int = 0) -> None:
    """The input, and an email's attachments under it, each level indented; the warnings of those added."""
    print("  " * depth + _added_text(added) + (", attached to it" if depth else ""))
    for attached in added.attached:
        _print_added(attached, depth + 1)
    for why in added.not_added:
        print("  " * (depth + 1) + f"Not added: {why}")
    for warning in added.warnings if added.status != "unchanged" else []:
        print(f"Warning: {Path(added.file).name + ': ' if depth else ''}{warning}", file=sys.stderr)


def _preflight(args: argparse.Namespace) -> int:
    from bridge_kit.preflight import format_preflight, preflight

    report = preflight()
    print(json.dumps(report.to_dict(), indent=2) if args.json else format_preflight(report))
    return 0 if report.ok else 1


def _print_findings(findings: list, files: list[Path], as_json: bool) -> int:
    errors = sum(f.severity == "error" for f in findings)
    if as_json:
        print(json.dumps({"errors": errors, "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        for finding in findings:
            print(finding)
        warnings = sum(f.severity == "warning" for f in findings)
        print(f"{len(files)} file(s): {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def _validate_digest(args: argparse.Namespace) -> int:
    from bridge_kit.validators.digest import validate_digest

    missing = [str(f) for f in args.files if not f.exists()]
    if missing:
        print(f"Not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    findings = [f for file in args.files for f in validate_digest(file, args.repository)]
    return _print_findings(findings, args.files, args.json)


def _validate_request(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.validators.request import validate_request

    missing = [str(f) for f in args.files if not f.exists()]
    if missing:
        print(f"Not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        model = InternalModel(args.model) if args.model else _config_model()
    except (ConfigError, ModelError) as e:
        print(str(e), file=sys.stderr)
        return 2
    findings = [f for file in args.files for f in validate_request(file, model, args.repository)]
    return _print_findings(findings, args.files, args.json)


def _validate_story(args: argparse.Namespace) -> int:
    from bridge_kit.paths import repo_root
    from bridge_kit.stories import story_files
    from bridge_kit.validators.story import validate_stories

    missing = [str(p) for p in args.paths if not p.exists()]
    if missing:
        print(f"Not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    files = story_files(args.paths)
    if not files:
        print(f"No stories in {', '.join(map(str, args.paths))}", file=sys.stderr)
        return 2
    return _print_findings(validate_stories(files, repo_root()), files, args.json)


def _validate_test_case(args: argparse.Namespace) -> int:
    from bridge_kit.paths import repo_root
    from bridge_kit.test_cases import case_files
    from bridge_kit.validators.test_case import validate_test_cases

    missing = [str(p) for p in args.paths if not p.exists()]
    if missing:
        print(f"Not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    files = case_files(args.paths)
    if not files:
        print(f"No test cases in {', '.join(map(str, args.paths))}", file=sys.stderr)
        return 2
    return _print_findings(validate_test_cases(files, repo_root()), files, args.json)


def _model_profile(args: argparse.Namespace) -> int:
    from bridge_kit.model_profile import ProfileError, profile, profile_json, render

    checkout = args.checkout
    if checkout is None:
        from bridge_kit.config import ConfigError, load_config

        try:
            checkout = load_config().model.path
        except ConfigError as e:
            print(f"{e}: name the model's checkout", file=sys.stderr)
            return 2
    if not checkout.is_dir():
        print(f"Not found: {checkout}", file=sys.stderr)
        return 2
    try:
        result = profile(checkout)
    except ProfileError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(profile_json(result) if args.json else render(result), end="\n" if args.json else "")
    return 0


def _workspace_scan(args: argparse.Namespace) -> int:
    import yaml

    from bridge_kit.config import CONFIG_FILE, ConfigError, config_dir
    from bridge_kit.paths import repo_root
    from bridge_kit.workspace_scan import render, scan, scan_json, write_missing

    root = repo_root()
    file = config_dir(root) / CONFIG_FILE
    if args.folder and not args.folder.is_dir():
        print(f"Not found: {args.folder}", file=sys.stderr)
        return 2
    declared = {}
    if file.exists():
        try:
            declared = ((yaml.safe_load(file.read_text(encoding="utf-8")) or {}).get("workspace") or {}).get("repos") \
                or {}
        except yaml.YAMLError as e:
            print(f"{file} isn't valid YAML: {e}", file=sys.stderr)
            return 2
    result = scan(root, args.folder, declared)
    print(scan_json(result) if args.json else render(result), end="\n" if args.json else "")
    if not args.write:
        return 0
    if not file.exists():
        print("No bridge-kit.yaml to add to: copy bridge-kit.example.yaml to it first", file=sys.stderr)
        return 2
    try:
        added = write_missing(file, result)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"Added to bridge-kit.yaml: {', '.join(added)}" if added else
          "Nothing to add: bridge-kit.yaml declares every repo found")
    return 0


def _tests_coverage(args: argparse.Namespace) -> int:
    from bridge_kit.case_coverage import coverage, format_coverage
    from bridge_kit.paths import repo_root

    result = coverage(args.work_item, repo_root())
    print(json.dumps(result.to_dict(), indent=2) if args.json else format_coverage(result), end="" if not args.json
          else "\n")
    return 1 if result.errors else 0


def _validate_impact(args: argparse.Namespace) -> int:
    from bridge_kit.paths import repo_root
    from bridge_kit.validators.impact import validate_impact

    findings = validate_impact(args.work_item, repo_root())
    return _print_findings(findings, [Path(f"work/{args.work_item}/impact.md")], args.json)


def _validate_package(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.paths import repo_root
    from bridge_kit.validators.package import validate_package, work_folder

    missing = [str(f) for f in args.maven_repo if not f.exists()]
    if missing:
        print(f"Not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    if work_folder(repo_root(), args.work_item) is None:
        print(f"No work folder for {args.work_item} in {repo_root() / 'work'}", file=sys.stderr)
        return 2
    try:
        config = load_config()
        config.model
        findings = validate_package(args.work_item, repo_root(), config, args.maven_repo, args.repository,
                                    build=not args.no_build)
    except (ConfigError, ModelError) as e:
        print(str(e), file=sys.stderr)
        return 2
    errors = sum(f.severity == "error" for f in findings)
    if args.json:
        print(json.dumps({"errors": errors, "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        for finding in findings:
            print(finding)
        warnings = sum(f.severity == "warning" for f in findings)
        verdict = "ready for the developers' check" if not errors else "not ready for the developers' check"
        print(f"{args.work_item}: {errors} error(s), {warnings} warning(s): {verdict}")
    return 1 if errors else 0


def _validate_model(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.paths import repo_root, work_dir
    from bridge_kit.validators.model import validate_model

    try:
        config = load_config()
        config.model
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2
    findings = validate_model(args.work_item, config, work_dir(), repo_root(), build=not args.no_build)
    return _print_findings(findings, [config.model.path], args.json)


def _model_start(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.model_change import ChangeError, start_change
    from bridge_kit.paths import work_dir

    try:
        config = load_config()
        base, version, recorded = start_change(config, work_dir(), args.work_item)
    except (ConfigError, ChangeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"work_item": args.work_item, "repo": config.model.name, "base": str(base),
                          "base_version": version, "recorded": recorded}, indent=2))
    elif recorded:
        print(f"Started {args.work_item}: {config.model.name} {version} recorded as the base. Change the model in "
              f"{config.model.path}, then run `bridge-kit model diff {args.work_item}`.")
    else:
        print(f"{args.work_item} was already started from {config.model.name} {version}; the base is kept.")
    return 0


def _model_diff(args: argparse.Namespace) -> int:
    from bridge_kit.config import ConfigError, load_config
    from bridge_kit.model_change import ChangeError, base_dir, diff_models, format_diff
    from bridge_kit.paths import work_dir

    try:
        config = load_config()
        base = base_dir(work_dir(), args.work_item)
        if not (base / config.model_layout.schemas).is_dir():
            raise ChangeError(f"No base recorded for {args.work_item}: run "
                              f"`bridge-kit model start {args.work_item}` first")
        diff = diff_models(base, config.model.path, config)
    except (ConfigError, ChangeError) as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(diff.to_dict(), indent=2) if args.json else format_diff(diff))
    return 0


def _spec_digest(args: argparse.Namespace) -> int:
    from bridge_kit.paths import repo_root
    from bridge_kit.spec_digest import DigestError, digest_spec, pick_spec, render
    from bridge_kit.spec_resolver import ResolveError, resolve
    from bridge_kit.validators.digest import repo_of

    if args.out and args.out.exists() and not args.force:
        print(f"{args.out} exists and may hold your answers: pass --force to overwrite it", file=sys.stderr)
        return 1
    try:
        if args.given == "-":
            resolution = resolve("-", pasted=sys.stdin.read(), pick=args.pick)
        else:
            resolution = resolve(args.given, repository_url=args.repository, pick=args.pick)
        if resolution.status != "resolved":
            print(f"{resolution.status}: {resolution.message}", file=sys.stderr)
            return 1
        spec = pick_spec(resolution.specs)
        digest = digest_spec(spec)
    except (ResolveError, DigestError) as e:
        print(str(e), file=sys.stderr)
        return 1
    repo = (repo_of(args.out) if args.out else None) or repo_root()
    text = render(digest, resolution, spec, args.upstream, repo)
    if not args.out:
        print(text, end="")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    fields = sum(len(op.outputs) for op in digest.operations)
    print(f"Wrote {args.out}: {len(digest.operations)} operations, {fields} fields returned. Write your answers into "
          f"its sections down to Open questions.")
    return 0


def _spec_resolve(args: argparse.Namespace) -> int:
    from bridge_kit.spec_resolver import ResolveError, format_resolution, resolve

    try:
        if args.given == "-":
            resolution = resolve("-", pasted=sys.stdin.read(), pick=args.pick)
        else:
            resolution = resolve(args.given, repository_url=args.repository, pick=args.pick)
    except ResolveError as e:
        if args.json:
            print(json.dumps({"input": args.given, "status": "error", "message": str(e)}, indent=2))
        else:
            print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(resolution.to_dict(), indent=2) if args.json else format_resolution(resolution))
    return 0 if resolution.status == "resolved" else 1
