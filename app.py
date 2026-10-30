"""
OKPELLA Risk Assessment — Streamlit app.

Fill in the job details -> Identify hazards (from the workbook only) -> untick what does not
apply -> Download PDF. Run locally with:  streamlit run app.py
"""
import datetime
import html
import os
import sys

import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import engine  # noqa: E402
import simple_auth  # noqa: E402
from pdf_report import build_pdf  # noqa: E402
OTHER = "Other (not in register)"
LEVEL_HEX = {"E": "#c6303e", "H": "#e0793a", "M": "#d9b23a", "L": "#4f9d63", "N": "#4a7fc9"}

st.set_page_config(page_title="OKPELLA Risk Assessment", page_icon="🦺", layout="centered")


# --------------------------------------------------------------------------- settings
def setting(key, default=""):
    """Read a value from Streamlit secrets, then environment variables."""
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # noqa: BLE001  no secrets file
        pass
    return os.environ.get(key, default)


def auth_configured():
    try:
        return "auth" in st.secrets
    except Exception:  # noqa: BLE001
        return False


def logged_in():
    try:
        return bool(st.user.get("is_logged_in", False))
    except Exception:  # noqa: BLE001
        return False


def require_login():
    """
    Sign-in, in this order:
      1. Microsoft (Entra ID) sign-in, if an [auth] block is in Secrets.
      2. Otherwise username + password ([users] in Secrets, or the built-in TEST account).
    Set LOGIN_MODE = "none" in Secrets to switch sign-in off (local testing only).
    Returns (display name, mode) where mode is "microsoft", "password", "test" or "none".
    """
    if setting("LOGIN_MODE").lower() == "none":
        return "", "none"
    if auth_configured():
        if not logged_in():
            st.title("OKPELLA Risk Assessment")
            st.write("Sign in with your Dangote Microsoft account to continue.")
            st.button("Sign in with Microsoft", on_click=st.login, type="primary")
            st.stop()
        domain = setting("ALLOWED_EMAIL_DOMAIN").lower().strip()
        email = str(st.user.get("email") or st.user.get("preferred_username") or "").lower()
        if domain and not email.endswith("@" + domain):
            st.error("This app is limited to @%s accounts. You are signed in as %s." % (domain, email or "unknown"))
            st.button("Sign out", on_click=st.logout)
            st.stop()
        return str(st.user.get("name") or ""), "microsoft"
    name, test_mode = simple_auth.require_password_login("OKPELLA Risk Assessment")
    return name, "test" if test_mode else "password"


# --------------------------------------------------------------------------- register
@st.cache_resource(show_spinner="Loading the OKPELLA register…")
def load_register(path, mtime):  # mtime is part of the cache key: a new file reloads automatically
    return engine.Register(path, os.path.basename(path))


def get_register():
    path = setting("WORKBOOK_PATH", "OKPELLA_Master_Workbook_v8.xlsx")
    if not os.path.isabs(path):
        path = os.path.join(APP_DIR, path)
    if not os.path.exists(path):
        st.error("Register workbook not found: %s. Put OKPELLA_Master_Workbook_v8.xlsx next to app.py, "
                 "or set WORKBOOK_PATH." % os.path.basename(path))
        st.stop()
    try:
        return load_register(path, os.path.getmtime(path))
    except engine.RegisterError as exc:
        st.error(str(exc))
        st.stop()


# --------------------------------------------------------------------------- helpers
def badge(level):
    colour = LEVEL_HEX.get(level, "#c7ccd1")
    text_col = "#3a2f00" if level == "M" else "#ffffff"
    return ('<span style="background:%s;color:%s;font-family:monospace;font-weight:700;font-size:0.8rem;'
            'padding:1px 7px;border-radius:5px">%s</span>' % (colour, text_col, html.escape(level or "—")))


def apply_preset():
    """When a preset is picked, prefill location, equipment and activities from the register."""
    reg = get_register()
    p = reg.preset(st.session_state.get("preset", ""))
    if not p:
        return
    locs = reg.match_location(p.get("LocationArea", ""))
    if len(locs) == 1:
        st.session_state["loc"] = locs[0]
    eqs = reg.match_equipment(p.get("EquipmentRef", ""), st.session_state.get("loc", ""))
    if len(eqs) == 1:
        st.session_state["eq"] = eqs[0]
    if not st.session_state.get("task"):
        st.session_state["task"] = p.get("Description", "")


def current_inputs(reg):
    s = st.session_state
    loc = s.get("loc")
    eq = s.get("eq")
    return {
        "preset": s.get("preset") or "",
        "dep": s.get("dep", "").strip(),
        "by": s.get("by", "").strip(),
        "rev": s.get("rev", "").strip(),
        "loc": s.get("loc_other", "").strip() if loc == OTHER else (loc or ""),
        "loc_in": loc not in (None, OTHER),
        "eq": s.get("eq_other", "").strip() if eq == OTHER else (eq or ""),
        "eq_in": eq not in (None, OTHER),
        "cls": s.get("cls") or "",
        "mo": s.get("mo") or "",
        "st": s.get("st") or "",
        "area": s.get("area", "").strip(),
        "task": s.get("task", "").strip(),
        "acts": tuple(t for cat in reg.categories() for t in s.get("cat_" + cat, [])),
    }


