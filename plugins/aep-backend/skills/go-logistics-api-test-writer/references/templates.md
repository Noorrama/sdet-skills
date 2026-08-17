# Copy-Paste Templates — Legacy/Proven Java Pattern

These are generalized from real code in the repo (with feature-specific business logic stripped
out and names replaced by `<Feature>` placeholders) — this is the pattern to default to for any
new endpoint in TMS, GoKilat/store, GoSend consumer, or GoBox, and is also safe for GoShop unless
the user explicitly wants the Kotlin rewrite (see `modern-kotlin-pattern.md`). Replace
`<Vertical>`, `<Feature>`, and field names to match your actual endpoint; keep the shape.

## 1. URL constant

```java
// src/main/java/properties/LogisticsProperties.java
// Add under the correct vertical's comment block — pick the SAME host constant an existing,
// analogous route in this vertical already uses. For TMS specifically, check whether the
// sibling route uses `tmsInternalHost` + "/tms/internal/..." or `gojekDriverHost` + "/tms/..."
// (no "internal") — see architecture.md §2 before guessing.
public static final String get<Feature>Url =
    String.format("%s/v1/<vertical>/<feature>/{id}", <verticalHost>);
```

## 2. Endpoint class

```java
// src/main/java/endpoint/<vertical>/<feature>/<Feature>Endpoint.java
package endpoint.<vertical>.<feature>;

import restidioms.security.core.entity.Param;
import restidioms.security.core.entity.RequestBody;
import restidioms.security.core.template.HttpMethod;
import restidioms.security.core.template.IServiceEndpoint;
import restidioms.security.core.template.UserType;
import core.models.headers.ConsumerHeaders;
import properties.LogisticsProperties;

import java.util.Collections;
import java.util.List;

public class <Feature>Endpoint implements IServiceEndpoint {

    private final ConsumerHeaders consumerHeaders;
    private final String id;                      // path param example
    private final <Feature>RequestDTO requestBody; // omit if this is a GET with no body

    public <Feature>Endpoint(ConsumerHeaders consumerHeaders, String id, <Feature>RequestDTO requestBody) {
        this.consumerHeaders = consumerHeaders;
        this.id = id;
        this.requestBody = requestBody;
    }

    @Override
    public String url() {
        return LogisticsProperties.get<Feature>Url;
    }

    @Override
    public HttpMethod httpMethod() {
        return HttpMethod.POST; // or GET/PUT/PATCH/DELETE as appropriate
    }

    @Override
    public UserType userType() {
        return UserType.CUSTOMER; // or DRIVER, depending on the vertical
    }

    @Override
    public List<Param> pathParameters() {
        return Collections.singletonList(new Param("id", id));
    }

    @Override
    public List<Param> queryParameters() {
        return null; // return a List<Param> if this endpoint takes query params
    }

    @Override
    public List<Param> headers() {
        return List.of(new Param("Authorization", "Bearer " + consumerHeaders.getToken()));
    }

    @Override
    public RequestBody body() {
        return new RequestBody(<Feature>RequestDTO.class, requestBody); // null if GET with no body
    }
}
```

If a vertical already has an abstract base (`endpoint/store/BaseStoreEndpoint.java`,
`endpoint/tms/DriverBaseEndPoint.java`) that fixes `userType()`/`headers()` for you, extend that
instead of implementing `IServiceEndpoint` from scratch — check the sibling endpoints in the same
package first.

## 3. Request/response DTOs

```java
// src/main/java/dto/<vertical>/<feature>/request/<Feature>RequestDTO.java
package dto.<vertical>.<feature>.request;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class <Feature>RequestDTO {
    @JsonProperty("order_id")
    private String orderId;
    private Drop drop;
    private Pickup pickup;
    private List<PaymentInstruction> paymentInstructions;

    @Data
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Drop {
        private double latitude;
        private double longitude;
        @JsonProperty("address")
        private String address;
    }
}
```

```java
// src/main/java/dto/<vertical>/<feature>/response/<Feature>ResponseDTO.java
package dto.<vertical>.<feature>.response;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import constants.api.HttpStatuses;
import lombok.Data;

import java.util.HashMap;
import java.util.List;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class <Feature>ResponseDTO {
    private String orderId;
    private String status;
    private List<ErrorDTO> errors;

    // Conventional thin-envelope fields on every response DTO in this codebase:
    private HttpStatuses statusCode;
    private HashMap<String, String> responseHeaders;
}
```

Only reach for Lombok `@Builder` instead of plain `@Data` setters if this DTO is constructed once,
from scratch, in code (not loaded from a JSON template and then mutated) — e.g.:

