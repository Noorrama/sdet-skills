#!/usr/bin/env python3
"""
Generate <module>_service_graph.json by tracing the service architecture.

Supports two architecture patterns (auto-detected per module):
  A. Controller-based (e.g. driver-platform):
       Controller → Client → Endpoint → PropertiesInternal
  B. Helper-based (e.g. gopay):
       Helper → Client → Endpoint (in apis/)

Works for any module — all paths are auto-discovered at runtime.

Usage:
    python3 generate_service_graph.py --module driver-platform
    python3 generate_service_graph.py --module driver-platform -bp PR-166
    python3 generate_service_graph.py --module gopay
    python3 generate_service_graph.py --module care-platform -b testcases_PR-100.json

Output: <module>_service_graph.json (in this script's directory)
"""

import base64
import csv
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------

def find_repo_root():
    """Walk up from SCRIPT_DIR to find the repo root (contains .git)."""
    d = SCRIPT_DIR
    while d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(os.path.dirname(SCRIPT_DIR))

REPO_ROOT = find_repo_root()

# ---------------------------------------------------------------------------
# Dynamic directory discovery
# ---------------------------------------------------------------------------

def discover_dirs(module_name):
    """Discover all relevant Java directories for a given module."""

    base_dir = os.path.join(REPO_ROOT, module_name)
    if not os.path.isdir(base_dir):
        print(f"ERROR: Module directory not found: {base_dir}", file=sys.stderr)
        sys.exit(1)

    main_java = os.path.join(base_dir, "src/main/java")
    test_java = os.path.join(base_dir, "src/test/java")
    resources = os.path.join(base_dir, "src/main/resources")

    dirs = {
        "base_dir": base_dir,
        "main_java": main_java if os.path.isdir(main_java) else None,
        "test_java": test_java if os.path.isdir(test_java) else None,
        "resources": resources if os.path.isdir(resources) else None,
        "properties_internal": None,
        "properties_reader": [],
        "controller_dirs": [],
        "helper_dirs": [],
        "client_dirs": [],
        "clientwrapper_dirs": [],
        "entities_dirs": [],
        "apis_dirs": [],
        "test_dirs": [],
    }

    if not dirs["main_java"]:
        print(f"WARNING: No src/main/java found in {module_name}", file=sys.stderr)
        return dirs

    # Find *PropertiesInternal.java (any location)
    for root, _, files in os.walk(main_java):
        for f in files:
            if f.endswith("PropertiesInternal.java"):
                dirs["properties_internal"] = os.path.join(root, f)
                break
        if dirs["properties_internal"]:
            break

    # Find *PropertiesReader.java files
    for root, _, files in os.walk(main_java):
        for f in files:
            if f.endswith("PropertiesReader.java"):
                dirs["properties_reader"].append(os.path.join(root, f))

    # Find all architectural directories at any nesting depth
    for root, subdirs, _ in os.walk(main_java):
        basename = os.path.basename(root)
        if basename == "controller":
            dirs["controller_dirs"].append(root)
        elif basename == "helpers":
            dirs["helper_dirs"].append(root)
        elif basename in ("client", "clients"):
            dirs["client_dirs"].append(root)
        elif basename in ("clientwrappers", "clientWrapper"):
            dirs["clientwrapper_dirs"].append(root)
        elif basename == "entities":
            dirs["entities_dirs"].append(root)
        elif basename == "apis":
            dirs["apis_dirs"].append(root)

    # Test directories: always use test_java root to catch all test patterns
    # (driver-platform uses tests/, gopay uses userJourneyTests/, paymentTooling/, etc.)
    if dirs["test_java"]:
        dirs["test_dirs"] = [test_java]

    return dirs


def detect_architecture(dirs):
    """Detect whether the module uses controller-based or helper-based architecture."""
    has_controllers = bool(dirs["controller_dirs"])
    has_helpers = bool(dirs["helper_dirs"])

    if has_controllers and has_helpers:
        return "both"
    elif has_controllers:
        return "controller"
    elif has_helpers:
        return "helper"
    else:
        return "none"


