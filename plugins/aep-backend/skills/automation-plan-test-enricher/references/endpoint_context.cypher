// Endpoint → existing-coverage context for one (module, endpoint) pair.
//
// Parameters (bound by the caller — never string-interpolated):
//   $module   e.g. "transport"
//   $endpoint the route as written in the source, with the String.format host
//             placeholder already stripped by the caller and the HTTP verb
//             removed, e.g. "/v1/internal/user/{userId}"
//
// `endpoint` is NOT compared with `=`. e.path holds whatever the Java literal
// spelled, which differs from an OpenAPI-style path in three ways that all
// break an equality match:
//   - the placeholder NAME comes from the source ({orderNumber}, {company_id},
//     or a bare {} when url() concatenated string literals), never from the
//     caller
//   - the ?query=string is part of e.path for some endpoints and absent for
//     others, as in ".../estimate?service_type={id}"
//   - a parameter that ended the route leaves an empty trailing segment
//
// So compare segment by segment and treat a placeholder on EITHER side as a
// wildcard. This stays anchored — same segment count, every static segment must
// agree — so unlike CONTAINS it cannot pull in sibling endpoints
// (".../payment-options/{id}/block") and multiply the whole query cost by
// however many extras got swept in.
WITH
  $module AS module,
  $endpoint AS endpoint

WITH module, endpoint, split(split(endpoint, "?")[0], "/") AS want
MATCH (e:Endpoint)
WITH module, endpoint, want, e, split(split(e.path, "?")[0], "/") AS got
WHERE size(got) = size(want)
  AND all(i IN range(0, size(want) - 1) WHERE
        got[i] = want[i]
        OR want[i] STARTS WITH "{" OR want[i] = ""
        OR got[i] STARTS WITH "{" OR got[i] = "")

// Rank candidates so the wildcard tolerance never costs precision when a better
// match exists: an exact string match beats a placeholder-only match, and among
// those, a candidate whose placeholders sit in the SAME positions as the input
// beats one where a wildcard landed on a static sibling segment (input
// /v1/a/{id} would otherwise match a literal /v1/a/status just as well).
WITH module, endpoint, want, e, got,
     CASE WHEN split(e.path, "?")[0] = split(endpoint, "?")[0] THEN 0 ELSE 100 END
     + reduce(pen = 0, i IN range(0, size(want) - 1) |
         CASE WHEN (want[i] STARTS WITH "{" OR want[i] = "")
                <> (got[i] STARTS WITH "{" OR got[i] = "")
              THEN pen + 1 ELSE pen END) AS score

MATCH (def:File)-[:CONTAINS]->(e)
WHERE def.path CONTAINS module
WITH module, collect({e: e, def: def, score: score}) AS cands
WITH module, cands,
     reduce(best = 9999, c IN cands | CASE WHEN c.score < best THEN c.score ELSE best END) AS best
UNWIND cands AS c
WITH module, best, c
WHERE c.score = best
WITH DISTINCT c.e AS e, c.def AS def, module
LIMIT 5

// role <> "test" here: test coverage is tracked precisely and separately
// below via the method-level CALLS/INSTANTIATES graph. Leaving test files
// in this file-level REFERENCES bucket reintroduces the "shared class"
// false-positive problem — e.g. V1SuggestionDefaultTests.java imports
// PickupApiController for something unrelated to pickup-spots, and
// PickupApiController's file also happens to reference the endpoint's
// file, so a pure file-level chain wrongly links them even though no
// test method in that file ever calls this endpoint.
OPTIONAL MATCH (upstream:File)-[:REFERENCES*1..1]->(def)
WHERE upstream.path CONTAINS module AND upstream.role <> "test"
WITH e, def, module,
     collect(DISTINCT CASE WHEN upstream IS NULL THEN NULL ELSE
       {path: upstream.path, role: upstream.role} END) AS ups,
     collect(DISTINCT upstream.path) AS up_paths

