"""Create a password hash for the [users] section of Streamlit Secrets.

Usage:  python make_password_hash.py
Paste the printed block into Secrets. The password itself is never stored.
"""
import getpass

from simple_auth import hash_password, verify_password

username = input("Username (e.g. jakukuata): ").strip().lower()
name = input("Full name shown on the form (e.g. John Akukuata): ").strip()
pw = getpass.getpass("Password (min 10 characters): ")
if len(pw) < 10 or pw != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords did not match or are shorter than 10 characters.")
h = hash_password(pw)
assert verify_password(pw, h)
print("\nPaste into Secrets:\n")
print('[users.%s]\nname = "%s"\npassword_hash = "%s"' % (username, name, h))
