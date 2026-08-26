#!/usr/bin/env python3
"""
Generate <module>_service_graph.json by tracing the service architecture.

Supports two architecture patterns (auto-detected per module):
  A. Controller-based (e.g. driver-platform):
       Controller → Client → Endpoint → PropertiesInternal
  B. Helper-based (e.g. gopay):
       Helper → Client → Endpoint (in apis/)

Works for any module — all paths are auto-discovered at runtime.

The BrowserStack project is auto-resolved from the module name
(see MODULE_BS_PROJECTS); -bp overrides it, -nb skips BrowserStack.

Omitting --module processes every module in settings.gradle, writing one
<module>_regression.json per module (one BrowserStack fetch per distinct project).

Usage:
    python3 generate_service_graph.py                             # all modules
    python3 generate_service_graph.py --module gopay              # → PR-166
    python3 generate_service_graph.py --module driver-platform    # → PR-143
    python3 generate_service_graph.py --module gopay -bp PR-999   # override
    python3 generate_service_graph.py --module gopay -nb          # offline
    python3 generate_service_graph.py --module care-platform -b testcases_PR-100.json

Output: <module>_regression.json (in this script's directory)
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
# Module → BrowserStack project mapping
# ---------------------------------------------------------------------------
# Keyed by the Gradle module directory name (as in settings.gradle), so
# `-m <module>` alone resolves the BrowserStack project. Override with -bp.
# Note: several modules deliberately share a project (payments domain on PR-166,
# and PR-143 across driver-platform / marketplace / pricing).

MODULE_BS_PROJECTS = {
    "care-platform": "PR-196",
    "cartography": "PR-149",
    "customer-platforms": "PR-140",
    "data-platform": "PR-152",
    "driver-platform": "PR-143",
    "ep-web-platform": "PR-181",
    "go-logistics": "PR-141",
    "gofood": "PR-125",
    "gomart": "PR-124",
    "gopay": "PR-166",
    "gopay-merchant": "PR-168",
    "gopaylater": "PR-178",
    "gtl": "PR-155",
    "helpcenter": "PR-119",
    "icp": "PR-129",
    "iris": "PR-166",
    "marketplace": "PR-143",
    "merchant-platform": "PR-134",
    "merchantlending": "PR-162",
    "midtrans-core-api": "PR-137",
    "midtrans-enterprise": "PR-294",
    "payment-core": "PR-166",
    "pricing": "PR-143",
    "ticket-arbitration": "PR-120",
    "transport": "PR-177",
    "vehicle-financing": "PR-193",
}



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
    if dashed in MODULE_BS_PROJECTS:
        return dashed
    return candidate


def resolve_bs_project(module_name):
    """Look up the BrowserStack project for a module, or None if unmapped."""
    return MODULE_BS_PROJECTS.get(module_name)


def discover_all_modules():
    """List every Gradle module from settings.gradle whose directory exists.

    Used when --module is omitted. Falls back to the BrowserStack mapping keys
    if settings.gradle can't be read.
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
        modules = sorted(MODULE_BS_PROJECTS)
    return [m for m in modules if os.path.isdir(os.path.join(REPO_ROOT, m))]

# ---------------------------------------------------------------------------
# Dynamic directory discovery
# ---------------------------------------------------------------------------

# Architectural directory names, matched case-insensitively. Modules spell these
# inconsistently — controller/controllers/Controller, and gomart's "controlers"
# typo — so each category carries every spelling that occurs in this repo.
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


def load_browserstack_lookup(bs_file):
    """Load BrowserStack test cases JSON → {numeric_id: {testId, testTitle, steps, expectedResult, folderId}}."""
    with open(bs_file) as f:
        data = json.load(f)

    lookup = {}
    for tc in data.get("testCases", []):
        bs_id = tc.get("testId", "")
        title = tc.get("testTitle", "")
        numeric = bs_id.replace("TC-", "") if bs_id.startswith("TC-") else bs_id
        if numeric:
            steps, expected = flatten_steps(tc.get("steps"))
            lookup[numeric] = {
                "testId": bs_id,
                "testTitle": title,
                "steps": steps,
                "expectedResult": expected or tc.get("expectedResult"),
                "folderId": tc.get("folderId"),
            }
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


