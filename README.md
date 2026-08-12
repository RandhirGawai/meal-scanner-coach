# 🥗 AI Meal Scanner + Body Recomposition Coach

A completely **free**, **local-first** app for Mac (Apple Silicon M1–M5) that:
- Scans meal photos with AI and estimates calories/protein/carbs/fat/fiber
- Tracks daily body metrics (weight, body fat %, muscle mass, water %)
- Tracks gym workouts and walking/steps
- Generates personalized AI coaching for **fat loss + muscle building (recomposition)**
- Stores everything locally in SQLite — your data never leaves your Mac except the
  meal photo + text you send to the AI model for analysis

Built with Streamlit + Groq's free API tier (or fully offline via Ollama).

---

## 1. Prerequisites (Mac)

You need Python 3.11+ and Homebrew. Open **Terminal** and run:

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11+
brew install python@3.12
```

Check your version:
```bash
python3 --version   # should show 3.11 or higher
```

## 2. Get a free Groq API key

1. Go to **https://console.groq.com/keys**
2. Sign up (free, no credit card required)
3. Click **Create API Key**, copy it — you'll paste it into `.env` below

Groq's free tier is generous (tens of thousands of tokens/minute, thousands of
requests/day) and is more than enough for personal daily use.

## 3. Set up the project

```bash
# 1. Unzip / cd into the project folder
cd meal-scanner-coach

# 2. Create a virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create your .env file
cp .env.example .env
```

Now open `.env` in any text editor (e.g. `open -e .env`) and paste your Groq key:

```
GROQ_API_KEY=gsk_your_actual_key_here
```

Save the file.

## 4. Run the app

```bash
streamlit run app.py
```

Your browser will open automatically at **http://localhost:8501**. On the
same Wi-Fi, you can also open it from your iPhone using the "Network URL"
Streamlit prints in the terminal — handy for snapping meal photos with your
phone camera.

To stop the app, press `Ctrl+C` in the terminal.

**Next time**, you only need:
```bash
cd meal-scanner-coach
source venv/bin/activate
streamlit run app.py
```

---

## 5. Host it for free — access from your phone anywhere, without losing data

You can deploy this to **Streamlit Community Cloud** for free and get a public
`https://your-app.streamlit.app` URL that works from your phone's browser
anywhere, camera included.

⚠️ **Important**: Streamlit Community Cloud does **not guarantee** that local
files survive a redeploy or reboot. To make your data genuinely permanent,
this app supports **Turso** — a free, SQLite-compatible cloud database. When
configured, every meal, photo, body metric, and workout is written straight
to Turso's cloud instead of a local file, so a Streamlit redeploy can never
touch it. This is the recommended setup for hosting.

### Step 1 — Create a free Turso database

```bash
# Install the Turso CLI
brew install tursodatabase/tap/turso

# Sign up / log in (free, opens your browser, no credit card)
turso auth login

# Create your database
turso db create meal-scanner-coach

# Get the connection URL
turso db show meal-scanner-coach --url

# Create an auth token
turso db tokens create meal-scanner-coach
```

Copy the URL (looks like `libsql://meal-scanner-coach-yourname.turso.io`) and
the token — you'll paste both into Secrets in Step 3.

Turso's free tier: 100 databases, 5GB storage, 500 million row reads/month,
10 million row writes/month — this personal app uses a tiny fraction of that.

*(Optional: add the same `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` to your*
*local `.env` too — then your Mac and your phone read/write the exact same*
*live database, so your history stays in sync everywhere.)*

### Step 2 — Push the project to GitHub

```bash
cd meal-scanner-coach
git init
git add .
git commit -m "Initial commit"
```

Create a new repo at **https://github.com/new** (private is fine — free tier
allows 1 private Community Cloud app), then push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/meal-scanner-coach.git
git branch -M main
git push -u origin main
```

`.gitignore` already excludes `.env` and local data — your keys and personal
data are never uploaded to GitHub.

### Step 3 — Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io**, sign in with GitHub (free)
2. Click **Create app** → your `meal-scanner-coach` repo → branch `main` →
   main file `app.py`
3. Before deploying, open **Advanced settings → Secrets** and paste:
   ```toml
   GROQ_API_KEY = "gsk_your_actual_key_here"
   APP_PASSWORD = "choose-a-password"
   TURSO_DATABASE_URL = "libsql://meal-scanner-coach-yourname.turso.io"
   TURSO_AUTH_TOKEN = "your_turso_token_here"
   ```
   `APP_PASSWORD` locks the app behind a simple password screen — recommended
   since the URL is public and this holds personal health data.
4. Click **Deploy**.

You'll get a URL like `https://your-username-meal-scanner-coach.streamlit.app`
— open it on your phone and, in Safari, tap Share → **Add to Home Screen**
for an app-like icon. The sidebar will show **"☁️ Storage: Turso"** once
it's connected correctly.

