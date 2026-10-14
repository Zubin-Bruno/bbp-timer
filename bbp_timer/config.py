"""Carga y guardado de perfiles y ajustes en %APPDATA%\\BBPTimer\\config.json."""
import copy
import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "BBPTimer")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_PROFILE = {
    "name": "Default",
    "phase1_seconds": 90,
    "gas1": 0.0,
    "air1": 0.0,
    "gas2": 0.0,
    "air2": 0.0,
    "phase2_alert_seconds": 0,  # 0 = sin aviso en fase 2
}

DEFAULTS = {
    "profiles": [DEFAULT_PROFILE],
    "last_profile": "Default",
    "alarm_mode": "until_silenced",  # o "seconds"
    "alarm_seconds": 5,
    "sound": "Alarm01",  # id de sound.SOUNDS o "custom"
    "sound_file": None,  # ruta del .wav propio (para "custom")
    "raise_volume": True,
    "target_volume": 100,
    "always_on_top": False,
    "mini_mode": False,
    "pos_full": None,  # [x, y]
    "geom_mini": None,  # [w, h, x, y]
}

_INT_FIELDS = ("phase1_seconds", "phase2_alert_seconds")
_FLOAT_FIELDS = ("gas1", "air1", "gas2", "air2")


def new_profile(name, base=None):
    profile = dict(base or DEFAULT_PROFILE)
    profile["name"] = name
    return profile


def _clean_profile(raw):
    if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
        return None
    profile = new_profile(str(raw["name"]).strip())
    for key in _INT_FIELDS:
        try:
            profile[key] = max(0, int(raw.get(key, profile[key])))
        except (TypeError, ValueError):
            pass
    for key in _FLOAT_FIELDS:
        try:
            profile[key] = max(0.0, float(raw.get(key, profile[key])))
        except (TypeError, ValueError):
            pass
    if profile["phase1_seconds"] <= 0:
        profile["phase1_seconds"] = DEFAULT_PROFILE["phase1_seconds"]
    return profile


def load():
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
            if "sound" not in data and data.get("sound_file"):  # config anterior con .wav propio
                cfg["sound"] = "custom"
    except (OSError, ValueError):
        pass

    profiles, names = [], set()
    for raw in cfg["profiles"] if isinstance(cfg["profiles"], list) else []:
        profile = _clean_profile(raw)
        if profile and profile["name"] not in names:
            names.add(profile["name"])
            profiles.append(profile)
    cfg["profiles"] = profiles or [new_profile("Default")]

    if cfg["alarm_mode"] not in ("until_silenced", "seconds"):
        cfg["alarm_mode"] = DEFAULTS["alarm_mode"]
    for key, lo, hi in (("alarm_seconds", 1, 3600), ("target_volume", 1, 100)):
        try:
            cfg[key] = min(hi, max(lo, int(cfg[key])))
        except (TypeError, ValueError):
            cfg[key] = DEFAULTS[key]
    for key in ("raise_volume", "always_on_top", "mini_mode"):
        cfg[key] = bool(cfg[key])
    if not isinstance(cfg["sound_file"], str) or not cfg["sound_file"]:
        cfg["sound_file"] = None
    if not isinstance(cfg["sound"], str) or (cfg["sound"] == "custom" and not cfg["sound_file"]):
        cfg["sound"] = DEFAULTS["sound"]
    return cfg


def save(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)
