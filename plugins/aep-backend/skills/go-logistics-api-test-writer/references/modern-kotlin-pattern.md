# The "Modern" Kotlin Pattern (GoShop scaffold) — Use With Caution

`go-logistics/Refactoring.md` describes a target convention (`IAPIResponse`,
`processAPIRequest`, `deserializeKt`, no assertions in controllers). The **only** place that
target convention is fully, consistently implemented is a Kotlin scaffold under
`src/main/kotlin/goShop/{clients,controllers,endpoints}/**` (plus the shared `common/` Kotlin
utilities). **As of this research pass, no test class anywhere in the repo calls into this
scaffold** — every real GoShop `@Test` (`src/test/java/goShop/*.java`) calls the *legacy* Java
`controller.GoShopController` / `clients.goShop.GoShopClient` / `endpoint.goShop.*` classes,
which happen to live in same-named-but-different packages. The Kotlin tree compiles and looks
production-ready, but it is unexercised — treat it as a design reference, not a battle-tested
path, until you've actually run a test through it.

**When to use this file instead of `templates.md`**: only when the user explicitly asks for the
Refactoring.md-style rewrite, or you're extending GoShop's Kotlin layer specifically (adding a
new endpoint/client/controller method alongside the existing ones in
`src/main/kotlin/goShop/**`). For every other vertical (TMS, GoKilat/store, GoSend consumer,
GoBox), and for GoShop unless told otherwise, use the proven Java pattern in `templates.md`.

## The core abstractions (defined externally, in `aep-backend-core`, not in this repo)

```java
// restidioms/security/core/entity/IAPIResponse.java
public interface IAPIResponse extends ISerialization, IJsonParser, IJsonSchemaValidator {
    String getResponseText();
    HttpStatuses getStatusCode();
    String getHeaderValue(String key);
    HashMap<String, String> getAllHeaders();
}
```
```java
// restidioms/security/core/entity/RestAssuredResponse.java — the sole implementation
public <T> T deserializeKt(Class<T> cls) throws IOException {
    Moshi serializer = new Moshi.Builder().add(new KotlinJsonAdapterFactory()).build();
    return serializer.adapter(cls).fromJson(this.responseText);
}
public <T> T deserialize(Class<T> cls) throws JsonProcessingException {
    return new ObjectMapper().readValue(this.responseText, cls);
}
```
```java
// restidioms/security/utility/RequestHandler.java
public Response processRequest(IServiceEndpoint e) { return makeRequest(e); }
public IAPIResponse processAPIRequest(IServiceEndpoint e) { return new RestAssuredResponse(makeRequest(e)); }
```
Both entry points funnel through the *same* RestAssured request-building/signing/retry/logging
code (`makeRequest`) — the refactor is purely about the return-type contract at the call site,
not a different transport.

```kotlin
// core.restidioms.BaseConsumerEndpoint — sane defaults for a customer-facing GET
abstract class BaseConsumerEndpoint(val headers: ConsumerHeaders) : IServiceEndpoint {
    override fun userType(): UserType = UserType.CUSTOMER
    override fun httpMethod(): HttpMethod = HttpMethod.GET
    override fun queryParameters(): List<Param>? = null
    override fun pathParameters(): List<Param>? = null
    override fun headers(): List<Param> = APIHeaderGenerator.getConsumerHeaders(this.headers)
    override fun body(): RequestBody? = null
}
```
Subclasses override only what differs — this is the biggest ergonomic win vs. the Java
`IServiceEndpoint` implementers, which must define every method by hand.

## Full worked example (endpoint -> client -> controller), generalized from the real
`NearByMerchants`/`Calculate` flow

**Endpoint** (query-param GET):
```kotlin
// src/main/kotlin/goShop/endpoints/<feature>/<Feature>EndPointV1.kt
class <Feature>EndPointV1(headers: ConsumerHeaders) : BaseConsumerEndpoint(headers) {
    var pageSize: Int = 10
    var pageNum: Int = 1
    override fun url() = GoShopUrls.v1<Feature>
    override fun httpMethod() = HttpMethod.GET
    override fun queryParameters(): MutableList<Param>? =
        arrayListOf(Param("pagesize", pageSize.toString()), Param("pagenum", pageNum.toString()))
}
```

**Endpoint** (POST with body — body is ALWAYS a pre-serialized JSON `String`, never the typed
request object passed straight in):
```kotlin
// src/main/kotlin/goShop/endpoints/<feature>/Post<Feature>EndPointV1.kt
class Post<Feature>EndPointV1(headers: ConsumerHeaders, val body: String) : BaseConsumerEndpoint(headers) {
    override fun url() = GoShopUrls.v1<Feature>
    override fun httpMethod() = HttpMethod.POST
    override fun body() = RequestBody(String::class.java, body)
}
```

**Serializer object** (loads a JSON template, converts request DTO <-> JSON string via Moshi):
```kotlin
// src/main/kotlin/goShop/endpoints/<feature>/<Feature>SerializerV1.kt
object <Feature>SerializerV1 {
    private val requestSerializer = BaseHelper().serializer.adapter(<Feature>RequestV1::class.java)!!
    fun getBodyFromTemplate(): <Feature>RequestV1 {
        val file = GoShopFilePaths.<FEATURE>_TEMPLATE.readFile()
        return requestSerializer.fromJson(file)!!
    }
    fun convertToRequestBodyString(body: <Feature>RequestV1): String = requestSerializer.toJson(body)!!
}
```

