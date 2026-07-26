# Setup

## Environment check (run before every session)

```bash
wsl -l -v 2>&1
wsl -d Ubuntu -- python3 -c "import nle; print('ok')" 2>&1
```

- WSL missing → ask user to install
- NLE missing → ask user to install
- Both OK → proceed

## Install WSL

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -NoRestart
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -NoRestart
# reboot, then:
wsl --install --no-distribution
wsl --import Ubuntu <target-path> <rootfs-path> --version 2
```

## Install NLE (WSL/Linux)

```bash
wsl -d Ubuntu -- bash -c "apt-get update -qq && apt-get install -y -qq python3 python3-pip cmake build-essential libncurses-dev bison flex && pip3 install nle gymnasium"
```

## macOS setup (verified — Apple Silicon, macOS 26)

nle has **no macOS wheels** — it builds NetHack from source. nle ships wheels only
up to CPython 3.13, so use Python 3.13 (not 3.14+). One-time:

```bash
brew install python@3.13 cmake tmux bison flex
PY=/opt/homebrew/opt/python@3.13/bin/python3.13
$PY -m venv .venv                      # local venv next to play.py (git-ignored)
# brew bison/flex are keg-only; the old system bison fails NetHack's build:
export PATH="/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/flex/bin:$PATH"
# modern clang treats NetHack's old C as errors without these:
export CFLAGS="-Wno-implicit-function-declaration -Wno-implicit-int -Wno-int-conversion"
.venv/bin/pip install nle gymnasium
.venv/bin/python -c "import nle, gymnasium; print('ok', nle.__version__)"
```

Run with `./start_game_mac.sh` and choose through the IPC prompt, or pass any valid
character explicitly, such as `.venv/bin/python play.py bar-hum-mal-neu`.
`play.py` needs the venv (nle); `agent_helper.py` is pure /tmp-file IPC and runs
under any python3. play.py talks only via `/tmp` files, so no tmux is required —
launch it in the background directly.

**macOS env check (run before every session):** `.venv/bin/python -c "import nle"`.
The `.venv` is git-ignored and **can go missing** (disk cleanup) — if it's absent or
the import fails, re-run the one-time build above (recompiles NetHack from source,
~3–5 min) **in the background**, then `rm -f /tmp/nethack_*` to clear stale IPC and
launch. Build needs `export PATH=".../bison/bin:.../flex/bin:$PATH"` and the
`CFLAGS` line, or the NetHack C build fails.
