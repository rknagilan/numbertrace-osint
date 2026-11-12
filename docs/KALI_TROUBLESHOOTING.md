# Kali Troubleshooting (English + தமிழ் குறிப்பு)

## `error: externally-managed-environment`
**Why:** Kali protects its system Python, so plain `pip install` is blocked.
**Fix:** use the venv. Do **not** use `--break-system-packages` or `sudo pip`.
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```
தமிழ்: system Python-ல install பண்ணாதீங்க — `.venv` activate பண்ணிட்டு install பண்ணுங்க.

## `The virtual environment was not created successfully because ensurepip is not available`
```bash
sudo apt install -y python3-venv
```
Then delete the broken venv and run the installer again:
```bash
rm -rf .venv && bash scripts/install_kali.sh
```

## `numbertrace: command not found`
The venv is not active. Run:
```bash
source .venv/bin/activate
```
Or call it directly: `.venv/bin/numbertrace doctor`.

## ARM (aarch64) Chromebook: wheels or build errors
All base dependencies are pure Python or have ARM64 wheels (pydantic-core). If pip tries to
compile something and fails:
```bash
pip install --upgrade pip
```
If it still fails, install the build tools (needs sudo once):
```bash
sudo apt install -y build-essential python3-dev
```
On low RAM, keep the **light** install (skip `--web` and `--dev`).

## SSL / certificate errors (`CERTIFICATE_VERIFY_FAILED`)
```bash
sudo apt install -y ca-certificates && sudo update-ca-certificates
```
Check the system clock (a wrong date breaks TLS): `date`. To fix it: `sudo timedatectl set-ntp true`.
Never disable TLS verification.

## DNS / network (`Could not resolve host`, doctor shows `Network/DNS WARN`)
```bash
ping -c 2 1.1.1.1
```
```bash
cat /etc/resolv.conf
```
If ping works but names don't resolve, your DNS is broken. In a VM, switch the network to NAT. Offline mode
(`--offline`) works without internet anyway.

## `Permission denied`
- Script: run it with `bash scripts/install_kali.sh` (no execute bit needed).
- Files owned by root (because you used sudo earlier): `sudo chown -R "$USER":"$USER" ~/numbertrace-osint`
- Never run NumberTrace as root.

## Low disk space (`No space left on device`)
```bash
df -h ~
```
```bash
sudo apt clean && rm -rf ~/.cache/pip
```
Use the light install. Delete old reports: `rm -rf reports/`.

## Dashboard: `Web extra is not installed`
```bash
pip install -e ".[web]"
```

## `Refusing to bind a non-local address`
This is intentional. The dashboard is localhost-only. Use the default `numbertrace serve`.

## Brave provider shows `provider rejected the API key (HTTP 401)`
The key in `.env` is wrong or expired. `HTTP 429` means you ran out of quota; wait or change your plan.
