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

OPTIONAL MATCH (testFile)-[:CONTAINS]->(tm2:TestMethod {name: hit_tm_name})
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2

OPTIONAL MATCH (tm2)-[:CALLS]->(fn:Function)
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2, fn

OPTIONAL MATCH (assertCls:Class)-[:DECLARES]->(fn)
WITH e, def, upstream_files, downstream_files, testFile, hit_tm_name, tm2, fn, assertCls

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
