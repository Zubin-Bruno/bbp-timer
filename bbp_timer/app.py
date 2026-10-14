"""Ventana principal: temporizador (fase 1) -> alarma -> cronómetro (fase 2)."""
import ctypes
import ctypes.wintypes
import math
import os
import re
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

import config
import sound
from volume import VolumeBooster

IDLE, PHASE1, PHASE2 = "idle", "phase1", "phase2"

FONT = "Consolas"
BG = "#000000"
FG = "#e6e6e6"
MUTED = "#8a8a8a"
FIELD = "#1a1a1a"
BUTTON = "#1e1e1e"
ACTIVE = "#333333"
ERROR = "#ff5252"
COLORS = {  # (fondo, texto) del bloque del reloj
    "idle": (BG, "#bfbfbf"),
    "phase1": (BG, "#ff9f1c"),
    "paused": (BG, "#a07a40"),
    "phase2": (BG, "#3ddc84"),
    "alarm": (BG, "#ff3b3b"),
}
# (texto vista completa, texto vista mini)
PHASE_TEXT = {
    "idle": ("LISTO", "LISTO"),
    "phase1": ("FASE 1 · TEMPORIZADOR", "FASE 1"),
    "paused": ("PAUSADO", "PAUSADO"),
    "phase2": ("FASE 2 · CRONÓMETRO", "FASE 2"),
}
SHORTCUTS = "Atajos: Espacio iniciar/pausar · R reiniciar · Esc silenciar · M mini · T siempre encima"


