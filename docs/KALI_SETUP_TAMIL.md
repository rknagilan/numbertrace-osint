# Kali Linux-ல் NumberTrace OSINT — படிப்படியான வழிகாட்டி (Tamil)

இந்த guide beginner-களுக்காக எழுதப்பட்டது. Commands, file names எல்லாம் English-லயே இருக்கும்;
அவற்றை **copy-paste** பண்ணுங்க. ஒவ்வொரு step-லயும்: விளக்கம் → command → எதிர்பார்க்கும் output →
சரியா நடந்ததா எப்படி check பண்றது → பொதுவான பிரச்சனைகள்.

> ⚠️ இந்த tool **உங்களுக்கு வந்த ஒரு call-ஐ** check பண்ண மட்டும். ஒருவரைத் தேட, track பண்ண
> பயன்படுத்தக் கூடாது. Result-கள் எல்லாம் "unverified" — உறுதியான அடையாளம் அல்ல.

---

## Phase 1 — Environment check (உங்க system எப்படி இருக்கு?)

**ஏன்?** Kali VM-லயா, நேரடியா install பண்ணியிருக்கீங்களா, CPU ARM-ஆ x86_64-ஆ என்று தெரிஞ்சா
பிரச்சனைகளை சீக்கிரம் தீர்க்கலாம்.

```bash
uname -m
```
- `x86_64` → சாதாரண Intel/AMD laptop அல்லது VM
- `aarch64` → ARM (பல Chromebook-கள்)

```bash
systemd-detect-virt
```
- `none` → நேரடியா install பண்ணியிருக்கீங்க
- `oracle` / `vmware` / `kvm` → VM-ல ஓடுது
- Chromebook-ல Linux container-ஆ இருந்தா `lxc` என்று வரலாம்

```bash
python3 --version
```
**எதிர்பார்ப்பு:** `Python 3.12.x` அல்லது `3.13.x`. 3.11 அல்லது அதற்கு கீழ இருந்தா →
`sudo apt update && sudo apt full-upgrade -y`

```bash
df -h ~
```
**குறைந்தது 300 MB free** இருக்கணும்.

---

## Phase 2 — System packages install

**ஏன் sudo?** `apt` system software install பண்ணும், அதனால இந்த ஒரு இடத்துல மட்டும் `sudo` (உங்க
password) தேவை. **`sudo pip` ஒருபோதும் பயன்படுத்த வேண்டாம்.**

```bash
sudo apt update && sudo apt install -y git python3 python3-venv
```
**சரியா?** கடைசியில `E:` என்று தொடங்கும் error இல்லைனா success.
**பிரச்சனை:** `Could not get lock` → வேற update ஓடிக்கிட்டு இருக்கு; 2 நிமிஷம் wait பண்ணி திரும்ப run பண்ணுங்க.

---

## Phase 3 — Project-ஐ clone பண்ணுங்க

```bash
cd ~
```
```bash
git clone https://github.com/<your-github-username>/numbertrace-osint.git
```
```bash
cd numbertrace-osint
```
**சரியா?** `ls` run பண்ணா `README.md  numbertrace  scripts ...` தெரியணும்.
**பிரச்சனை:** `Could not resolve host` → internet/DNS பிரச்சனை (Troubleshooting பார்க்கவும்).

---

## Phase 4 + 5 — Virtual environment + package install (ஒரே script)

**Virtual environment (venv) என்ன?** Project-க்கு மட்டும் தனி Python "பெட்டி". Kali-யோட system
Python-ஐ தொடாது, அதனால `externally-managed-environment` error வராது.

Light install (CLI மட்டும், குறைந்த RAM-க்கு சிறந்தது):
```bash
bash scripts/install_kali.sh
```
Dashboard-உம் வேணும்னா `--web`, tests run பண்ணணும்னா `--dev`:
```bash
bash scripts/install_kali.sh --dev
```
**எதிர்பார்ப்பு:**
```text
==> NumberTrace installer (arch: x86_64)
==> Python 3.13 OK
==> Creating virtual environment in .venv
==> Installing NumberTrace (light)
==> Created .env from .env.example ...
==> Done. Next steps:
```
இப்போ venv-ஐ activate பண்ணுங்க (ஒவ்வொரு புது terminal-லயும் இதை பண்ணணும்):
```bash
source .venv/bin/activate
```
**சரியா?** Prompt முன்னாடி `(.venv)` தெரியும்.

