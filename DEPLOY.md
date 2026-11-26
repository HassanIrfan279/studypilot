# Deploy StudyPilot on a free Google Cloud VM

What you get: StudyPilot running 24/7 at `https://<your-ip>.sslip.io`, with real HTTPS (needed for
Google sign-in and the microphone), auto-restart after crashes and reboots, and your sign-in + data kept
on disk. Time: about 30 minutes. Cost: the e2-micro VM and its 30 GB disk are in Google's
**always-free tier**; the public IP address may cost about $3–4/month, which your $5 credit covers.

> Run only ONE StudyPilot at a time on your Google account. If the cloud one is live, stop the local
> backend (Ctrl-C in its terminal), otherwise both agents react to the same Classroom change.

---

## 1. Create the VM (Google Cloud Console, in the browser)

1. Open <https://console.cloud.google.com/compute/instances> — pick the **same project** as your OAuth
   client. If asked, click **Enable** for the Compute Engine API (takes ~1 minute).
2. Click **Create instance** and set:
   - **Name:** `studypilot`
   - **Region:** `us-central1 (Iowa)` (must be us-central1, us-west1 or us-east1 to be free)
   - **Machine type:** series **E2** → **e2-micro**
   - **OS and storage → Change:** Debian GNU/Linux 12, **Standard persistent disk**, **30 GB** → Select
   - **Networking → Firewall:** tick **Allow HTTP traffic** and **Allow HTTPS traffic**
3. Click **Create**. Wait for the green tick.

## 2. Make the IP address permanent

Your web address is built from the IP, so it must never change.

1. Open <https://console.cloud.google.com/networking/addresses/list>.
2. Find the row for `studypilot` (type *Ephemeral*) → ⋮ → **Promote to static IP address** → name it
   `studypilot-ip` → Reserve.
3. Note the IP, e.g. `34.123.45.67`. Your domain is the IP with dashes + `.sslip.io`:
   **`34-123-45-67.sslip.io`** (sslip.io is a free service that points that name at your IP).

## 3. Tell Google sign-in about the new address

1. Open <https://console.cloud.google.com/apis/credentials> → click your OAuth 2.0 Client ID (the web one).
2. Under **Authorized redirect URIs** → **Add URI**:
   `https://34-123-45-67.sslip.io/auth/callback` (with YOUR domain) → **Save**.
   Keep the localhost one too, so local still works.

## 4. Set up the VM (one command)

1. Back on the VM list, click **SSH** next to `studypilot`. A terminal opens in the browser
   (click Authorize if asked).
2. Paste this and press Enter (takes 2–3 minutes):

   ```bash
   curl -fsSL https://raw.githubusercontent.com/HassanIrfan279/studypilot/main/deploy/setup-vm.sh | bash
   ```

   It ends with: `Your free domain is: 34-123-45-67.sslip.io`.

## 5. Upload your secrets (never put them in GitHub)

In the SSH window, click **UPLOAD FILE** (top right) and upload, from
`D:\claude\agentathon\studypilot\backend\` on your PC:

- `.env`  (in the file picker, type `.env` in the File name box if it is hidden)
- `credentials.json`

Then move them into place:

```bash
mv ~/.env ~/credentials.json ~/studypilot/backend/
```

You don't need to edit `.env`: the server sets the web address, redirect URI and data folder itself.

## 6. Start it

```bash
bash ~/studypilot/deploy/start.sh
```

The first build takes ~5–10 minutes on the small VM. It ends with
`LIVE: https://34-123-45-67.sslip.io`. Open that link, click **Sign in with Google**, tick every box.
Then open the **Check** page and click **Warm up**, then **Run checks** → "All systems go".

---

## Everyday commands (in the SSH window)

| What | Command |
|---|---|
| Update to the latest code from GitHub | `cd ~/studypilot && git pull && bash deploy/start.sh` |
| See live logs | `cd ~/studypilot/deploy && sudo docker compose logs -f --tail=100 app` (Ctrl-C to exit) |
| Restart | `cd ~/studypilot/deploy && sudo docker compose restart app` |
| Is it healthy? | `sudo docker ps` (STATUS should say `healthy`) |
| Stop | `cd ~/studypilot/deploy && sudo docker compose down` (data is kept) |

The app restarts by itself if it crashes or the VM reboots. Your sign-in, plans, notes and prep packs
live in a Docker volume, so updates and restarts keep them.

## If something goes wrong

- **`start.sh` says "Not answering yet"**: run the logs command above. During the first start the
  HTTPS certificate can take a minute; run `bash deploy/start.sh` again.
- **Google says `redirect_uri_mismatch`**: the URI in step 3 must match exactly — `https://`, dashes,
  `/auth/callback`, no trailing slash.
- **Google refuses the sslip.io address**: get a free name at <https://www.duckdns.org> (sign in, create
  e.g. `studypilot-hassan`, set it to your static IP), use `https://studypilot-hassan.duckdns.org/auth/callback`
  in step 3, then start with: `DOMAIN=studypilot-hassan.duckdns.org bash ~/studypilot/deploy/start.sh`
  (use that same command for every later update).
- **Build stops with "Killed"**: out of memory; check the swap exists (`swapon --show`), then re-run
  `start.sh`.
- **Sign-in expires after 7 days** (Google testing mode): sign in again on the website, same as local.

## Cost safety

Set a budget alert so nothing surprises you: <https://console.cloud.google.com/billing/budgets> →
Create budget → $5 → alerts at 50/90/100%.
