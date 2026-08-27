#!/usr/bin/env python3
"""
Generate <module>_regression.json for every module using a GLOBAL BrowserStack index.

Self-contained alternative to generate_service_graph.py — the two scripts share
no code, so either can be deleted without touching the other.

  generate_service_graph.py   resolves each module to its BrowserStack
                              project(s) from a hand-maintained mapping and
                              fetches only those projects.
  this script                 enumerates ALL projects (/api/v2/projects), fetches
                              every project's test cases once, builds one global
                              {id: test case} index, and enriches every module
                              from it — no module→project mapping needed.

Why: a wrong or missing mapping entry silently yields 0% enrichment for a module,
indistinguishable from "these test cases were deleted". A global index removes
the mapping from the critical path — an annotation ID matches whichever project
it actually lives in — and enriches modules that have no mapping at all. As a
by-product the run reports the mapping it observed, so the module→project
relationship can be read off real data instead of maintained by hand.

Cost: one sweep of every project per run, amortised across all modules.
Use --use-cache while iterating, --max-projects N for a quick smoke test.

How a module is turned into a service graph (the static half):
  A. Controller-based:  Controller → Client → Endpoint → PropertiesInternal
  B. Helper-based:      Helper → Client → Endpoint
Both are auto-detected per module; all paths are discovered at runtime.

Test case IDs: BrowserStack identifies a test case as "TC-<n>" or "C<n>" (two
separate namespaces). GBT annotations use "TC-<n>", "C<n>", or a bare "<n>";
a bare ID resolves to whichever prefix exists, and is reported as ambiguous when
both do.

Credentials come from regression-extractor/.env or the environment:
    BS_USERNAME / BS_ACCESS_KEY   (or BS_AUTH_TOKEN), optional BS_API_HOST

Usage:
    python3 generate_service_graph_get_all_tc.py                  # all modules
    python3 generate_service_graph_get_all_tc.py -m gopay          # one module
    python3 generate_service_graph_get_all_tc.py --use-cache       # reuse index
    python3 generate_service_graph_get_all_tc.py --workers 16
    python3 generate_service_graph_get_all_tc.py --max-projects 10 # smoke test
    python3 generate_service_graph_get_all_tc.py --index-only      # build index only

Output: <module>_regression.json + .csv (one per module, in this script's
        directory), plus bs_index_all_projects.json (the cached global index).
"""

import argparse
import base64
import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(SCRIPT_DIR, "bs_index_all_projects.json")

DEFAULT_API_HOST = "https://test-management.browserstack.com"
PAGE_SIZE = 300
MAX_RETRIES = 4


# ===========================================================================
# Static analysis — repo layout, service graph, output files
# ===========================================================================

def find_repo_root():
    """Walk up from SCRIPT_DIR to find the repo root (contains .git)."""
    d = SCRIPT_DIR
    while d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(os.path.dirname(SCRIPT_DIR))


REPO_ROOT = find_repo_root()


def normalize_module_name(name):
    """Normalize a module argument to its Gradle directory name.

    Accepts the shapes people actually type — GOPAY, gopay, DRIVER_PLATFORM,
    driver_platform — and resolves them to the on-disk module directory.
    """
    if not name:
        return name
    candidate = name.strip().lower()
    if os.path.isdir(os.path.join(REPO_ROOT, candidate)):
        return candidate
    dashed = candidate.replace("_", "-")
    if os.path.isdir(os.path.join(REPO_ROOT, dashed)):
        return dashed
    # Modules whose directory drops the separator entirely (helpcenter, merchantlending)
    squashed = candidate.replace("_", "").replace("-", "")
    if os.path.isdir(os.path.join(REPO_ROOT, squashed)):
        return squashed
    return candidate


def discover_all_modules():
    """List every Gradle module from settings.gradle whose directory exists.

    Used when --module is omitted. Falls back to scanning for directories that
    look like Gradle modules if settings.gradle can't be read.
    """
    settings = os.path.join(REPO_ROOT, "settings.gradle")
    modules = []
    if os.path.isfile(settings):
        with open(settings, encoding="utf-8", errors="ignore") as f:
            for m in re.finditer(r"^\s*include\s+['\"]([^'\"]+)['\"]", f.read(), re.M):
                name = m.group(1).lstrip(":").strip()
                if name and name not in modules:
                    modules.append(name)
    if not modules:
        modules = sorted(
            d for d in os.listdir(REPO_ROOT)
            if os.path.isdir(os.path.join(REPO_ROOT, d, "src"))
        )
    return [m for m in modules if os.path.isdir(os.path.join(REPO_ROOT, m))]