OPTIONAL MATCH (def)-[:REFERENCES*1..1]->(downstream:File)
WHERE downstream.path CONTAINS module
WITH e, def, module, ups, up_paths,
     collect(DISTINCT CASE WHEN downstream IS NULL THEN NULL ELSE
       {path: downstream.path, role: downstream.role} END) AS downs,
     collect(DISTINCT downstream.path) AS down_paths

OPTIONAL MATCH (indUpstream:File)-[:REFERENCES *BFS 2..3]->(def)
WHERE indUpstream.path CONTAINS module
  AND indUpstream.role <> "test"
  AND NOT indUpstream.path IN up_paths
WITH e, def, module, ups, downs, down_paths,
     collect(DISTINCT CASE WHEN indUpstream IS NULL THEN NULL ELSE
       {path: indUpstream.path, role: indUpstream.role} END) AS ind_ups

OPTIONAL MATCH (def)-[:REFERENCES *BFS 2..3]->(indDownstream:File)
WHERE indDownstream.path CONTAINS module
  AND NOT indDownstream.path IN down_paths
WITH e, def, module, ups + ind_ups AS all_ups, downs,
     collect(DISTINCT CASE WHEN indDownstream IS NULL THEN NULL ELSE
       {path: indDownstream.path, role: indDownstream.role} END) AS ind_downs

WITH e, def, module, all_ups, downs + ind_downs AS all_downs_base

OPTIONAL MATCH (sibling:File {java_package: def.java_package})
WHERE sibling.path <> def.path AND sibling.path CONTAINS module
WITH e, def, module, all_ups, all_downs_base,
     collect(DISTINCT CASE WHEN sibling IS NULL THEN NULL ELSE
       {path: sibling.path, role: sibling.role} END) AS sibs
WITH e, def, module, all_ups, all_downs_base + sibs AS all_downs

// Resolve upstream_files / downstream_files down to small scalars RIGHT AWAY,
// before test_file_summaries (also a large, per-file list) is computed below.
// Carrying two large lists through the same UNWIND at once made Memgraph
// materialize roughly their cross product (~1196 x 1196 rows here) even
// though logically nothing was being joined — this was the real cause of
// the memory blow-up on the gopay module, independent of the *BFS fix.
UNWIND (CASE WHEN size(all_ups) = 0 THEN [{path: null, role: null}] ELSE all_ups END) AS u
WITH e, def, module, all_downs, u.role AS u_role, u.path AS u_path
WITH e, def, module, all_downs, u_role, collect(DISTINCT u_path) AS u_files
WITH e, def, module, all_downs,
     collect(CASE WHEN u_role IS NULL THEN NULL ELSE {role: u_role, files: u_files} END) AS upstream_files

UNWIND (CASE WHEN size(all_downs) = 0 THEN [{path: null, role: null}] ELSE all_downs END) AS d
WITH e, def, module, upstream_files, d.role AS d_role, d.path AS d_path
WITH e, def, module, upstream_files, d_role, collect(DISTINCT d_path) AS d_files
WITH e, def, module, upstream_files,
     collect(CASE WHEN d_role IS NULL THEN NULL ELSE {role: d_role, files: d_files} END) AS downstream_files

