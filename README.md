# lhwmonitor

Hardware Information and Monitor Tool for Linux

**Version: v0.1.1**

Linux-only desktop app with an **Info** tab (static hardware identification, CPU-Z–style) and a **Monitor** tab (live sensors and usage, HWMonitor–style).

## Requirements

- Python 3.11+
- PySide6 (installed automatically via pip)
- Optional but recommended: **lm-sensors** (`sensors`, `sensors-detect`) for temperature and fan data
- Optional: **dmidecode** (often needs root) for motherboard/BIOS strings on the Info tab
- **pciutils** (`lspci`) for GPU listing

## Install (development)

On some Linux distributions (notably Debian and Ubuntu), the `venv` module is shipped separately. If `python3 -m venv` fails (often mentioning `ensurepip` or `venv`), install **python3-venv** first—for example: `sudo apt install python3-venv`.

```bash
cd lhwmonitor
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
lhwmonitor
# or
python -m lhwmonitor
```

### Running with `sudo` (DMI and PATH)

Motherboard/BIOS details from **dmidecode** usually require root. If you run `sudo lhwmonitor` and see **command not found**, `sudo` resets `PATH` and no longer sees a venv or `~/.local/bin` install. Use either:

```bash
sudo env PATH="$PATH" lhwmonitor
# or
sudo "$(command -v lhwmonitor)"
```

## GitHub

Create a new repository on GitHub, then:

```bash
git init
git add .
git commit -m "Initial release v0.1.0"
git branch -M main
git tag -a v0.1.0 -m "v0.1.0 — first public release"
git remote add origin https://github.com/YOUR_USER/lhwmonitor.git
git push -u origin main
git push origin v0.1.0
```

On the GitHub repo page, under **About → Topics**, you can add tags for discoverability, for example: `linux`, `python`, `pyside6`, `qt`, `hardware-monitoring`, `system-monitor`, `lm-sensors`, `sensors`.

## License

Add a `LICENSE` file of your choice when you publish the repo.
