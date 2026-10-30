"""
OKPELLA Risk Assessment engine (v4.0, Streamlit edition).

Same selection logic as the Copilot agent script (v3.1/v3.2), so the same inputs and the
same workbook give the same hazard IDs. The engine never writes hazard text: every hazard,
control, level, PPE item and responsible person is copied from the workbook row.
"""
import datetime
import hashlib
import json
import re

import openpyxl

ENGINE_VERSION = "4.0"

# Tables included in the register fingerprint (same list and method as the agent script).
FINGERPRINT_TABLES = [
    "Locations", "JobTags", "EquipmentTypes", "Equipment", "ActivityHazards",
    "EquipmentHazards", "TaskPresets", "ToolRecognition", "InferenceRules",
    "ReportTemplate", "AgentText",
]
REQUIRED_TABLES = [
    "Locations", "JobTags", "Equipment", "ActivityHazards", "EquipmentHazards",
    "TaskPresets", "ToolRecognition", "InferenceRules",
]
HAZARD_CATEGORIES = [
    "Job Related Hazard",
    "Job Location Related Hazard",
    "Equipment and Material Related Hazard",
]
LEVELS = "EHMLN"
LEVEL_NAMES = {"E": "EXTREME", "H": "HIGH", "M": "MODERATE", "L": "LOW", "N": "NEGLIGIBLE"}
GENERIC_WORDS = {"plant", "area", "line", "system", "main", "with", "storage",
                 "conveying", "loading", "station"}


# --------------------------------------------------------------------------- helpers
def norm(s):
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def words(s):
    return set(re.findall(r"[a-z]{4,}", norm(s))) - GENERIC_WORDS


def numbered(row, prefix, n):
    return [row[prefix + str(i)] for i in range(1, n + 1) if row.get(prefix + str(i))]


class RegisterError(Exception):
    pass