// --- Per-test-file aggregation, computed only now that upstream_files /
// downstream_files are already small scalars.
//
// Precision fix #1: a plain file-level REFERENCES chain (testFile -> ... ->
// def) says "this test file's file is connected to the endpoint's file
// somewhere", which produces false positives whenever a big shared class
// sits on the path — e.g. PickupApiController declares methods for a
// dozen unrelated endpoints, so ANY test that uses ANY method on it looks
// "connected" to ALL of those endpoints, even ones it never touches.
//
// Precision fix #2: walking a mixed CALLS|INSTANTIATES *BFS pattern isn't
// enough by itself, because the moment that walk lands on ANY intermediate
// Class node (via a TestMethod-INSTANTIATES->Class hop, which is real and
// unavoidable — the test genuinely does `new SomeController()`), it can
// then continue via the Class-[:CALLS]->Class / Class-[:INSTANTIATES]->
// Class rollup edges. Those rollups mean "some method somewhere in this
// class calls/constructs some method/class somewhere in that one" — not
// tied to any specific method — so this silently reintroduces the exact
// same "shared God class" false-positive problem one layer down (this is
// how V1DropoffSpotsTests / an unrelated goCorp billing test were wrongly
// showing up as callers of the pickup-spots endpoint: both instantiate
// PickupApiController for something unrelated, and PickupApiController's
// class-level rollup happens to also reach PandaClient -> the endpoint).
// The fix is to never take a Class-level edge mid-path: walk pure
// TestMethod/Function-level :CALLS edges only, and require the FINAL hop
// into the endpoint's Class to be a real, specific :INSTANTIATES fact.
OPTIONAL MATCH (endpointClass:Class)-[:DECLARES]->(e)
WITH e, def, module, upstream_files, downstream_files, endpointClass

OPTIONAL MATCH (tmDirect:TestMethod)-[:INSTANTIATES]->(endpointClass)
WITH e, def, module, upstream_files, downstream_files, endpointClass,
     collect(DISTINCT tmDirect) AS direct_tms

OPTIONAL MATCH (tmIndirect:TestMethod)-[:CALLS *BFS 1..6]->(:Function)-[:INSTANTIATES]->(endpointClass)
WITH e, def, module, upstream_files, downstream_files, endpointClass,
     direct_tms + collect(DISTINCT tmIndirect) AS tms_raw
UNWIND (CASE WHEN size(tms_raw) = 0 THEN [null] ELSE tms_raw END) AS tm
OPTIONAL MATCH (preciseFile:File)-[:CONTAINS]->(tm)
WHERE endpointClass IS NOT NULL AND preciseFile.path CONTAINS module
WITH e, def, module, upstream_files, downstream_files, endpointClass,
     collect(DISTINCT CASE WHEN tm IS NULL THEN NULL ELSE
       {file: preciseFile.path, method: tm.name} END) AS precise_hits

// Fallback to the coarser file-level match only when the endpoint has no
// resolvable Class at all (e.g. non-Java/gRPC endpoints), so those don't
// silently lose all test coverage just because the precise path is unusable.
OPTIONAL MATCH (fbFile:File)-[:REFERENCES *BFS 1..3]->(def)
WHERE endpointClass IS NULL AND fbFile.path CONTAINS module
WITH e, def, upstream_files, downstream_files, precise_hits, fbFile

OPTIONAL MATCH (fbFile)-[:CONTAINS]->(fbtm:TestMethod)
WITH e, def, upstream_files, downstream_files, precise_hits,
     collect(DISTINCT CASE WHEN fbtm IS NULL THEN NULL ELSE
       {file: fbFile.path, method: fbtm.name} END) AS fallback_hits

WITH e, def, upstream_files, downstream_files,
     precise_hits + fallback_hits AS test_hits_raw
UNWIND (CASE WHEN size(test_hits_raw) = 0 THEN [null] ELSE test_hits_raw END) AS hit
WITH e, def, upstream_files, downstream_files,
     CASE WHEN hit IS NULL THEN NULL ELSE hit.file END AS testFile_path,
     CASE WHEN hit IS NULL THEN NULL ELSE hit.method END AS hit_tm_name
OPTIONAL MATCH (testFile:File {path: testFile_path})
WITH DISTINCT e, def, upstream_files, downstream_files, testFile, hit_tm_name

