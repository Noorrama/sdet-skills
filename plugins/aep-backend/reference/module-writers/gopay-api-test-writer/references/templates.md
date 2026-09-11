# Full code templates

Copy these and adapt names/fields. All examples are drawn from the real miniapp/parking
packages in this repo — check the actual sibling file in the target package before assuming
a detail (error field cardinality, header set, builder annotation) hasn't changed.

## 1. Endpoint (GET, header-auth only)

```java
package com.gopay.backendtests.apis.gopayAPIs.miniapp.<feature>;

import com.gopay.backendtests.apis.gopayAPIs.miniapp.common.BaseEndpoint;
import com.gopay.backendtests.core.entity.Param;
import com.gopay.backendtests.core.template.HttpMethod;
import com.gopay.backendtests.properties.GopayProperties;

import java.util.List;
import java.util.Map;

public class <Feature>Endpoint<T> extends BaseEndpoint<T> {
    public <Feature>Endpoint(T params) { super(params); }

    @Override public String url() { return GopayProperties.<urlConstantName>; }
    @Override public List<Param> pathParameters() { return null; }
    @Override public HttpMethod httpMethod() { return HttpMethod.GET; }
    @Override public List<Param> headers() {
        if (params instanceof Map) {
            Map<String, String> paramMap = (Map<String, String>) params;
            return List.of(new Param("Authorization", paramMap.getOrDefault("bearerToken", "")));
        }
        return List.of();
    }
}
```

## 2. Endpoint (POST with a typed request body)

```java
package com.gopay.backendtests.apis.gopayAPIs.miniapp.<feature>;

import com.gopay.backendtests.apis.gopayAPIs.miniapp.common.BaseEndpoint;
import com.gopay.backendtests.core.entity.Param;
import com.gopay.backendtests.core.entity.RequestBody;
import com.gopay.backendtests.core.template.HttpMethod;
import com.gopay.backendtests.core.template.UserType;
import com.gopay.backendtests.properties.GopayProperties;

import java.util.List;
import java.util.Map;
import java.util.UUID;

public class <Feature>Endpoint<T, R> extends BaseEndpoint<T> {
    private final Class requestBodyClass;
    public <Feature>Endpoint(T params, Class<R> requestBodyClass) {
        super(params);
        this.requestBodyClass = requestBodyClass;
    }

    @Override public String url() { return GopayProperties.<urlConstantName>; }
    @Override public HttpMethod httpMethod() { return HttpMethod.POST; }
    @Override public List<Param> headers() {
        if (params instanceof Map) {
            Map<String, Object> paramMap = (Map<String, Object>) params;
            return List.of(
                new Param("Content-Type", "application/json"),
                new Param("Request-Id", UUID.randomUUID().toString()),
                new Param("Authorization", (String) paramMap.getOrDefault("bearerToken", ""))
            );
        }
        return List.of();
    }
    @Override public RequestBody body() {
        if (params instanceof Map) return new RequestBody(requestBodyClass, ((Map<?, ?>) params).get("requestBody"));
        return null;
    }
    @Override public UserType userType() { return null; }
}
```

## 3. RequestBody POJO

```java
package com.gopay.backendtests.apis.gopayAPIs.miniapp.<feature>;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Getter;
import lombok.Setter;
import lombok.experimental.SuperBuilder;
// use lombok.Builder + @NoArgsConstructor + @AllArgsConstructor instead of @SuperBuilder
// if this POJO has no builder-inheritance needs

@Getter @Setter @SuperBuilder
public class <Feature>RequestBody {
    private String someField;
    private Amount amount;

    @Getter @Setter @SuperBuilder @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Amount {
        public String currency;
        public int value;
    }
}
```

## 4. Response POJO

```java
package com.gopay.backendtests.apis.gopayAPIs.miniapp.<feature>;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.gopay.backendtests.apis.gopayAPIs.miniapp.common.BaseResponse;
import lombok.Getter;
import lombok.Setter;

@Getter @Setter
public class <Feature>Response extends BaseResponse<<Feature>Response.Data, <Feature>Response.Errors> {
    private Data data;
    private Errors error; // check sibling responses: some use List<Errors> instead

    @Getter @Setter @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Data {
        private String someField;
    }

    @Getter @Setter @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Errors {
        private String code;
        private String description;
    }
}
```

## 5. Client method (add inside `MiniAppClient.java`)

```java
// Simple GET, no body
public <Feature>Response <methodName>(String bearerToken) {
    Map<String, String> params = Map.of("bearerToken", "Bearer " + bearerToken);
    <Feature>Endpoint endpoint = new <Feature>Endpoint(params);
    Response response = new RequestHandler().processRequest((IServiceEndpoint) endpoint);
    <Feature>Response result = response.as(<Feature>Response.class);
    result.setHttpStatusCode(response.getStatusCode());
    return result;
}

// POST with a request body
public <Feature>Response <methodName>(String authToken, <Feature>RequestBody requestBody) {
    Map<String, Object> params = Map.of("bearerToken", authToken, "requestBody", requestBody);
    <Feature>Endpoint endpoint = new <Feature>Endpoint(params, <Feature>RequestBody.class);
    Response response = new RequestHandler().processRequest((IServiceEndpoint) endpoint);
    <Feature>Response result = response.as(<Feature>Response.class);
    result.setHttpStatusCode(response.getStatusCode());
    return result;
}
```