CONTROLLER_DIR_NAMES = {"controller", "controllers", "controlers"}


HELPER_DIR_NAMES = {"helper", "helpers"}


CLIENT_DIR_NAMES = {"client", "clients"}


CLIENTWRAPPER_DIR_NAMES = {"clientwrapper", "clientwrappers"}


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
        "endpoint_dirs": [],
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
        basename = os.path.basename(root).lower()
        if basename in CONTROLLER_DIR_NAMES:
            dirs["controller_dirs"].append(root)
        elif basename in HELPER_DIR_NAMES:
            dirs["helper_dirs"].append(root)
        elif basename in CLIENT_DIR_NAMES:
            dirs["client_dirs"].append(root)
        elif basename in CLIENTWRAPPER_DIR_NAMES:
            dirs["clientwrapper_dirs"].append(root)

    # Endpoints are matched by file name (*Endpoint.java), so scan the whole
    # module rather than a whitelist of directory names — modules put them in
    # entities/, apis/, serviceEndpoints/, endpoint/, endpoints/, ...
    dirs["endpoint_dirs"] = [main_java]

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
    print(f"  Endpoint scan     : {'whole src/main/java' if dirs['endpoint_dirs'] else '(none)'}")
    print(f"  Test dirs         : {len(dirs['test_dirs'])}")


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


def scan_entry_points(scan_dirs, base_dir, name_token=None):
    """Scan entry point classes (controllers or helpers) across directories.

    Args:
        scan_dirs: list of directories to scan
        base_dir: module base dir for relative paths
        name_token: if set, only include classes whose name *contains* this
                    token (e.g. "Controller", "Helper"). None = include all.
                    Substring rather than suffix, so real entry points like
                    WalkerServiceControllerInternal, CourierControllers and
                    ThaiKycHelperV2 are kept, while unrelated classes that
                    share the directory are still filtered out.

    Returns {ClassName: {clients: [...], methods: [...], file: str}}
    """
    entry_points = {}
    for sdir in scan_dirs:
        for root, _, files in os.walk(sdir):
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                class_name = fname.replace(".java", "")
                if name_token and name_token not in class_name:
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
                # String.format host+path (gofood-style):
                #   String.format("%s/gofood/meal-scheduler/v1/orders", SomeProperties.host)
                for m in re.finditer(r'String\.format\(\s*"%s(/[^"]*)"', content):
                    if m.group(1) != "/":
                        url_paths.add(m.group(1))

                # Extract host references from the endpoint
                host_ref = None
                # Pattern: PropertiesReader.getXxxHost() or propertiesReader.getXxxHost()
                m = re.search(r'(?:\w+\.)*(?:get\w*Host\w*|get\w*BaseUrl\w*)\s*\(', content)
                if m:
                    host_ref = m.group(0).rstrip("(").strip()
                else:
                    # Static field host refs (gofood-style): GoFoodProperties.mealSchedulerHost
                    m = re.search(r'(\w*Propert(?:ies|y)\.\w*(?:[Hh]ost|[Bb]aseUrl)\w*)', content)
                    if m:
                        host_ref = m.group(1)

                endpoints[class_name] = {
                    "urlConstant": url_const,
                    "urlPaths": sorted(url_paths),
                    "hostRef": host_ref,
                    "file": os.path.relpath(fpath, base_dir),
                }
    return endpoints


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

        # Capture every quoted value, then keep only the ones that parse as IDs.
        # Values take several shapes: "5214458", "TC-5214458", "C1046", and
        # "5228461||5228581||..." — and sometimes prose, which is dropped.
        tc_ids = []
        tc_match = re.search(r'testCaseIds\s*=\s*\{([^}]*)\}', block)
        if tc_match:
            for value in re.findall(r'"([^"]*)"', tc_match.group(1)):
                for token in split_id_tokens(value):
                    if token not in tc_ids:
                        tc_ids.append(token)

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