// Precision fix: only credit an assertion class to a test file if it's
// actually reachable from THIS SPECIFIC test method's own call chain
// (pure method-level :CALLS, same rollup-avoidance principle used for the
// endpoint-reachability check above), not "this test FILE references
// that assertion file somewhere" — the latter picks up assertions used
// by completely unrelated test methods that just happen to live in the
// same file. Matches both dedicated assertion-helper files (by role) AND
// classes with assertion logic embedded directly in them (e.g.
// Assert*/verify* methods living on a nested class inside a Response/DTO
// file) — the latter is invisible to the name/path-based role heuristic,
// since a file named "...Response.java" is classified purely as
// "request / response model" regardless of what its methods actually do.
// Note: each OPTIONAL MATCH below is followed by its own WITH before the
// next one starts — chaining multiple OPTIONAL MATCHes back-to-back
// without an intermediate WITH causes Memgraph to leak a previous row's
// bound value forward into later rows whenever one of them fails to
// match (observed directly: filtering on assertCls.name = "X" returned
// completely unrelated class names). Materializing each step explicitly
// avoids that.
OPTIONAL MATCH (testFile)-[:CONTAINS]->(tm2:TestMethod {name: hit_tm_name})
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2

// Only DIRECT (1-hop) calls from the test method count now — no BFS /
// transitive walk through intermediate helpers. Crediting an assertion
// class reached several hops down the test method's call chain produced
// false positives (an assertion helper used by some OTHER method further
// down the chain, unrelated to what this specific test method actually
// asserts). A class counts as an assertion class for this test method if
// either (a) it's already classified as an assertion helper by role or
// has_assertion_methods, or (b) the specific method the test method
// called directly is itself named assert*/verify* — covers a class with
// just one verify*-named method that never tripped the
// has_assertion_methods bar on its own.
OPTIONAL MATCH (tm2)-[:CALLS]->(fn:Function)
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2, fn

OPTIONAL MATCH (assertCls:Class)-[:DECLARES]->(fn)
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2, fn, assertCls

// The assertion test decides what goes IN the collect — it must never be a
// WHERE. As a hard filter it deleted the whole endpoint whenever a test method
// called no assertion class: every candidate row for that method was dropped,
// and those rows are what carry testFile, hit_tm_name and the already-computed
// upstream_files / downstream_files. /gojek/customer/v2/history/{custId} had 69
// candidate rows, none of them an assertion class, and returned zero rows.
//
// coalesce() is equally load-bearing: has_assertion_methods is absent on most
// Class nodes, and in Cypher `missing = true` is NULL, not false. A NULL
// disjunct makes the whole OR chain NULL unless something else is true, and
// WHERE drops anything that is not true — so that one comparison silently
// filtered rows that all three real conditions had already declined to keep.
OPTIONAL MATCH (assertFile:File)-[:DECLARES]->(assertCls)
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2, fn, assertCls, assertFile,
     (coalesce(assertFile.role = "assertion helper", false)
      OR coalesce(assertCls.has_assertion_methods, false)
      OR coalesce(toLower(fn.name) =~ "^(assert|verify).*", false)) AS is_assertion
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name,
     collect(DISTINCT CASE WHEN assertCls IS NULL OR NOT is_assertion THEN NULL ELSE
       {class: assertCls.name, file: assertFile.path} END) AS assertions_for_method

WITH DISTINCT e, def, upstream_files, downstream_files, testFile, hit_tm_name, assertions_for_method
WITH e, def, upstream_files, downstream_files, testFile,
     collect(DISTINCT hit_tm_name) AS tm_names,
     collect(assertions_for_method) AS assertions_nested

// Flatten the per-method assertion lists back into one deduped list per
// test file, since that's the shape the rest of the pipeline (and the
// final output) expects.
UNWIND (CASE WHEN size(assertions_nested) = 0 THEN [[]] ELSE assertions_nested END) AS assertions_for_one_method
UNWIND (CASE WHEN size(assertions_for_one_method) = 0 THEN [null] ELSE assertions_for_one_method END) AS assert_entry
WITH e, def, upstream_files, downstream_files, testFile, tm_names,
     collect(DISTINCT assert_entry) AS assert_entries

