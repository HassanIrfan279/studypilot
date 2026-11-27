# Deploy StudyPilot to Google Cloud (step by step)

**What you'll have at the end:** StudyPilot running 24/7 at a real HTTPS web address, like
`https://34-123-45-67.sslip.io`.
- The agents keep working while your laptop is off: sync, nightly review, internship hunt, phone alerts.
- It restarts by itself after a crash or a reboot.
- Your sign-in and data are kept on the server's disk.

**Time:** about 45 minutes, most of it waiting for the first build.

**Cost:** the e2-micro server and its 30 GB disk are in Google Cloud's **always-free tier**. The fixed IP
address may cost about $3–4 a month, which your $5 credit covers. Step 12 sets a budget alert so nothing surprises you.

**You need:**
- A browser signed in to the Google account that owns your Google Cloud project, the one with your OAuth client and billing.
- These files from your PC, in `D:\claude\agentathon\studypilot\backend\`:
  - `.env`
  - `credentials.json`
  - `studypilot.db` (optional, to bring all your data)
  - `cv.pdf` (optional)

> **Golden rule: only one StudyPilot "brain" at a time.** Once the cloud copy is live, don't run
> `start.ps1` on your laptop. Otherwise two copies react to the same Classroom change and book double
> sessions. Step 10 explains this.

---

## Step 1 — Create the server

1. Open **https://console.cloud.google.com/compute/instances**.
2. At the top, make sure the **project** is the same one that holds your OAuth client (the one you used for StudyPilot).
3. If you see **"Enable Compute Engine API"**, click **Enable** and wait about 1 minute.
4. Click **Create instance**, then fill in:

   | Setting | Value |
   |---|---|
   | Name | `studypilot` |
   | Region | **us-central1 (Iowa)** (must be us-central1, us-west1 or us-east1 to be free) |
   | Zone | any (e.g. us-central1-a) |
   | Machine configuration | Series **E2** → Machine type **e2-micro** |
   | OS and storage → **Change** | Operating system **Debian**, version **Debian GNU/Linux 12**, Boot disk type **Standard persistent disk**, Size **30** GB → **Select** |
   | Networking → Firewall | ✅ **Allow HTTP traffic**  ✅ **Allow HTTPS traffic** |

5. Click **Create**. Wait for the green tick next to `studypilot`.

## Step 2 — Give it a permanent IP address

Your web address is built from the IP address, so the IP must never change.

1. Open **https://console.cloud.google.com/networking/addresses/list**.
2. Find the row whose "In use by" is `studypilot`. Its type says **Ephemeral**.
3. Click the **⋮** at the end of the row → **Promote to static IP address** → Name: `studypilot-ip` → **Reserve**.
4. Write down the **IP address**, e.g. `34.123.45.67`.

## Step 3 — Work out your web address

Take the IP, replace the dots with dashes, and add `.sslip.io`:

```
34.123.45.67   →   34-123-45-67.sslip.io
```

That's your free domain. sslip.io is a free service that points this name at your IP. Your site will be
**`https://34-123-45-67.sslip.io`** (with your numbers).

## Step 4 — Allow Google sign-in on the new address

1. Open **https://console.cloud.google.com/apis/credentials**.
2. Under **OAuth 2.0 Client IDs**, click your StudyPilot client (type "Web application").
3. Under **Authorized redirect URIs**, click **+ Add URI** and paste (with YOUR numbers):
   ```
   https://34-123-45-67.sslip.io/auth/callback
   ```
   Keep the existing `http://localhost:8000/auth/callback` too, so your laptop still works.