def _iter_step_pairs(raw):
    """Yield (step, expected_result) pairs from any BrowserStack steps payload shape.

    BrowserStack returns steps in a few shapes depending on the endpoint:
      - list of {step, result} / {description, expected_result}
      - dict already keyed by step number
      - a plain string (single-block / BDD style test case)
    """
    if not raw:
        return

    if isinstance(raw, str):
        yield raw, None
        return

    if isinstance(raw, dict):
        # Some payloads wrap the list, e.g. {"test_case_steps": [...]}
        for key in ("steps", "test_case_steps", "data"):
            if isinstance(raw.get(key), (list, dict)):
                yield from _iter_step_pairs(raw[key])
                return
        # A single step object rather than a map of them
        if "step" in raw or "description" in raw:
            yield (raw.get("step") or raw.get("description"),
                   raw.get("expected_result") or raw.get("result"))
            return
        for _, value in sorted(raw.items(), key=lambda kv: str(kv[0])):
            yield from _iter_step_pairs(value)
        return

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield (item.get("step") or item.get("description") or item.get("name"),
                       item.get("expected_result") or item.get("result"))
            else:
                yield from _iter_step_pairs(item)
        return


def flatten_steps(raw):
    """Flatten a BrowserStack steps payload into (steps, expected_result) strings.

    All step text is joined into one string, and all expected results into another.
    Returns (None, None) when there is nothing usable.
    """
    steps = []
    expected = []
    for step, exp in _iter_step_pairs(raw):
        if step and str(step).strip():
            steps.append(str(step).strip())
        if exp and str(exp).strip():
            expected.append(str(exp).strip())

    return ("\n".join(steps) or None, "\n".join(expected) or None)


def extract_steps_from_testcase(tc):
    """Pull (steps, expected_result) out of a raw BrowserStack test case dict."""
    for key in ("steps", "test_case_steps", "testCaseSteps", "test_steps"):
        if tc.get(key):
            return flatten_steps(tc[key])
    return (None, None)


ID_RE = re.compile(r'^\s*(TC|C)?[-_\s]*(\d+)\s*$', re.IGNORECASE)


PREFIX_PREFERENCE = ("TC", "C")


def parse_test_case_id(raw):
    """Parse an ID into (prefix, digits); prefix is 'TC', 'C' or '' (bare).

    Returns None for anything that isn't an ID — blank strings and the prose
    that sometimes lands in testCaseIds are rejected rather than matched.
    """
    if raw is None:
        return None
    m = ID_RE.match(str(raw))
    if not m:
        return None
    prefix = (m.group(1) or "").upper()
    return prefix, m.group(2)


def canonical_key(prefix, digits):
    """Internal lookup key for a prefixed ID: 'TC-123' / 'C-123'."""
    return f"{prefix}-{digits}"


def split_id_tokens(raw):
    """Split one annotation value into individual ID tokens.

    Handles the '5228461||5228581||5228482' form some tests use, and drops
    tokens that aren't IDs.
    """
    if raw is None:
        return []
    tokens = []
    for part in re.split(r"\|\||,|;", str(raw)):
        # Keep the token as the annotation wrote it (just trimmed) — matching
        # goes through parse_test_case_id, so no need to rewrite the form.
        if parse_test_case_id(part):
            tokens.append(part.strip())
    return tokens


