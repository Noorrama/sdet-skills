# Location identification (TDP-grounded)

TDP models location only at the **service-area** granularity — country-level operating zones with
a lock/status lifecycle — not the fine-grained geo primitives (`stop location`, `route distance`,
pickup/drop coordinates) that `../test_data_domains.md`'s LOCATION section describes. Identify
against what actually exists before falling back to that file's illustrative signals.

## What TDP actually models: service areas

Controller: `ServiceAreaController.java` (`/aep/test-data-generator/`):

| Endpoint | Purpose |
|---|---|
| `GET /service-areas/{countryCode}` | List service areas for a country |
| `GET /service-areas/{countryCode}/get` · `GET /service-areas/{countryCode}/fetchAvailable` | Fetch / fetch-available variants |
| `PUT /service-areas/update` | Update a service area |
| `PUT /service-areas/{serviceAreaId}/release` | Release a lock on one service area |
| `POST /service-areas/restricted-areas` · `GET /service-areas/restricted-areas` · `PUT /service-areas/releaseRestrictedServiceArea` | Restricted-area set management |

Model: `ServiceAreaModel.java` (`@Document(collection = "service_areas")`) — `serviceAreaId` (`@Id`,
int), `serviceAreaName`, `country`, `slaInMinutes`, `timezone`, `currency`, `isRestrictedSA`
(boolean), `status`, `lockedOn`, `insertedOn`, `updatedOn`.

Status enum, `ServiceAreaStatus.java`, verbatim: `AVAILABLE`, `LOCKED`, `INVALID`.

Service: `ServiceAreaService.java` — `updateServiceArea`, `setRestrictedServiceAreas`,
`getListOfServiceAreaByCountryCode`, `getRestrictedServiceAreaList`, `getAvailableServiceArea`,
`releaseLockedServiceArea`, `releaseRestrictedServiceArea`, `findAndLockServiceArea`. Locking is
generic infrastructure shared via `GenericLockEntityService` / `GenericLockEntityController`
(`GenericEntityLockModel.java`) — a service area is fetched under a lock, then released, the same
shape as a pooled account being engaged and freed.

## Polygon — a driver-fleet tag, not a location entity

`../test_data_domains.md` lists `Polygon` as a LOCATION signal, but in this codebase it is purely a
**driver-side fleet-zone tag**, with no standalone `Polygon` class:

| Code | Role |
|---|---|
| `DriverModel.java` — `polygonTag` field | Tags a driver with a delivery polygon |
| `DriverFleetMigrationService.java` — `POLYGON_TAG_PREFIX = "polygon/daily-income-delivery\|"` | Prefix convention for the tag value |
| `GetTestDataRequest.java`, `AddCategoryRequest.java` — `polygonId` filter | Selects/filters pooled drivers by polygon |
| `TestDataPoolingController.java` — `PUT /sdf1/add-polygon` | Assigns a polygon to a driver |

So "a driver associated with a polygon" is a **Driver** identification
(`../driver/index.md`) plus this tag, per the parent skill's disambiguation rule ("Driver-to-polygon
association → DRIVER. Standalone stops/routes → LOCATION" — `../test_data_domains.md`). A fixture
naming a polygon in isolation, with no driver, has no code path to serve it.

## What is absent

No hits anywhere for `serviceAreaId` used as a route/stop concept beyond the field itself, no
"route distance", no "stop location" entity, no static-pooling-of-coordinates model. The LOCATION
domain's `Stop location`, `Route distance`, `Pickup`, `Drop`, `Coordinates` signals
(`../test_data_domains.md`) have no corresponding model or endpoint — TDP's location data stops at
"which service area, and is it locked/restricted", not fine-grained geography.

## Identification consequence

- A fixture naming a **country + service area name/status** ("an available service area in ID",
  "a restricted service area") → `TDP_SUPPORTED` via `ServiceAreaController`/`ServiceAreaModel`.
- A fixture naming a **driver-polygon association** → Driver domain
  (`../driver/index.md`) plus the polygon tag/`add-polygon` operation, not a standalone LOCATION
  record.
- A fixture naming **pickup/drop coordinates, route distance, or standalone stop locations** → no
  TDP category or operation exists; route to `TESTBUDDY_OPERATION_FALLBACK` only if a live
  TestBuddy/Pertamax/GBT location tool is confirmed in the MCP inventory; `TDP_PARTIAL` when the
  service area resolves and only the route/stop geometry is unserved, else `TDP_NOT_SUPPORTED` —
  per the parent skill's worked example (`FETCH_LOCATION`), verify the tool is real before citing
  it, don't assume it from that example.

## Where the rest lives

`serviceAreaId` also appears as a booking-request field on `GetBookingRequest.java` — a booking's
service area is a precondition supplied at booking time
([../workflow/index.md](../workflow/index.md)), not a separately provisioned LOCATION fixture.
