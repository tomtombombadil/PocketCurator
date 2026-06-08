"""
EmulationStation theme detection and system-logo resolution.

The user's idea: rather than bundle our own system logos, ask the device
which theme is currently active and pull logos out of it. Themes are
already installed on the device for ES itself, so we get whatever look
the user has chosen for free.

Strategy:
    1. Find candidate theme root directories for the firmware
    2. Find the active theme name from the firmware's config file
    3. For each system shortname, probe a small list of known relative
       path patterns inside the theme directory
    4. Return the first file that exists, or None

We do NOT parse the theme's theme.xml. Every popular ES theme has
per-system subfolders (knulli, art-book-next, canvas, etc.) and the
heuristic patterns below catch all of them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional


# Theme root directories, ordered by firmware preference. Earlier entries
# take priority - user-installed themes shadow firmware-bundled ones, so
# we put user paths first.
THEME_ROOT_CANDIDATES: List[str] = [
    # Batocera / Knulli
    "/userdata/themes",
    # ROCKNIX / JELOS / AmberELEC: ES config share + the roms theme dirs
    # (themes commonly live on the ROMs storage, internal or external SD)
    "/storage/.config/emulationstation/themes",
    "/storage/themes",
    "/storage/roms/themes",
    "/storage/games-internal/roms/themes",
    "/storage/games-external/roms/themes",
    "/roms/themes",
    "/roms2/themes",
    # ArkOS / dArkOS
    "/home/ark/.emulationstation/themes",
    # System-bundled (last resort, available on most firmwares)
    "/usr/share/emulationstation/themes",
    "/etc/emulationstation/themes",
]

# Firmware config files we know how to read for the "active theme name".
# Each entry is (path, regex). The regex must define one capture group
# returning the theme name.
ES_CONFIG_PATTERNS = [
    # Batocera / Knulli: line like "global.theme=knulli"
    ("/userdata/system/batocera.conf",
        re.compile(r"^\s*global\.theme\s*=\s*(\S+)", re.MULTILINE)),
    # LibreELEC-based (JELOS, Rocknix, AmberELEC). XML format:
    #   <string name="ThemeSet" value="es-theme-knulli" />
    ("/storage/.emulationstation/es_settings.cfg",
        re.compile(r'name="ThemeSet"\s+value="([^"]+)"')),
    # Same pattern, different path - some forks put it elsewhere
    ("/storage/.config/emulationstation/es_settings.cfg",
        re.compile(r'name="ThemeSet"\s+value="([^"]+)"')),
    # ArkOS
    ("/home/ark/.emulationstation/es_settings.cfg",
        re.compile(r'name="ThemeSet"\s+value="([^"]+)"')),
]


# Some themes use shorter shortnames than the firmware does. When the
# theme has no logo for our primary name, fall through to these aliases.
# Bidirectional - both directions need to work.
LOGO_ALIASES: dict = {
    # Atari
    "atari800":      ["a800", "800"],
    "atari2600":     ["a2600", "2600", "vcs"],
    "atari5200":     ["a5200", "5200"],
    "atari7800":     ["a7800", "7800"],
    "atarijaguar":   ["jaguar", "jag"],
    "atarilynx":     ["lynx"],
    "atarist":       ["st"],
    # Bandai / Wonderswan
    "wonderswan":      ["wswan", "ws"],
    "wonderswancolor": ["wswanc", "wsc"],
    # Sega
    "megadrive":     ["md", "genesis"],
    "genesis":       ["megadrive", "md"],
    "mastersystem":  ["sms"],
    "gamegear":      ["gg"],
    "sega32x":       ["32x"],
    "segacd":        ["mcd", "scd", "megacd"],
    # NEC / PC Engine
    "pcengine":      ["tg16", "tgrafx16", "pce"],
    "tg16":          ["pcengine", "pce"],
    "pcenginecd":    ["tg-cd", "pcecd", "tgcd"],
    "tg-cd":         ["pcenginecd", "pcecd"],
    "supergrafx":    ["sgfx"],
    # SNK Neo Geo
    "neogeo":        ["aes", "mvs"],
    "neogeocd":      ["ngcd"],
    "ngp":           ["neogeopocket"],
    "ngpc":          ["neogeopocketcolor"],
    # Nintendo
    "gb":            ["gameboy"],
    "gbc":           ["gameboycolor"],
    "gba":           ["gameboyadvance"],
    "nes":           ["famicom"],
    "snes":          ["sfc", "supernes", "supernintendo"],
    "n64":           ["nintendo64"],
    # Commodore / Amstrad
    "amstradcpc":    ["cpc"],
    # Sony
    "ps":            ["psx", "ps1", "playstation"],
    "psx":           ["ps", "ps1"],
    "ps1":           ["ps", "psx"],
    # Misc
    "videopac":      ["odyssey2", "o2em"],
    "odyssey2":      ["videopac", "o2em"],
    "channelf":      ["channelfairchild"],
    "intellivision": ["intv"],
    "coleco":        ["colecovision"],
    "sg-1000":       ["sg1000"],
    "scummvm":       ["scumm"],
    "pc88":          ["pc8801", "pc8800"],
    "pc98":          ["pc9801", "pc9800"],
}


def _system_aliases(shortname: str) -> List[str]:
    """Return shortname plus any alternative names a theme might use."""
    primary = shortname.lower()
    alts = LOGO_ALIASES.get(primary, [])
    # Also, for any alias entry, if its value list contains us, include
    # the other names in that list as alternates.
    extras: List[str] = []
    for k, v in LOGO_ALIASES.items():
        if primary in v:
            extras.append(k)
            extras.extend(x for x in v if x != primary)
    seen = set()
    out = []
    for name in [primary, *alts, *extras]:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# File-path templates relative to a theme directory. {sys} is the
# EmulationStation system shortname (or alias). Tried in order; first
# match wins.
LOGO_PATH_TEMPLATES: List[str] = [
    # Knulli theme convention
    "_inc/logos/{sys}/logo.png",
    "_inc/logos/{sys}/logo.svg",
    "_inc/systems/{sys}/logo.png",
    "_inc/systems/{sys}/logo.svg",
    # Art Book Next, Canvas, and several others
    "{sys}/art/system.png",
    "{sys}/art/system.svg",
    "{sys}/art/logo.png",
    "{sys}/art/logo.svg",
    # Older es-theme-basic convention
    "{sys}/logo.png",
    "{sys}/logo.svg",
    "{sys}/logo.jpg",
    # CRT Royale / Trinity / a few others
    "{sys}/data/logo.png",
    "{sys}/data/logo.svg",
    # Top-level logos folder
    "logos/{sys}.png",
    "logos/{sys}.svg",
    # Some themes split into images/ subfolder
    "{sys}/images/logo.png",
    "{sys}/images/logo.svg",
    # carbon and several derivatives
    "art/{sys}/logo.png",
    "art/{sys}/system.png",
    # Some lay out by category
    "systems/{sys}/logo.png",
    "systems/{sys}/logo.svg",
]


def detect_active_theme() -> Optional[Path]:
    """
    Return the absolute path to the currently active theme directory, or
    ``None`` if we cannot determine it.

    We read the live theme name from the firmware's ES config and look for
    it under the candidate theme roots. We deliberately do NOT guess from
    "the first theme folder we see" - that guess silently locks onto the
    wrong theme (and is why every theme looked like art-book-next before).
    No name, or a name we can't locate, returns ``None``.
    """
    theme_name, source = _read_active_theme_name()
    if not theme_name:
        print("[theme] could not read active theme name from ES config")
        return None
    print(f"[theme] active theme name '{theme_name}' (from {source})")

    for root_str in THEME_ROOT_CANDIDATES:
        root = Path(root_str)
        if not root.is_dir():
            continue
        candidate = root / theme_name
        if candidate.is_dir():
            return candidate
        prefixed = root / f"es-theme-{theme_name}"
        if prefixed.is_dir():
            return prefixed
        for child in _safe_listdir(root):
            if child.name.lower() == theme_name.lower():
                return child
            if child.name.lower() == f"es-theme-{theme_name.lower()}":
                return child

    print(f"[theme] active theme '{theme_name}' not found under known roots")
    return None


_LOGO_BLOCK_RE = re.compile(
    r'<image\b[^>]*\bname="logo"[^>]*>(.*?)</image>', re.DOTALL | re.IGNORECASE)
_PATH_RE = re.compile(r"<path>\s*([^<]+?)\s*</path>", re.IGNORECASE)
_VAR_RE = re.compile(r"\$\{([^}]+)\}")
_VARIABLES_BLOCK_RE = re.compile(
    r"<variables>(.*?)</variables>", re.DOTALL | re.IGNORECASE)
_VAR_DEF_RE = re.compile(r"<([A-Za-z0-9_]+)\b[^>]*>([^<]*)</\1>")

# Cache the discovered logo-path template (and theme variables) per theme
# directory, so we parse each theme's XML only once.
_template_cache: dict = {}

# <path> with optional attributes (group 1 = attrs, group 2 = path text)
_PATH_TAG_RE = re.compile(r"<path\b([^>]*)>\s*([^<]+?)\s*</path>", re.IGNORECASE)
# ifSubset="subsetname:value"
_IFSUBSET_RE = re.compile(r'ifSubset="([^":]+):([^"]+)"', re.IGNORECASE)


def _score_logo_block(per_system_paths: list) -> int:
    """
    Rank an <image name="logo"> block by how likely it is the real system
    wordmark (vs. backdrop/system artwork that some themes also expose as
    name="logo", e.g. art-book-next). Signals, combined:
      +2  a path points at a "logo" (logos/, .../logo.*, colorlogos, ...)
      +1  a path is an .svg (real logos are usually vector; backdrops raster)
      -2  a path looks like backdrop/system art (artwork/background/fanart)
    Extension alone isn't enough (techdweeb and ARCADEPLANET ship .png
    logos), so it's one signal among several.
    """
    joined = " ".join(per_system_paths).lower()
    score = 0
    if "logo" in joined:
        score += 2
    if any(p.lower().rstrip().endswith(".svg") for p in per_system_paths):
        score += 1
    if any(w in joined for w in
           ("artwork", "background", "backdrop", "fanart")):
        score -= 2
    return score


def _discover_logo_template(theme_dir: Path):
    """
    Scan a theme's XML the way EmulationStation does and return
    ``(paths, variables)`` for the system-view logo, where ``paths`` is the
    ORDERED list of ``(condition, path_template)`` entries declared in the
    ``<image name="logo">`` element. ``condition`` is ``None`` for an
    unconditional ``<path>`` or ``(subset_name, value)`` for one carrying
    ``ifSubset="subset_name:value"`` (e.g. region variants like
    ``ifSubset="artworkregion:US"``). Returns ``(None, {})`` if the theme
    declares no per-system logo path.

    Themes split the logo's <path> (in theme.xml) from its <pos>/<size>
    overrides (in per-aspect-ratio files), so we scan every XML file and
    take the first ``<image name="logo">`` block that actually declares a
    per-system path. A purely static logo path (no ``${system...}``) is
    rejected - it would show one icon for every system - so the fallback
    theme can supply real per-system logos instead.
    """
    key = str(theme_dir)
    if key in _template_cache:
        return _template_cache[key]

    variables: dict = {}
    candidates: list = []  # (score, paths)

    for xml_file in _iter_theme_xml(theme_dir):
        try:
            text = xml_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for vm in _VARIABLES_BLOCK_RE.findall(text):
            for name, value in _VAR_DEF_RE.findall(vm):
                variables.setdefault(name, value.strip())

        file_candidates: list = []
        for block in _LOGO_BLOCK_RE.findall(text):
            paths: list = []
            per_system_paths: list = []
            for attrs, raw in _PATH_TAG_RE.findall(block):
                path = raw.strip()
                if "{system:" in path:
                    # ES-internal indirection (e.g. {system:logo}); not a
                    # literal file path we can resolve ourselves.
                    continue
                cond = None
                cm = _IFSUBSET_RE.search(attrs)
                if cm:
                    cond = (cm.group(1).strip(), cm.group(2).strip())
                if "${system" in path or "{system" in path:
                    per_system_paths.append(path)
                paths.append((cond, path))
            if not per_system_paths or not paths:
                continue
            file_candidates.append((_score_logo_block(per_system_paths), paths))

        # EmulationStation resolves the system logo from the theme's entry
        # file (theme.xml), pulling in only what it explicitly includes. We
        # mirror that: take the logo from the FIRST theme file that declares
        # one (theme.xml is yielded first) and stop. Scanning every stray XML
        # in the folder pulls in dormant layout variants whose relative paths
        # ("./../art/...") resolve wrong and point at files that don't exist
        # (e.g. Pulse's layouts/Layout.xml), which then beat the real logo.
        if file_candidates:
            candidates = file_candidates
            break

    chosen = None
    if candidates:
        # Highest score wins; ties keep document order (first seen).
        best_i = max(range(len(candidates)), key=lambda i: candidates[i][0])
        chosen = candidates[best_i][1]

    result = (chosen, variables)
    _template_cache[key] = result
    return result


def _iter_theme_xml(theme_dir: Path):
    """Yield the theme's XML files, shallow files first (theme.xml is most
    likely to hold the logo <path>), then the rest."""
    try:
        top = [p for p in theme_dir.iterdir()
               if p.is_file() and p.suffix.lower() == ".xml"]
    except OSError:
        return
    # theme.xml first, then other top-level xml, then nested.
    top.sort(key=lambda p: (p.name.lower() != "theme.xml", p.name.lower()))
    yield from top
    try:
        for p in sorted(theme_dir.rglob("*.xml")):
            if p.parent != theme_dir:
                yield p
    except OSError:
        pass


def _expand_vars(template: str, system_name: str, variables: dict) -> str:
    """Substitute ${system.theme} (and friends) plus theme ${variables}."""
    def repl(m):
        var = m.group(1)
        if var in ("system.theme", "system.name", "system.fullName",
                   "system.fullname"):
            return system_name
        if var in variables:
            return variables[var]
        return m.group(0)  # leave unknown vars; they just won't match a file

    out = template
    for _ in range(3):  # a few passes to resolve nested ${var} references
        new = _VAR_RE.sub(repl, out)
        if new == out:
            break
        out = new
    return out


def _template_to_path(theme_dir: Path, expanded: str) -> Path:
    rel = expanded.strip()
    if rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    return theme_dir / rel


def _condition_satisfied(cond, region: Optional[str], subsets: dict) -> bool:
    """Is a <path>'s ifSubset condition met? Region subsets match the
    detected artwork region; other subsets match the user's saved
    selection."""
    if cond is None:
        return True
    name, value = cond
    name_l = name.lower()
    if "region" in name_l:
        return region is not None and value.lower() == region.lower()
    sel = subsets.get(name_l) if subsets else None
    return sel is not None and sel.lower() == value.lower()


def find_system_logo(theme_dir: Optional[Path],
                     system_shortname: str,
                     region: Optional[str] = None,
                     subsets: Optional[dict] = None) -> Optional[Path]:
    """
    Resolve a per-system logo inside ``theme_dir`` the way EmulationStation
    does: read the theme's declared ``<image name="logo">`` paths, keep the
    ones whose ``ifSubset`` condition is satisfied (region/subset), and use
    the LAST applicable one - so a US user gets the ``US/`` variant when the
    theme provides region artwork. ``${system.theme}`` is filled with the
    system's theme key (aliases tried for naming differences). Returns the
    first existing file, or ``None``.

    Falls back to hardcoded layout guesses only if the theme declares no
    resolvable logo path.
    """
    if theme_dir is None or not theme_dir.is_dir():
        return None

    subsets = subsets or {}
    names = _system_aliases(system_shortname)
    paths, variables = _discover_logo_template(theme_dir)

    if paths:
        # Applicable paths in document order; ES uses the last one that
        # applies, so we try them last-first and fall back to earlier ones
        # if the preferred file happens to be missing.
        applicable = [tmpl for cond, tmpl in paths
                      if _condition_satisfied(cond, region, subsets)]
        for tmpl in reversed(applicable):
            for name in names:
                expanded = _expand_vars(tmpl, name, variables)
                candidate = _template_to_path(theme_dir, expanded)
                if candidate.is_file():
                    return candidate

    # Last-ditch: legacy hardcoded layout guesses.
    for name in names:
        for tmpl in LOGO_PATH_TEMPLATES:
            candidate = theme_dir / tmpl.format(sys=name)
            if candidate.is_file():
                return candidate
    return None


# The firmware's bundled default theme ("system-theme") carries a complete,
# stock per-system logo set. Its location is fixed per firmware, so we check
# these known paths directly instead of scanning every installed theme at
# startup (which is slow on SD storage). Add new firmwares' paths here as
# they're confirmed on real hardware.
SYSTEM_THEME_CANDIDATES: List[str] = [
    # ROCKNIX / JELOS / AmberELEC: dedicated 'system-theme'
    "/storage/.config/emulationstation/themes/system-theme",
    "/storage/roms/themes/system-theme",
    "/storage/games-internal/roms/themes/system-theme",
    "/storage/games-external/roms/themes/system-theme",
    "/roms/themes/system-theme",
    "/userdata/themes/system-theme",
    "/usr/share/emulationstation/themes/system-theme",
    # Knulli / Batocera: no 'system-theme'; the firmware bundles complete
    # themes here. art-book-next is the Knulli default and ships a full
    # per-system logo set, so it's the natural fallback source there.
    "/usr/share/emulationstation/themes/es-theme-art-book-next",
    "/usr/share/emulationstation/themes/es-theme-knulli",
    "/usr/share/emulationstation/themes/es-theme-carbon",
]


def find_logo_fallback_dirs(active_theme_dir: Optional[Path]) -> List[Path]:
    """
    The theme to borrow logos from when the active theme has none (or only a
    generic icon) for a system: the firmware's bundled ``system-theme``,
    which ships a full per-system logo set. We probe a few known fixed
    locations rather than scanning every installed theme - that scan was the
    visible delay at startup, and the system-theme is always in the same
    place for a given firmware.
    """
    for cand in SYSTEM_THEME_CANDIDATES:
        p = Path(cand)
        try:
            if not (p.is_dir() and (p / "theme.xml").is_file()):
                continue
            if active_theme_dir is not None and p.resolve() == active_theme_dir.resolve():
                continue
            return [p]
        except OSError:
            continue
    return []


def find_all_theme_dirs() -> List[Path]:
    """
    List every theme directory the device has, de-duplicated by real path.
    Several candidate roots can point at the same physical folder on
    ROCKNIX (e.g. /roms/themes is a symlink/merge of /storage/roms/themes),
    so we resolve each and skip ones we've already seen.
    """
    found: List[Path] = []
    seen = set()
    for root_str in THEME_ROOT_CANDIDATES:
        root = Path(root_str)
        if not root.is_dir():
            continue
        for child in _safe_listdir(root):
            if not (child.is_dir() and (child / "theme.xml").is_file()):
                continue
            try:
                real = child.resolve()
            except OSError:
                real = child
            if real in seen:
                continue
            seen.add(real)
            found.append(child)
    return found


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

# User es_settings.cfg locations (NOT the read-only system config). Holds
# ThemeSet, ScraperRegion, and subset.* selections.
ES_SETTINGS_CANDIDATES: List[str] = [
    "/userdata/system/configs/emulationstation/es_settings.cfg",  # Knulli/Batocera
    "/storage/.emulationstation/es_settings.cfg",                  # ROCKNIX/JELOS
    "/storage/.config/emulationstation/es_settings.cfg",
    "/home/ark/.emulationstation/es_settings.cfg",                 # ArkOS
    str(Path.home() / ".emulationstation" / "es_settings.cfg"),
]

_ES_SETTING_RE = re.compile(r'name="([^"]+)"\s+value="([^"]*)"')


def _read_es_settings() -> dict:
    """Parse the first es_settings.cfg we find into a {name: value} dict."""
    for cand in ES_SETTINGS_CANDIDATES:
        try:
            text = Path(cand).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        return dict(_ES_SETTING_RE.findall(text))
    return {}


def _region_from_timezone() -> Optional[str]:
    """Last-resort region hint from the system timezone."""
    tz = ""
    try:
        tz = Path("/etc/timezone").read_text(encoding="utf-8",
                                             errors="replace").strip().lower()
    except OSError:
        import os
        tz = os.environ.get("TZ", "").lower()
    if not tz:
        return None
    if tz.startswith("america/"):
        return "us"
    if tz.startswith("europe/") or tz.startswith("africa/"):
        return "eu"
    if tz.startswith("asia/") and "tokyo" in tz:
        return "jp"
    return None


def detect_artwork_region():
    """
    Return ``(region, subsets)`` for theme region/subset resolution.

    ``subsets`` is the user's saved theme subset selections ({name: value}).
    ``region`` is the artwork region a theme should use, in priority order:
      1. an explicit theme region subset (any ``subset.*region*`` setting)
      2. the EmulationStation ScraperRegion (us / eu / jp / ...)
      3. the system timezone
    Not every theme exposes a region subset, so the ScraperRegion/timezone
    fallbacks are what make region artwork work without per-theme setup.
    """
    settings = _read_es_settings()
    subsets = {k[len("subset."):].lower(): v
               for k, v in settings.items() if k.lower().startswith("subset.")}

    region = None
    for name, value in subsets.items():
        if "region" in name:
            region = value
            break
    if not region:
        region = settings.get("ScraperRegion") or None
    if not region:
        region = _region_from_timezone()
    return region, subsets


_THEMESET_RE = re.compile(r'name="ThemeSet"\s+value="([^"]+)"')
_GLOBAL_THEME_RE = re.compile(r"^\s*global\.theme\s*=\s*(\S+)", re.MULTILINE)


def _read_active_theme_name():
    """
    Return ``(theme_name, source)`` for the live ES theme, or
    ``(None, None)``.

    Preference: the live ``ThemeSet`` in es_settings.cfg - what the
    EmulationStation theme menu writes on both ROCKNIX and Knulli - then
    Batocera's ``global.theme``. ES_SETTINGS_CANDIDATES includes Knulli's
    ``/userdata/system/configs/emulationstation/es_settings.cfg``, whose
    absence is exactly what made detection fall back to the wrong theme.
    """
    for cand in ES_SETTINGS_CANDIDATES:
        try:
            text = Path(cand).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _THEMESET_RE.search(text)
        if m:
            return m.group(1).strip(), cand
    try:
        text = Path("/userdata/system/batocera.conf").read_text(
            encoding="utf-8", errors="replace")
        m = _GLOBAL_THEME_RE.search(text)
        if m:
            return m.group(1).strip(), "/userdata/system/batocera.conf"
    except OSError:
        pass
    return None, None


def _safe_listdir(path: Path):
    try:
        return sorted(path.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