class BSLookup:
    """BrowserStack test cases indexed for prefix-aware matching.

    Entries are keyed by canonical prefixed key ('TC-123' / 'C-123'), with a
    secondary index by bare number so a bare annotation ID can find whichever
    prefix exists.
    """

    def __init__(self):
        self.by_key = {}
        self.by_number = defaultdict(list)
        self.collisions = []
        self.ambiguous = {}

    def __len__(self):
        return len(self.by_key)

    def __bool__(self):
        return bool(self.by_key)

    def entries(self):
        return self.by_key.values()

    def add(self, entry):
        """Index one entry, keyed off its BrowserStack identifier."""
        parsed = parse_test_case_id(entry.get("testId"))
        if not parsed:
            return False
        prefix, digits = parsed
        # A BrowserStack ID with no prefix is treated as TC- (the default form).
        prefix = prefix or "TC"
        key = canonical_key(prefix, digits)
        if key in self.by_key:
            existing = self.by_key[key].get("project")
            incoming = entry.get("project")
            if existing != incoming:
                self.collisions.append((key, existing, incoming))
            return False
        entry = dict(entry, canonicalKey=key)
        self.by_key[key] = entry
        self.by_number[digits].append(key)
        return True

    def get(self, raw_id):
        """Resolve a GBT annotation ID. Returns (entry_or_None, was_ambiguous).

        An explicit prefix must match that prefix exactly. A bare ID resolves to
        whichever prefix exists; if both do it is ambiguous and PREFIX_PREFERENCE
        decides, with the choice recorded for reporting.
        """
        parsed = parse_test_case_id(raw_id)
        if not parsed:
            return None, False
        prefix, digits = parsed

        if prefix:
            return self.by_key.get(canonical_key(prefix, digits)), False

        candidates = self.by_number.get(digits) or []
        if not candidates:
            return None, False
        if len(candidates) == 1:
            return self.by_key[candidates[0]], False

        for preferred in PREFIX_PREFERENCE:
            key = canonical_key(preferred, digits)
            if key in candidates:
                self.ambiguous[digits] = list(candidates)
                return self.by_key[key], True
        self.ambiguous[digits] = list(candidates)
        return self.by_key[candidates[0]], True

    def merge(self, other):
        """Merge another lookup in — existing keys win (first project listed)."""
        for entry in other.entries():
            self.add(entry)
        self.collisions.extend(other.collisions)
        return self

    def to_dict(self):
        return {k: v for k, v in self.by_key.items()}

    @classmethod
    def from_entries(cls, entries):
        lookup = cls()
        for entry in entries:
            lookup.add(entry)
        return lookup

    def prefix_counts(self):
        counts = defaultdict(int)
        for key in self.by_key:
            counts[key.split("-", 1)[0]] += 1
        return dict(counts)


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
        controllers = scan_entry_points(dirs["controller_dirs"], base_dir,
                                        name_token="Controller")
        print(f"  Found {len(controllers)} controllers")
        entry_points.update(controllers)

    if dirs["helper_dirs"]:
        print("Scanning helpers...")
        helpers = scan_entry_points(dirs["helper_dirs"], base_dir, name_token="Helper")
        print(f"  Found {len(helpers)} helpers")
        entry_points.update(helpers)

    if not entry_points:
        print(f"WARNING: No controllers or helpers found in {module_name}.", file=sys.stderr)

    # 5. Scan clients (including clientwrappers)
    all_client_dirs = dirs["client_dirs"] + dirs["clientwrapper_dirs"]
    print("Scanning clients...")
    clients = scan_clients(all_client_dirs, base_dir)
    print(f"  Found {len(clients)} clients")

    # 6. Scan endpoints (*Endpoint.java anywhere under src/main/java)
    print("Scanning endpoints...")
    endpoints = scan_endpoints(dirs["endpoint_dirs"], base_dir, properties_internal_class)
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

        # Collect test cases — one object per (id, method), deduplicated.
        # name/steps stay null here; they are filled in from BrowserStack later.
        raw_ids = ep_test_ids.get(ep_name, [])
        seen_methods = set()
        seen_keys = set()
        test_cases = []
        for tid in raw_ids:
            method_name = tid["method"]
            if method_name in seen_methods:
                continue
            seen_methods.add(method_name)
            # No TCID on the annotation → method_name only, everything else null
            for tc_id in (tid["testCaseIds"] or [None]):
                key = (tc_id, method_name)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                test_cases.append({
                    "id": tc_id,
                    "name": None,
                    "steps": None,
                    "expected_result": None,
                    "method_name": method_name,
                })
        test_cases.sort(key=lambda tc: (tc["id"] or "", tc["method_name"]))

        graph[display_key] = {
            "serviceName": service_name,
            "host": host,
            "features": features,
            "TestGroups": groups,
            "testCaseIds": test_cases,
            "impacted_service": sorted(impacted),
            "supported_flows": sorted(flows),
        }

    return graph


def write_outputs(module_name, graph):
    """Write <module>_regression.json + .csv. Returns (json_path, csv_path)."""
    module_slug = module_name.replace("-", "_")
    output_json = os.path.join(SCRIPT_DIR, f"{module_slug}_regression.json")
    output_csv = os.path.join(SCRIPT_DIR, f"{module_slug}_regression.csv")

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
                "testCaseIds": ";".join(
                    tc["id"] or tc["method_name"] for tc in entry["testCaseIds"]
                ),
                "impacted_service": ";".join(entry["impacted_service"]),
                "supported_flows": ";".join(entry["supported_flows"]),
            })

    return output_json, output_csv


