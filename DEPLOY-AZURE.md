# Deploy StudyPilot to Azure (step by step)

**What you'll have at the end:** StudyPilot running 24/7 at a real HTTPS address like
`https://studypilot-hassan.centralindia.cloudapp.azure.com`.
- The agents keep working while your laptop is off.
- It restarts by itself after a crash or a reboot.
- Your data is kept on the server's disk.

**Time:** about 45 minutes, most of it waiting for the first build.

**Cost:** about **$15 a month** for a B1ms server (1 vCPU, 2 GB RAM), taken from your Azure credits. It runs in
its **own resource group**, so it never touches your Fanout deployment. Step 12 adds a budget alert.

**You need:**
- portal.azure.com, signed in to the subscription that has your credits.
- These files from `D:\claude\agentathon\studypilot\backend\`:
  - `.env`
  - `credentials.json`
  - `studypilot.db` (optional, to bring all your data)
  - `cv.pdf` (optional)
- PowerShell on your PC (Windows already has `ssh` and `scp`).

> **Golden rule: only one StudyPilot "brain" at a time.** Once the Azure copy is live, don't run
> `start.ps1` on your laptop (see Step 10).

---

## Step 1 — Create the server

1. Open **https://portal.azure.com** → search **Virtual machines** → **Create** → **Azure virtual machine**.
2. **Basics** tab:

   | Setting | Value |
   |---|---|
   | Subscription | the one with your credits (same as Fanout) |
   | Resource group | **Create new** → `studypilot-rg` (keeps it separate from Fanout) |
   | Virtual machine name | `studypilot` |
   | Region | **(Asia Pacific) Central India**, or **(Middle East) UAE North**: both close to Pakistan |
   | Availability options | No infrastructure redundancy required |
   | Security type | Standard |
   | Image | **Ubuntu Server 24.04 LTS - x64 Gen2** |
   | Size | **B1ms** (1 vCPU, 2 GiB). Click "See all sizes" if it isn't listed. |
   | Authentication type | **SSH public key** |
   | Username | `azureuser` |
   | SSH public key source | Generate new key pair · Key pair name `studypilot_key` |
   | Public inbound ports | Allow selected ports → tick **SSH (22)**, **HTTP (80)**, **HTTPS (443)** |

3. **Disks** tab: OS disk type **Standard SSD**. Keep the default size.
4. Click **Review + create** → **Create**.
5. A popup appears: click **Download private key and create resource**. A file
   **`studypilot_key.pem`** downloads to your Downloads folder. **Keep it safe; it is your server key.**
6. Wait for "Your deployment is complete" → **Go to resource**.

## Step 2 — Give it a free web address

1. On the VM page, under **Essentials**, click the **Public IP address** link (e.g. `20.198.x.x`).
2. Left menu → **Configuration**.
3. **Assignment:** **Static**. Usually it already is. If it isn't, select it.
4. **DNS name label:** type `studypilot-hassan` (any free name, lowercase).
5. Click **Save**.
6. Your web address is shown under the label, e.g.
   **`studypilot-hassan.centralindia.cloudapp.azure.com`**. Write it down; this guide calls it **YOUR-DOMAIN**.

## Step 3 — Allow Google sign-in on that address

1. Open **https://console.cloud.google.com/apis/credentials** (Google, not Azure: that's where your
   OAuth client lives).
2. Click your StudyPilot **OAuth 2.0 Client ID**.
3. Under **Authorized redirect URIs**, click **+ Add URI**:
   ```
   https://YOUR-DOMAIN/auth/callback
   ```
   e.g. `https://studypilot-hassan.centralindia.cloudapp.azure.com/auth/callback`.
   Keep the localhost one too.
4. Click **Save** and wait about 5 minutes.
5. If Google asks for an authorized domain, add `YOUR-DOMAIN` at
   https://console.cloud.google.com/auth/branding. Make sure your Gmail address is under **Test users** at
   https://console.cloud.google.com/auth/audience.

## Step 4 — Connect to the server from PowerShell

1. Open **PowerShell** on your PC.
2. Lock down the key file. SSH refuses keys other users can read, so run these three lines:
   ```powershell
   $key = "$HOME\Downloads\studypilot_key.pem"
   icacls $key /inheritance:r
   icacls $key /grant:r "$($env:USERNAME):(R)"
   ```
3. Connect, replacing YOUR-DOMAIN:
   ```powershell
   ssh -i $HOME\Downloads\studypilot_key.pem azureuser@YOUR-DOMAIN
   ```
4. Type **yes** at the "Are you sure you want to continue connecting" question.
5. You'll see a prompt like `azureuser@studypilot:~$`. You're now on the server.

## Step 5 — Set up the server

In that same window (now on the server), paste and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/HassanIrfan279/studypilot/main/deploy/setup-vm.sh | bash
```

Wait 2–4 minutes. It installs Docker, adds swap memory, and downloads StudyPilot. It ends with
`Setup done. Server IP: ...`.

## Step 6 — Upload your secret files

1. Open a **second PowerShell window** on your PC. Leave the server window open.
2. Run, replacing YOUR-DOMAIN:
   ```powershell
   cd D:\claude\agentathon\studypilot\backend
   scp -i $HOME\Downloads\studypilot_key.pem .env credentials.json azureuser@YOUR-DOMAIN:~/
   ```
3. Back in the **server** window, move them into place:
   ```bash
   mv ~/.env ~/credentials.json ~/studypilot/backend/
   ```

You don't need to edit `.env`. The server sets the web address, the sign-in address and the data folder by itself.

## Step 7 — Start StudyPilot

In the **server** window, replacing YOUR-DOMAIN:

```bash
DOMAIN=YOUR-DOMAIN bash ~/studypilot/deploy/start.sh
```

e.g. `DOMAIN=studypilot-hassan.centralindia.cloudapp.azure.com bash ~/studypilot/deploy/start.sh`

The first build takes **5–10 minutes**. It ends with `LIVE:  https://YOUR-DOMAIN`. The domain is
remembered, so from now on plain `bash ~/studypilot/deploy/start.sh` is enough.