def missing_fields(i):
    labels = [("dep", "Department"), ("by", "Assessed by"), ("rev", "Reviewed by"), ("loc", "Location of work"),
              ("cls", "Equipment type (rotating/static)"), ("eq", "Specific equipment"),
              ("area", "Specific work area"), ("mo", "Current motion"), ("st", "Current status"),
              ("task", "Work to be done")]
    return [label for key, label in labels if not i[key]]


# --------------------------------------------------------------------------- page
signed_in_name, login_mode = require_login()
reg = get_register()

with st.sidebar:
    st.markdown("### OKPELLA Risk Assessment")
    st.caption("Register: %s" % reg.name)
    st.caption("Fingerprint: **%s** · Engine v%s" % (reg.fingerprint, engine.ENGINE_VERSION))
    if login_mode == "microsoft":
        st.caption("Signed in as %s" % (st.user.get("name") or ""))
        st.button("Sign out", on_click=st.logout)
    elif login_mode in ("password", "test"):
        st.caption("Signed in as %s" % signed_in_name)
        st.button("Sign out", on_click=simple_auth.sign_out)
        if login_mode == "test":
            st.warning("Test account in use. Set real accounts in Secrets before the pilot.")
    with st.expander("Self-test (5 reference cases)"):
        st.caption("Checks the engine against the reference results for workbook v8 (fingerprint %s)."
                   % engine.GOLDEN_FINGERPRINT)
        if st.button("Run self-test"):
            res = engine.run_golden(reg)
            for r in res:
                st.write(("✅ " if r["pass"] else "❌ ") + r["case"])
                if not r["pass"]:
                    st.caption("Got %s · expected %s" % (r["got"], r["expected"]))
            if reg.fingerprint != engine.GOLDEN_FINGERPRINT:
                st.info("This workbook's fingerprint differs from %s, so different totals can be expected "
                        "if the register was edited." % engine.GOLDEN_FINGERPRINT)

st.title("OKPELLA Risk Assessment")
st.caption("Every hazard comes from the OKPELLA register. Untick what does not apply, then download the PDF.")

if signed_in_name and "by" not in st.session_state:
    st.session_state["by"] = signed_in_name

# ---- 1. Job details
st.subheader("1. Job details")
preset_names = [""] + [p["PresetName"] for p in reg.presets()]
st.selectbox("Start from a preset (optional)", preset_names, key="preset", on_change=apply_preset,
             format_func=lambda x: x or "— No preset —")

c1, c2, c3 = st.columns(3)
c1.text_input("Department", key="dep")
c2.text_input("Assessed by (full name)", key="by")
c3.text_input("Reviewed by (full name)", key="rev")

loc_options = reg.location_names() + [OTHER]
st.selectbox("Location of work", loc_options, key="loc", index=None, placeholder="Choose a plant area")
if st.session_state.get("loc") == OTHER:
    st.text_input("Location (as written)", key="loc_other")

loc_val = st.session_state.get("loc")
eq_options = reg.equipment_names_for(loc_val if loc_val not in (None, OTHER) else "") + [OTHER]
if st.session_state.get("eq") not in eq_options:
    st.session_state["eq"] = None
st.selectbox("Specific equipment", eq_options, key="eq", index=None, placeholder="Choose equipment",
             help="Only equipment registered in the chosen area is listed.")
if st.session_state.get("eq") == OTHER:
    st.text_input("Equipment (as written)", key="eq_other")
    st.caption("Unlisted equipment: only activity hazards will be included.")

c1, c2, c3 = st.columns(3)
c1.radio("Equipment type", ["Rotating", "Static"], key="cls", index=None)
c2.radio("Current motion", ["Running", "Static"], key="mo", index=None)
c3.radio("Current status", ["Operational", "Shutdown/Isolated"], key="st", index=None)
st.text_input("Specific work area", key="area", placeholder="e.g. kiln inlet, inside shell")
st.text_area("Work to be done (task, tools, method)", key="task", height=100)

# ---- 2. Activities
st.subheader("2. Additional activities (optional)")
st.caption("Activities are also detected from the work description and the preset. Add any others that apply.")
cats = reg.categories()
cols = st.columns(2)
for n, (cat, tags) in enumerate(cats.items()):
    with cols[n % 2].expander("%d. %s" % (n + 1, cat)):
        st.multiselect(cat, tags, key="cat_" + cat, label_visibility="collapsed")