def print_discovery(module_name, dirs, arch):
    """Print what was discovered for the module."""
    print(f"  Module            : {module_name}")
    print(f"  Architecture      : {arch}")
    print(f"  Base dir          : {dirs['base_dir']}")
    pi = os.path.basename(dirs["properties_internal"]) if dirs["properties_internal"] else "(none)"
    print(f"  PropertiesInternal: {pi}")
    print(f"  PropertiesReader  : {len(dirs['properties_reader'])} file(s)")
    print(f"  Controller dirs   : {len(dirs['controller_dirs'])}")
    print(f"  Helper dirs       : {len(dirs['helper_dirs'])}")
    print(f"  Client dirs       : {len(dirs['client_dirs'])}")
    print(f"  ClientWrapper dirs: {len(dirs['clientwrapper_dirs'])}")
    print(f"  Entities dirs     : {len(dirs['entities_dirs'])}")
    print(f"  APIs dirs         : {len(dirs['apis_dirs'])}")
    print(f"  Test dirs         : {len(dirs['test_dirs'])}")


# ---------------------------------------------------------------------------
# Properties parsing (generic)
# ---------------------------------------------------------------------------

def parse_properties_internal(filepath):
    """Parse a *PropertiesInternal.java to extract host vars and URL constants."""
    if not filepath or not os.path.isfile(filepath):
        return {}, {}, {}

    with open(filepath) as f:
        content = f.read()

    host_vars = {}
    for m in re.finditer(
        r'(?:private|public)\s+static\s+final\s+String\s+(\w+)\s*=\s*propertiesReader\.(\w+)\(\)',
        content
    ):
        host_vars[m.group(1)] = m.group(2)

    url_constants = {}
    url_paths = {}
    # String.format pattern
    for m in re.finditer(
        r'public\s+static\s+final\s+String\s+(\w+)\s*=\s*String\.format\(\s*"[^"]*(/[^"]+)"'
        r'\s*,\s*(\w+)\s*\)',
        content
    ):
        url_constants[m.group(1)] = m.group(3)
        url_paths[m.group(1)] = m.group(2)

    # Direct concatenation pattern
    for m in re.finditer(
        r'public\s+static\s+final\s+String\s+(\w+)\s*=\s*(\w+)\s*\+\s*"(/[^"]+)"',
        content
    ):
        url_constants[m.group(1)] = m.group(2)
        url_paths[m.group(1)] = m.group(3)

    return host_vars, url_constants, url_paths


def parse_properties_reader(filepaths):
    """Parse *PropertiesReader.java files to build getter → property key mapping."""
    getter_to_prop_key = {}
    for fp in filepaths:
        if not os.path.isfile(fp):
            continue
        with open(fp) as f:
            content = f.read()
        for m in re.finditer(
            r'public\s+String\s+(\w+)\s*\(\)\s*\{[^}]*?getProperty\(\s*"([^"]+)"\s*\)',
            content, re.DOTALL
        ):
            getter_to_prop_key[m.group(1)] = m.group(2)
    return getter_to_prop_key