```java
@Data
@Builder
@JsonIgnoreProperties(ignoreUnknown = true)
public class <Feature>CreateRequestBody {
    private String name;
    private Map<String, Object> tags; // arbitrary/extra attributes, if the API supports them
}
// usage: <Feature>CreateRequestBody.builder().name("x").build();
```

## 4. Client method

Add to the vertical's existing `<Vertical>Client` (create one only if the vertical genuinely has
none). Always return `IAPIResponse` via `processAPIRequest` for new methods:

```java
// src/main/java/clients/<vertical>/<Vertical>Client.java
public class <Vertical>Client {
    private final RequestHandler handler = new RequestHandler();
    private final ConsumerHeaders headers;

    public <Vertical>Client(ConsumerHeaders headers) {
        this.headers = headers;
    }

    public IAPIResponse create<Feature>(String id, <Feature>RequestDTO requestBody) {
        <Feature>Endpoint endpoint = new <Feature>Endpoint(headers, id, requestBody);
        SecurityHelper.runSecurityScanIfRequired(endpoint); // matches existing sibling methods
        return handler.processAPIRequest(endpoint);
    }
}
```

## 5. Controller method

```java
// src/main/java/controller/<Feature>Controller.java  (flat package — no per-vertical subfolder)
public class <Feature>Controller {
    private final <Vertical>Client client;

    public <Feature>Controller(ConsumerHeaders headers) {
        this.client = new <Vertical>Client(headers);
    }

    // Happy-path: typed DTO return, no assertions in here (Refactoring.md's stated direction).
    public <Feature>ResponseDTO create<Feature>(String id, <Feature>RequestDTO requestBody) {
        IAPIResponse response = client.create<Feature>(id, requestBody);
        try {
            <Feature>ResponseDTO dto = response.deserialize(<Feature>ResponseDTO.class);
            dto.setStatusCode(response.getStatusCode());
            return dto;
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to deserialize <Feature> response", e);
        }
    }

    // Negative/error path: some verticals define a distinct method returning an error-shaped DTO
    // instead of overloading the happy-path method — check what sibling Controllers in this
    // vertical already do and match it.
    public <Feature>ErrorResponseDTO create<Feature>Error(String id, <Feature>RequestDTO requestBody) {
        IAPIResponse response = client.create<Feature>(id, requestBody);
        try {
            return response.deserialize(<Feature>ErrorResponseDTO.class);
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to deserialize <Feature> error response", e);
        }
    }
}
```

## 6. Assertion class

```java
// src/test/java/assertions/<domain>/<Feature>Assertion.java
package assertions.<domain>;

import org.testng.asserts.SoftAssert;

public class <Feature>Assertion {

    // Accept SoftAssert as a parameter — don't instantiate one as an instance field here.
    public void verify<Feature>Success(SoftAssert softAssert, <Feature>ResponseDTO response, <Feature>RequestDTO expectedRequest) {
        softAssert.assertEquals(response.getStatusCode().getCode(), 200);
        softAssert.assertEquals(response.getOrderId(), expectedRequest.getOrderId());
        softAssert.assertEquals(response.getStatus(), "created");
    }

    // Negative: status code TOGETHER WITH a specific error code/message, never status alone.
    public void verify<Feature>NotFound(SoftAssert softAssert, <Feature>ErrorResponseDTO response) {
        softAssert.assertEquals(response.getStatusCode().getCode(), 404);
        softAssert.assertEquals(response.getErrors().get(0).getCode(), "not_found");
        softAssert.assertEquals(response.getErrors().get(0).getMessage(), "<Feature> not found");
    }

    // "Router" pattern — use when one data-provider-driven test method needs to validate several
    // status-code-keyed outcomes with a single assertion call (mirrors CalculateAssertions /
    // ShipmentAssertion in the real codebase).
    public void verify<Feature>ByExpectedStatus(SoftAssert softAssert, int expectedStatusCode, Object response) {
        switch (expectedStatusCode) {
            case 200:
                verify<Feature>Success(softAssert, (<Feature>ResponseDTO) response, null);
                break;
            case 404:
                verify<Feature>NotFound(softAssert, (<Feature>ErrorResponseDTO) response);
                break;
            default:
                softAssert.fail("Unhandled status code in test case: " + expectedStatusCode);
        }
    }
}
```

## 7. Base test class + DataProvider (only if you need a new one — usually you extend an existing one)

