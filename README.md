# OKPELLA Risk Assessment: Streamlit App

A web form that identifies hazards **only** from the OKPELLA register workbook. The user unticks what doesn't apply and downloads the PDF. No Copilot agent, no code interpreter, no review link.

```
Job details (dropdowns from the workbook) → Identify hazards → untick → Download PDF
```

## What's in this folder
| File | Purpose |
|---|---|
| `app.py` | The web app (sign-in, form, review screen, PDF button) |
| `simple_auth.py` | Username + password sign-in (test account and pilot accounts) |
| `make_password_hash.py` | Creates a password hash for a new pilot account |
| `engine.py` | Hazard selection: same rules as the Copilot agent, so the same inputs give the same hazard IDs |
| `pdf_report.py` | PDF in the OKPELLA v1.11 form design |
| `fonts/` | Liberation Sans (SIL Open Font Licence), so symbols such as °, – and ≥ print correctly |
| `requirements.txt` | Python packages for the server |
| `.streamlit/config.toml` | OKPELLA colours |
| `.streamlit/secrets.toml.example` | Template for sign-in settings (never commit the real one) |
| **You add:** `OKPELLA_Master_Workbook_v8.xlsx` | The register. Put it next to `app.py` |

## How the app uses the register
- Location, equipment, presets and activity lists come straight from the workbook.
- Equipment is filtered to what is registered in the chosen area. An "Other (not in register)" option exists for both location and equipment. With unlisted equipment, only activity hazards are included.
- Hazards are selected, de-duplicated and sorted exactly as the agent did. Every hazard, control, level, PPE item and responsible person is copied from its workbook row, and each card shows its row ID.
- **Same inputs + same workbook = same hazards.** The register fingerprint is shown in the sidebar and printed on every PDF.
- If any detail is changed after **Identify hazards**, the review is hidden until the user runs it again, so the PDF always matches the inputs shown.

---

## Step 1: Run it on your PC first (10 minutes)
1. Install Python 3.12 from python.org. Tick **Add Python to PATH**.
2. Put this folder somewhere, e.g. `C:\OKPELLA_RA\`, and copy `OKPELLA_Master_Workbook_v8.xlsx` into it.
3. Open **Command Prompt** in that folder and run:
   ```
   pip install -r requirements.txt
   streamlit run app.py
   ```
4. The app opens in your browser at `http://localhost:8501`. Sign in with the test account: `okpella.test` / `Okpella@Test2026`.
5. **Run the self-test:** in the sidebar, open **Self-test (5 reference cases)** → **Run self-test**. All five should show ✅, and the sidebar fingerprint should read **493DA897**.
   - If any case shows ❌, send the "Got … expected …" line. Don't deploy until all five pass.

## Step 2: Put it on GitHub (10 minutes)
1. Create a **private** repository, e.g. `okpella-risk-assessment`. You must be an admin of the repository.
2. Upload everything in this folder **plus the workbook**, keeping the `.streamlit` and `fonts` folders.
   - Do **not** upload a real `secrets.toml`.

## Step 3: Deploy on Streamlit Community Cloud (10 minutes)
1. Go to **share.streamlit.io** and sign in with GitHub.
2. Select **Create app** → **Deploy a public app from GitHub** (the repository itself stays private).
3. Choose the repository, branch `main` and file `app.py`. Pick an app address, e.g. `okpella-ra.streamlit.app`.
4. Open **Advanced settings**, choose Python **3.12**, then **Deploy**.
5. When it opens, run the self-test again: you should see 5 × ✅ and fingerprint 493DA897.

## Step 4: Sign-in

### 4a. Test sign-in (works straight away)
With no accounts configured, the app uses one **test account**:

| Username | Password |
|---|---|
| `okpella.test` | `Okpella@Test2026` |

A yellow banner on the sign-in page and in the sidebar shows while the test account is in use. The **Assessed by** field fills in from the signed-in name. After 5 wrong passwords, sign-in is blocked for 60 seconds.

> The test password is printed in this README and in the code, so treat the test account as **public**. Use it only for testing, and replace it before real users or real register data go on the cloud.

### 4b. Pilot accounts (replace the test account)
1. On your PC, in the app folder, run `python make_password_hash.py` and answer the prompts. It prints a block like:
   ```
   [users.jakukuata]
   name = "John Akukuata"
   password_hash = "pbkdf2_sha256$200000$…"
   ```
2. Repeat for each pilot user.
3. Paste all the blocks into the app's **Settings → Secrets** on Streamlit Community Cloud (or `.streamlit/secrets.toml` on your PC), then **Save**.
4. Once any `[users]` account exists, **the test account stops working** and the banner disappears.

Passwords are stored only as salted hashes (PBKDF2-SHA256, 200,000 rounds), never as plain text. To reset a password, make a new hash and replace that user's line. To remove a user, delete their block.

### 4c. Microsoft sign-in (later, needs IT)
Adding an `[auth]` block to Secrets switches the app to Microsoft sign-in, and `[users]` is then ignored. The settings are in `.streamlit/secrets.toml.example` (Option B):
1. IT registers the app in **Microsoft Entra ID** → **App registrations** → **New registration**:
   - Account types: **this organizational directory only**
   - Redirect URI (Web): `https://<your-app>.streamlit.app/oauth2callback`
2. IT gives you the client ID, the tenant ID and a client secret value. Paste them into Secrets, with `ALLOWED_EMAIL_DOMAIN` set to your company domain.

### Switching sign-in off
For local testing only, add `LOGIN_MODE = "none"` to Secrets.

---

## Updating the register
1. The register owner edits the workbook, keeping sheet, table and column names unchanged.
2. Upload the new copy to the GitHub repository, replacing the old one. The app reloads it automatically.
3. The fingerprint changes. Run the self-test:
   - Totals may legitimately differ after register edits.
   - Record the new fingerprint as your reference.

To use a different file name, set `WORKBOOK_PATH` in the app's Secrets.

## Known limits of the free Community Cloud plan
- The app sleeps when unused and takes a short time to wake.
- Resources are limited, and there's no uptime guarantee.
- Suitable for the pilot. For plant-wide use, IT can run the same folder on a company server or in Azure with no code changes (`streamlit run app.py`).
- Get IT/HSE approval before putting the register on an external cloud service.

## Troubleshooting
| Message | Fix |
|---|---|
| Register workbook not found | Put `OKPELLA_Master_Workbook_v8.xlsx` next to `app.py`, or set `WORKBOOK_PATH` |
| Workbook is missing table(s) | Use workbook v8 (it has tblInferenceRules); don't rename tables |
| "You changed the job details…" | Select **Identify hazards** again |
| "Incorrect username or password" | Usernames aren't case-sensitive; passwords are. If you added `[users]`, the test account no longer works |
| "Too many failed attempts" | Wait 60 seconds |
| Microsoft sign-in loops or fails | Check that the redirect URI in Entra exactly matches `redirect_uri` in Secrets, including `/oauth2callback` |
| "This app is limited to @… accounts" | The user signed in with a non-company account, or `ALLOWED_EMAIL_DOMAIN` is wrong |