def read_properties_files(resources_dir):
    """Read all .properties files from resources dir."""
    props = {}
    if not resources_dir or not os.path.isdir(resources_dir):
        return props
    for name in sorted(os.listdir(resources_dir)):
        if not name.endswith(".properties"):
            continue
        props_file = os.path.join(resources_dir, name)
        try:
            with open(props_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, _, val = line.partition("=")
                        pk = key.strip()
                        if pk not in props:
                            props[pk] = val.strip()
        except Exception:
            pass
    return props


# ---------------------------------------------------------------------------
# Java source scanners (unified for controllers + helpers)
# ---------------------------------------------------------------------------

def scan_entry_points(scan_dirs, base_dir, suffix_filter=None):
    """Scan entry point classes (controllers or helpers) across directories.

    Args:
        scan_dirs: list of directories to scan
        base_dir: module base dir for relative paths
        suffix_filter: if set, only include classes whose name ends with this
                       (e.g. "Controller", "Helper"). None = include all.

    Returns {ClassName: {clients: [...], methods: [...], file: str}}
    """
    entry_points = {}
    for sdir in scan_dirs:
        for root, _, files in os.walk(sdir):
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                class_name = fname.replace(".java", "")
                if suffix_filter and not class_name.endswith(suffix_filter):
                    continue

                fpath = os.path.join(root, fname)
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Find client references (imports + instantiations)
                clients = set()
                # Import patterns: import ...client(s).SomeClient;
                for m in re.finditer(
                    r'import\s+(?:\w+\.)*(?:client|clients|clientwrappers?)\.(?:\w+\.)*(\w+(?:Client|ClientWrapper)\w*)\s*;',
                    content
                ):
                    clients.add(m.group(1))
                # Field/instantiation patterns
                for m in re.finditer(
                    r'(?:new|private|protected|public)\s+(?:final\s+)?(\w+(?:Client|ClientWrapper)\w*)\s*[(\s;]',
                    content
                ):
                    clients.add(m.group(1))
                # Static import pattern (gopay uses this): import static ...clients.xxx.SomeClient.method
                for m in re.finditer(
                    r'import\s+static\s+(?:\w+\.)*(?:client|clients)\.(?:\w+\.)*(\w+(?:Client)\w*)\.', content
                ):
                    clients.add(m.group(1))

                # Find public methods (features)
                methods = []
                skip_methods = {class_name, "toString", "hashCode", "equals",
                                "setUp", "tearDown", "beforeMethod", "afterMethod"}
                for m in re.finditer(r'public\s+\w+(?:<[^>]+>)?\s+(\w+)\s*\(', content):
                    method_name = m.group(1)
                    if method_name not in skip_methods:
                        methods.append(method_name)

                entry_points[class_name] = {
                    "clients": sorted(clients),
                    "methods": methods,
                    "file": os.path.relpath(fpath, base_dir),
                }
    return entry_points


def scan_clients(client_dirs, base_dir):
    """Scan all Client classes across discovered directories."""
    clients = {}
    for cdir in client_dirs:
        for root, _, files in os.walk(cdir):
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                fpath = os.path.join(root, fname)
                class_name = fname.replace(".java", "")
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                endpoints = set()
                # Import patterns for endpoints — from entities/ or apis/
                for m in re.finditer(
                    r'import\s+(?:\w+\.)*(?:endpoint|apis?)\.(?:\w+\.)*(\w+Endpoint\w*)\s*;', content
                ):
                    endpoints.add(m.group(1))
                # Instantiation
                for m in re.finditer(r'new\s+(\w+Endpoint\w*)\s*\(', content):
                    endpoints.add(m.group(1))
                # Enum constant usage: SomeEndpoint.CONSTANT
                for m in re.finditer(r'(\w+Endpoint)\.\w+', content):
                    endpoints.add(m.group(1))

                clients[class_name] = {
                    "endpoints": sorted(endpoints),
                    "file": os.path.relpath(fpath, base_dir),
                }
    return clients


def scan_endpoints(endpoint_dirs, base_dir, properties_internal_class):
    """Scan all Endpoint classes/enums across entities/ and apis/ directories."""
    endpoints = {}
    for edir in endpoint_dirs:
        for root, _, files in os.walk(edir):
            for fname in files:
                if not fname.endswith("Endpoint.java"):
                    continue
                fpath = os.path.join(root, fname)
                class_name = fname.replace(".java", "")
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Try to extract URL constant from PropertiesInternal reference
                url_const = None
                if properties_internal_class:
                    m = re.search(rf'{properties_internal_class}\.(\w+)', content)
                    if m:
                        url_const = m.group(1)

                # Extract URL paths from the endpoint itself (gopay-style enums/classes)
                url_paths = set()
                # Enum constants with path strings: SEARCH_BILLERS_V1("/v1/billers/search")
                for m in re.finditer(r'\w+\s*\(\s*"(/[^"]+)"\s*\)', content):
                    url_paths.add(m.group(1))
                # String returns with paths: return baseUrl + "/v1/path"
                for m in re.finditer(r'return\s+\w+\s*\+\s*"(/[^"]+)"', content):
                    url_paths.add(m.group(1))
                # Direct URL path string assignments
                for m in re.finditer(r'String\s+\w*[Uu]rl\w*\s*=\s*[^;]*"(/[^"]+)"', content):
                    url_paths.add(m.group(1))

                # Extract host references from gopay-style endpoints
                host_ref = None
                # Pattern: PropertiesReader.getXxxHost() or propertiesReader.getXxxHost()
                m = re.search(r'(?:\w+\.)*(?:get\w*Host\w*|get\w*BaseUrl\w*)\s*\(', content)
                if m:
                    host_ref = m.group(0).rstrip("(").strip()

                endpoints[class_name] = {
                    "urlConstant": url_const,
                    "urlPaths": sorted(url_paths),
                    "hostRef": host_ref,
                    "file": os.path.relpath(fpath, base_dir),
                }
    return endpoints


# ---------------------------------------------------------------------------
# Test scanners (unified for controller + helper patterns)
# ---------------------------------------------------------------------------

# Suffixes for "entry point" classes that tests may reference
_ENTRY_SUFFIXES = ("Controller", "Helper")


def _find_entry_point_refs(content):
    """Find both Controller and Helper references in Java source."""
    refs = set()
    for suffix in _ENTRY_SUFFIXES:
        # Import patterns
        for m in re.finditer(
            rf'import\s+(?:\w+\.)*(?:controller|helpers?)(?:\.\w+)*\.(\w+{suffix}\w*)\s*;',
            content
        ):
            refs.add(m.group(1))
        # Instantiation / field declaration
        for m in re.finditer(
            rf'(?:new|protected|private|public)\s+(?:final\s+)?(\w+{suffix}\w*)\s*[(\s;]',
            content
        ):
            name = m.group(1)
            if name.endswith(suffix):
                refs.add(name)
    return refs


def scan_test_bases(test_dirs):
    """Scan base test classes to find which entry points (controllers/helpers) they hold."""
    bases = {}
    for tdir in test_dirs:
        for root, _, files in os.walk(tdir):
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                class_name = fname.replace(".java", "")
                if "Base" not in class_name and "TestBase" not in class_name:
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                refs = _find_entry_point_refs(content)
                bases[class_name] = sorted(refs)
    return bases


def extract_test_ids_from_file(filepath):
    """Extract all test case IDs from a Java test file."""
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        content = f.read()

    class_name = os.path.basename(filepath).replace(".java", "")
    results = []
    blocks = re.split(r"(?=@Test\b)", content)

    for block in blocks:
        if not block.startswith("@Test"):
            continue

        desc_match = re.search(r'description\s*=\s*"([^"]+)"', block)
        description = desc_match.group(1) if desc_match else ""

        tc_match = re.search(r'testCaseIds\s*=\s*\{([^}]+)\}', block)
        tc_ids = re.findall(r'"(\w+)"', tc_match.group(1)) if tc_match else []

        method_match = re.search(r"public\s+void\s+(\w+)\s*\(", block)
        if method_match:
            method_name = method_match.group(1)
            if method_name in ("beforeMethod", "setUp", "tearDown", "afterMethod",
                               "initializeTest", "beforeTest", "afterTest"):
                continue
            test_id = ";".join(tc_ids) if tc_ids else f"{class_name}.{method_name}"
            results.append({
                "testId": test_id,
                "method": method_name,
                "description": description,
                "testCaseIds": tc_ids,
            })

    return results


def scan_test_files(test_dirs, base_dir):
    """Scan all test files. Finds references to both Controllers and Helpers."""
    test_files = {}
    for tdir in test_dirs:
        for root, _, files in os.walk(tdir):
            for fname in files:
                if not fname.endswith(".java") or "Base" in fname:
                    continue
                fpath = os.path.join(root, fname)
                class_name = fname.replace(".java", "")
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Find parent class
                base = None
                m = re.search(r'class\s+\w+\s+extends\s+(\w+)', content)
                if m:
                    base = m.group(1)

                # Extract test groups
                groups = set()
                for gm in re.finditer(r'groups\s*=\s*\{([^}]+)\}', content):
                    raw = gm.group(1)
                    for c in re.findall(r'([A-Z][A-Z_0-9]+)', raw):
                        groups.add(c)

                # Find entry point references (controllers + helpers)
                own_entry_points = _find_entry_point_refs(content)

                test_ids = extract_test_ids_from_file(fpath)

                test_files[class_name] = {
                    "base": base,
                    "groups": sorted(groups),
                    "ownEntryPoints": sorted(own_entry_points),
                    "file": os.path.relpath(fpath, base_dir),
                    "testIds": test_ids,
                }
    return test_files


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def method_to_feature(method_name):
    """Convert a camelCase method name to a snake_case feature name."""
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', method_name)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    return s.lower()


def path_to_feature(path):
    """Convert a URL path to a feature name."""
    parts = [p for p in path.strip("/").split("/") if p and not re.match(r'^v\d+$', p)]
    noise = {"api", "internal", "gojek", "admin", "external", "drivers", "driver"}
    parts = [p for p in parts if p.lower() not in noise]
    if parts:
        return "_".join(parts[:3]).lower().replace("-", "_")
    return None


def derive_service_name(class_name):
    """Derive a service name from a controller/helper class name."""
    name = class_name
    # Remove trailing suffixes
    for suffix in ("Controller", "Helper", "Service"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    # Remove common prefixes
    for prefix in ("DP", "NCP", "CP"):
        if name.startswith(prefix) and len(name) > len(prefix) and name[len(prefix)].isupper():
            name = name[len(prefix):]
            break
    if name:
        return name[0].lower() + name[1:]
    return class_name


def derive_display_key(class_name):
    """Derive a display key for the service graph entry."""
    name = class_name
    for suffix in ("Controller", "Helper"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    if not name.endswith("Service") and not name.endswith("Internal"):
        name = name + "Service"
    return name


# ---------------------------------------------------------------------------
# BrowserStack integration
# ---------------------------------------------------------------------------

def load_env_file():
    """Load variables from a .env file next to this script."""
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value


def load_browserstack_lookup(bs_file):
    """Load BrowserStack test cases JSON and return {numeric_id: {testId, testTitle}}."""
    with open(bs_file) as f:
        data = json.load(f)

    lookup = {}
    for tc in data.get("testCases", []):
        bs_id = tc.get("testId", "")
        title = tc.get("testTitle", "")
        numeric = bs_id.replace("TC-", "") if bs_id.startswith("TC-") else bs_id
        if numeric:
            lookup[numeric] = {"testId": bs_id, "testTitle": title}
    return lookup


def build_browserstack_auth_header():
    """Build the Authorization header from .env / environment variables."""
    # TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.
    token = os.environ.get("BS_AUTH_TOKEN", "").strip()
    if token:
        return f"Basic {token}"

    # TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.
    username = os.environ.get("BS_USERNAME", "").strip()
    access_key = os.environ.get("BS_ACCESS_KEY", "").strip()
    if username and access_key:
        encoded = base64.b64encode(f"{username}:{access_key}".encode()).decode()
        return f"Basic {encoded}"

    return None


def fetch_browserstack_page(project_id, page, page_size, auth_header, api_host):
    """Fetch a single page of test cases from BrowserStack API."""
    url = f"{api_host}/api/v2/projects/{project_id}/test-cases?p={page}&page_size={page_size}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", auth_header)
    req.add_header("Accept", "application/json")
    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code} on page {page}: {body[:200]}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"  URL error on page {page}: {e.reason}", file=sys.stderr)
        return None