If it says "Not answering yet", wait 1 minute and run it again. The HTTPS certificate is sometimes
still being issued.

## Step 8 — Bring your data, or start fresh (pick one)

**Option A: bring everything from your laptop (recommended).** This copies your sign-in, prep packs,
notes, plans, CV and internships.

1. On your laptop, stop the backend (Ctrl+C in its window).
2. In the **PC** PowerShell window:
   ```powershell
   cd D:\claude\agentathon\studypilot\backend
   scp -i $HOME\Downloads\studypilot_key.pem studypilot.db cv.pdf azureuser@YOUR-DOMAIN:~/
   ```
   (If you have no `cv.pdf`, leave it out of the command.)
3. In the **server** window:
   ```bash
   bash ~/studypilot/deploy/copy-data.sh
   ```
4. Open `https://YOUR-DOMAIN`. You're already signed in and everything is there.

**Option B: start fresh**
1. Open `https://YOUR-DOMAIN` → **Sign in with Google** → tick **every** box.
2. Sidebar → **System check** → **Warm up**, then wait about 5 minutes for "All set".
3. **Internships** → upload or build your CV.

## Step 9 — Check that everything works

1. Open `https://YOUR-DOMAIN` → sidebar **System check** → **Run checks**.
2. You want **"All systems go"** (16 checks). Anything red shows its fix right under it.
3. Click **Send test alert**. Your phone should get the Discord message.
4. Open **Meet the agents** and watch the status dots light up.

## Step 10 — Turn off the laptop copy

From now on Azure is your StudyPilot. **Don't** run `start.ps1` while it's live.

To use the laptop as a stage backup, stop Azure's copy first (server window):
```bash
cd ~/studypilot/deploy && sudo docker compose stop app
```
Start it again later with:
```bash
cd ~/studypilot/deploy && sudo docker compose start app
```

## Step 11 — Get an email if it goes down (optional, free)

**https://uptimerobot.com** → free account → **Add New Monitor**:
- Type: **HTTP(s)**
- URL: `https://YOUR-DOMAIN/health`
- Interval: 5 minutes

## Step 12 — Budget alert (protects your credits)

Azure portal → search **Cost Management** → **Budgets** → **+ Add**:
- Scope: resource group **`studypilot-rg`**
- Amount: **$20 per month**
- Alerts at **50%, 90%, 100%**, sent to your email

## Step 13 — Submit

- **Live app:** `https://YOUR-DOMAIN`
- **Code:** https://github.com/HassanIrfan279/studypilot

---

## Everyday commands

To connect from PowerShell:

```powershell
ssh -i $HOME\Downloads\studypilot_key.pem azureuser@YOUR-DOMAIN
```

Then, on the server:

| What you want | Paste this |
|---|---|
| Get the latest code from GitHub and restart | `cd ~/studypilot && git pull && bash deploy/start.sh` |
| Watch the live log (Ctrl+C to stop) | `cd ~/studypilot/deploy && sudo docker compose logs -f --tail=100 app` |
| Restart the app | `cd ~/studypilot/deploy && sudo docker compose restart app` |
| Is it healthy? (look for `healthy`) | `sudo docker ps` |
| Stop it (data is kept) | `cd ~/studypilot/deploy && sudo docker compose stop app` |
| Change a setting | `nano ~/studypilot/backend/.env` → edit → Ctrl+O, Enter, Ctrl+X → restart |

**Saving credits when you're not using it:** Azure portal → the VM → **Stop**. A stopped (deallocated) VM costs almost
nothing; only the disk and IP are billed. **Start** it again before the demo. Your address and data stay the same.

## Demo-day checklist

- **The day before:** site → **System check** → **Renew Google sign-in** → tick every box. Google
  testing-mode sign-ins expire after 7 days.
- **30 minutes before:**
  1. **System check** → **Warm up** → wait for "All set" → **Run checks** → "All systems go".
  2. **Send test alert** and keep Discord open.
  3. Click once on the page, so the browser allows spoken alerts.
- **Backup plan:** the laptop copy (Step 10) and your recorded demo video.

## If something goes wrong

| Problem | Fix |
|---|---|
| `ssh` says **UNPROTECTED PRIVATE KEY FILE** | Run the 3 `icacls` lines from Step 4 again. |
| `ssh` just waits, then times out | In Azure: VM → **Networking** → check the inbound rules allow port **22**. Also check the VM is **Running**. |
| `start.sh` says "Not answering yet" | Wait a minute and run it again. In Azure → VM → Networking, make sure ports **80 and 443** are allowed (the HTTPS certificate needs both). |
| Google says **redirect_uri_mismatch** | The URI in Step 3 must be exactly `https://YOUR-DOMAIN/auth/callback`. Wait 5 minutes after saving. |
| The build stops with **Killed** | Out of memory. Check the swap with `swapon --show`, then run `start.sh` again. Or resize the VM to **B2s**. |
| "Sign in again" banner, or the agents stopped | **System check** → **Renew Google sign-in** (7-day testing-mode limit). |
| The voice button doesn't work | Click the lock icon in the address bar → Microphone → Allow. |