Always: build Endpoint -> `RequestHandler().processRequest(...)` -> `.as(ResponseClass.class)`
-> `setHttpStatusCode(response.getStatusCode())` -> return. Don't drop the status-code line;
every downstream assertion on `response.getHttpStatusCode()` depends on it.

## 6. Helper method (add inside `MiniAppHelper.java`)

```java
// Thin delegate — no body to assemble
public <Feature>Response <methodName>(String bearerToken) {
    return this.miniAppClient.<methodName>(bearerToken);
}

// Assembles a RequestBody from primitive args + constants before delegating
public <Feature>Response <methodName>(String authToken, int amt, String currency, String description) {
    <Feature>RequestBody.Amount amount = <Feature>RequestBody.Amount.builder()
            .currency(currency).value(amt).build();
    <Feature>RequestBody requestBody = <Feature>RequestBody.builder()
            .amount(amount).someField(description).build();
    return this.miniAppClient.<methodName>(authToken, requestBody);
}
```

## 7. Test class

```java
package userJourneyTests.userspend.miniapp.<feature>;

import com.gojek.TestInfo;
import com.gopay.backendtests.apis.gopayAPIs.miniapp.<feature>.<Feature>Response;
import com.gopay.backendtests.constants.UserSpendOwnerEmail;
import com.gopay.backendtests.helpers.miniAppHelper.MiniAppHelper;
import com.gopay.backendtests.utils.Categories;
import com.gopay.backendtests.utils.Countries;
import com.gopay.backendtests.utils.customer.Customer;
import com.gopay.backendtests.utils.customer.CustomerGroup;
import constants.SuiteConstants;
import org.apache.http.HttpStatus;
import org.testng.Assert;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.Test;
import testBase.TestBase;

import static com.gopay.backendtests.testData.GopayError.*;
import static com.gopay.backendtests.testData.MiniAppEnvConfig.*;

public class <Feature>Tests extends TestBase {
    protected MiniAppHelper miniAppHelper;
    protected Customer customer;

    @BeforeClass(alwaysRun = true)
    public void setUp() {
        miniAppHelper = new MiniAppHelper();
        customer = customerHelper.getCustomer(CustomerGroup.MINI_APP_USER);
    }

    @Test(groups = {Categories.MINI_APP, Categories.MINI_APP_SMOKE, Countries.ID})
    @TestInfo(projectId = SuiteConstants.GOPAY_PROJECT_ID, suiteId = SuiteConstants.US_MINI_APP_SUITE_ID,
              owner = UserSpendOwnerEmail.<OWNER>, testCaseIds = {"<PLACEHOLDER-TESTRAIL-ID>"})
    public void verify<HappyPathScenario>() {
        <Feature>Response response = miniAppHelper.<methodName>(customer.getBearerToken());
        Assert.assertEquals(response.getHttpStatusCode(), HttpStatus.SC_OK, "Status code should be 200");
        Assert.assertTrue(response.isSuccess(), "Response should be successful");
    }

    @Test(groups = {Categories.MINI_APP, Categories.MINI_APP_REGRESSION, Countries.ID})
    @TestInfo(projectId = SuiteConstants.GOPAY_PROJECT_ID, suiteId = SuiteConstants.US_MINI_APP_SUITE_ID,
              owner = UserSpendOwnerEmail.<OWNER>, testCaseIds = {"<PLACEHOLDER-TESTRAIL-ID>"})
    public void verify<ErrorScenario>() {
        <Feature>Response response = miniAppHelper.<methodName>(INVALID_TOKEN);
        Assert.assertEquals(response.getHttpStatusCode(), HttpStatus.SC_UNAUTHORIZED, "Status code should be 401");
        Assert.assertFalse(response.isSuccess(), "Response should not be successful");
    }
}
```

## Parking-style variant notes

Parking has no dedicated Helper/Client — it reuses the shared `CustomerAdapterClient` plus a
`<Feature>Builder` class living inside the test tree (e.g.
`userJourneyTests.userspend.parking.skyparking.common.SkyParkingBuilder`), and often wires
fixtures in the test class constructor + `@BeforeMethod` instead of `@BeforeClass`:

```java
public <Feature>Tests() {
    this.customerAdapterClient = new CustomerAdapterClient();
    this.customer = new GopayIndonesiaStagingUsersData().getParkingCustomer();
    this.builder = new <Feature>Builder();
}

@BeforeMethod(alwaysRun = true)
public void testDataSetup() {
    qrCode = ParkingCode.existingSkyParkingQRCode();
}
```

Use this shape when the target folder is under `userspend/parking/**` (or the user says the
domain has no existing Helper class); use the miniapp shape otherwise.
