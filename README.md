<div align="center">

# 💧 Ariston Deos

**Control an Ariston Deos 16S NET dehumidifier from Home Assistant through the Ariston Clima cloud**

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Home Assistant](https://img.shields.io/badge/Home_Assistant-2026.9-41BDF5?logo=homeassistant&logoColor=white)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://hacs.xyz)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

> **Untested against the live cloud.** Nothing here has yet talked to a real Ariston Clima
> account or a real Deos. Run the [probe](#-usage) first: it tells you whether this is worth
> installing.

## 💡 Why it exists

HA Core's Midea integration fails for this device. Its Ariston Clima login works, but the
token and key call (`/v1/iot/secure/getToken` on `mapp.appsmb.com`, the US server) answers
code 9999 "system error", so local control is impossible. This integration controls the
dehumidifier through the cloud instead, using the
[`midea-beautiful-air`](https://pypi.org/project/midea-beautiful-air/) library (pinned in
`manifest.json`).

First hypothesis to test: the cloud region. The library lists a US server and an EU server
for Ariston Clima, and the house is in Scotland.

---

## ✨ Features

| | Feature | What it does |
|---|---|---|
| 🩺 | Probe script | Logs in on the EU then the US server, lists appliances, asks for the local token and key, sends one status query, and prints a verdict. Read-only |
| ☁️ | Cloud integration | A Home Assistant integration, domain `ariston_deos`, that polls the cloud (`iot_class` is `cloud_polling`) |

What the integration exposes as entities is not documented here until it has run against a real device.

---

## 🚀 Quick Start

You need Home Assistant 2026.9 or newer and your Ariston Clima app login.

1. **Run the probe** (below). It costs nothing and changes nothing.
2. **Install manually:** copy `custom_components/ariston_deos/` into `config/custom_components/` and restart Home Assistant.
3. **Add it:** **Settings, Devices and services, Add integration, Ariston Deos.**

The repository is private and HACS cannot install from a private repository, so manual copy is the only route until it is public.

---

## 📖 Usage

### The probe

```bash
pip install midea-beautiful-air        # the probe's only dependency
export ARISTON_EMAIL=you@example.com   # or leave unset: the prompt is hidden
export ARISTON_PASSWORD=...            # or leave unset: the prompt is hidden
python3 scripts/probe.py               # add --region EU or --region US for one server
python3 scripts/probe.py --save-keys ./deos.keys   # also keep the token and key
```

The login never goes on the command line, on screen or onto disk. Unset variables are asked for at hidden prompts (email and password), and errors print only the exception class and a numeric code. `--save-keys` writes a new mode 600 file, refuses symlinks, and refuses an existing file unless you add `--force`. The probe never sends a
set command. It runs these steps for the EU server, then the US server, one line each with
PASS or FAIL and the reason:

| Step | What it does |
|---|---|
| Login | `connect_to_cloud` with the "Ariston Clima EU" or "Ariston Clima" app profile |
| Appliances | Lists type, name and the id masked to its last 4 characters; marks dehumidifiers (type `0xA1`) |
| Local token | Asks for the token and key the way the library does (udp id from the appliance id, little-endian then big-endian). Reports only whether they came back and their lengths. With `--save-keys PATH` writes them to PATH with mode 600 and prints the path |
| Cloud status | One status query through `appliance_transparent_send`; prints power, mode (raw number), humidity, target and tank |

Errors print the library's error code, never a credential.

### Reading the verdict

| Verdict line | What to do |
|---|---|
| Login works on EU (or US) | That region is the one to use |
| Local token route WORKS | Use HA Core Midea with manual token and key from the `--save-keys` file; delete the file after |
| Local token route FAILS | Local control is out; use this integration's cloud path |
| Cloud status WORKS | The cloud path can read the device; install the integration |
| No region accepted the login | Check the email and password in the Ariston Clima app |

The probe exits 0 if the token or the status worked, 1 if neither did, 2 if the library is missing.

---

## 🗺️ How the cloud path works

Every read and command goes from Home Assistant to the Midea cloud and back to the device.
Details, and what comes from the library's source, are in [docs/how-it-works.md](docs/how-it-works.md). Limits:

- It needs the internet and the Midea servers up.
- It polls, so changes appear on the next poll (default 300 seconds, range 60 to 900).
- The API is unofficial: if Midea changes it, this breaks until the library catches up.

---

## 📁 Repo structure

```text
Ariston-Deos-Home-Assistant/
├── custom_components/
│   └── ariston_deos/       # 🧩 the integration
├── tests/                  # 🧪 integration tests
├── scripts/
│   ├── probe.py            # 🩺 read-only cloud diagnostic
│   └── test_probe.py       # 🧪 unit tests of the probe's pure parts
├── docs/
│   └── how-it-works.md     # 📚 routes, region hypothesis, limits
├── .env.example            # ⚙️ the probe's two optional variables
├── hacs.json  pyproject.toml  .gitignore
└── AGENTS.md  CHANGELOG.md  LICENSE  README.md  SECURITY.md
```

---

## 🧪 Testing

```bash
python3 -m unittest scripts/test_probe.py
```

Covers the probe's id masking, appliance-type matching, udp id derivation, error text,
verdict logic and the mode of the key file. The integration's own tests live in `tests/`.

---

## 🔒 Security

The login stays in the Home Assistant config entry and goes only to the Midea cloud
servers. See [SECURITY.md](SECURITY.md).

---

## 📄 License

MIT, see [LICENSE](LICENSE). Not affiliated with Ariston or Midea; their names are used only to say what this works with.

---

<p align="center"><sub>Made with ❤️ by <a href="https://github.com/CaputoDavide93">Davide Caputo</a></sub></p>