def format_duration(seconds):
    """Render an elapsed time as e.g. '48.3s' or '3m 12.4s' or '1h 04m 09s'."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:04.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes:02d}m {int(secs):02d}s"
# ===========================================================================
# BrowserStack — HTTP with retry / backoff
# ===========================================================================

def api_host():
    return os.environ.get("BS_API_HOST", DEFAULT_API_HOST).rstrip("/")


def request_json(url, auth_header, label="", retries=MAX_RETRIES):
    """GET JSON with retry + backoff on 429 and 5xx.

    Returns (data, error). A rate limit must not be mistaken for "no more
    pages": sweeping every project makes 429s likely, and a silent truncation
    would look like unmatched test case IDs.
    """
    ctx = ssl.create_default_context()
    delay = 1.0

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url)
        req.add_header("Authorization", auth_header)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            retryable = e.code == 429 or 500 <= e.code < 600
            if retryable and attempt < retries:
                wait = float(e.headers.get("Retry-After") or delay)
                print(f"    HTTP {e.code} on {label} — retry {attempt}/{retries - 1} "
                      f"in {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                delay = min(delay * 2, 30)
                continue
            return None, f"HTTP {e.code} on {label}: {body}"
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                print(f"    Network error on {label} — retry {attempt}/{retries - 1} "
                      f"in {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            return None, f"URL error on {label}: {e}"
        except json.JSONDecodeError as e:
            return None, f"Bad JSON on {label}: {e}"

    return None, f"gave up on {label}"


def unwrap(data, *keys):
    """Pull a list out of a BrowserStack payload, tolerating the wrapper shapes."""
    payload = data
    if isinstance(data.get("data"), dict):
        payload = data["data"]
    elif isinstance(data.get("data"), list):
        return data["data"], data.get("info") or {}
    for k in keys:
        if isinstance(payload.get(k), list):
            return payload[k], payload.get("info") or data.get("info") or {}
    return [], payload.get("info") or data.get("info") or {}


def has_more(info, got, page_size):
    """Decide whether to ask for another page."""
    nxt = info.get("next")
    if nxt is False or str(nxt).lower() == "false":
        return False
    if nxt:
        return True
    return got >= page_size


# ===========================================================================
# Phase 1 — enumerate every project
# ===========================================================================

def fetch_all_projects(auth_header, max_projects=None):
    """Page /api/v2/projects and return an ordered list of (identifier, name)."""
    projects = []
    page = 1
    while True:
        url = f"{api_host()}/api/v2/projects?p={page}"
        data, err = request_json(url, auth_header, label=f"projects page {page}")
        if err:
            print(f"  {err}", file=sys.stderr)
            break

        items, info = unwrap(data, "projects", "project")
        if not items:
            break

        known = {pid for pid, _ in projects}
        for p in items:
            ident = p.get("identifier") or p.get("project_id") or p.get("id")
            if ident is None:
                continue
            ident = str(ident)
            if ident not in known:
                known.add(ident)
                projects.append((ident, p.get("name") or p.get("title") or ""))

        print(f"    page {page}: {len(items)} project(s) (total {len(projects)})")

        if max_projects and len(projects) >= max_projects:
            projects = projects[:max_projects]
            break
        if not has_more(info, len(items), len(items) or 1):
            break
        page += 1

    return projects


# ===========================================================================
# Phase 2 — fetch every project's test cases
# ===========================================================================

def fetch_project_test_cases(project_id, auth_header):
    """Fetch all test cases for one project. Returns (project_id, list, error)."""
    out = []
    page = 1
    while True:
        url = (f"{api_host()}/api/v2/projects/{project_id}/test-cases"
               f"?p={page}&page_size={PAGE_SIZE}")
        data, err = request_json(url, auth_header, label=f"{project_id} page {page}")
        if err:
            return project_id, out, err

        items, info = unwrap(data, "test_cases", "testcases")
        if not items:
            break

        for tc in items:
            identifier = tc.get("identifier") or tc.get("id") or ""
            steps, expected = extract_steps_from_testcase(tc)
            out.append({
                "testId": str(identifier),
                "testTitle": tc.get("title") or tc.get("name") or "",
                "steps": steps,
                "expectedResult": expected,
                "folderId": tc.get("folder_id") or tc.get("folderId"),
                "project": project_id,
            })

        if not has_more(info, len(items), PAGE_SIZE):
            break
        page += 1

    return project_id, out, None


def build_global_index(projects, auth_header, workers=8):
    """Fetch every project in parallel and merge into one BSLookup.

    Returns (index, stats). Collisions — the same test case ID in more than one
    project — are counted and reported, since the approach rests on IDs being
    unique across projects.
    """
    index = BSLookup()
    per_project_counts = {}
    errors = []
    fetched = {}

    print(f"  Fetching test cases from {len(projects)} project(s) "
          f"with {workers} worker(s)...")

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_project_test_cases, pid, auth_header): pid
            for pid, _ in projects
        }
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                project_id, test_cases, err = fut.result()
            except Exception as e:  # a worker blew up — keep the sweep going
                errors.append((pid, str(e)))
                continue

            done += 1
            if err:
                errors.append((project_id, err))
            per_project_counts[project_id] = len(test_cases)
            fetched[project_id] = test_cases

            if done % 20 == 0 or done == len(projects):
                print(f"    {done}/{len(projects)} projects — "
                      f"{sum(len(v) for v in fetched.values())} test cases")

    # Merge in project order, not completion order: threads finish
    # nondeterministically, and an ID present in two projects must resolve the
    # same way on every run.
    for project_id, _ in projects:
        for tc in fetched.get(project_id, []):
            index.add(tc)

    stats = {
        "projects": len(projects),
        "testCases": len(index),
        "collisions": index.collisions,
        "errors": errors,
        "perProject": per_project_counts,
        "prefixCounts": index.prefix_counts(),
    }
    return index, stats


# ===========================================================================
# Index cache
# ===========================================================================

def save_index(index, projects, path=INDEX_FILE):
    payload = {
        "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "projects": [{"id": pid, "name": name} for pid, name in projects],
        "testCases": index.to_dict(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"  Index saved to {path} ({size_mb:.1f} MB)")


def load_index(path=INDEX_FILE):
    """Load a saved index. Returns (BSLookup, fetched_at, projects) or None."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    raw = payload.get("testCases") or {}
    if not raw:
        return None
    index = BSLookup.from_entries(raw.values())
    return index, payload.get("fetchedAt", "unknown"), payload.get("projects", [])