def browserstack_get(url, auth_header, label=""):
    """GET a BrowserStack API URL and return the decoded JSON (or None)."""
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
        print(f"  HTTP {e.code} on {label or url}: {body[:200]}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"  URL error on {label or url}: {e.reason}", file=sys.stderr)
        return None


def fetch_browserstack_page(project_id, page, page_size, auth_header, api_host):
    """Fetch a single page of test cases from BrowserStack API."""
    url = f"{api_host}/api/v2/projects/{project_id}/test-cases?p={page}&page_size={page_size}"
    return browserstack_get(url, auth_header, label=f"page {page}")


def fetch_browserstack_testcase_detail(project_id, tc_id, folder_id, auth_header, api_host):
    """Fetch a single test case detail (used to pull steps the list endpoint omits)."""
    urls = []
    if folder_id:
        urls.append(
            f"{api_host}/api/v2/projects/{project_id}/folder/{folder_id}/test-cases/{tc_id}"
        )
    urls.append(f"{api_host}/api/v2/projects/{project_id}/test-cases/{tc_id}")

    for url in urls:
        data = browserstack_get(url, auth_header, label=f"test case {tc_id}")
        if not data:
            continue
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        tc = payload.get("test_case") or payload.get("testcase") or payload
        if isinstance(tc, dict):
            return tc
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
            steps, expected = extract_steps_from_testcase(tc)
            all_test_cases.append({
                "testId": str(identifier),
                "testTitle": title,
                "steps": steps,
                "expectedResult": expected,
                "folderId": tc.get("folder_id") or tc.get("folderId"),
            })

        print(f"got {len(test_cases)} (total: {len(all_test_cases)})")

        has_next = info.get("next")
        if has_next is None:
            if len(test_cases) < page_size:
                break
        if has_next is False or has_next == "false":
            break

        page += 1

    print(f"  Fetched {len(all_test_cases)} test cases from BrowserStack")

    lookup = {}
    for tc in all_test_cases:
        bs_id = tc["testId"]
        numeric = bs_id.replace("TC-", "") if bs_id.startswith("TC-") else bs_id
        if numeric:
            lookup[numeric] = tc
    return lookup


def hydrate_steps(bs_lookup, numeric_ids, project_id):
    """Fetch steps from the test case detail endpoint for IDs whose steps are missing.

    Only the IDs actually referenced by the graph are fetched, so this stays bounded.
    """
    missing = [n for n in sorted(numeric_ids)
               if n in bs_lookup and not bs_lookup[n].get("steps")]
    if not missing or not project_id:
        return 0

    load_env_file()
    auth_header = build_browserstack_auth_header()
    if not auth_header:
        return 0
    api_host = os.environ.get("BS_API_HOST", "https://test-management.browserstack.com").rstrip("/")

    print(f"  Fetching steps for {len(missing)} referenced test case(s)...")
    fetched = 0
    for numeric in missing:
        entry = bs_lookup[numeric]
        detail = fetch_browserstack_testcase_detail(
            project_id, entry.get("testId") or numeric, entry.get("folderId"),
            auth_header, api_host,
        )
        if not detail:
            continue
        steps, expected = extract_steps_from_testcase(detail)
        if steps:
            entry["steps"] = steps
            fetched += 1
        if expected and not entry.get("expectedResult"):
            entry["expectedResult"] = expected
        if not entry.get("testTitle"):
            entry["testTitle"] = detail.get("title") or detail.get("name") or ""
    print(f"  Got steps for {fetched}/{len(missing)}")
    return fetched


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def collect_referenced_numeric_ids(graph):
    """Collect the BrowserStack numeric IDs actually referenced by the graph."""
    numeric_ids = set()
    for entry in graph.values():
        for tc in entry["testCaseIds"]:
            numeric = normalize_bs_id(tc.get("id"))
            if numeric:
                numeric_ids.add(numeric)
    return numeric_ids


def normalize_bs_id(tc_id):
    """Strip a 'TC-' prefix so annotation IDs line up with the BrowserStack lookup."""
    if not tc_id:
        return None
    return tc_id[3:] if tc_id.startswith("TC-") else tc_id


def enrich_with_browserstack(graph, bs_lookup):
    """Fill in name + steps + expected_result on each test case object from BrowserStack.

    Test cases with an ID that BrowserStack doesn't know about — and those with no ID
    at all (method_name only) — keep those fields as null.
    """
    total_matched = 0
    total_with_id = 0

    for entry in graph.values():
        for tc in entry["testCaseIds"]:
            numeric = normalize_bs_id(tc.get("id"))
            if not numeric:
                continue
            total_with_id += 1
            bs = bs_lookup.get(numeric)
            if not bs:
                continue
            tc["name"] = bs.get("testTitle") or None
            tc["steps"] = bs.get("steps")
            tc["expected_result"] = bs.get("expectedResult")
            total_matched += 1

    return total_matched, total_with_id


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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


def get_bs_lookup(bs_project, args, bs_cache):
    """Resolve the BrowserStack lookup for a project, fetching at most once per project.

    Modules deliberately share projects (PR-166, PR-143), so the cache keeps an
    all-modules run down to one fetch per distinct project.
    """
    if bs_project:
        if bs_project in bs_cache:
            print(f"\nReusing BrowserStack test cases for {bs_project} "
                  f"(already fetched this run)")
            return bs_cache[bs_project]
        print(f"\nFetching BrowserStack test cases for {bs_project} from API...")
        lookup = fetch_browserstack_testcases(bs_project)
        bs_cache[bs_project] = lookup
        return lookup

    if args.browserstack:
        if "__file__" in bs_cache:
            return bs_cache["__file__"]
        bs_file = args.browserstack
        if not os.path.exists(bs_file):
            auto_path = os.path.join(SCRIPT_DIR, f"testcases_{bs_file}.json")
            if os.path.exists(auto_path):
                bs_file = auto_path
        if os.path.exists(bs_file):
            print(f"\nEnriching with BrowserStack data from {bs_file}...")
            lookup = load_browserstack_lookup(bs_file)
        else:
            print(f"\nWARNING: BrowserStack file not found: {bs_file}", file=sys.stderr)
            lookup = None
        bs_cache["__file__"] = lookup
        return lookup

    return None


def process_module(module_name, args, bs_cache):
    """Build, enrich and write the graph for one module. Returns a stats dict."""

    # Resolve the BrowserStack project: explicit -bp wins, otherwise the mapping.
    bs_project = args.browserstack_project
    if not bs_project and not args.browserstack and not args.no_browserstack:
        bs_project = resolve_bs_project(module_name)

    print()
    print("=" * 70)
    print(f"Generating Service Graph — {module_name}")
    print("=" * 70)
    if args.browserstack_project:
        print(f"  BrowserStack project: {bs_project} (override)")
    elif bs_project:
        print(f"  BrowserStack project: {bs_project} (auto-resolved from module)")
    elif not args.browserstack and not args.no_browserstack:
        print(f"  BrowserStack project: (no mapping for '{module_name}' — "
              f"pass -bp <project> to enrich)")

    # Discover directories
    print("\nDiscovering module structure...")
    dirs = discover_dirs(module_name)
    arch = detect_architecture(dirs)
    print_discovery(module_name, dirs, arch)
    print()

    # Build the graph
    graph = build_service_graph(module_name, dirs, arch)

    stats = {
        "module": module_name,
        "arch": arch,
        "bsProject": bs_project,
        "services": len(graph),
        "testCases": 0,
        "withSteps": 0,
        "bsMatched": 0,
        "bsTotal": 0,
        "written": False,
    }

    if not graph:
        print(f"\nNo services found in {module_name} — nothing to write.")
        return stats

    # Enrich with BrowserStack
    bs_lookup = get_bs_lookup(bs_project, args, bs_cache)

    if bs_lookup:
        print(f"  Loaded {len(bs_lookup)} BrowserStack test cases")
        hydrate_steps(bs_lookup, collect_referenced_numeric_ids(graph), bs_project)
        bs_matched, bs_total = enrich_with_browserstack(graph, bs_lookup)
        stats["bsMatched"], stats["bsTotal"] = bs_matched, bs_total
        print(f"  Matched {bs_matched}/{bs_total} test case IDs to BrowserStack")

    output_json, output_csv = write_outputs(module_name, graph)
    stats["written"] = True

    total_features = sum(len(v['features']) for v in graph.values())
    total_groups = len(set(g for v in graph.values() for g in v['TestGroups']))
    services_with_host = sum(1 for v in graph.values() if v['host'])
    services_with_tests = sum(1 for v in graph.values() if v['TestGroups'])
    total_test_ids = sum(len(v['testCaseIds']) for v in graph.values())
    with_steps = sum(1 for v in graph.values() for tc in v['testCaseIds'] if tc['steps'])
    stats["testCases"] = total_test_ids
    stats["withSteps"] = with_steps

    print()
    print("=" * 70)
    print(f"Service graph written to {output_json}")
    print(f"  Module: {module_name}")
    print(f"  Architecture: {arch}")
    print(f"  Services: {len(graph)}")
    print(f"  Features: {total_features}")
    print(f"  Unique test groups: {total_groups}")
    print(f"  Services with host: {services_with_host}/{len(graph)}")
    print(f"  Services with tests: {services_with_tests}/{len(graph)}")
    print(f"  Test cases: {total_test_ids}")
    print(f"  Test cases with steps: {with_steps}/{total_test_ids}")
    if bs_lookup and stats["bsTotal"]:
        print(f"  BrowserStack enriched: {stats['bsMatched']}/{stats['bsTotal']}")
    print("=" * 70)
    print(f"CSV written to {output_csv}")

    return stats


def print_run_summary(results):
    """Print the aggregate table for an all-modules (or multi-module) run."""
    print()
    print("=" * 78)
    print("ALL MODULES SUMMARY")
    print("=" * 78)
    print(f"{'Module':<24}{'Project':<10}{'Services':>9}{'TestCases':>11}"
          f"{'Steps':>8}{'BS':>12}")
    print("-" * 78)
    for r in results:
        bs = f"{r['bsMatched']}/{r['bsTotal']}" if r["bsTotal"] else "-"
        project = r["bsProject"] or "-"
        note = "" if r["written"] else "  (skipped)"
        print(f"{r['module']:<24}{project:<10}{r['services']:>9}{r['testCases']:>11}"
              f"{r['withSteps']:>8}{bs:>12}{note}")
    print("-" * 78)
    written = [r for r in results if r["written"]]
    print(f"Modules processed : {len(results)}  "
          f"(written: {len(written)}, skipped: {len(results) - len(written)})")
    print(f"Services          : {sum(r['services'] for r in results)}")
    print(f"Test cases        : {sum(r['testCases'] for r in results)}")
    print(f"With steps        : {sum(r['withSteps'] for r in results)}")
    print("=" * 78)


def main():
    import argparse as _ap

    parser = _ap.ArgumentParser(
        description="Generate a service graph for one module, or for all "
                    "modules when --module is omitted."
    )
    parser.add_argument(
        "--module", "-m",
        help="Module name (e.g. driver-platform, gopay, care-platform). "
             "Omit to process every module in settings.gradle.",
    )
    bs_group = parser.add_mutually_exclusive_group()
    bs_group.add_argument(
        "--browserstack", "-b",
        help="Path to a local BrowserStack test cases JSON file.",
    )
    bs_group.add_argument(
        "--browserstack-project", "-bp",
        help="BrowserStack project ID (e.g. PR-143). Overrides the module's "
             "auto-resolved project; without it the project is looked up from "
             "the module name.",
    )
    bs_group.add_argument(
        "--no-browserstack", "-nb", action="store_true",
        help="Skip BrowserStack entirely (offline run — names/steps stay null).",
    )
    args = parser.parse_args()

    if args.module:
        modules = [normalize_module_name(args.module)]
    else:
        modules = discover_all_modules()
        print("=" * 70)
        print(f"No --module given — processing all {len(modules)} modules")
        print("=" * 70)
        for m in modules:
            print(f"  {m:<24} → {resolve_bs_project(m) or '(no BS project)'}")
        if args.browserstack_project:
            print(f"\n  NOTE: -bp {args.browserstack_project} overrides the mapping "
                  f"for every module in this run.")

    bs_cache = {}
    results = []
    for module_name in modules:
        results.append(process_module(module_name, args, bs_cache))

    if len(results) > 1:
        print_run_summary(results)


if __name__ == "__main__":
    main()