```java
// src/test/java/<vertical>/<feature>/<Feature>BaseTest.java
package <vertical>.<feature>;

import helpers.GologisticBaseHelper; // or the vertical's own nearest base — see architecture.md §3
import org.testng.annotations.DataProvider;
import utilities.ReadFile;
import utilities.Utilities;

public class <Feature>BaseTest extends GologisticBaseHelper {

    @DataProvider(name = "create<Feature>")
    public Object[][] create<Feature>Cases() {
        String json = ReadFile.readFileAsString(<Vertical>FilePaths.CREATE_<FEATURE>_CASES);
        <Feature>Cases cases = (<Feature>Cases) Utilities.convertJsonToListDTO(json, <Feature>Cases.class.getCanonicalName());
        Object[][] data = new Object[cases.getCases().size()][1];
        for (int i = 0; i < cases.getCases().size(); i++) {
            data[i][0] = cases.getCases().get(i);
        }
        return data;
    }
}
```

## 8. Test class — positive + negative method pair

```java
// src/test/java/<vertical>/<feature>/<Feature>Tests.java
package <vertical>.<feature>;

import com.gojek.Ownership;
import com.gojek.TestInfo;
import common.constants.test.TestGroups;
import org.testng.Assert;
import org.testng.annotations.Test;
import org.testng.asserts.SoftAssert;
import retrier.RetryAnalyzer;
import utilities.GojekEngineer;

public class <Feature>Tests extends <Feature>BaseTest {

    @Test(
        groups = {TestGroups.<SOME_EXISTING_OR_NEW_GROUP>},
        dataProvider = "create<Feature>",
        retryAnalyzer = RetryAnalyzer.class // only if genuinely flaky/timing-sensitive
    )
    @TestInfo(projectId = "<PROJECT_ID>", suiteId = "<SUITE_ID>", owner = "<owner>", testCaseIds = {"<REAL_TESTRAIL_ID_OR_TODO>"})
    @Ownership(author = GojekEngineer.<SOME_ENGINEER>)
    public void verify<Feature>ForCase(<Feature>Case testCase) {
        Reporter.log("<b>Verifying <Feature>: " + testCase.getCase_description() + "</b>");

        Consumer consumer = provideConsumer();
        ConsumerHeaders headers = new ConsumerHeaders(consumer.getToken(), new CountryAndLanguage(Country.INDONESIA));
        <Feature>Controller controller = new <Feature>Controller(headers);

        SoftAssert softAssert = new SoftAssert();
        int expectedStatus = testCase.getAssertions().getStatus_code();

        if (expectedStatus == 200) {
            <Feature>ResponseDTO response = controller.create<Feature>(testCase.getId(), testCase.toRequestDTO());
            new <Feature>Assertion().verify<Feature>Success(softAssert, response, testCase.toRequestDTO());
        } else {
            <Feature>ErrorResponseDTO response = controller.create<Feature>Error(testCase.getId(), testCase.toRequestDTO());
            new <Feature>Assertion().verify<Feature>NotFound(softAssert, response);
        }
        softAssert.assertAll();
    }

    // Pure negative, no data provider — mirrors e.g. ShipmentTests.verifyCancellationInvalidShipment
    @Test(groups = {TestGroups.<SOME_EXISTING_OR_NEW_GROUP>})
    @TestInfo(projectId = "<PROJECT_ID>", suiteId = "<SUITE_ID>", owner = "<owner>", testCaseIds = {"<REAL_TESTRAIL_ID_OR_TODO>"})
    @Ownership(author = GojekEngineer.<SOME_ENGINEER>)
    public void verify<Feature>WithInvalidId() {
        Consumer consumer = provideConsumer();
        ConsumerHeaders headers = new ConsumerHeaders(consumer.getToken(), new CountryAndLanguage(Country.INDONESIA));
        <Feature>Controller controller = new <Feature>Controller(headers);

        <Feature>ErrorResponseDTO response = controller.create<Feature>Error("invalid-id-1234", null);
        Assert.assertEquals(response.getStatusCode().getCode(), 404);
        Assert.assertEquals(response.getErrors().get(0).getMessage(), "<Feature> not found");
    }
}
```

Notes on the skeleton above:
- If a scenario's precondition can't be met (an unrelated upstream error, an ID that never got
  generated), `throw new SkipException("...")` instead of failing.
- If the vertical's real DTOs don't need a distinct `*ErrorResponseDTO` (some verticals reuse the
  same response DTO for both, with `errors` populated only on failure), don't invent one — match
  what sibling test/DTO files in that package already do.
- `Consumer`, `ConsumerHeaders`, `CountryAndLanguage`, `Country` are the shared auth/locale types
  described in `architecture.md` §4 — import from wherever the sibling test files in the same
  package import them from.