# --------------------------------------------------------------------------- register
class Register:
    """The workbook's named tables, read as text exactly as the agent script reads them."""

    def __init__(self, source, name=""):
        try:
            wb = openpyxl.load_workbook(source, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise RegisterError("Could not open the workbook: %s" % exc) from exc
        self.name = name
        self.tables = {}
        for ws in wb.worksheets:
            for tname, ref in ws.tables.items():
                rows = [[str(c.value or "").strip() for c in r] for r in ws[ref]]
                self.tables[tname] = [dict(zip(rows[0], r)) for r in rows[1:] if any(r)]
        missing = [t for t in REQUIRED_TABLES if "tbl" + t not in self.tables]
        if missing:
            raise RegisterError(
                "This workbook is missing table(s): %s. Use OKPELLA_Master_Workbook_v8 or later."
                % ", ".join("tbl" + t for t in missing))
        payload = json.dumps([self.tables.get("tbl" + k, []) for k in FINGERPRINT_TABLES],
                             sort_keys=True)
        self.fingerprint = hashlib.sha256(payload.encode()).hexdigest()[:8].upper()

    def t(self, key):
        return self.tables["tbl" + key]

    # ---- lists for the form
    def locations(self):
        return [r for r in self.t("Locations") if r.get("AreaType") != "Other" and r.get("LocationArea")]

    def location_names(self):
        return [r["LocationArea"] for r in self.locations()]

    def equipment_rows(self):
        return [e for e in self.t("Equipment") if e.get("EquipmentName")]

    def equipment_available(self, e, loc):
        scope = e.get("LocationScope", "")
        if not loc or scope == "All areas":
            return True
        if scope == "All process areas":
            return any(r["LocationArea"] == loc and r.get("AreaType") == "Process" for r in self.locations())
        return loc in numbered(e, "LocationArea", 10)

    def equipment_names_for(self, loc):
        return [e["EquipmentName"] for e in self.equipment_rows() if self.equipment_available(e, loc)]

    def equipment(self, name):
        return next((e for e in self.equipment_rows() if e["EquipmentName"] == name), None)

    def job_tags(self):
        return [r["JobTag"] for r in self.t("JobTags") if r.get("JobTag")]

    def categories(self):
        out = {}
        for r in self.t("JobTags"):
            if r.get("JobTag"):
                out.setdefault(r.get("Category", ""), []).append(r["JobTag"])
        return out

    def presets(self):
        return [p for p in self.t("TaskPresets") if p.get("PresetName")]

    def preset(self, name):
        return next((p for p in self.presets() if norm(p["PresetName"]) == norm(name)), None) if name else None

    # ---- free-text matching (used for presets and the self-test; same rules as the agent)
    def match_location(self, text):
        if not text:
            return []
        locs = self.locations()
        hit = [r["LocationArea"] for r in locs if norm(text) in (norm(r["LocationArea"]), norm(r.get("LocationCode", "")))]
        return hit or [r["LocationArea"] for r in locs if words(text) & words(r["LocationArea"])]

    def match_equipment(self, text, loc=""):
        if not text:
            return []
        eq = self.equipment_rows()
        c = [e for e in eq if norm(e["EquipmentName"]) == norm(text)] or \
            [e for e in eq if norm(e["EquipmentName"]) in norm(text)]
        longest = max([len(x["EquipmentName"]) for x in c] + [0])
        c = [e for e in c if len(e["EquipmentName"]) == longest]
        if len(c) > 1:
            c = [e for e in c if self.equipment_available(e, loc)] or c
        if c:
            return [e["EquipmentName"] for e in c]
        return [e["EquipmentName"] for e in eq if words(text) & words(e["EquipmentName"])]


# --------------------------------------------------------------------------- normalisers
def norm_motion(s):
    k = norm(s)
    if re.search(r"static|stop|not run|idle", k):
        return "Static"
    if re.search(r"run|moving|rotat|operat", k):
        return "Running"
    return ""


def norm_status(s):
    k = norm(s)
    if re.search(r"shut|isolat|lock|loto|outage", k):
        return "Shutdown/Isolated"
    if re.search(r"operat|service|online", k):
        return "Operational"
    return ""


def norm_class(s):
    k = norm(s)
    return "Rotating" if "rotat" in k else "Static" if "static" in k else ""


def class_conflict(cls, equipment_type):
    t = norm(equipment_type)
    return bool(cls and equipment_type and ("rotat" in t) != ("static" in t) and (cls == "Rotating") != ("rotat" in t))


# --------------------------------------------------------------------------- activities
def detect_activities(reg, task="", area="", selected=(), preset=None):
    """Return ({JobTag: [reasons]} in register order, [ignored names])."""
    tags = reg.job_tags()
    found = {}
    ignored = []

    def add(tag, why):
        if tag in tags and why not in found.setdefault(tag, []):
            found[tag].append(why)

    for s in selected:
        m = [t for t in tags if norm(t) == norm(s)]
        if m:
            add(m[0], "selected by user")
        elif str(s).strip():
            ignored.append(str(s).strip())
    if preset:
        for t in numbered(preset, "JobTag", 10):
            add(t, "preset")
    text = norm(task + " " + area)
    spans = []
    for r in sorted(reg.t("ToolRecognition"), key=lambda r: -len(r.get("ToolPhrase", ""))):
        ph = norm(r.get("ToolPhrase", ""))
        if not ph:
            continue
        m = re.search(r"\b" + re.escape(ph) + (r"\b" if len(ph) < 5 else ""), text)
        if m and not any(m.start() < b and a < m.end() for a, b in spans):
            spans.append(m.span())
            for t in numbered(r, "JobTag", 8):
                add(t, "tool: " + ph)
    for r in reg.t("InferenceRules"):
        if re.search(r["TriggerRegex"], text) and re.search(r.get("AlsoRequiresRegex") or ".", text):
            for t in numbered(r, "JobTag", 3):
                add(t, "description: " + r.get("Label", ""))
    ordered = {t: found[t] for t in tags if t in found}
    return ordered, ignored


# --------------------------------------------------------------------------- hazards
def select_hazards(reg, tags, equipment_type, motion, status):
    """Filter, de-duplicate and sort hazards. Returns a list of hazard dicts in final order."""
    pool = {}
    rows = [(0, "ActivityHazardID", i, r) for i, r in enumerate(reg.t("ActivityHazards")) if r.get("JobTag") in tags]
    if equipment_type:
        rows += [(1, "EquipmentHazardID", i, r) for i, r in enumerate(reg.t("EquipmentHazards"))
                 if r.get("EquipmentType") == equipment_type]
    for src, idcol, i, r in rows:
        if r.get("AppliesWhenMotion", "") in ("", "Any", motion) and r.get("AppliesWhenStatus", "") in ("", "Any", status):
            key = (LEVELS.find(r.get("LevelOfRisk", "")), src, i)
            source = "Equipment: " + equipment_type if src else "Activity: " + r.get("JobTag", "")
            pool.setdefault(norm(r.get("Hazard", "")), []).append((key, r[idcol], source, r))
    out = []
    for key, hid, source, r in sorted(min(v, key=lambda x: x[0]) for v in pool.values()):
        out.append({
            "id": hid,
            "category": r.get("HazardCategory", ""),
            "hazard": r.get("Hazard", ""),
            "level": r.get("LevelOfRisk", ""),
            "controls": r.get("ControlMeasures", ""),
            "residual": r.get("ReducedLevelOfRisk", ""),
            "responsible": r.get("ResponsiblePerson", ""),
            "ppe": numbered(r, "PPE", 7),
            "source": source,
        })
    return out


def level_counts(hazards):
    return {k: sum(1 for h in hazards if h["level"] == k) for k in LEVELS}


def make_serial(when, equipment_name):
    days = (when.date() - datetime.date(1899, 12, 30)).days
    initials = "".join(w[0] for w in (re.sub(r"[^A-Z ]", " ", equipment_name.upper()).split() + ["X"] * 3)[:3])
    return "%d%s%s" % (days, when.strftime("%H%M%S%f")[:8], initials)


# --------------------------------------------------------------------------- one call
def assess(reg, location, location_in_register, equipment, equipment_in_register,
           equipment_class, motion, status, area, task, selected=(), preset_name=""):
    """Run the full selection. All inputs are already chosen from the form."""
    preset = reg.preset(preset_name)
    eq_row = reg.equipment(equipment) if equipment_in_register else None
    etype = eq_row["EquipmentType"] if eq_row else ""
    cls = norm_class(equipment_class)
    mo = norm_motion(motion)
    st = norm_status(status)
    warnings = []
    if not equipment_in_register:
        warnings.append("Equipment not in register: only activity hazards are included.")
    if not location_in_register:
        warnings.append("Location not in register: recorded as written.")
    if eq_row and location_in_register and not reg.equipment_available(eq_row, location):
        warnings.append("%s is not registered in %s. Check the area or the equipment." % (equipment, location))
    if class_conflict(cls, etype):
        warnings.append("You selected %s, but the register lists %s as '%s'. Check which is correct." % (cls, equipment, etype))
    acts, ignored = detect_activities(reg, task, area, selected, preset)
    for x in ignored:
        warnings.append("Not a register activity, ignored: " + x)
    hazards = select_hazards(reg, set(acts), etype, mo, st)
    title = (preset["PresetName"] if preset else "Work on " + equipment) + " — " + area
    return {
        "engine": ENGINE_VERSION,
        "fingerprint": reg.fingerprint,
        "location": location,
        "equipment": equipment,
        "equipment_type": etype or "unlisted",
        "equipment_class": cls,
        "motion": mo,
        "status": st,
        "title": title,
        "activities": acts,
        "warnings": warnings,
        "hazards": hazards,
        "levels": level_counts(hazards),
    }


# --------------------------------------------------------------------------- self-test
GOLDEN_FINGERPRINT = "493DA897"
GOLDEN_CASES = [
    {"name": "GT01 Kiln brick lining", "loc": "56", "cls": "rotating", "eq": "Rotary Kiln",
     "area": "Kiln inlet, inside shell", "mo": "static", "st": "shutdown/isolated",
     "task": "We are entering the kiln to replace the refractory brick lining during the shutdown. "
             "We will use a jack hammer and a chain block.",
     "expect": (36, {"E": 21, "H": 12, "M": 3, "L": 0, "N": 0})},
    {"name": "GT02 Belt walk-down", "loc": "02 Limestone/Correctives Crushing and Conveying", "cls": "rotating",
     "eq": "Belt Conveyor", "area": "Belt 02BC01 tail end walkway", "mo": "running", "st": "operational",
     "task": "Routine inspection walk-down of the running belt, checking idlers and spillage.",
     "acts": ["Visual Inspection", "Walking", "Working Near Moving Machinery",
              "Working in Dusty Environment", "Working in Noisy Environment"],
     "expect": (10, {"E": 3, "H": 5, "M": 2, "L": 0, "N": 0})},
    {"name": "GT03 Workshop fabrication", "loc": "Mechanical Workshop", "cls": "static",
     "eq": "Maintenance Workshop", "area": "Fabrication bay 2", "mo": "static", "st": "operational",
     "task": "Fabricating a chute section using a welding set and an angle grinder.",
     "expect": (14, {"E": 2, "H": 11, "M": 1, "L": 0, "N": 0})},
    {"name": "GT04 Bag filter preset", "preset": "Bag filter bag change-out", "loc": "84A", "cls": "static",
     "eq": "Bag Filter / Dust Collector", "area": "Cement mill A bag house, top deck", "mo": "static",
     "st": "shutdown", "task": "Replace filter bags in the cement mill A bag filter.",
     "expect": (27, {"E": 15, "H": 8, "M": 4, "L": 0, "N": 0})},
    {"name": "GT05 Unlisted pump", "loc": "Water Treatment", "cls": "rotating", "eq": "Other: P-301 slurry pump",
     "area": "Pump bay", "mo": "static", "st": "isolated",
     "task": "Replace the pump bearing using spanners and a chain block.",
     "expect": (9, {"E": 2, "H": 4, "M": 3, "L": 0, "N": 0})},
]


def run_golden(reg):
    """Run the five reference cases with the agent's free-text matching. Returns result rows."""
    results = []
    for c in GOLDEN_CASES:
        locs = reg.match_location(c["loc"])
        loc = locs[0] if len(locs) == 1 else ""
        if c["eq"].lower().startswith("other:"):
            eq, eq_in = c["eq"][6:].strip(), False
        else:
            eqs = reg.match_equipment(c["eq"], loc)
            eq, eq_in = (eqs[0], True) if len(eqs) == 1 else ("", False)
        if not loc or (not eq_in and not c["eq"].lower().startswith("other:")):
            results.append({"case": c["name"], "pass": False, "got": "could not match location/equipment",
                            "expected": c["expect"][0]})
            continue
        r = assess(reg, loc, True, eq, eq_in, c["cls"], c["mo"], c["st"], c["area"], c["task"],
                   c.get("acts", []), c.get("preset", ""))
        got = (len(r["hazards"]), r["levels"])
        results.append({"case": c["name"], "pass": got == c["expect"],
                        "got": "%d %s" % (got[0], got[1]), "expected": "%d %s" % c["expect"]})
    return results