### Step 4 (optional but still worth doing) — periodic backups

Even with Turso, it costs nothing to also keep your own copy. The sidebar's
**💾 Backup & Restore** panel exports everything (including meal photos,
which are stored as compressed data inside the database) to one downloadable
file. Grab one occasionally — it's a second safety net, not a requirement.

### Free tier limits to know

- Streamlit Cloud: ~1 GB memory (plenty here), sleeps after ~12h with no
  visitors (next visitor sees a brief "waking up" screen, data unaffected),
  unlimited public apps, 1 private app
- Turso: free tier limits listed above — a single person logging a few
  meals a day will never come close

---

## 6. First-time setup inside the app

1. Open the **sidebar** → fill in your profile (age, height, sex, goal, activity
   level) and click **Save Profile**.
2. Go to **⚖️ Body Metrics** → log today's weight/body fat/muscle from your
   smart scale.
3. Go to **📸 Scan Meal** → upload or take a photo → click **Analyze with AI**
   → review/correct the numbers → **Save Meal**.
4. Go to **🏃 Activity** → log your workout and walking.
5. Go to **🧠 AI Insights** → click **Generate Today's AI Coaching** for
   personalized advice.
6. Go to **📊 History** to see trends over time.

---

## 7. Fully offline mode (no internet, 100% free, uses your Mac's GPU)

If you'd rather not use any cloud API at all:

```bash
# Install Ollama
brew install ollama

# Start the Ollama server (leave this running in its own terminal tab)
ollama serve

# In another terminal tab, pull a vision model and a text model
ollama pull llava        # for meal photo analysis
ollama pull llama3.1     # for coaching insights
```

Then in your `.env` file, set:
```
USE_OLLAMA_FALLBACK=true
```

Restart the Streamlit app. All AI calls now run 100% locally on your Mac —
no API key needed. Vision quality is somewhat lower than Groq's hosted models,
but it works entirely offline. Apple Silicon Macs with 16GB+ RAM run `llava`
and `llama3.1:8b` comfortably.

---

## 8. Project structure

```
meal-scanner-coach/
├── app.py              # Main Streamlit UI — all 5 tabs + password gate
├── database.py         # Storage layer — local SQLite or Turso, same code either way
├── ai_engine.py         # Groq/Ollama API calls + system prompts + target calculator
├── config.py             # Shared helper: reads Secrets (deployed) or .env (local)
├── utils.py             # Image encoding, formatting, backup/restore
├── requirements.txt     # Python dependencies
├── .env.example          # Copy to .env and fill in your keys (local use)
├── .gitignore             # Keeps secrets & personal data out of GitHub
├── .streamlit/
│   └── secrets.toml.example  # Template for Streamlit Cloud secrets
├── README.md             # You are here
└── data/
    └── app.db            # SQLite database — ONLY used when Turso isn't configured
```

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Make sure you activated the venv: `source venv/bin/activate` |
| "No GROQ_API_KEY found" | Check `.env` has your real key and is saved in the project root |
| Vision analysis fails/times out | Check internet connection; Groq free tier has rate limits — wait ~30s and retry |
| Camera doesn't work in browser | Streamlit's camera input needs HTTPS or `localhost` — works fine on localhost, may need a workaround for the network URL on some browsers |
| Want to reset all data | Delete `data/app.db` (and optionally `data/meal_images/`) — the app recreates an empty database automatically |
| Groq model errors ("model decommissioned") | Groq periodically retires models. Check https://console.groq.com/docs/models and update `GROQ_VISION_MODEL` / `GROQ_TEXT_MODEL` in `.env` (or Secrets, if deployed) |
| Data disappeared after redeploying to Streamlit Cloud | If you haven't set up Turso yet, this is expected — see section 5. Restore your last backup from the sidebar's **Backup & Restore** panel, then set up Turso so it doesn't happen again |
| Sidebar shows "💾 Storage: local SQLite" after deploying | `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` aren't set correctly in Secrets — double-check them at share.streamlit.io → your app → Settings → Secrets |
| Forgot my `APP_PASSWORD` on the deployed app | Go to share.streamlit.io → your app → Settings → Secrets, and view/change it there |

## 10. Customizing

- **Change AI personality/advice style**: edit `COACH_SYSTEM_PROMPT` in `ai_engine.py`
- **Change vision analysis detail**: edit `MEAL_VISION_SYSTEM_PROMPT` in `ai_engine.py`
- **Add more body metrics**: add columns to `body_metrics` table in `database.py`
  and matching fields in the `⚖️ Body Metrics` tab in `app.py`
- **Change calorie/protein formula**: edit `calculate_targets()` in `ai_engine.py`

---

Everything here is free: Streamlit is open-source, Groq's API free tier needs no
credit card, SQLite is built into Python, and Ollama is free/open-source for
the fully offline path. No subscriptions, no paid tiers required.