# ===========================================================================
# Per-module processing
# ===========================================================================

def enrich_from_index(graph, index):
    """Enrich a module's graph from the global index.

    Returns (matched, total_with_id, project_hits, ambiguous). project_hits
    counts how many matched IDs came from each project — an empirical read on
    which project(s) a module actually belongs to.
    """
    matched = 0
    total_with_id = 0
    ambiguous = 0
    project_hits = Counter()

    for entry in graph.values():
        for tc in entry["testCaseIds"]:
            raw = tc.get("id")
            if not raw:
                continue
            total_with_id += 1
            bs, was_ambiguous = index.get(raw)
            if was_ambiguous:
                ambiguous += 1
            if not bs:
                continue
            tc["name"] = bs.get("testTitle") or None
            tc["steps"] = bs.get("steps")
            tc["expected_result"] = bs.get("expectedResult")
            matched += 1
            if bs.get("project"):
                project_hits[bs["project"]] += 1

    return matched, total_with_id, project_hits, ambiguous


def process_module(module_name, index):
    """Build, enrich and write one module. Returns a stats dict."""
    print()
    print("=" * 70)
    print(f"Generating Service Graph — {module_name}")
    print("=" * 70)

    print("\nDiscovering module structure...")
    dirs = discover_dirs(module_name)
    arch = detect_architecture(dirs)
    print_discovery(module_name, dirs, arch)
    print()

    graph = build_service_graph(module_name, dirs, arch)

    stats = {
        "module": module_name,
        "arch": arch,
        "services": len(graph),
        "testCases": 0,
        "withSteps": 0,
        "matched": 0,
        "withId": 0,
        "ambiguous": 0,
        "projectHits": Counter(),
        "written": False,
    }

    if not graph:
        print(f"\nNo services found in {module_name} — nothing to write.")
        return stats

    matched, with_id, project_hits, ambiguous = enrich_from_index(graph, index)
    stats["matched"], stats["withId"] = matched, with_id
    stats["projectHits"] = project_hits
    stats["ambiguous"] = ambiguous
    pct = (100.0 * matched / with_id) if with_id else 0.0
    print(f"  Enriched {matched}/{with_id} test case IDs from the global index "
          f"({pct:.1f}%)")
    if ambiguous:
        print(f"  NOTE: {ambiguous} bare ID(s) existed as both TC-<n> and C<n> — "
              f"resolved as {PREFIX_PREFERENCE[0]}-<n>")
    if project_hits:
        top = ", ".join(f"{p}:{n}" for p, n in project_hits.most_common(4))
        print(f"  Matched IDs by project: {top}")

    output_json, output_csv = write_outputs(module_name, graph)
    stats["written"] = True
    stats["testCases"] = sum(len(v["testCaseIds"]) for v in graph.values())
    stats["withSteps"] = sum(1 for v in graph.values()
                             for tc in v["testCaseIds"] if tc["steps"])

    print(f"\n  Services: {len(graph)}  Test cases: {stats['testCases']}  "
          f"With steps: {stats['withSteps']}")
    print(f"  Written: {output_json}")
    print(f"           {output_csv}")
    return stats


