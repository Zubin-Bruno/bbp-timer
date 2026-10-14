"""Sube el volumen maestro de Windows durante la alarma y luego lo restaura.

Usa pycaw si está instalado; si no, no hace nada.
"""


def _endpoint():
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        device = AudioUtilities.GetSpeakers()
        endpoint = getattr(device, "EndpointVolume", None)  # pycaw reciente
        if endpoint is None:
            iface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = cast(iface, POINTER(IAudioEndpointVolume))
        return endpoint
    except Exception:
        return None


class VolumeBooster:
    def __init__(self):
        self._saved = None  # (nivel 0..1, mute)

    def boost(self, percent):
        if self._saved is not None:
            return
        endpoint = _endpoint()
        if endpoint is None:
            return
        try:
            level = endpoint.GetMasterVolumeLevelScalar()
            mute = endpoint.GetMute()
            self._saved = (level, mute)
            endpoint.SetMute(0, None)
            endpoint.SetMasterVolumeLevelScalar(max(level, min(100, percent) / 100), None)
        except Exception:
            self._saved = None

    def restore(self):
        if self._saved is None:
            return
        level, mute = self._saved
        self._saved = None
        endpoint = _endpoint()
        if endpoint is None:
            return
        try:
            endpoint.SetMasterVolumeLevelScalar(level, None)
            endpoint.SetMute(mute, None)
        except Exception:
            pass