def fmt_time(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_num(value):
    return f"{value:g}"


def parse_num(text, field, integer=False):
    t = text.strip().replace(",", ".")
    if not t:
        return 0
    try:
        value = int(t) if integer else float(t)
    except ValueError:
        raise ValueError(f"{field}: valor inválido") from None
    if value < 0:
        raise ValueError(f"{field}: no puede ser negativo")
    return value


def on_screen(x, y):
    try:
        point = ctypes.wintypes.POINT(x + 40, y + 20)
        return bool(ctypes.windll.user32.MonitorFromPoint(point, 0))  # 0 = MONITOR_DEFAULTTONULL
    except Exception:
        return True


class Display:
    """Bloque coloreado con fase, tiempo, GAS y AIRE."""

    def __init__(self, parent, compact):
        time_size, value_size, caption_size = (30, 18, 8) if compact else (48, 28, 10)
        self.compact = compact
        self.frame = tk.Frame(parent, padx=10, pady=4 if compact else 10)
        self.phase = tk.Label(self.frame, font=(FONT, caption_size, "bold"))
        self.phase.pack()
        self.time = tk.Label(self.frame, font=(FONT, time_size, "bold"))
        self.time.pack()
        row = tk.Frame(self.frame)
        row.pack(fill="x")
        self.widgets = [self.frame, self.phase, self.time, row]
        self.values = {}
        for col, key, caption in ((0, "gas", "GAS"), (1, "air", "AIRE")):
            row.columnconfigure(col, weight=1, uniform="values")
            cell = tk.Frame(row)
            cell.grid(row=0, column=col, sticky="nsew")
            cap = tk.Label(cell, text=caption, font=(FONT, caption_size, "bold"))
            cap.pack()
            val = tk.Label(cell, font=(FONT, value_size, "bold"))
            val.pack()
            self.values[key] = val
            self.widgets += [cell, cap, val]
        self._last = None

    def bind_all_widgets(self, sequence, func):
        for w in self.widgets:
            w.bind(sequence, func)

    def set(self, phase, time_text, gas, air, bg, fg):
        state = (phase, time_text, gas, air, bg, fg)
        if state == self._last:
            return
        self._last = state
        for w in self.widgets:
            w.configure(bg=bg)
            if isinstance(w, tk.Label):
                w.configure(fg=fg)
        self.phase.configure(text=PHASE_TEXT[phase][1 if self.compact else 0])
        self.time.configure(text=time_text)
        self.values["gas"].configure(text=gas)
        self.values["air"].configure(text=air)


class App:
    def __init__(self):
        self.cfg = config.load()
        self.root = tk.Tk()
        self.root.title("BBP Timer")
        self._apply_theme()
        self.player = sound.AlarmPlayer()
        self.volume = VolumeBooster()

        self.state = IDLE
        self.paused = False
        self.phase1_end = 0.0
        self.remaining = 0.0
        self.phase2_start = 0.0
        self.alert_fired = False
        self.alarm_active = False
        self.run_values = None  # copia del perfil al iniciar fase 1
        self._alarm_after = None
        self._save_after = None
        self._loading = False

        self.profile = self._find_profile(self.cfg["last_profile"]) or self.cfg["profiles"][0]
        self._build_vars()
        self._build_full()
        self._build_mini()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.attributes("-topmost", self.cfg["always_on_top"])
        self._update_sound_label()
        self._load_profile(self.profile)
        self._apply_mode(self.cfg["mini_mode"], initial=True)
        self._refresh_buttons()
        self.root.update_idletasks()
        self._dark_titlebar()
        self._tick()

    def run(self):
        self.root.mainloop()

    # ---------- construcción de la UI ----------

    def _apply_theme(self):
        r = self.root
        for name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont", "TkHeadingFont",
                     "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(family=FONT)
            except tk.TclError:
                pass
        r.configure(bg=BG)
        for pattern, value in (
            ("*Background", BG), ("*Foreground", FG),
            ("*activeBackground", ACTIVE), ("*activeForeground", FG),
            ("*disabledForeground", "#555555"), ("*selectColor", FIELD),
            ("*highlightBackground", BG), ("*highlightColor", MUTED),
            ("*insertBackground", FG), ("*selectBackground", ACTIVE), ("*selectForeground", FG),
            ("*Entry.Background", FIELD), ("*Entry.relief", "flat"),
            ("*Button.Background", BUTTON), ("*Button.relief", "flat"),
            ("*TCombobox*Listbox.background", FIELD), ("*TCombobox*Listbox.foreground", FG),
            ("*TCombobox*Listbox.selectBackground", ACTIVE), ("*TCombobox*Listbox.font", (FONT, 9)),
        ):
            r.option_add(pattern, value)

        style = ttk.Style(r)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=FIELD, background=BUTTON, foreground=FG,
                        arrowcolor=FG, bordercolor=ACTIVE, lightcolor=FIELD, darkcolor=FIELD)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])

    def _dark_titlebar(self):
        """Barra de título oscura (Windows 10 20H1+ / 11). Requiere que la ventana ya exista."""
        try:
            hwnd = int(self.root.wm_frame(), 16)
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
        except Exception:
            pass

    def _build_vars(self):
        self.v = {k: tk.StringVar() for k in ("p1_min", "p1_sec", "gas1", "air1", "gas2", "air2", "al_min", "al_sec")}
        for var in self.v.values():
            var.trace_add("write", self._on_form_change)

        c = self.cfg
        self.alarm_mode = tk.StringVar(value=c["alarm_mode"])
        self.alarm_seconds = tk.StringVar(value=str(c["alarm_seconds"]))
        self.raise_volume = tk.BooleanVar(value=c["raise_volume"])
        self.target_volume = tk.StringVar(value=str(c["target_volume"]))
        self.always_on_top = tk.BooleanVar(value=c["always_on_top"])
        for var in (self.alarm_mode, self.alarm_seconds, self.raise_volume, self.target_volume, self.always_on_top):
            var.trace_add("write", self._on_settings_change)

        self.profile_name = tk.StringVar()
        self.sound_choice = tk.StringVar()
        self.error = tk.StringVar()

    def _button(self, parent, text, command, **kw):
        return tk.Button(parent, text=text, command=command, takefocus=0, **kw)

    def _entry(self, parent, var, width=6):
        return tk.Entry(parent, textvariable=var, width=width, justify="center")

    def _build_full(self):
        f = self.full_frame = tk.Frame(self.root)
        self.full_display = Display(f, compact=False)
        self.full_display.frame.pack(fill="x")

        btns = tk.Frame(f)
        btns.pack(fill="x", padx=8, pady=6)
        self.btn_start = self._button(btns, "▶ Iniciar", self.toggle_start, width=10)
        self.btn_start.pack(side="left", fill="x", expand=True)
        for text, cmd in (("⟲ Reiniciar", self.restart), ("■ Detener", self.stop),
                          ("Silenciar", self.silence), ("Mini", self.toggle_mini)):
            self._button(btns, text, cmd).pack(side="left", fill="x", expand=True, padx=(4, 0))

        tk.Label(f, textvariable=self.error, fg=ERROR, wraplength=360, justify="left").pack(fill="x", padx=8)

        body = tk.Frame(f)
        body.pack(fill="both", padx=8, pady=(0, 8))

        lf = tk.LabelFrame(body, text="Perfil", padx=6, pady=4)
        lf.pack(fill="x", pady=3)
        self.profile_combo = ttk.Combobox(lf, textvariable=self.profile_name, state="readonly", width=16)
        self.profile_combo.pack(side="left", fill="x", expand=True)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        for text, cmd in (("Nuevo", self._new_profile), ("Renombrar", self._rename_profile),
                          ("Eliminar", self._delete_profile)):
            self._button(lf, text, cmd).pack(side="left", padx=(4, 0))

        lf1 = tk.LabelFrame(body, text="Fase 1 · Temporizador", padx=6, pady=4)
        lf1.pack(fill="x", pady=3)
        tk.Label(lf1, text="Tiempo").grid(row=0, column=0, sticky="w")
        self._entry(lf1, self.v["p1_min"], 4).grid(row=0, column=1)
        tk.Label(lf1, text=":").grid(row=0, column=2)
        self._entry(lf1, self.v["p1_sec"], 4).grid(row=0, column=3)
        tk.Label(lf1, text="(mm:ss)", fg=MUTED).grid(row=0, column=4, sticky="w", padx=4)
        tk.Label(lf1, text="Gas").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._entry(lf1, self.v["gas1"]).grid(row=1, column=1, columnspan=3, sticky="we", pady=(4, 0))
        tk.Label(lf1, text="Aire").grid(row=1, column=4, sticky="e", padx=(8, 4), pady=(4, 0))
        self._entry(lf1, self.v["air1"]).grid(row=1, column=5, pady=(4, 0))

        lf2 = tk.LabelFrame(body, text="Fase 2 · Cronómetro", padx=6, pady=4)
        lf2.pack(fill="x", pady=3)
        tk.Label(lf2, text="Gas").grid(row=0, column=0, sticky="w")
        self._entry(lf2, self.v["gas2"]).grid(row=0, column=1, columnspan=3, sticky="we")
        tk.Label(lf2, text="Aire").grid(row=0, column=4, sticky="e", padx=(8, 4))
        self._entry(lf2, self.v["air2"]).grid(row=0, column=5)
        tk.Label(lf2, text="Aviso a").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._entry(lf2, self.v["al_min"], 4).grid(row=1, column=1, pady=(4, 0))
        tk.Label(lf2, text=":").grid(row=1, column=2, pady=(4, 0))
        self._entry(lf2, self.v["al_sec"], 4).grid(row=1, column=3, pady=(4, 0))
        tk.Label(lf2, text="(00:00 = sin aviso)", fg=MUTED).grid(
            row=1, column=4, columnspan=2, sticky="w", padx=4, pady=(4, 0))

        lfa = tk.LabelFrame(body, text="Alarma", padx=6, pady=4)
        lfa.pack(fill="x", pady=3)
        tk.Radiobutton(lfa, text="Hasta silenciar", variable=self.alarm_mode, value="until_silenced",
                       takefocus=0).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Radiobutton(lfa, text="Durante", variable=self.alarm_mode, value="seconds",
                       takefocus=0).grid(row=1, column=0, sticky="w")
        self._entry(lfa, self.alarm_seconds, 4).grid(row=1, column=1, sticky="w")
        tk.Label(lfa, text="segundos").grid(row=1, column=2, sticky="w", padx=4)

        snd = tk.Frame(lfa)
        snd.grid(row=2, column=0, columnspan=3, sticky="we", pady=(4, 0))
        tk.Label(snd, text="Sonido:").pack(side="left")
        self.sound_combo = ttk.Combobox(snd, textvariable=self.sound_choice, state="readonly", width=24)
        self.sound_combo.pack(side="left", padx=4)
        self.sound_combo.bind("<<ComboboxSelected>>", self._on_sound_selected)
        snd_btns = tk.Frame(lfa)
        snd_btns.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))
        for text, cmd in (("Elegir .wav…", self._choose_sound), ("Probar alarma", self._test_alarm)):
            self._button(snd_btns, text, cmd).pack(side="left", padx=(0, 4))

        vol = tk.Frame(lfa)
        vol.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        tk.Checkbutton(vol, text="Subir volumen de Windows a", variable=self.raise_volume,
                       takefocus=0).pack(side="left")
        self._entry(vol, self.target_volume, 4).pack(side="left")
        tk.Label(vol, text="%").pack(side="left", padx=2)

        tk.Checkbutton(body, text="Siempre encima", variable=self.always_on_top,
                       takefocus=0).pack(anchor="w", pady=(4, 0))
        tk.Label(body, text=SHORTCUTS, fg=MUTED, wraplength=360, justify="left").pack(anchor="w")

        self.full_display.bind_all_widgets("<Double-Button-1>", lambda e: self.toggle_mini())

    def _build_mini(self):
        f = self.mini_frame = tk.Frame(self.root)
        self.mini_display = Display(f, compact=True)
        self.mini_display.frame.pack(fill="both", expand=True)
        btns = tk.Frame(f)
        btns.pack(fill="x")
        self.mini_btn_start = self._button(btns, "▶", self.toggle_start, width=3)
        self.mini_btn_start.pack(side="left", fill="x", expand=True)
        for text, cmd in (("⟲", self.restart), ("■", self.stop), ("Silenciar", self.silence), ("⤢", self.toggle_mini)):
            self._button(btns, text, cmd).pack(side="left", fill="x", expand=True)
        self.mini_display.bind_all_widgets("<Double-Button-1>", lambda e: self.toggle_mini())

    def _bind_keys(self):
        def guarded(func):
            def handler(event):
                if isinstance(event.widget, (tk.Entry, ttk.Entry)):  # escribiendo en un campo
                    return None
                func()
                return "break"
            return handler

        r = self.root
        r.bind("<space>", guarded(self.toggle_start))
        for key, func in (("r", self.restart), ("m", self.toggle_mini), ("t", self._toggle_topmost)):
            r.bind(f"<KeyPress-{key}>", guarded(func))
            r.bind(f"<KeyPress-{key.upper()}>", guarded(func))
        r.bind("<Escape>", lambda e: self.silence())
        r.bind("<Return>", lambda e: r.focus_set())
        # Clic fuera de un campo: sacar el foco para que funcionen los atajos.
        r.bind("<Button-1>", lambda e: None if isinstance(e.widget, (tk.Entry, ttk.Entry)) else r.focus_set())

    # ---------- perfiles y formulario ----------

    def _find_profile(self, name):
        return next((p for p in self.cfg["profiles"] if p["name"] == name), None)

    def _read_form(self):
        g = lambda key: self.v[key].get()
        p1 = (parse_num(g("p1_min"), "Minutos fase 1", True) * 60
              + parse_num(g("p1_sec"), "Segundos fase 1", True))
        if p1 <= 0:
            raise ValueError("El temporizador de fase 1 debe ser mayor a 0")
        return {
            "phase1_seconds": p1,
            "gas1": parse_num(g("gas1"), "Gas fase 1"),
            "air1": parse_num(g("air1"), "Aire fase 1"),
            "gas2": parse_num(g("gas2"), "Gas fase 2"),
            "air2": parse_num(g("air2"), "Aire fase 2"),
            "phase2_alert_seconds": (parse_num(g("al_min"), "Minutos aviso", True) * 60
                                     + parse_num(g("al_sec"), "Segundos aviso", True)),
        }

    def _on_form_change(self, *_):
        if self._loading:
            return
        try:
            values = self._read_form()
        except ValueError as e:
            self.error.set(str(e))
            return
        self.error.set("")
        self.profile.update(values)
        self._schedule_save()

    def _load_profile(self, profile):
        self.profile = profile
        self._loading = True
        try:
            m, s = divmod(int(profile["phase1_seconds"]), 60)
            am, asec = divmod(int(profile["phase2_alert_seconds"]), 60)
            for key, value in (("p1_min", m), ("p1_sec", f"{s:02d}"), ("al_min", am), ("al_sec", f"{asec:02d}"),
                               ("gas1", fmt_num(profile["gas1"])), ("air1", fmt_num(profile["air1"])),
                               ("gas2", fmt_num(profile["gas2"])), ("air2", fmt_num(profile["air2"]))):
                self.v[key].set(str(value))
        finally:
            self._loading = False
        self.cfg["last_profile"] = profile["name"]
        self.profile_combo["values"] = [p["name"] for p in self.cfg["profiles"]]
        self.profile_name.set(profile["name"])
        self.error.set("")
        self._schedule_save()

    def _on_profile_selected(self, _event):
        profile = self._find_profile(self.profile_name.get())
        if profile:
            self._load_profile(profile)
        self.root.focus_set()

    def _ask_name(self, title, initial=""):
        name = simpledialog.askstring(title, "Nombre del perfil:", initialvalue=initial, parent=self.root)
        name = (name or "").strip()
        if not name or name == initial:
            return None
        if self._find_profile(name):
            messagebox.showerror(title, f"Ya existe un perfil llamado «{name}».", parent=self.root)
            return None
        return name

    def _new_profile(self):
        name = self._ask_name("Nuevo perfil")
        if name:
            profile = config.new_profile(name, base=self.profile)  # parte de los valores actuales
            self.cfg["profiles"].append(profile)
            self._load_profile(profile)

    def _rename_profile(self):
        name = self._ask_name("Renombrar perfil", self.profile["name"])
        if name:
            self.profile["name"] = name
            self._load_profile(self.profile)

    def _delete_profile(self):
        if len(self.cfg["profiles"]) == 1:
            messagebox.showinfo("Eliminar perfil", "Debe quedar al menos un perfil.", parent=self.root)
            return
        if not messagebox.askyesno("Eliminar perfil", f"¿Eliminar el perfil «{self.profile['name']}»?",
                                   parent=self.root):
            return
        self.cfg["profiles"].remove(self.profile)
        self._load_profile(self.cfg["profiles"][0])

    # ---------- ajustes ----------

    def _on_settings_change(self, *_):
        c = self.cfg
        c["alarm_mode"] = self.alarm_mode.get()
        c["raise_volume"] = self.raise_volume.get()
        c["always_on_top"] = self.always_on_top.get()
        self.root.attributes("-topmost", c["always_on_top"])
        try:
            seconds = parse_num(self.alarm_seconds.get(), "Segundos de alarma", True)
            if seconds <= 0:
                raise ValueError("Segundos de alarma: debe ser mayor a 0")
            volume = parse_num(self.target_volume.get(), "Volumen", True)
            if not 1 <= volume <= 100:
                raise ValueError("Volumen: debe estar entre 1 y 100")
        except ValueError as e:
            self.error.set(str(e))
        else:
            self.error.set("")
            c["alarm_seconds"] = seconds
            c["target_volume"] = volume
        self._schedule_save()

    def _toggle_topmost(self):
        self.always_on_top.set(not self.always_on_top.get())

    def _sound_options(self):
        path = self.cfg["sound_file"]
        custom = f"Archivo: {os.path.basename(path)}" if path else "Archivo propio…"
        return sound.available_sounds() + [("custom", custom)]

    def _sound_path(self):
        return sound.resolve(self.cfg["sound"], self.cfg["sound_file"])

    def _update_sound_label(self):
        options = self._sound_options()
        self.sound_combo["values"] = [label for _, label in options]
        self.sound_choice.set(dict(options).get(self.cfg["sound"], options[0][1]))

    def _on_sound_selected(self, _event):
        self.root.focus_set()
        choice = self.sound_choice.get()
        sound_id = next(sid for sid, label in self._sound_options() if label == choice)
        if sound_id == "custom" and not self.cfg["sound_file"]:
            self._choose_sound()
            return
        self.cfg["sound"] = sound_id
        self._update_sound_label()
        self._schedule_save()
        self._preview_sound()

    def _preview_sound(self):
        if not self.alarm_active:
            self.player.preview(self._sound_path())

    def _choose_sound(self):
        path = filedialog.askopenfilename(parent=self.root, title="Elegir sonido de alarma",
                                          filetypes=[("Audio WAV", "*.wav")])
        if path and not sound.is_valid_wav(path):
            messagebox.showerror("Sonido", "Ese archivo WAV no es compatible. Usa un WAV PCM de 16 bits.",
                                 parent=self.root)
            path = None
        if path:
            self.cfg["sound_file"] = path
            self.cfg["sound"] = "custom"
            self._schedule_save()
        self._update_sound_label()
        if path:
            self._preview_sound()

    def _test_alarm(self):
        if self.alarm_active:
            self.silence()
        else:
            self._start_alarm()

    # ---------- temporizador ----------

    def toggle_start(self):
        if self.state == IDLE:
            self._start_phase1()
        elif self.state == PHASE1:
            now = time.monotonic()
            if self.paused:
                self.phase1_end = now + self.remaining
                self.paused = False
            else:
                self.remaining = max(0.0, self.phase1_end - now)
                self.paused = True
        self._refresh_buttons()

    def restart(self):
        self.silence()
        self._start_phase1()

    def stop(self):
        self.silence()
        self.state = IDLE
        self.paused = False
        self._refresh_buttons()

    def _start_phase1(self):
        try:
            values = self._read_form()
        except ValueError as e:
            self.error.set(str(e))
            if self.cfg["mini_mode"]:
                self.toggle_mini()  # mostrar el error
            self.root.bell()
            return
        self.profile.update(values)
        self._schedule_save()
        self.run_values = dict(self.profile)
        self.state = PHASE1
        self.paused = False
        self.phase1_end = time.monotonic() + self.run_values["phase1_seconds"]
        self._refresh_buttons()

    def _enter_phase2(self, start):
        self.state = PHASE2
        self.phase2_start = start  # justo cuando el temporizador llegó a 0
        self.alert_fired = False
        self._start_alarm()
        self._refresh_buttons()

    def _start_alarm(self):
        self.silence()
        if self.cfg["raise_volume"]:
            self.volume.boost(self.cfg["target_volume"])
        self.player.play(self._sound_path())
        self.alarm_active = True
        if self.cfg["alarm_mode"] == "seconds":
            self._alarm_after = self.root.after(int(self.cfg["alarm_seconds"] * 1000), self.silence)
        if self.root.state() == "iconic":
            self.root.deiconify()
        self.root.lift()

    def silence(self):
        if self._alarm_after:
            self.root.after_cancel(self._alarm_after)
            self._alarm_after = None
        if self.alarm_active:
            self.player.stop()
            self.volume.restore()
            self.alarm_active = False

    def _refresh_buttons(self):
        if self.state == IDLE:
            text, icon, state = "▶ Iniciar", "▶", "normal"
        elif self.state == PHASE1 and self.paused:
            text, icon, state = "▶ Reanudar", "▶", "normal"
        else:
            text, icon, state = "⏸ Pausar", "⏸", "normal" if self.state == PHASE1 else "disabled"
        self.btn_start.configure(text=text, state=state)
        self.mini_btn_start.configure(text=icon, state=state)

    def _tick(self):
        now = time.monotonic()
        if self.state == PHASE1 and not self.paused and now >= self.phase1_end:
            self._enter_phase2(self.phase1_end)
        if self.state == PHASE2:
            alert = self.run_values["phase2_alert_seconds"]
            if alert > 0 and not self.alert_fired and now - self.phase2_start >= alert:
                self.alert_fired = True
                self._start_alarm()
        self._render(now)
        self.root.after(50, self._tick)

    def _render(self, now):
        if self.state == IDLE:
            p = self.profile
            phase, t, gas, air = "idle", fmt_time(p["phase1_seconds"]), p["gas1"], p["air1"]
        elif self.state == PHASE1:
            remaining = self.remaining if self.paused else max(0.0, self.phase1_end - now)
            phase = "paused" if self.paused else "phase1"
            t, gas, air = fmt_time(math.ceil(remaining - 1e-9)), self.run_values["gas1"], self.run_values["air1"]
        else:
            phase = "phase2"
            t, gas, air = fmt_time(now - self.phase2_start), self.run_values["gas2"], self.run_values["air2"]

        color = phase
        if self.alarm_active and int(now * 2.5) % 2 == 0:
            color = "alarm"
        bg, fg = COLORS[color]
        for display in (self.full_display, self.mini_display):
            display.set(phase, t, fmt_num(gas), fmt_num(air), bg, fg)

    # ---------- ventana ----------

    def toggle_mini(self):
        self._apply_mode(not self.cfg["mini_mode"])

    def _remember_geometry(self):
        if self.root.state() != "normal":
            return
        m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", self.root.geometry())
        if not m:
            return
        w, h, x, y = map(int, m.groups())
        if self.cfg["mini_mode"]:
            self.cfg["geom_mini"] = [w, h, x, y]
        else:
            self.cfg["pos_full"] = [x, y]

    def _apply_mode(self, mini, initial=False):
        if not initial:
            self._remember_geometry()
        self.cfg["mini_mode"] = mini
        if mini:
            self.full_frame.pack_forget()
            self.mini_frame.pack(fill="both", expand=True)
            self.root.minsize(150, 100)
            self.root.geometry("")
            g = self.cfg["geom_mini"]
            if g and on_screen(g[2], g[3]):
                self.root.geometry(f"{g[0]}x{g[1]}+{g[2]}+{g[3]}")
        else:
            self.mini_frame.pack_forget()
            self.full_frame.pack(fill="both", expand=True)
            self.root.minsize(1, 1)
            self.root.geometry("")  # tamaño natural del contenido
            pos = self.cfg["pos_full"]
            if pos and on_screen(*pos):
                self.root.geometry(f"+{pos[0]}+{pos[1]}")
        self._schedule_save()

    # ---------- persistencia ----------

    def _schedule_save(self):
        if self._save_after:
            self.root.after_cancel(self._save_after)
        self._save_after = self.root.after(600, self._save_now)

    def _save_now(self):
        self._save_after = None
        try:
            config.save(self.cfg)
        except OSError as e:
            self.error.set(f"No se pudo guardar la configuración: {e}")

    def on_close(self):
        self.silence()
        self._remember_geometry()
        if self._save_after:
            self.root.after_cancel(self._save_after)
            self._save_after = None
        try:
            config.save(self.cfg)
        except OSError:
            pass
        self.root.destroy()