OPTIONAL MATCH (testFile)-[:REFERENCES]->(dp:File)
WHERE dp.role = "data provider"
WITH e, def, upstream_files, downstream_files, testFile, tm_names, assert_entries, dp

OPTIONAL MATCH (dp)-[:DECLARES]->(dpCls:Class)-[:DECLARES]->(dpm:DataProviderMethod)
WITH e, def, upstream_files, downstream_files, testFile, tm_names, assert_entries,
     collect(DISTINCT CASE WHEN dpm IS NULL THEN NULL ELSE
       {class: dpCls.name, method: dpm.name, provider_name: dpm.provider_name} END) AS dp_entries

WITH e, def, upstream_files, downstream_files,
     collect(CASE WHEN testFile IS NULL OR size(tm_names) = 0 THEN NULL ELSE
       {test_file: testFile.path, test_methods: tm_names,
        data_providers: dp_entries, assertions: assert_entries}
     END) AS test_file_summaries

UNWIND (CASE WHEN size(test_file_summaries) = 0 THEN [null] ELSE test_file_summaries END) AS tfs1
UNWIND (CASE WHEN tfs1 IS NULL THEN [null] ELSE tfs1.test_methods END) AS tm_name
WITH e, def, upstream_files, downstream_files, test_file_summaries,
     collect(DISTINCT CASE WHEN tfs1 IS NULL OR tm_name IS NULL THEN NULL ELSE
       {test_file: tfs1.test_file, test_method: tm_name} END) AS test_calls

// Add role="test" back into upstream_files, but populated only with the
// PRECISE set of test files already proven (above) to call the endpoint
// directly via the method-level CALLS/INSTANTIATES graph — never via the
// generic file-level REFERENCES walk used for the other roles, which is
// exactly what caused unrelated test files (e.g. V1SuggestionDefaultTests
// for the pickup-spots endpoint) to show up here before.
UNWIND (CASE WHEN size(test_calls) = 0 THEN [null] ELSE test_calls END) AS tc
WITH e, def, upstream_files, downstream_files, test_calls, test_file_summaries,
     collect(DISTINCT CASE WHEN tc IS NULL THEN NULL ELSE tc.test_file END) AS calling_test_files
WITH e, def, downstream_files, test_calls, test_file_summaries,
     upstream_files + (CASE WHEN size(calling_test_files) = 0 THEN []
       ELSE [{role: "test", files: calling_test_files}] END) AS upstream_files

UNWIND (CASE WHEN size(test_file_summaries) = 0 THEN [null] ELSE test_file_summaries END) AS tfs2
WITH e, def, upstream_files, downstream_files, test_calls, test_file_summaries,
     CASE WHEN tfs2 IS NULL OR size(tfs2.data_providers) = 0 THEN NULL ELSE
       {test_file: tfs2.test_file, data_providers: tfs2.data_providers} END AS dp_row
WITH e, def, upstream_files, downstream_files, test_calls, test_file_summaries,
     collect(DISTINCT dp_row) AS test_data_providers

UNWIND (CASE WHEN size(test_file_summaries) = 0 THEN [null] ELSE test_file_summaries END) AS tfs3
WITH e, def, upstream_files, downstream_files, test_calls, test_data_providers,
     CASE WHEN tfs3 IS NULL OR size(tfs3.assertions) = 0 THEN NULL ELSE
       {test_file: tfs3.test_file, assertions: tfs3.assertions} END AS assert_row
WITH e, def, upstream_files, downstream_files, test_calls, test_data_providers,
     collect(DISTINCT assert_row) AS test_assertions

RETURN
  e.key AS endpoint,
  e.method AS http_method,
  def.path AS endpoint_file,
  upstream_files,
  downstream_files,
  test_calls AS test_methods_calling_endpoint,
  test_data_providers,
  test_assertions