def fetch_browserstack_testcases(project_id, page_size=300):
    """Fetch all test cases from BrowserStack API and return the lookup dict."""
    load_env_file()
    # TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.
    api_host = os.environ.get("BS_API_HOST", "https://test-management.browserstack.com").rstrip("/")

    auth_header = build_browserstack_auth_header()
    if not auth_header:
        print("ERROR: No BrowserStack credentials found.", file=sys.stderr)
        print("       Create a .env file in this folder with:", file=sys.stderr)
        print("         BS_USERNAME=your_username", file=sys.stderr)
        print("         BS_ACCESS_KEY=your_access_key", file=sys.stderr)
        return {}

    print(f"  Fetching test cases from BrowserStack project {project_id}...")
    all_test_cases = []
    page = 1

    while True:
        print(f"    Page {page}...", end=" ", flush=True)
        data = fetch_browserstack_page(project_id, page, page_size, auth_header, api_host)

        if data is None:
            print("FAILED — stopping.")
            break

        payload = data
        if isinstance(data.get("data"), dict):
            payload = data["data"]
        elif isinstance(data.get("data"), list):
            payload = {"test_cases": data["data"]}

        test_cases = payload.get("test_cases") or payload.get("testcases") or []
        info = payload.get("info") or data.get("info") or {}

        if not test_cases:
            print("done.")
            break

        for tc in test_cases:
            identifier = tc.get("identifier") or tc.get("id") or ""
            title = tc.get("title") or tc.get("name") or ""
            all_test_cases.append({"testId": str(identifier), "testTitle": title})

        print(f"got {len(test_cases)} (total: {len(all_test_cases)})")

        has_next = info.get("next")
        if has_next is None:
            if len(test_cases) < page_size:
                break
        if has_next is False or has_next == "false":
            break

        page += 1

    print(f"  Fetched {len(all_test_cases)} test cases from BrowserStack")

    cache_file = os.path.join(SCRIPT_DIR, f"testcases_{project_id}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"testCases": all_test_cases}, f, indent=4, ensure_ascii=False)
    print(f"  Cached to {cache_file}")

    lookup = {}
    for tc in all_test_cases:
        bs_id = tc["testId"]
        numeric = bs_id.replace("TC-", "") if bs_id.startswith("TC-") else bs_id
        if numeric:
            lookup[numeric] = tc
    return lookup


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def enrich_with_browserstack(graph, bs_lookup):
    """Enrich testCaseIds with BrowserStack test case names."""
    total_matched = 0
    total_numeric = 0

    for service_key, entry in graph.items():
        enriched = []
        for tc_id in entry["testCaseIds"]:
            if tc_id.isdigit():
                total_numeric += 1
                if tc_id in bs_lookup:
                    bs = bs_lookup[tc_id]
                    enriched.append(f"{bs['testId']}: {bs['testTitle']}")
                    total_matched += 1
                else:
                    enriched.append(tc_id)
            else:
                enriched.append(tc_id)
        entry["testCaseIds"] = enriched

    return total_matched, total_numeric


def build_service_graph(module_name, dirs, arch):
    """Build the complete service graph for the given module."""

    base_dir = dirs["base_dir"]

    # Determine the PropertiesInternal class name
    properties_internal_class = None
    if dirs["properties_internal"]:
        properties_internal_class = os.path.basename(dirs["properties_internal"]).replace(".java", "")

    # 1. Parse PropertiesInternal (optional)
    if dirs["properties_internal"]:
        print(f"Parsing {os.path.basename(dirs['properties_internal'])}...")
        host_vars, url_constants, url_paths = parse_properties_internal(dirs["properties_internal"])
        print(f"  Found {len(host_vars)} host variables, {len(url_constants)} URL constants")
    else:
        print("No PropertiesInternal found — skipping URL constant extraction")
        host_vars, url_constants, url_paths = {}, {}, {}

    # 2. Read properties files
    print("Reading properties files for host URLs...")
    props = read_properties_files(dirs["resources"])
    print(f"  Found {len(props)} properties")

    # 3. Parse PropertiesReader
    if dirs["properties_reader"]:
        print(f"Parsing PropertiesReader ({len(dirs['properties_reader'])} file(s))...")
        getter_to_prop_key = parse_properties_reader(dirs["properties_reader"])
        print(f"  Found {len(getter_to_prop_key)} getter→property mappings")
    else:
        print("No PropertiesReader found — skipping getter mapping")
        getter_to_prop_key = {}

    # 4. Scan entry points: controllers AND/OR helpers
    entry_points = {}

    if dirs["controller_dirs"]:
        print("Scanning controllers...")
        controllers = scan_entry_points(dirs["controller_dirs"], base_dir)
        print(f"  Found {len(controllers)} controllers")
        entry_points.update(controllers)

    if dirs["helper_dirs"]:
        print("Scanning helpers...")
        helpers = scan_entry_points(dirs["helper_dirs"], base_dir, suffix_filter="Helper")
        print(f"  Found {len(helpers)} helpers")
        entry_points.update(helpers)

    if not entry_points:
        print(f"WARNING: No controllers or helpers found in {module_name}.", file=sys.stderr)

    # 5. Scan clients (including clientwrappers)
    all_client_dirs = dirs["client_dirs"] + dirs["clientwrapper_dirs"]
    print("Scanning clients...")
    clients = scan_clients(all_client_dirs, base_dir)
    print(f"  Found {len(clients)} clients")

    # 6. Scan endpoints (from entities/ and apis/)
    all_endpoint_dirs = dirs["entities_dirs"] + dirs["apis_dirs"]
    print("Scanning endpoints...")
    endpoints = scan_endpoints(all_endpoint_dirs, base_dir, properties_internal_class)
    print(f"  Found {len(endpoints)} endpoints")

    # 7. Scan test bases
    print("Scanning test base classes...")
    test_bases = scan_test_bases(dirs["test_dirs"])
    print(f"  Found {len(test_bases)} base classes")

    # 8. Scan test files
    print("Scanning test files...")
    test_files = scan_test_files(dirs["test_dirs"], base_dir)
    print(f"  Found {len(test_files)} test files")

    # Build host variable → actual host URL mapping
    host_var_to_url = {}
    for var_name, getter in host_vars.items():
        prop_key = getter_to_prop_key.get(getter)
        if prop_key and prop_key in props:
            host_var_to_url[var_name] = props[prop_key]
        elif var_name in props:
            host_var_to_url[var_name] = props[var_name]
        else:
            for pk, pv in props.items():
                if pk.lower() == var_name.lower():
                    host_var_to_url[var_name] = pv
                    break

    # Build entry_point → host/features mapping
    ep_hosts = {}
    ep_features = {}

    for ep_name, ep_info in entry_points.items():
        hosts = set()
        features = set()

        # Features from entry point methods
        for method in ep_info["methods"]:
            features.add(method_to_feature(method))

        # Trace: entry_point → clients → endpoints → URLs
        for client_name in ep_info["clients"]:
            if client_name not in clients:
                continue
            for endpoint_name in clients[client_name]["endpoints"]:
                if endpoint_name not in endpoints:
                    continue
                ep_data = endpoints[endpoint_name]

                # PropertiesInternal-style URL constant mapping
                url_const = ep_data.get("urlConstant")
                if url_const and url_const in url_constants:
                    host_var = url_constants[url_const]
                    if host_var in host_var_to_url:
                        hosts.add(host_var_to_url[host_var])
                    else:
                        hosts.add(host_var)
                    if url_const in url_paths:
                        feat = path_to_feature(url_paths[url_const])
                        if feat:
                            features.add(feat)

                # Endpoint-embedded URL paths (gopay-style)
                for path in ep_data.get("urlPaths", []):
                    feat = path_to_feature(path)
                    if feat:
                        features.add(feat)

                # Host reference from endpoint
                if ep_data.get("hostRef"):
                    hosts.add(ep_data["hostRef"])

        ep_hosts[ep_name] = sorted(hosts)
        ep_features[ep_name] = sorted(features)

    # Build base class → entry point mapping
    base_to_eps = test_bases

    # Build entry_point → test groups and test IDs mapping
    ep_groups = defaultdict(set)
    ep_test_files = defaultdict(set)
    ep_test_ids = defaultdict(list)

    for test_name, test_info in test_files.items():
        base = test_info["base"]
        groups = test_info["groups"]

        connected_eps = set()
        connected_eps.update(test_info["ownEntryPoints"])

        # Walk inheritance chain: test → base → base's base (if bases reference other bases)
        if base and base in base_to_eps:
            connected_eps.update(base_to_eps[base])

        # Also check if the test's base class is itself in test_files (mid-level bases)
        # This handles gopay's pattern where MiniAppBaseTest extends TestBase
        if base and base in test_files:
            mid = test_files[base]
            connected_eps.update(mid.get("ownEntryPoints", []))
            mid_base = mid.get("base")
            if mid_base and mid_base in base_to_eps:
                connected_eps.update(base_to_eps[mid_base])

        for ep in connected_eps:
            if ep in entry_points:
                ep_groups[ep].update(groups)
                ep_test_files[ep].add(test_name)
                ep_test_ids[ep].extend(test_info["testIds"])

    # Build the service graph
    graph = {}
    for ep_name in sorted(entry_points.keys()):
        service_name = derive_service_name(ep_name)
        hosts = ep_hosts.get(ep_name, [])
        host = hosts[0] if hosts else ""
        features = ep_features.get(ep_name, [])
        groups = sorted(ep_groups.get(ep_name, set()))

        # Find impacted services (other entry points sharing tests)
        impacted = set()
        for test_name in ep_test_files.get(ep_name, set()):
            test_info = test_files[test_name]
            base = test_info["base"]
            if base and base in base_to_eps:
                for other_ep in base_to_eps[base]:
                    if other_ep != ep_name and other_ep in entry_points:
                        impacted.add(derive_service_name(other_ep))

        # Derive supported flows from test group names
        flows = set()
        for g in groups:
            gl = g.lower()
            if "component" in gl:
                flows.add("component")
            if "regression" in gl:
                flows.add("regression")
            if "sanity" in gl or "smoke" in gl:
                flows.add("sanity")
            if "e2e" in gl or "end_to_end" in gl:
                flows.add("end_to_end")

        display_key = derive_display_key(ep_name)

        # Collect test case IDs — deduplicated
        raw_ids = ep_test_ids.get(ep_name, [])
        seen_methods = set()
        flat_ids = set()
        for tid in raw_ids:
            if tid["method"] in seen_methods:
                continue
            seen_methods.add(tid["method"])
            if tid["testCaseIds"]:
                flat_ids.update(tid["testCaseIds"])
            else:
                flat_ids.add(tid["method"])

        graph[display_key] = {
            "serviceName": service_name,
            "host": host,
            "features": features,
            "TestGroups": groups,
            "testCaseIds": sorted(flat_ids),
            "impacted_service": sorted(impacted),
            "supported_flows": sorted(flows),
        }

    return graph


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse as _ap

    parser = _ap.ArgumentParser(
        description="Generate a service graph for any module."
    )
    parser.add_argument(
        "--module", "-m", required=True,
        help="Module name (e.g. driver-platform, gopay, care-platform).",
    )
    bs_group = parser.add_mutually_exclusive_group()
    bs_group.add_argument(
        "--browserstack", "-b",
        help="Path to a local BrowserStack test cases JSON file.",
    )
    bs_group.add_argument(
        "--browserstack-project", "-bp",
        help="BrowserStack project ID (e.g. PR-143). Fetches live from the API.",
    )
    args = parser.parse_args()

    module_name = args.module

    print("=" * 70)
    print(f"Generating Service Graph — {module_name}")
    print("=" * 70)

    # Discover directories
    print("\nDiscovering module structure...")
    dirs = discover_dirs(module_name)
    arch = detect_architecture(dirs)
    print_discovery(module_name, dirs, arch)
    print()

    # Build the graph
    graph = build_service_graph(module_name, dirs, arch)

    # Enrich with BrowserStack
    bs_lookup = None
    if args.browserstack_project:
        project_id = args.browserstack_project
        cache_file = os.path.join(SCRIPT_DIR, f"testcases_{project_id}.json")
        if os.path.exists(cache_file):
            print(f"\nFound cached BrowserStack data: {cache_file}")
            print("  Using cached file (delete it to force re-fetch from API)")
            bs_lookup = load_browserstack_lookup(cache_file)
        else:
            print(f"\nFetching BrowserStack test cases from API...")
            bs_lookup = fetch_browserstack_testcases(project_id)
    elif args.browserstack:
        bs_file = args.browserstack
        if not os.path.exists(bs_file):
            auto_path = os.path.join(SCRIPT_DIR, f"testcases_{bs_file}.json")
            if os.path.exists(auto_path):
                bs_file = auto_path
        if os.path.exists(bs_file):
            print(f"\nEnriching with BrowserStack data from {bs_file}...")
            bs_lookup = load_browserstack_lookup(bs_file)
        else:
            print(f"\nWARNING: BrowserStack file not found: {bs_file}", file=sys.stderr)

    bs_matched, bs_total = 0, 0
    if bs_lookup:
        print(f"  Loaded {len(bs_lookup)} BrowserStack test cases")
        bs_matched, bs_total = enrich_with_browserstack(graph, bs_lookup)
        print(f"  Matched {bs_matched}/{bs_total} numeric IDs to BrowserStack names")

    # Dynamic output file name
    module_slug = module_name.replace("-", "_")
    output_json = os.path.join(SCRIPT_DIR, "regression.json")
    output_csv = os.path.join(SCRIPT_DIR, f"{module_slug}_service_graph.csv")

    with open(output_json, "w") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "serviceName", "host", "features", "TestGroups",
            "testCaseIds", "impacted_service", "supported_flows"
        ])
        writer.writeheader()
        for key, entry in graph.items():
            writer.writerow({
                "serviceName": entry["serviceName"],
                "host": entry["host"],
                "features": ";".join(entry["features"]),
                "TestGroups": ";".join(entry["TestGroups"]),
                "testCaseIds": ";".join(entry["testCaseIds"]),
                "impacted_service": ";".join(entry["impacted_service"]),
                "supported_flows": ";".join(entry["supported_flows"]),
            })

    print()
    print("=" * 70)
    print(f"Service graph written to {output_json}")
    print(f"  Module: {module_name}")
    print(f"  Architecture: {arch}")
    print(f"  Services: {len(graph)}")
    total_features = sum(len(v['features']) for v in graph.values())
    total_groups = len(set(g for v in graph.values() for g in v['TestGroups']))
    services_with_host = sum(1 for v in graph.values() if v['host'])
    services_with_tests = sum(1 for v in graph.values() if v['TestGroups'])
    total_test_ids = sum(len(v['testCaseIds']) for v in graph.values())
    print(f"  Features: {total_features}")
    print(f"  Unique test groups: {total_groups}")
    print(f"  Services with host: {services_with_host}/{len(graph)}")
    print(f"  Services with tests: {services_with_tests}/{len(graph)}")
    print(f"  Test cases: {total_test_ids}")
    if bs_lookup and bs_total:
        print(f"  BrowserStack enriched: {bs_matched}/{bs_total}")
    print("=" * 70)
    print(f"CSV written to {output_csv}")


if __name__ == "__main__":
    main()