**Request/response DTOs** (Moshi, not Lombok):
```kotlin
// src/main/kotlin/goShop/endpoints/<feature>/request/<Feature>RequestV1.kt
@JsonClass(generateAdapter = true)
data class <Feature>RequestV1(
    @Json(name = "order_id") var orderId: String,
    @Json(name = "reason_id") var reasonId: Int
)

// src/main/kotlin/goShop/endpoints/<feature>/response/<Feature>ResponseV1.kt
@JsonClass(generateAdapter = true)
data class <Feature>ResponseV1(
    val orderId: String? = null,
    val status: String? = null,
    val items: List<Item>? = listOf()
) {
    @JsonClass(generateAdapter = true)
    data class Item(val id: String = "", val name: String = "")
}
```

**Builder** (hand-rolled fluent class, always seeds from the template — this is NOT a Lombok
`@Builder` and does not use Kotlin `copy()`):
```kotlin
// src/main/kotlin/goShop/endpoints/<feature>/request/<Feature>RequestBuilderV1.kt
class <Feature>RequestBuilderV1(val bearerToken: String) {
    private val request: <Feature>RequestV1 = <Feature>SerializerV1.getBodyFromTemplate()
    fun setOrderId(orderId: String): <Feature>RequestBuilderV1 { request.orderId = orderId; return this }
    fun setReasonId(reasonId: Int): <Feature>RequestBuilderV1 { request.reasonId = reasonId; return this }
    fun build(): <Feature>RequestV1 = request
}
```

**Client**:
```kotlin
// src/main/kotlin/goShop/clients/GoShopConsumerClient.kt (add a method here)
class GoShopConsumerClient(bearerId: String, var language: Language = Language.ENGLISH) : BaseClient() {
    private val headers = ConsumerHeaders(bearerId, CountryAndLanguage(Country.INDONESIA, isLocalLanguage(language)))

    fun post<Feature>V1(requestBody: String): IAPIResponse {
        val endPoint = Post<Feature>EndPointV1(headers, requestBody)
        runSecurityScanIfRequired(endPoint)
        return requestHandler.processAPIRequest(endPoint)
    }
}
```

**Controller** (thin wrapper, one line of actual logic — no try/catch needed since Kotlin
doesn't enforce Java's checked exceptions, and no embedded assertions per Refactoring.md):
```kotlin
// src/main/kotlin/goShop/controllers/<Feature>ControllerV1.kt
class <Feature>ControllerV1(token: String) {
    private val client = GoShopConsumerClient(token)

    fun post<Feature>V1(requestBody: <Feature>RequestV1): <Feature>ResponseV1? {
        val bodyString = <Feature>SerializerV1.convertToRequestBodyString(requestBody)
        val response = client.post<Feature>V1(bodyString)
        return response.deserializeKt(<Feature>ResponseV1::class.java)
    }

    // Raw pass-through variant, for callers that want the unparsed IAPIResponse (e.g. to check
    // status code directly on a negative path) rather than a typed DTO:
    fun post<Feature>V1ForRawResponse(requestBody: <Feature>RequestV1): IAPIResponse {
        val bodyString = <Feature>SerializerV1.convertToRequestBodyString(requestBody)
        return client.post<Feature>V1(bodyString)
    }
}
```

## Two real pitfalls to watch for if you write in this style

1. **Missing `@JvmOverloads` breaks Java callers of Kotlin default parameters, silently, until
   someone actually tries it.** None of the classes in `src/main/kotlin/goShop/**` use
   `@JvmOverloads`, even though several declare default parameters
   (`GoShopConsumerClient(bearerId: String, var language: Language = Language.ENGLISH)`,
   `<Feature>RequestBuilderV1(bearerToken, countryAndLanguage = CountryAndLanguage(...))`).
   Since every `@Test` class in this repo is Java, and Kotlin only generates the single
   full-arity signature for Java consumption unless `@JvmOverloads` is present, a Java test
   calling `new GoShopConsumerClient(token)` (omitting `language`) **will not compile** without
   it. If you write a new Kotlin class in this tree that a Java test is meant to call, add
   `@JvmOverloads` to any constructor/function with default parameters.
2. **Always use named arguments when calling these Kotlin functions**, especially ones with
   multiple adjacent same-typed parameters. A real, currently-undetected bug exists in this exact
   tree: `NearByMerchantsControllerV1` calls its client as
   `client.getNearByMerchantsV1(pagenum, pagesize, lat, long, c2c)`, but the client's actual
   parameter order is `(pagesize, pagenum, lat, long, c2c)` — the two `Int` args are silently
   swapped. It's gone unnoticed only because nothing tests that path. Don't repeat this — call
   with named arguments (`client.getNearByMerchantsV1(pagesize = pageSize, pagenum = pageNum,
   ...)`) whenever there's any ambiguity.

## `@JvmStatic` for Kotlin `@DataProvider`s

If you add a TestNG `@DataProvider` inside a Kotlin `object` (the existing example is
`goShop/dataProviders/GoShopDataProviders.kt`), mark it `@JvmStatic` — without it, TestNG's Java
reflection can't invoke it, since a Kotlin `object`'s members are otherwise only exposed via an
`INSTANCE` field from Java's point of view:
```kotlin
object <Feature>DataProviders {
    @DataProvider(name = "create<Feature>")
    @JvmStatic
    fun create<Feature>Cases(): Array<Array<Any>> { ... }
}
```

## If you go this route, verify it actually works

Because this pattern has no existing test to point to as proof it's wired correctly end-to-end
in this exact repo, **compile and run whatever you write through it** (or ask the user to) before
calling the task done — don't assume it works just because it matches the shape described here
and in `Refactoring.md`.