---

## Phase 6 — Doctor (எல்லாம் சரியா இருக்கா?)

```bash
numbertrace doctor
```
**எதிர்பார்ப்பு:** கடைசியில `All required checks passed.`
`FAIL` வந்தா அதுக்கு கீழே `fix ->` என்று ஒரு command இருக்கும்; அதை run பண்ணுங்க.
Internet இல்லைனா: `numbertrace doctor --offline`

---

## Phase 7 — Safe demo

```bash
numbertrace demo
```
இது **கற்பனை எண்** (`+1 415 555 0100`) மற்றும் **SYNTHETIC** (போலி) data பயன்படுத்துது. எந்த
உண்மையான நபரும் இதில் இல்லை.

Offline metadata check (internet தேவையில்லை):
```bash
numbertrace inspect --number '+94771234567' --offline
```
(இந்த எண் `phonenumbers` library-யோட example எண் — illustrative மட்டும்.)

Sri Lanka national format:
```bash
numbertrace normalize 0771234567 --country LK
```
Report save பண்ண:
```bash
numbertrace search --number '+94771234567' --offline --export
```
→ `reports/` folder-ல `.html` மற்றும் `.json` file-கள் வரும். HTML-ஐ browser-ல திறக்கலாம்:
```bash
xdg-open reports/
```

---

## Phase 8 — (விருப்பம்) Online search API

API key இல்லாமலும் tool வேலை செய்யும் — அப்போ **manual search links** காட்டும், நீங்களே click பண்ணலாம்.

Brave Search API key வேணும்னா:
1. https://api-dashboard.search.brave.com/ — account create பண்ணி key எடுங்க.
2. `.env` file-ஐ edit பண்ணுங்க:
```bash
nano .env
```
`NUMBERTRACE_BRAVE_API_KEY=` க்கு பிறகு key-ஐ paste பண்ணுங்க → `Ctrl+O`, `Enter`, `Ctrl+X`.
3. Check:
```bash
numbertrace providers
```
`brave_search` → `Configured: yes` என்று வரணும்.

⚠️ Key-ஐ யாரிடமும் share பண்ண வேண்டாம்; `.env` GitHub-க்கு போகாது (`.gitignore`-ல இருக்கு).
Google Custom Search API புதிய customers-க்கு மூடப்பட்டுவிட்டது (2027-01-01-ல் முழுசா நிற்கும்).

---

## Phase 9 — (விருப்பம்) Local dashboard

`--web` அல்லது `--dev` install தேவை.
```bash
numbertrace serve
```
Browser-ல திறங்க: http://127.0.0.1:8765 — இது உங்க computer-க்கு மட்டும் (network-க்கு expose ஆகாது).
Demo mode-ல பார்க்க: `numbertrace serve --demo`. நிறுத்த: `Ctrl+C`.

---

## Phase 10 — Tests run பண்ணுங்க

`--dev` install தேவை.
```bash
pytest
```
**எதிர்பார்ப்பு:** எல்லா tests-உம் pass ஆகும் (புள்ளிகள் `....` மட்டும், `F` இல்லை).
Lint + type check:
```bash
ruff check numbertrace tests && mypy
```

---

## Phase 11 — GitHub-க்கு commit / push

முதல் முறை மட்டும் உங்க பெயர் set பண்ணுங்க:
```bash
git config --global user.name "Your Name"
```
```bash
git config --global user.email "you@example.com"
```
மாற்றங்களை save பண்ணி push:
```bash
git add -A
```
```bash
git commit -m "Describe your change"
```
```bash
git push
```
Push-க்கு password கேட்டா, GitHub **Personal Access Token** பயன்படுத்தணும் (password வேலை செய்யாது)
அல்லது `gh auth login` பயன்படுத்துங்க.
⚠️ `git status`-ல `.env` தெரிஞ்சா commit பண்ண வேண்டாம்.

---

## Phase 12 — Update & troubleshoot

Update:
```bash
git pull
```
```bash
source .venv/bin/activate && pip install -e .
```
பிரச்சனைகள் → **[KALI_TROUBLESHOOTING.md](KALI_TROUBLESHOOTING.md)**.
Manual smoke test checklist → [SMOKE_TEST_KALI.md](SMOKE_TEST_KALI.md).