4. Click **Save**. It can take up to 5 minutes to take effect.
5. Check the consent screen: open **https://console.cloud.google.com/auth/audience**. Under **Test users**, make sure
   your Gmail address is listed. If Google asks for an **Authorized domain**
   (https://console.cloud.google.com/auth/branding), add `34-123-45-67.sslip.io` (your numbers).

## Step 5 — Open the server and run the setup

1. Go back to **https://console.cloud.google.com/compute/instances**.
2. In the `studypilot` row, click **SSH**. A black terminal window opens in your browser. Click
   **Authorize** if asked.
3. Copy this whole line, paste it into that window (right-click → Paste, or Ctrl+V), and press **Enter**:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/HassanIrfan279/studypilot/main/deploy/setup-vm.sh | bash
   ```

4. Wait 2–4 minutes. It installs Docker, adds 2 GB of swap memory, and downloads StudyPilot from
   GitHub. It ends with:
   ```
   Setup done. Your free domain is:  34-123-45-67.sslip.io
   ```
   Check that it matches Step 3.

## Step 6 — Upload your secret files

Secrets never go to GitHub; you upload them straight to your server.

1. In the SSH window, click **UPLOAD FILE** (the up-arrow button at the top right).
2. Select `D:\claude\agentathon\studypilot\backend\.env`.
   - If you can't see `.env`, type `.env` in the **File name** box and press Enter.
3. Click **UPLOAD FILE** again and select `D:\claude\agentathon\studypilot\backend\credentials.json`.
4. Move both into place by pasting this and pressing Enter:

   ```bash
   mv ~/.env ~/credentials.json ~/studypilot/backend/
   ```

You don't need to edit `.env`. The server sets the web address, the sign-in address and the data folder by itself.

## Step 7 — Start StudyPilot

Paste and press Enter:

```bash
bash ~/studypilot/deploy/start.sh
```

The first time, it builds the whole app, which takes **8–15 minutes** on the small server. When it
finishes you'll see:

```
LIVE:  https://34-123-45-67.sslip.io
```

If it says "Not answering yet", wait 1 minute and run the same command again. The HTTPS certificate is
sometimes still being issued.

## Step 8 — Bring your data, or start fresh (pick one)

**Option A: bring everything from your laptop (recommended).** This copies your sign-in, prep packs,
notes, plans, CV and internships.

1. **On your laptop:** close the backend window (Ctrl+C), so the database file is complete.
2. In the SSH window: **UPLOAD FILE** → `D:\claude\agentathon\studypilot\backend\studypilot.db`
3. Also **UPLOAD FILE** → `D:\claude\agentathon\studypilot\backend\cv.pdf`, if that file exists.
4. Paste and press Enter:
   ```bash
   bash ~/studypilot/deploy/copy-data.sh
   ```
5. Open your site. You're already signed in and everything is there.

**Option B: start fresh**
1. Open your site, click **Sign in with Google**, and tick **every** checkbox.
2. Open **System check** in the sidebar and click **Warm up**. Wait about 5 minutes for "All set" in the agent log.
3. Open **Internships** and upload or build your CV again.

## Step 9 — Check that everything works

1. Open your site → sidebar **System check** → **Run checks**.
2. You want the green bar **"All systems go"** (16 checks: Google, Gemini, voice, alerts, agents).
   Anything red shows its fix right under it.
3. Click **Send test alert**. Your phone should get the Discord message.
4. Open **Meet the agents**. The status dots show the agents working.

## Step 10 — Turn off the laptop copy

From now on the **cloud** is your StudyPilot.
- **Don't** run `start.ps1` on your laptop while the cloud copy is running.
- To use the laptop as a backup (e.g. no internet on stage), first stop the cloud copy. In the SSH window:
  ```bash
  cd ~/studypilot/deploy && sudo docker compose stop app
  ```
  Start it again later with:
  ```bash
  cd ~/studypilot/deploy && sudo docker compose start app
  ```

## Step 11 — Get an email if it ever goes down (optional, free)

1. Sign up at **https://uptimerobot.com** (free plan).
2. **Add New Monitor** → type **HTTP(s)** → URL `https://34-123-45-67.sslip.io/health` → interval 5 minutes.
3. You'll get an email if the site stops answering.

## Step 12 — Budget alert (so the $5 is never a surprise)

1. Open **https://console.cloud.google.com/billing/budgets** → **Create budget**.
2. Amount **$5**, alerts at **50%, 90%, 100%** → **Finish**.

## Step 13 — Submit

- **Live app:** `https://34-123-45-67.sslip.io`
- **Code:** https://github.com/HassanIrfan279/studypilot

---

## Everyday commands (in the SSH window)

| What you want | Paste this |
|---|---|
| Get the latest code from GitHub and restart | `cd ~/studypilot && git pull && bash deploy/start.sh` |
| Watch the live server log (Ctrl+C to stop watching) | `cd ~/studypilot/deploy && sudo docker compose logs -f --tail=100 app` |
| Restart the app | `cd ~/studypilot/deploy && sudo docker compose restart app` |
| Is it healthy? (look for `healthy`) | `sudo docker ps` |
| Stop it (your data is kept) | `cd ~/studypilot/deploy && sudo docker compose stop app` |
| Change a setting in `.env` | `nano ~/studypilot/backend/.env` → edit → Ctrl+O, Enter, Ctrl+X → then the restart command above |

## Demo-day checklist

- **The day before:** open your site → **System check** → **Renew Google sign-in**, then tick every box.
  Google testing-mode sign-ins expire after **7 days**; the System check shows the exact expiry.
- **30 minutes before:**
  1. **System check** → **Warm up** → wait for "All set" → **Run checks** → "All systems go".
  2. **Send test alert** and keep your phone's Discord open.
  3. Click once anywhere on the page, so the browser allows sound for spoken alerts.
- **Backup plan:** keep the laptop copy ready (Step 10), and keep your recorded demo video handy.

## If something goes wrong

| Problem | Fix |
|---|---|
| `start.sh` says "Not answering yet" | Wait a minute and run `bash ~/studypilot/deploy/start.sh` again. Still stuck: read the log (command above). |
| Google says **redirect_uri_mismatch** | The URI in Step 4 must match exactly: `https://`, dashes not dots, `/auth/callback`, no slash at the end. Wait 5 minutes after saving. |
| Google refuses the sslip.io address | Use a free DuckDNS name: sign in at https://www.duckdns.org, create e.g. `studypilot-hassan`, set it to your IP, then use `https://studypilot-hassan.duckdns.org/auth/callback` in Step 4. Start with `DOMAIN=studypilot-hassan.duckdns.org bash ~/studypilot/deploy/start.sh`, and use that same command for every later restart. |
| The build stops with **Killed** | The server ran out of memory. Check the swap exists with `swapon --show`, then run `start.sh` again. |
| "Sign in again" banner, or the agents stopped | Your Google sign-in expired (7 days in testing mode). **System check** → **Renew Google sign-in**. |
| A System check line is red | Do what its **Fix:** line says. Voice failing on stage? Use the chat box; it has the same powers. |
| The site works but the voice button doesn't | The browser needs microphone permission: click the lock icon in the address bar → Microphone → Allow. |