inputs = current_inputs(reg)
if st.button("Identify hazards", type="primary", use_container_width=True):
    gaps = missing_fields(inputs)
    if gaps:
        st.error("Please complete: " + ", ".join(gaps))
    else:
        result = engine.assess(reg, inputs["loc"], inputs["loc_in"], inputs["eq"], inputs["eq_in"],
                               inputs["cls"], inputs["mo"], inputs["st"], inputs["area"], inputs["task"],
                               inputs["acts"], inputs["preset"])
        now = datetime.datetime.now()
        st.session_state["result"] = result
        st.session_state["inputs_used"] = inputs
        st.session_state["serial"] = engine.make_serial(now, inputs["eq"])
        st.session_state["generated"] = now.strftime("%Y-%m-%d %H:%M")

# ---- 3. Review
result = st.session_state.get("result")
if result:
    if st.session_state.get("inputs_used") != inputs:
        st.warning("You changed the job details after identifying hazards. Select **Identify hazards** again.")
        st.stop()
    if result["fingerprint"] != reg.fingerprint:
        st.warning("The register was updated. Select **Identify hazards** again.")
        st.stop()

    serial = st.session_state["serial"]
    hz = result["hazards"]
    st.subheader("3. Review the hazards")
    st.caption("Assessment No. **%s** · fingerprint %s" % (serial, result["fingerprint"]))
    for w in result["warnings"]:
        st.warning(w)
    with st.expander("Activities used (%d)" % len(result["activities"])):
        for tag, why in result["activities"].items():
            st.markdown("- **%s** — %s" % (tag, "; ".join(why)))

    if not hz:
        st.info("No register hazards match these details. Add the activities involved in step 2.")
        st.stop()

    keys = {h["id"]: "inc_%s_%s" % (serial, h["id"]) for h in hz}
    included = {hid for hid, k in keys.items() if st.session_state.get(k, True)}
    counts = engine.level_counts([h for h in hz if h["id"] in included])
    chips = " ".join("%s %d" % (badge(lv), counts[lv]) for lv in engine.LEVELS if counts[lv])
    st.markdown("**%d included · %d excluded** &nbsp; %s" % (len(included), len(hz) - len(included), chips),
                unsafe_allow_html=True)
    st.caption("Untick any hazard that does not apply. Excluded hazards stay on the PDF, marked as excluded.")

    for n, cat in enumerate(engine.HAZARD_CATEGORIES, 1):
        rows = [h for h in hz if h["category"] == cat]
        st.markdown("##### %d. %s" % (n, cat))
        if not rows:
            st.caption("No hazards in this category for the current selection.")
        for h in rows:
            with st.container(border=True):
                a, b = st.columns([0.07, 0.93])
                a.checkbox("Include %s" % h["id"], value=True, key=keys[h["id"]], label_visibility="collapsed")
                on = st.session_state.get(keys[h["id"]], True)
                title = html.escape(h["hazard"])
                b.markdown("%s &nbsp; %s" % (badge(h["level"]), title if on else "<s>%s</s>" % title),
                           unsafe_allow_html=True)
                b.markdown("<span style='color:#5c7086;font-size:0.9rem'>%s</span>" % html.escape(h["controls"]),
                           unsafe_allow_html=True)
                b.markdown("<span style='font-size:0.8rem;color:#5c7086'>Residual risk after controls</span> %s"
                           "<br><span style='font-family:monospace;font-size:0.72rem;color:#8b99a8'>%s · %s · "
                           "Responsible: %s</span>%s"
                           % (badge(h["residual"]), html.escape(h["id"]), html.escape(h["source"]),
                              html.escape(h["responsible"] or "—"),
                              "" if on else "<br><b style='font-size:0.72rem;color:#5f6b77'>REVIEWED AND "
                                            "EXCLUDED BY ASSESSOR AS NOT APPLICABLE</b>"),
                           unsafe_allow_html=True)

    ppe = []
    for h in hz:
        if h["id"] in included:
            ppe += [p for p in h["ppe"] if p not in ppe]
    st.markdown("##### PPE required (from included hazards)")
    st.write("; ".join(ppe) or "No PPE listed for the included hazards.")

    used = st.session_state["inputs_used"]
    header = {
        "serial": serial,
        "department": used["dep"],
        "location": used["loc"] + ("" if used["loc_in"] else " (not in register)"),
        "area": used["area"],
        "equipment": used["eq"] + ("" if used["eq_in"] else " (not in register)"),
        "equipment_type": "%s · %s" % (result["equipment_type"], result["equipment_class"]),
        "motion_status": "%s / %s" % (result["motion"], result["status"]),
        "title": result["title"],
        "description": used["task"],
        "activities": ", ".join(result["activities"]),
        "assessed_by": used["by"],
        "reviewed_by": used["rev"],
    }
    pdf = build_pdf(header, hz, included, result["fingerprint"], result["engine"], st.session_state["generated"])
    st.download_button("Download PDF", pdf, file_name="Risk_Assessment_%s.pdf" % serial,
                       mime="application/pdf", type="primary", use_container_width=True)
