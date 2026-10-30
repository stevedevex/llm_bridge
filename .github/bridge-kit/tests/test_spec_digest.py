from pathlib import Path

import pytest
from conftest import SPECS, UPSTREAM_1, UPSTREAM_2

from bridge_kit.cli import main
from bridge_kit.markdown import read_markdown
from bridge_kit.spec_digest import DigestError, digest_location, operation_key, path_key
from bridge_kit.specs import find_jar

RATINGS = """\
openapi: 3.0.1
info: {title: Ratings, version: 1.2.0}
paths:
  /ratings/{id}:
    parameters:
      - {name: id, in: path, required: true, schema: {type: string}, description: The rating's own id}
    get:
      summary: Read one rating
      responses:
        "200":
          content:
            application/json:
              schema: {$ref: "#/components/schemas/Rating"}
    put:
      summary: Change a rating
      requestBody:
        content:
          application/json:
            schema: {$ref: "#/components/schemas/Rating"}
      responses:
        "200":
          content:
            application/json:
              schema: {$ref: "#/components/schemas/Rating"}
components:
  schemas:
    Rating:
      type: object
      required: [Value]
      properties:
        Value: {type: string, description: The rating}
        Kind: {type: string, enum: [Credit, Risk]}
        History:
          type: array
          items: {$ref: "#/components/schemas/Rating"}
        Agency:
          type: object
          properties:
            Name: {type: string}
            Rated: {type: string, format: date}
"""

LOANS_WSDL = """\
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
                  xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:l="urn:loans" targetNamespace="urn:loans"
                  name="LoanService">
  <wsdl:types>
    <xsd:schema targetNamespace="urn:loans" version="3.1.0">
      <xsd:simpleType name="StateCode">
        <xsd:restriction base="xsd:string">
          <xsd:enumeration value="OPEN"/>
          <xsd:enumeration value="CLOSED"/>
        </xsd:restriction>
      </xsd:simpleType>
      <xsd:complexType name="Loan">
        <xsd:sequence>
          <xsd:element name="Id" type="xsd:string"/>
          <xsd:element name="State" type="l:StateCode">
            <xsd:annotation><xsd:documentation>Whether the loan is still running.</xsd:documentation></xsd:annotation>
          </xsd:element>
          <xsd:element name="Parent" type="l:Loan" minOccurs="0"/>
        </xsd:sequence>
      </xsd:complexType>
      <xsd:element name="Caller"><xsd:complexType><xsd:sequence>
        <xsd:element name="System" type="xsd:string"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="GetLoans"><xsd:complexType><xsd:sequence>
        <xsd:element name="Borrower" type="xsd:string"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="GetLoansResponse"><xsd:complexType><xsd:sequence>
        <xsd:element name="Loan" type="l:Loan" minOccurs="0" maxOccurs="unbounded"/>
      </xsd:sequence></xsd:complexType></xsd:element>
    </xsd:schema>
  </wsdl:types>
  <wsdl:message name="CallerHeader"><wsdl:part name="caller" element="l:Caller"/></wsdl:message>
  <wsdl:message name="In"><wsdl:part name="parameters" element="l:GetLoans"/></wsdl:message>
  <wsdl:message name="Out"><wsdl:part name="parameters" element="l:GetLoansResponse"/></wsdl:message>
  <wsdl:portType name="Loans">
    <wsdl:operation name="GetLoans">
      <wsdl:documentation>Every loan of a borrower.</wsdl:documentation>
      <wsdl:input message="l:In"/>
      <wsdl:output message="l:Out"/>
    </wsdl:operation>
  </wsdl:portType>
  <wsdl:binding name="LoansSoap" type="l:Loans">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="GetLoans">
      <wsdl:input><soap:header message="l:CallerHeader" part="caller" use="literal"/><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
  </wsdl:binding>
</wsdl:definitions>
"""


@pytest.fixture
def ratings(tmp_path: Path) -> Path:
    spec = tmp_path / "ratings.yaml"
    spec.write_text(RATINGS, encoding="utf-8")
    return spec


@pytest.fixture
def loans(tmp_path: Path) -> Path:
    spec = tmp_path / "LoanService.wsdl"
    spec.write_text(LOANS_WSDL, encoding="utf-8")
    return spec


def fields(operation):
    return {f.path: f for f in operation.outputs}


def test_every_rest_operation_is_listed_with_what_it_takes_and_returns(ratings):
    digest = digest_location(ratings)

    assert (digest.title, digest.version, digest.category) == ("Ratings", "1.2.0", "REST")
    read, change = digest.operations
    assert (read.name, read.reads_only, read.summary) == ("GET /ratings/{id}", True, "Read one rating")
    assert change.reads_only is False
    [parameter] = read.inputs
    assert (parameter.path, parameter.type, parameter.required) == ("id", "string, in path", True)
    returned = fields(read)
    assert list(returned) == ["Value", "Kind", "History[]", "Agency", "Agency.Name", "Agency.Rated"]
    assert returned["Value"].required and not returned["Kind"].required
    assert returned["Kind"].allowed == ["Credit", "Risk"]
    assert returned["History[]"].type == "list of Rating"
    assert returned["Agency.Rated"].type == "string (date)"


def test_request_bodies_are_listed_at_the_top_level_only(ratings):
    change = digest_location(ratings).operations[1]

    assert [f.path for f in change.inputs] == ["id", "Value", "Kind", "History[]", "Agency"]
    assert change.inputs[1].type == "string, in body"


