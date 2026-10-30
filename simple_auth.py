"""
Username + password sign-in for testing and the pilot.

Accounts come from the [users] section of Streamlit Secrets:

    [users.jakukuata]
    name = "John Akukuata"
    password_hash = "pbkdf2_sha256$200000$<salt>$<hash>"

Make a hash with:  python make_password_hash.py
Passwords are never stored in plain text. If [users] is missing, one TEST account is used
(see DEFAULT_TEST_USER below) and the app shows a warning banner until real accounts are set.
"""
import hashlib
import hmac
import secrets
import time

import streamlit as st

ITERATIONS = 200_000
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

# TEST ONLY. Username: okpella.test   Password: Okpella@Test2026
DEFAULT_TEST_USER = {
    "okpella.test": {
        "name": "OKPELLA Test User",
        "password_hash": "",  # filled in below
    }
}


def hash_password(password, salt_hex=None, iterations=ITERATIONS):
    salt_hex = salt_hex or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (iterations, salt_hex, digest.hex())


def verify_password(password, stored):
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(check.hex(), digest_hex)
    except Exception:  # noqa: BLE001  malformed hash
        return False


# Build the test account's hash once (fixed salt, so it is reproducible and readable in code review).
DEFAULT_TEST_USER["okpella.test"]["password_hash"] = hash_password("Okpella@Test2026",
                                                                   "6f6b70656c6c612d746573742d73616c74")


def load_users():
    """Return (users, using_test_account)."""
    try:
        if "users" in st.secrets:
            users = {}
            for username, info in st.secrets["users"].items():
                if info.get("password_hash"):
                    users[username.strip().lower()] = {"name": info.get("name", username),
                                                       "password_hash": info["password_hash"]}
            if users:
                return users, False
    except Exception:  # noqa: BLE001  no secrets file
        pass
    return DEFAULT_TEST_USER, True


def current_user():
    return st.session_state.get("_auth_user")


def sign_out():
    for k in ("_auth_user", "_auth_name"):
        st.session_state.pop(k, None)


def require_password_login(app_title):
    """Show the sign-in form until a valid user signs in. Returns (display_name, using_test_account)."""
    users, test_mode = load_users()
    if current_user() in users:
        return st.session_state.get("_auth_name", ""), test_mode

    st.title(app_title)
    if test_mode:
        st.warning("Test sign-in is active. Username **okpella.test**, password **Okpella@Test2026**. "
                   "Replace it with real accounts before the pilot (see README).")

    locked_until = st.session_state.get("_auth_locked_until", 0)
    if time.time() < locked_until:
        st.error("Too many failed attempts. Try again in %d seconds." % int(locked_until - time.time()))
        st.stop()

    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        ok = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if ok:
        user = users.get(username.strip().lower())
        if user and verify_password(password, user["password_hash"]):
            st.session_state["_auth_user"] = username.strip().lower()
            st.session_state["_auth_name"] = user["name"]
            st.session_state["_auth_fails"] = 0
            st.rerun()
        fails = st.session_state.get("_auth_fails", 0) + 1
        st.session_state["_auth_fails"] = fails
        if fails >= MAX_ATTEMPTS:
            st.session_state["_auth_locked_until"] = time.time() + LOCKOUT_SECONDS
            st.session_state["_auth_fails"] = 0
        st.error("Incorrect username or password.")
    st.stop()
