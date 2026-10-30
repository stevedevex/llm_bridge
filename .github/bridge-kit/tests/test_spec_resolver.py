import http.server
import shutil
import threading
import zipfile
from functools import partial

import pytest
from conftest import SPECS

from bridge_kit import spec_resolver
from bridge_kit.spec_resolver import ResolveError, resolve

OPENAPI = "openapi: 3.0.1\ninfo:\n  title: Accounts\n  version: 2.1.0\npaths:\n  /a:\n    get: {}\n    post: {}\n"


def test_a_file_is_used_as_it_is(tmp_path):
    spec = tmp_path / "accounts.yaml"
    spec.write_text(OPENAPI, encoding="utf-8")

    result = resolve(str(spec), cache=tmp_path / "cache")

    assert (result.kind, result.status) == ("file", "resolved")
    assert [(s.format, s.title, s.version, s.detail) for s in result.specs] == [
        ("openapi-3", "Accounts", "2.1.0", "2 operations")]


def test_several_specs_need_a_choice(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(OPENAPI, encoding="utf-8")

    assert resolve(str(tmp_path), cache=tmp_path / "cache").status == "choose"
    assert resolve(str(tmp_path), cache=tmp_path / "cache", pick="b.yaml").status == "resolved"


def test_pasted_content_is_saved_to_a_working_file(tmp_path):
    result = resolve("-", pasted=OPENAPI, cache=tmp_path / "cache")

    assert result.kind == "pasted"
    assert result.location.startswith(str(tmp_path / "cache" / "pasted"))
    assert result.specs[0].format == "openapi-3"


@pytest.mark.parametrize("snippet, question", [
    ("<dependency><groupId>a</groupId><artifactId>b</artifactId></dependency>", "has no version"),
    ("<dependency><groupId>a</groupId><artifactId>b</artifactId><version>${x}</version></dependency>", "property"),
    ("<dependency><groupId>a</groupId>", "isn't complete"),
    ("a:b:${spec.version}", "property"),
])
def test_unclear_coordinates_become_a_question(tmp_path, snippet, question):
    result = resolve(snippet, cache=tmp_path / "cache")

    assert result.status == "ask"
    assert question in result.message


def test_a_url_is_downloaded_once(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    (served / "accounts.yaml").write_text(OPENAPI, encoding="utf-8")
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/accounts.yaml"
    try:
        first = resolve(url, cache=tmp_path / "cache")
        (served / "accounts.yaml").unlink()
        second = resolve(url, cache=tmp_path / "cache")
    finally:
        server.shutdown()

    assert first.status == second.status == "resolved"
    assert second.specs[0].title == "Accounts"


def test_a_jar_with_an_escaping_entry_is_refused(tmp_path):
    jar = tmp_path / "evil.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("../escaped.yaml", OPENAPI)

    with pytest.raises(ResolveError):
        spec_resolver._unzip(jar, tmp_path / "out")
    assert not (tmp_path / "escaped.yaml").exists()


def test_a_wsdl_comes_with_the_xsds_it_imports(tmp_path):
    spec = SPECS / "com.example.upstream2" / "customer-directory-soap-spec" / "1.3.0"
    folder = tmp_path / "customer-directory"
    shutil.copytree(spec / "wsdl", folder / "wsdl")
    shutil.copytree(spec / "xsd", folder / "xsd")

    result = resolve(str(folder), cache=tmp_path / "cache")

    assert result.status == "resolved"
    [wsdl] = result.specs
    assert wsdl.format == "wsdl"
    assert sorted(p.rsplit("/", 1)[-1] for p in wsdl.includes) == ["directory-messages.xsd", "directory-types.xsd"]