def test_a_wsdl_with_inline_types_lists_its_header_request_and_response(loans):
    digest = digest_location(loans)

    assert (digest.title, digest.version, digest.category) == ("LoanService", "3.1.0", "SOAP")
    [op] = digest.operations
    assert (op.name, op.summary, op.reads_only) == ("GetLoans", "Every loan of a borrower.", None)
    assert [f.path for f in op.inputs] == ["Caller/System", "GetLoans/Borrower"]
    returned = fields(op)
    assert list(returned) == ["GetLoansResponse/Loan[]", "GetLoansResponse/Loan[]/Id", "GetLoansResponse/Loan[]/State",
                              "GetLoansResponse/Loan[]/Parent"]
    assert returned["GetLoansResponse/Loan[]/State"].allowed == ["OPEN", "CLOSED"]
    assert returned["GetLoansResponse/Loan[]/State"].description == "Whether the loan is still running."
    assert not returned["GetLoansResponse/Loan[]"].required


PARTIES = """\
openapi: 3.0.1
info: {title: Parties, version: 1.0.0}
paths:
  /party:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  LegalStructure: {type: string, x-namespaced-enum: [UK.OBIE.Charity, UK.OBIE.Sole]}
                  Country: {type: string, pattern: '^[A-Z]{2}$'}
                  Kind: {type: string, enum: [A, B], pattern: '^[AB]$'}
"""


def test_namespaced_codes_and_patterns_are_listed(tmp_path):
    spec = tmp_path / "parties.yaml"
    spec.write_text(PARTIES, encoding="utf-8")
    out = tmp_path / "spec-digest-parties.md"

    returned = fields(digest_location(spec).operations[0])

    assert returned["LegalStructure"].allowed == ["UK.OBIE.Charity", "UK.OBIE.Sole"]
    assert returned["Country"].pattern == "^[A-Z]{2}$"
    assert main(["spec", "digest", str(spec), "--upstream", "parties", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "| `LegalStructure` | string | no | UK.OBIE.Charity, UK.OBIE.Sole |" in text
    assert "| `Country` | string | no | matches `^[A-Z]{2}$` |" in text
    assert "| `Kind` | string | no | A, B; matches `^[AB]$` |" in text


def test_an_xsd_pattern_is_listed(tmp_path):
    spec = tmp_path / "LoanService.wsdl"
    spec.write_text(LOANS_WSDL.replace(
        '<xsd:complexType name="Loan">',
        '<xsd:simpleType name="LoanId"><xsd:restriction base="xsd:string"><xsd:pattern value="L[0-9]{6}"/>'
        '</xsd:restriction></xsd:simpleType><xsd:complexType name="Loan">').replace(
        '<xsd:element name="Id" type="xsd:string"/>', '<xsd:element name="Id" type="l:LoanId"/>'), encoding="utf-8")

    returned = fields(digest_location(spec).operations[0])

    assert returned["GetLoansResponse/Loan[]/Id"].pattern == "L[0-9]{6}"


def test_operations_and_paths_compare_loosely():
    assert operation_key("`get  /ratings/{id}`") == "GET /ratings/{id}"
    assert path_key("`GetLoansResponse/Loan[]/Id`") == path_key("GetLoansResponse/Loan/Id")


def test_an_xsd_on_its_own_isnt_digested(tmp_path):
    xsd = tmp_path / "types.xsd"
    xsd.write_text('<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"/>', encoding="utf-8")

    with pytest.raises(DigestError, match="ask the BA for the WSDL"):
        digest_location(xsd)


def test_the_command_writes_a_digest_with_sections_to_fill_and_keeps_answers(ratings, tmp_path, capsys):
    out = tmp_path / "work" / "REQ-1" / "inputs" / "spec-digest-ratings.md"

    assert main(["spec", "digest", str(ratings), "--upstream", "ratings", "--out", str(out)]) == 0
    doc = read_markdown(out.read_text(encoding="utf-8"))
    assert doc.front_matter["upstream"] == "ratings"
    assert doc.front_matter["spec"] == ""
    assert [s.heading for s in doc.sections[1:]] == ["Summary", "Where the data is", "Not available",
                                                    "Open questions", "Operations"]
    text = out.read_text(encoding="utf-8")
    assert "**Returns:** response body (schema Rating, not part of the paths): the same fields as `GET /ratings/{id}`" \
        in text

    assert main(["spec", "digest", str(ratings), "--upstream", "ratings", "--out", str(out)]) == 1
    assert "--force" in capsys.readouterr().err


def test_the_customer_api_jar_is_digested(maven_repo):
    digest = digest_location(find_jar(UPSTREAM_1, [maven_repo]))

    customer = digest.operation("GET /customers/{id}")
    assert customer.reads_only
    assert digest.has_path(customer, "contactPreference.channelCode")
    assert not digest.operation("PUT /customers/{id}/contact-preference").reads_only


def test_the_customer_directory_jar_is_digested(maven_repo):
    digest = digest_location(find_jar(UPSTREAM_2, [maven_repo]))

    party = digest.operation("GetParty")
    assert [op.name for op in digest.operations] == ["GetParty", "GetBalance"]
    assert [f.path for f in party.inputs] == ["GetPartyRequest/PartyId"]
    assert digest.has_path(party, "GetPartyResponse/Party/Account[]/StatusCode")


def test_the_customer_directory_wsdl_is_digested_with_the_xsds_it_imports():
    digest = digest_location(SPECS / "com.example.upstream2" / "customer-directory-soap-spec" / "1.3.0" / "wsdl" /
                             "CustomerDirectoryService.wsdl")

    assert [op.name for op in digest.operations] == ["GetParty", "GetBalance"]
    assert digest.has_path(digest.operation("GetBalance"), "GetBalanceResponse/Balance[]/Amount/Value")
