# Install

## Prerequisites (installed on the machine, not by this project)

| Requirement | Why |
| --- | --- |
| Python **3.11** (`python3` on `PATH`) | the runtime the project is written and tested against |
| pip and a working wheel toolchain for Python 3.11 | `python3 -m pip install -r requirements.txt` |
| ~400 MB free disk | Gradio and its dependencies (pandas, pillow, numpy) live in site-packages |
| A free TCP port, default **7860** | the Gradio runner's conventional port |

No database server, no Node, no system packages, no external services. Nothing is downloaded at
runtime: the Lexend font, the icons and the seeded spore-print images are all vendored in the tree.

## One command (recommended)

```bash
bash install.sh
```

`install.sh` runs as an unprivileged user and, in order:

1. upgrades `pip`, `setuptools` and `wheel`;
2. installs the pinned dependencies from `requirements.txt`;
3. writes a random `SESSION_SECRET` into `.env` if one is not already there;
4. creates the SQLite schema and seeds the demo data (`python3 seed.py`);
5. imports `app` as a self-check, prints the start command and **exits** (it never starts a server).

It is safe to re-run: the seed checks before it inserts.

## Step by step (if you prefer to do it manually)

```bash
# 1. dependencies
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt

# 2. optional configuration
cp .env.example .env          # every value has a working default
                              # add SESSION_SECRET=<64 random hex chars> for a non-dev secret

# 3. schema + demo data (idempotent, exits when done)
python3 seed.py

# 4. run
python3 app.py                # http://localhost:7860
```

## Configuration

All variables are optional; the app boots with no `.env` at all.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `7860` | HTTP port (bound on `0.0.0.0`) |
| `DATABASE_URL` | `sqlite:///./foray.db` | SQLAlchemy URL; a relative SQLite file by default |
| `UPLOAD_DIR` | `./uploads` | where uploaded spore-print photos are stored (never served directly) |
| `SESSION_SECRET` | in-code development fallback | signs the session cookie. `install.sh` generates a real one |

`.env` is git-ignored. For a production deploy, also remove the demo account (`cenius`) and set a
secret that is not the in-code development fallback.

## Upgrading / resetting

```bash
rm -f foray.db && python3 seed.py     # rebuild the database and reseed the demo foray
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'gradio'` | `python3 -m pip install -r requirements.txt` |
| `Address already in use` on start | another process holds `PORT`; stop it or set `PORT=7861` |
| Sign-in succeeds but you land back on `/login` | your browser is blocking the cookie; the app needs cookies for `localhost` |
| Charts are empty | the selected foray session has no finds — pick “All sessions” on the Dashboard tab |
| `sqlite3.OperationalError: unable to open database file` | the directory for `DATABASE_URL` must exist; the default (`./foray.db`) always does |