# ===========================================================================
# Reporting
# ===========================================================================

def print_index_report(stats, index, elapsed):
    print()
    print("=" * 78)
    print("GLOBAL INDEX")
    print("=" * 78)
    print(f"  Projects swept    : {stats['projects']}")
    print(f"  Test cases indexed: {stats['testCases']}")
    if stats.get("prefixCounts"):
        print("  By ID prefix      : "
              + ", ".join(f"{p}-*: {n}" for p, n in sorted(stats["prefixCounts"].items())))
    if index is not None:
        with_steps = sum(1 for v in index.entries() if v.get("steps"))
        print(f"  With steps        : {with_steps}/{stats['testCases']}")
    print(f"  Fetch time        : {format_duration(elapsed)}")

    failed = {p for p, _ in stats["errors"]}
    empty = [p for p, n in sorted(stats["perProject"].items())
             if n == 0 and p not in failed]
    if empty:
        print(f"  Empty projects    : {len(empty)} "
              f"({', '.join(empty[:8])}{' ...' if len(empty) > 8 else ''})")

    if stats["collisions"]:
        print(f"  COLLISIONS        : {len(stats['collisions'])} test case ID(s) "
              f"appear in more than one project — kept the first seen.")
        for key, kept, dropped in stats["collisions"][:5]:
            print(f"                      {key}: kept {kept}, ignored {dropped}")
        if len(stats["collisions"]) > 5:
            print(f"                      ... +{len(stats['collisions']) - 5} more")
    else:
        print("  Collisions        : none (IDs are unique across projects)")

    if stats["errors"]:
        print(f"  ERRORS            : {len(stats['errors'])} project(s) failed — "
              f"their test cases are missing from the index:", file=sys.stderr)
        for pid, err in stats["errors"][:8]:
            print(f"                      {pid}: {err}", file=sys.stderr)
    print("=" * 78)


def print_run_summary(results):
    width = 96
    print()
    print("=" * width)
    print("ALL MODULES SUMMARY")
    print("=" * width)
    print(f"{'Module':<24}{'Services':>9}{'TestCases':>11}{'Steps':>8}"
          f"{'Enriched':>18}{'Top project':>14}")
    print("-" * width)
    for r in results:
        enriched = f"{r['matched']}/{r['withId']}" if r["withId"] else "-"
        pct = f" ({100.0 * r['matched'] / r['withId']:.0f}%)" if r["withId"] else ""
        top = r["projectHits"].most_common(1)[0][0] if r["projectHits"] else "-"
        note = "" if r["written"] else "  (skipped)"
        print(f"{r['module']:<24}{r['services']:>9}{r['testCases']:>11}"
              f"{r['withSteps']:>8}{enriched + pct:>18}{top:>14}{note}")
    print("-" * width)
    written = [r for r in results if r["written"]]
    tot_matched = sum(r["matched"] for r in results)
    tot_with_id = sum(r["withId"] for r in results)
    tot_ambiguous = sum(r["ambiguous"] for r in results)
    print(f"Modules processed : {len(results)}  "
          f"(written: {len(written)}, skipped: {len(results) - len(written)})")
    print(f"Services          : {sum(r['services'] for r in results)}")
    print(f"Test cases        : {sum(r['testCases'] for r in results)}")
    print(f"With steps        : {sum(r['withSteps'] for r in results)}")
    if tot_with_id:
        print(f"Enriched          : {tot_matched}/{tot_with_id} "
              f"({100.0 * tot_matched / tot_with_id:.1f}%)")
    if tot_ambiguous:
        print(f"Ambiguous bare IDs: {tot_ambiguous} "
              f"(resolved as {PREFIX_PREFERENCE[0]}-<n>)")
    print("=" * width)


