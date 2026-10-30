# The upstreams' specs

Made up, for the kit's tests, each in a folder named by its Maven coordinates: `<groupId>/<artifactId>/<version>/`.
The `maven_repo` fixture packs each folder into a jar in a Maven repository folder, as an upstream team publishes it.

- **upstream-1, the customer API** (`com.example.upstream1:customer-api-spec:4.2.0`, OpenAPI): one customer, with how
  they want to be contacted.
- **upstream-2, the customer directory** (`com.example.upstream2:customer-directory-soap-spec:1.3.0`, a WSDL and its
  XSDs): who the customer is, their accounts, and each account's balances.
