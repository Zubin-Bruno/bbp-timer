"""Sonidos de alarma (Windows o pitido generado), normalizados al máximo y reproducidos con winsound."""
import array
import hashlib
import math
import os
import struct
import wave
import winsound

from config import APP_DIR

SOUNDS_DIR = os.path.join(APP_DIR, "sounds")
BEEP_PATH = os.path.join(SOUNDS_DIR, "beep_v1.wav")
MEDIA_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media")

# (id, etiqueta). Los ids Alarm/Ring son los sonidos que usa la app Reloj de Windows.
SOUNDS = (
    [(f"Alarm{i:02d}", f"Alarma {i}") for i in range(1, 11)]
    + [(f"Ring{i:02d}", f"Llamada {i}") for i in range(1, 11)]
    + [("beep", "Pitido agudo")]
)
DEFAULT_SOUND = "Alarm01"

_RATE = 44100
_TARGET_PEAK = 0.98


def _write_beep(path):
    samples = bytearray()

    def silence(seconds):
        samples.extend(b"\x00\x00" * int(_RATE * seconds))

    def beep(seconds, freq=2800):
        n = int(_RATE * seconds)
        fade = _RATE * 0.003
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            s = max(-1.0, min(1.0, 1.8 * math.sin(2 * math.pi * freq * i / _RATE)))
            samples.extend(struct.pack("<h", int(s * env * 32000)))

    for _ in range(4):
        beep(0.09)
        silence(0.05)
    silence(0.35)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes(bytes(samples))


def _beep():
    if not os.path.isfile(BEEP_PATH):
        _write_beep(BEEP_PATH)
    return BEEP_PATH


def _normalized(src):
    """Copia de `src` amplificada hasta el pico máximo (cacheada). Si no se puede, devuelve `src`."""
    try:
        st = os.stat(src)
        key = hashlib.md5(f"{os.path.abspath(src)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:12]
        dest = os.path.join(SOUNDS_DIR, f"{os.path.splitext(os.path.basename(src))[0]}_{key}.wav")
        if os.path.isfile(dest):
            return dest
        with wave.open(src, "rb") as w:
            if w.getsampwidth() != 2:
                return src
            params = w.getparams()
            data = array.array("h", w.readframes(w.getnframes()))
        peak = max((abs(s) for s in data), default=0)
        if peak == 0:
            return src
        gain = _TARGET_PEAK * 32767 / peak
        if gain > 1.05:
            data = array.array("h", (max(-32768, min(32767, int(s * gain))) for s in data))
        os.makedirs(SOUNDS_DIR, exist_ok=True)
        tmp = dest + ".tmp"
        with wave.open(tmp, "wb") as w:
            w.setparams(params)
            w.writeframes(data.tobytes())
        os.replace(tmp, dest)
        return dest
    except (OSError, wave.Error, EOFError):
        return src


def _windows_path(sound_id):
    return os.path.join(MEDIA_DIR, f"{sound_id}.wav")


def available_sounds():
    return [(sid, label) for sid, label in SOUNDS if sid == "beep" or os.path.isfile(_windows_path(sid))]


def resolve(sound_id, custom_file=None):
    """Ruta del WAV a reproducir para el sonido elegido (con fallback al pitido)."""
    if sound_id == "custom" and custom_file and os.path.isfile(custom_file):
        return _normalized(custom_file)
    if sound_id not in ("beep", "custom") and os.path.isfile(_windows_path(sound_id)):
        return _normalized(_windows_path(sound_id))
    return _beep()


def is_valid_wav(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() > 0
    except (wave.Error, EOFError, OSError):
        return False


class AlarmPlayer:
    _FLAGS = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT

    def play(self, path):
        """En bucle hasta stop()."""
        try:
            winsound.PlaySound(path, self._FLAGS | winsound.SND_LOOP)
        except RuntimeError:
            winsound.PlaySound(_beep(), self._FLAGS | winsound.SND_LOOP)

    def preview(self, path):
        """Una sola vez, para escuchar el sonido al elegirlo."""
        try:
            winsound.PlaySound(path, self._FLAGS)
        except RuntimeError:
            pass

    def stop(self):
        winsound.PlaySound(None, 0)