def print_observed_mapping(results):
    """Print the module → project mapping the index actually observed.

    This script needs no mapping, but the observed one is worth reporting: it is
    read off real ID matches rather than maintained by hand, so it doubles as a
    check on any mapping kept elsewhere. Projects contributing fewer than 1% of a
    module's matches are treated as noise and dropped.
    """
    rows = [r for r in results if r["projectHits"]]
    if not rows:
        return
    print()
    print("=" * 78)
    print("OBSERVED MODULE → PROJECT MAPPING (from matched IDs)")
    print("=" * 78)
    for r in rows:
        total = sum(r["projectHits"].values())
        significant = [(p, n) for p, n in r["projectHits"].most_common()
                       if n >= max(2, total * 0.01)]
        detail = ", ".join(f"{p} ({100.0 * n / total:.0f}%)" for p, n in significant)
        print(f'  "{r["module"]}": "{", ".join(p for p, _ in significant)}",'
              f'{"":<{max(0, 34 - len(r["module"]))}}# {detail}')
    print("=" * 78)


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate <module>_regression.json for all modules using a "
                    "global BrowserStack index (every project fetched once)."
    )
    parser.add_argument("--module", "-m",
                        help="Only this module (the index is still global). "
                             "Omit to process every module in settings.gradle.")
    parser.add_argument("--use-cache", action="store_true",
                        help=f"Reuse the saved index ({os.path.basename(INDEX_FILE)}) "
                             "instead of fetching. Default is always fetch fresh.")
    parser.add_argument("--index-file", default=INDEX_FILE,
                        help="Path of the index cache file.")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel project fetches (default 8).")
    parser.add_argument("--max-projects", type=int,
                        help="Stop after N projects — for a quick smoke test.")
    parser.add_argument("--index-only", action="store_true",
                        help="Build and report the index, then stop.")
    args = parser.parse_args()

    started = time.perf_counter()
    index_elapsed = 0.0

    try:
        # ---------------- Phases 1 + 2: the global index ----------------
        index = None
        if args.use_cache:
            cached = load_index(args.index_file)
            if cached:
                index, fetched_at, projects = cached
                print("=" * 78)
                print(f"Using cached index: {args.index_file}")
                print(f"  {len(index)} test cases from {len(projects)} projects, "
                      f"fetched {fetched_at}")
                print("  (drop --use-cache to refresh)")
                print("=" * 78)
            else:
                print(f"No usable cache at {args.index_file} — fetching fresh.",
                      file=sys.stderr)

        if index is None:
            load_env_file()
            auth_header = build_browserstack_auth_header()
            if not auth_header:
                print("ERROR: No BrowserStack credentials found.", file=sys.stderr)
                print("       Put BS_USERNAME / BS_ACCESS_KEY in "
                      f"{os.path.join(SCRIPT_DIR, '.env')}", file=sys.stderr)
                return 2

            index_started = time.perf_counter()
            print("=" * 78)
            print("Enumerating BrowserStack projects...")
            print("=" * 78)
            projects = fetch_all_projects(auth_header, args.max_projects)
            if not projects:
                print("ERROR: No projects returned — cannot build an index.",
                      file=sys.stderr)
                return 2
            print(f"  Found {len(projects)} project(s)")

            index, index_stats = build_global_index(projects, auth_header, args.workers)
            index_elapsed = time.perf_counter() - index_started
            print_index_report(index_stats, index, index_elapsed)
            save_index(index, projects, args.index_file)

        if args.index_only:
            return 0

        # ---------------- Phase 3: modules ----------------
        build_started = time.perf_counter()
        if args.module:
            modules = [normalize_module_name(args.module)]
        else:
            modules = discover_all_modules()
            print()
            print("=" * 70)
            print(f"Processing all {len(modules)} modules against the global index")
            print("=" * 70)

        results = [process_module(m, index) for m in modules]
        build_elapsed = time.perf_counter() - build_started

        if len(results) > 1:
            print_run_summary(results)
        print_observed_mapping(results)

        print()
        print(f"Index fetch time : {format_duration(index_elapsed)}"
              f"{' (cached — no fetch)' if index_elapsed == 0 else ''}")
        print(f"Graph build time : {format_duration(build_elapsed)}")
        return 0
    finally:
        print(f"Total time taken : {format_duration(time.perf_counter() - started)}")


if __name__ == "__main__":
    sys.exit(main())
