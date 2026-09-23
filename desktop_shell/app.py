# desktop-shell/app.py
#
# WHAT: The Tkinter desktop window â€” a THIN layer over ShellController.
# WHY:  P5.2. All behavior lives in controller.py so this file only maps
#       FlowResults to widgets/dialogs. Import of tkinter is deferred to
#       main() so headless test runs never need a display.
# BREAKS IF DELETED: There is no graphical entry point; engines remain
#       reachable only from code.

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PyInstaller ships every packaged module under its importable name inside
# the PYZ archive â€” the hyphenated source dirs do not exist on disk there.
# In a frozen build the source aliases below would clobber the real
# `desktop_shell`/`model_layer`/`engines` packages with paths pointing at
# loose files that PyInstaller never extracts, breaking every lazy import
# ("No module named 'desktop_shell.controller'"). Only alias from a
# checked-out source tree.
_FROZEN = bool(getattr(sys, "frozen", False))


def _install_source_aliases() -> None:
    """Mirror conftest.py: engines live in HYPHENATED dirs that cannot be
    imported directly; register underscore-named package aliases so a
    plain `python app.py` works exactly like the test suite and the
    PyInstaller build (which stages real packages at build time)."""
    def alias(dotted: str, real: Path) -> None:
        if dotted not in sys.modules:
            module = types.ModuleType(dotted)
            module.__path__ = [str(real)]
            sys.modules[dotted] = module

    alias("engines", _ROOT / "engines")
    alias("model_layer", _ROOT / "model-layer")
    alias("desktop_shell", _ROOT / "desktop_shell")
    for dir_name, mod_name in [
        ("audio-engine", "audio_engine"),
        ("career-engine", "career_engine"),
        ("export-engine", "export_engine"),
        ("journey-core", "journey_core"),
        ("language-lab", "language_lab"),
        ("playground-bridge", "playground_bridge"),
    ]:
        alias(f"engines.{mod_name}", _ROOT / "engines" / dir_name)


if not _FROZEN:
    _install_source_aliases()

ERROR_TITLES = {
    "no_model": "LM Studio not reachable",
    "bad_output": "Model output rejected",
    "input": "Check your input",
    "connector": "Generation service failed",
    "license": "License limit reached",
    "device": "Microphone problem",
    "et_repeat": "E.T. asks to repeat",
    "unexpected": "Unexpected error",
}

ERROR_ACTIONS = {
    "no_model": "Start LM Studio and load a model via the model picker.",
    "bad_output": "The pipeline now repairs truncated/malformed JSON "
                   "automatically â€” if this still happens, rephrase or "
                   "lower the size and run Probe model once.",
    "input": "Fill in all required fields correctly.",
    "connector": "Check the service documentation or try again later.",
    "license": "Activate a Pro key to remove all limits, or wait for "
               "the weekly reset.",
    "device": "Connect a microphone or pick another input in E.T.'s "
              "mic menu â€” typing to E.T. always works.",
    "et_repeat": "No pressure and no turn lost â€” just say it once "
                 "more, a little louder.",
    "unexpected": "Check the log for details and restart if needed.",
}

# 2026-09-05 owner directive: Journey topic generation and Audio Studio
# are FROZEN â€” Study Studio already ships those. The app's focus is the
# Language Lab, Career Development, and Paradise Playground. Frozen
# sections stay visible (their artifacts still open/export) but their
# GENERATION buttons are disabled with a pointer to Study Studio.
FROZEN_NOTE = ("Frozen for now â€” topic + audio generation live in the "
               "Study Studio app. This tab keeps browsing/exporting your "
               "existing artifacts.")


def _open_path(path: str) -> None:
    """Open a file/path in the default application without a terminal window.
    Uses os.startfile on Windows (native, no console flash) and xdg-open elsewhere."""
    import os
    import sys as _sys
    if _sys.platform == "win32":
        os.startfile(path)
    else:
        import subprocess
        subprocess.Popen(["xdg-open", path],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def _open_audio(wav_bytes: bytes) -> None:
    """Play E.T.'s voice (WAV bytes) on a daemon thread via
    sounddevice â€” the UI never blocks, and audio failure is silent
    (the text reply is already on screen; voice is a bonus)."""
    if not wav_bytes:
        return

    def _play():
        try:
            import io
            import numpy as np
            import sounddevice as sd
            import soundfile as sf
            data, rate = sf.read(io.BytesIO(wav_bytes), dtype="float32")
            if data.ndim > 1:
                data = data[:, 0]
            sd.play(data, rate)
            sd.wait()
        except Exception:  # noqa: BLE001 â€” audio is best-effort
            pass

    import threading
    threading.Thread(target=_play, daemon=True).start()


def run() -> None:  # pragma: no cover â€” needs a display
    import logging
    import queue
    import threading
    import tkinter as tk
    from tkinter import messagebox, ttk
    from tkinter import filedialog

    from desktop_shell.controller import FlowResult, ShellController

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ctrl = ShellController()
    root = tk.Tk()
    root.title("L&D Command Center â€” Dark Mode")
    root.geometry("1200x800")
    root.configure(bg="#0d1b2e")
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background='#0d1b2e')
    style.configure('TNotebook', background='#0d1b2e', tabmargins=[2,5,2,0])
    style.configure('TNotebook.Tab', background='#1d3552', foreground='#edf4ff', padding=[10,4])
    style.map('TNotebook.Tab', background=[('selected','#76a9ff')], foreground=[('selected','#07111f')])
    root.title("L&D Command Center")
    root.geometry("960x640")

    # ------------------------------------------------------------------
    # Async runner: every slow flow (generation, search, connector jobs)
    # runs on a worker thread; results marshal back through a queue the
    # Tk main loop polls. The window NEVER freezes during generation.
    # ------------------------------------------------------------------
    _results: "queue.Queue[tuple]" = queue.Queue()

    def _poll_results() -> None:
        try:
            while True:
                callback, result = _results.get_nowait()
                callback(result)
        except queue.Empty:
            pass
        root.after(100, _poll_results)

    def run_async(work, on_done, *, busy=None, busy_text="Workingâ€¦"):
        """Run `work()` on a worker thread; deliver its return value to
        `on_done(result)` on the Tk thread. `busy` is a Button-like
        widget disabled for the duration (restored after)."""
        if busy is not None:
            busy.config(state="disabled", text=busy_text)
            root.update_idletasks()

        def _worker():
            try:
                result = work()
            except Exception as exc:  # marshal everything, never lose it
                result = exc
            _results.put((on_done, result))

        threading.Thread(target=_worker, daemon=True).start()

    def show_error(res: FlowResult):
        title = ERROR_TITLES.get(res.error_kind, "Error")
        action = ERROR_ACTIONS.get(res.error_kind, "")
        message = res.detail or "Unknown failure."
        if action:
            message = f"{message}\n\n{action}"
        messagebox.showerror(title, message)

    # -- header -----------------------------------------------------------
    status = tk.StringVar(value="checking LM Studioâ€¦")
    header = ttk.Frame(root); header.pack(fill="x", padx=8, pady=6)
    health_label = tk.Label(header, textvariable=status, fg="gray")
    health_label.pack(side="left")
    ttk.Button(header, text="Refresh",
               command=lambda: refresh_health()).pack(side="left", padx=6)
    ttk.Button(header, text="Probe model",
               command=lambda: run_probe()).pack(side="left")

    # model picker â€” the user always sees and chooses what is running
    model_var = tk.StringVar()
    models_res = ctrl.list_available_models()
    model_frame = ttk.Frame(header); model_frame.pack(side="right")
    ttk.Label(model_frame, text="Model:").pack(side="left")
    model_combo = ttk.Combobox(model_frame, textvariable=model_var,
                               state="readonly", width=26,
                               values=models_res.payload if models_res.ok else [])
    model_combo.pack(side="left", padx=4)
    if models_res.ok and ctrl.model in (models_res.payload or []):
        model_var.set(ctrl.model)
    elif models_res.ok and models_res.payload:
        ctrl.model = models_res.payload[0]
        model_var.set(models_res.payload[0])

    def on_model_selected(_event=None):
        ctrl.model = model_var.get()
        refresh_health()

    model_combo.bind("<<ComboboxSelected>>", on_model_selected)

    def refresh_health():
        res = ctrl.check_model_health()
        if res.ok:
            cap = ctrl.capability_summary()
            line = "LM Studio: ready"
            if cap.ok and cap.payload:
                line += f" | {cap.payload}"
            status.set(line)
            health_label.config(fg="green")
        else:
            status.set(f"LM Studio: {res.detail}")
            health_label.config(fg="red")
        _refresh_quickstart()
        _refresh_license()

    def run_probe():
        status.set("probing model capabilitiesâ€¦")
        health_label.config(fg="gray")
        root.update_idletasks()

        def work():
            return ctrl.run_capability_probe()

        def done(res):
            if not res:
                return show_error(res)
            refresh_health()

        run_async(work, done)

    # -- quickstart hint (PROFIT_PLAN آ§8 risk #1: model dependency) --------
    # When LM Studio is not reachable or no model is loaded, show the
    # curated model quick-start text so the user knows exactly what to
    # install.  The hint lives in a collapsible label under the header.
    quickstart_var = tk.StringVar(value="")
    quickstart_label = tk.Label(
        header, textvariable=quickstart_var, fg="gray",
        wraplength=860, justify="left")
    quickstart_label.pack(side="bottom", fill="x", pady=(2, 0))

    def _refresh_quickstart():
        """Show the model hint only when the model is missing."""
        res = ctrl.check_model_health()
        if res.ok:
            quickstart_var.set("")
            quickstart_label.pack_forget()
            return
        from model_layer.quickstart import quickstart_hint
        models_res = ctrl.list_available_models()
        loaded = models_res.payload if models_res.ok else None
        hint = quickstart_hint(loaded)
        quickstart_var.set(hint)
        quickstart_label.pack(side="bottom", fill="x", pady=(2, 0))

    # -- license panel (PROFIT_PLAN آ§2: Free / Pro $9 / Campaign $29) ------
    # A compact entitlement bar: tier badge, quota summary, activate-key
    # field, and the upgrade link.  Everything reads offline through the
    # controller's license_status() -> LicenseStore.summary().
    license_var = tk.StringVar(value="Free tier")
    license_detail = tk.StringVar(value="")

    def _refresh_license():
        """One offline read â€” fills the badge + quota line."""
        res = ctrl.license_status()
        if not res.ok:
            license_var.set("Free tier")
            license_detail.set("")
            return
        info = res.payload
        tier = info.get("tier", "free")
        if info.get("valid"):
            badge = f"{info['label']} tier"
            if info.get("days_left") is not None:
                badge += f" ({info['days_left']}d left)"
        else:
            badge = "Free tier"
        license_var.set(badge)
        quotas = info.get("quotas") or {}
        parts = []
        for name in ("lesson_pack", "application_package",
                     "resume_profile", "linkedin_post"):
            q = quotas.get(name) or {}
            remaining = q.get("remaining")
            limit = q.get("limit")
            label = q.get("label") or name.replace("_", " ")
            if remaining is not None:
                parts.append(f"{label}: {remaining}/{limit}")
            else:
                parts.append(f"{label}: unlimited")
        license_detail.set("  |  ".join(parts))

    # license bar (right side of the header, below model picker)
    license_bar = ttk.Frame(root)
    license_bar.pack(fill="x", padx=8, pady=(0, 2))
    tk.Label(license_bar, textvariable=license_var,
             fg="#0066cc", font=("TkDefaultFont", 9, "bold")
             ).pack(side="left")
    tk.Label(license_bar, textvariable=license_detail,
             fg="gray").pack(side="left", padx=8)
    ttk.Button(license_bar, text="Activate keyâ€¦",
               command=lambda: _activate_dialog()).pack(side="right")
    ttk.Button(license_bar, text="Upgrade",
               command=lambda: _open_upgrade_page()).pack(side="right",
                                                           padx=4)

    def _activate_dialog():
        from tkinter import simpledialog
        token = simpledialog.askstring(
            "Activate License Key",
            "Paste your L&D Command Center license key\n"
            "(looks like LDCC1.â€¦.â€¦):",
            parent=root)
        if not token:
            return
        res = ctrl.activate_license(token.strip())
        if not res:
            return show_error(res)
        _refresh_license()
        messagebox.showinfo(
            "License Activated",
            f"Tier: {res.payload.get('label', 'Pro')}\n"
            f"Licensee: {res.payload.get('licensee', '')}\n"
            "All limits removed â€” enjoy unlimited generation.")

    def _open_upgrade_page():
        _open_path("https://github.com/HatemIsmailShalaby1979/"
                   "L-D-Command-Center#pricing")

    # -- tabs ---------------------------------------------------------------
    # Scrollable dark container
    canvas = tk.Canvas(root, bg="#0d1b2e", highlightthickness=0)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    scroll_frame = ttk.Frame(canvas)
    scroll_window = canvas.create_window((0,0), window=scroll_frame, anchor="nw")
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    scroll_frame.bind("<Configure>", on_frame_configure)
    def on_canvas_configure(event):
        canvas.itemconfig(scroll_window, width=event.width)
    canvas.bind("<Configure>", on_canvas_configure)

    tab = ttk.Notebook(scroll_frame); tab.pack(fill="both", expand=True, padx=8, pady=6)

    # == Learning Journey (ACTIVE — unfrozen 2026-09-24) ========================
    journey_tab = ttk.Frame(tab); tab.add(journey_tab, text="Learning Journey")

    form = ttk.Frame(journey_tab); form.pack(fill="x", pady=4)
    topic_var = tk.StringVar()
    level_var = tk.StringVar(value="beginner")
    cards_var = tk.IntVar(value=5)
    last_journey: list[dict] = []

    ttk.Label(form, text="Topic").grid(row=0, column=0, sticky="w")
    ttk.Entry(form, textvariable=topic_var, width=42).grid(row=0, column=1, padx=4)
    ttk.Button(form, text="Clear",
               command=lambda: topic_var.set("")).grid(row=0, column=6, padx=4)
    ttk.Label(form, text="Level").grid(row=0, column=2)
    ttk.Combobox(form, textvariable=level_var, width=12, state="readonly",
                 values=["beginner", "intermediate", "advanced"]).grid(row=0, column=3, padx=4)
    ttk.Label(form, text="Cards").grid(row=0, column=4)
    ttk.Spinbox(form, from_=1, to=20, textvariable=cards_var, width=4).grid(row=0, column=5, padx=4)

    output = tk.Text(journey_tab, height=20)
    output.pack(fill="both", expand=True, pady=6)

    def do_generate_journey():
        def work():
            return ctrl.generate_journey(topic_var.get(), level_var.get(),
                                         cards_var.get())

        def done(res):
            generate_btn.config(state="normal", text="Generate")
            if not res:
                return show_error(res)
            journey = res.payload
            last_journey.clear(); last_journey.append(journey)
            saved = ctrl.render_and_save_journey(journey)
            output.delete("1.0", "end")
            for i, card in enumerate(journey.get("cards", []), 1):
                output.insert("end", f"[{i}] {card.get('title','')}\n{card.get('content','')}\n\n")
            if saved:
                output.insert("end", f"\nSaved interactive HTML -> {saved.payload}")
                _open_path(str(saved.payload))

        if not last_journey and generate_btn.instate(["disabled"]):
            return  # frozen: no generation, exports still work
        run_async(work, done, busy=generate_btn,
                  busy_text="Generatingâ€¦")

    def do_save_journey():
        """Save the current journey HTML to a user-selected location."""
        if not last_journey:
            messagebox.showinfo("Nothing to save", "Generate a journey first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            title="Save Journey HTML",
        )
        if not path:
            return
        journey = last_journey[0]
        from engines.journey_core.renderer import JourneyRenderer
        html = JourneyRenderer().render(journey)
        Path(path).write_text(html, encoding="utf-8")
        output.insert("end", f"\nSaved to -> {path}")
        messagebox.showinfo("Saved", f"Journey saved to:\n{path}")

    def do_export(fmt: str):
        if not last_journey:
            messagebox.showinfo("Nothing to export", "Generate a journey first.")
            return
        res = ctrl.export_artifact(last_journey[0], fmt)
        if not res:
            return show_error(res)
        name = (topic_var.get().strip().lower().replace(" ", "-") or "journey") + \
               {"text": ".txt", "pdf": ".pdf", "pptx": ".pptx", "xlsx": ".xlsx"}[fmt]
        saved = ctrl.save_raw_export(res.payload, name)
        if saved:
            output.insert("end", f"\nExported {fmt} -> {saved.payload}")

    actions = ttk.Frame(journey_tab); actions.pack(fill="x", pady=4)
    generate_btn = ttk.Button(actions, text="Generate (frozen)",
                              command=do_generate_journey,
                              state="disabled")
    generate_btn.pack(side="left")
    ttk.Button(actions, text="Save asâ€¦",
               command=do_save_journey).pack(side="left", padx=4)
    for fmt in ("text", "pdf", "pptx", "xlsx"):
        ttk.Button(actions, text=f"Export {fmt.upper()}",
                   command=lambda f=fmt: do_export(f)).pack(side="left", padx=4)

    # == Language Lab (FLAGSHIP â€” always the first tab) ======================
    lab_tab = ttk.Frame(tab); tab.add(lab_tab, text="Language Lab")

    LANG_NAMES = {
        "en": "English", "es": "Spanish", "fr": "French", "de": "German",
        "it": "Italian", "pt": "Portuguese", "ru": "Russian",
        "zh": "Chinese", "ar": "Arabic", "ja": "Japanese", "ko": "Korean",
        "hi": "Hindi", "nl": "Dutch", "tr": "Turkish", "vi": "Vietnamese",
    }
    lab_lang_values = list(LANG_NAMES)

    lab_form = ttk.Frame(lab_tab); lab_form.pack(fill="x", pady=4)
    lab_topic = tk.StringVar()
    lab_target = tk.StringVar(value="es")
    lab_known = tk.StringVar(value="en")
    lab_level = tk.StringVar(value="beginner")
    lab_status = tk.StringVar(
        value="The flagship: ONE validated lesson pack (two-voice dialogue "
              "with per-line audio, vocab flashcards, grammar drills, "
              "evaluation) opens in your browser. Runs in the background â€” "
              "the window stays responsive. CPU models may take a few "
              "minutes; the health bar above tells you what to expect.")
    ttk.Label(lab_form, text="Topic").grid(row=0, column=0, sticky="w")
    ttk.Entry(lab_form, textvariable=lab_topic, width=30).grid(row=0, column=1,
                                                                padx=4)
    ttk.Button(lab_form, text="Clear",
               command=lambda: lab_topic.set("")).grid(row=0, column=2, padx=4)
    for i, (label, var) in enumerate((("Target", lab_target),
                                      ("Known", lab_known)), start=3):
        ttk.Label(lab_form, text=label).grid(row=0, column=i)
        ttk.Combobox(lab_form, textvariable=var, width=9, state="readonly",
                     values=[f"{code} ({LANG_NAMES[code]})"
                             for code in lab_lang_values]).grid(
            row=0, column=i + 1, padx=4)

    def _lang_code(combined: str) -> str:
        return combined.split(" ")[0] if combined else "en"

    ttk.Label(lab_form, text="Level").grid(row=0, column=6)
    ttk.Combobox(lab_form, textvariable=lab_level, width=11,
                 state="readonly",
                 values=["beginner", "intermediate", "advanced"]).grid(
        row=0, column=7, padx=4)

    lab_history: list[tuple[str, str]] = []  # (filename, path) newest last

    def _refresh_lab_history():
        history_box.delete(0, "end")
        lab_history.clear()
        res = ctrl.list_saved("lesson_packs")
        if not res.ok or not res.payload:
            return
        for name in list(res.payload)[-8:]:
            lab_history.append((name, name))
            history_box.insert("end", name)

    def _reopen_pack():
        sel = history_box.curselection()
        if not sel:
            return
        stem = lab_history[sel[0]][0].rsplit(".", 1)[0]
        exports = ctrl.list_saved("exports")
        if not exports.ok:
            return
        for name in exports.payload:
            if name == f"{stem}.html":
                lab_status.set(f"Opening saved pack -> {name}")
                _open_path(str(Path(ctrl.storage.root) / "exports" / name))
                return
        messagebox.showinfo("Language Lab",
                            "Pack data found but no HTML export â€” "
                            "generate it again to re-render.")

    def do_lesson_pack():
        topic = lab_topic.get().strip()
        if not topic:
            return messagebox.showinfo("Language Lab", "Enter a topic first.")
        target = _lang_code(lab_target.get())
        known = _lang_code(lab_known.get())
        level = lab_level.get()
        lab_status.set(f"Generating lesson pack for '{topic}' ({target})â€¦ "
                       "running in the background; keep using the app.")
        health_label.config(fg="gray")

        def work():
            return ctrl.generate_lesson_pack(topic, target, known, level)

        def done(res):
            lab_btn.config(state="normal", text="Generate lesson pack")
            if not res:
                lab_status.set("Generation failed â€” see the error dialog.")
                return show_error(res)
            lab_status.set(f"Saved -> {res.payload}  (openingâ€¦)")
            _refresh_lab_history()
            _refresh_lab_quota()
            _refresh_license()
            _open_path(str(res.payload))

        run_async(work, done, busy=lab_btn,
                  busy_text="Generatingâ€¦")

    # Generate row: frame FIRST so the quota badge can pack into it.
    lab_actions = ttk.Frame(lab_tab); lab_actions.pack(fill="x", pady=4)
    lab_btn = ttk.Button(lab_actions, text="Generate lesson pack",
                         command=do_lesson_pack)
    lab_btn.pack(side="left")

    # quota badge â€” shows remaining packs (free tier: 3/week)
    lab_quota_label = tk.Label(lab_actions, text="", fg="gray")
    lab_quota_label.pack(side="left", padx=8)

    def _refresh_lab_quota():
        q = ctrl.licenses.quota("lesson_pack")
        if q.remaining is not None:
            lab_quota_label.config(
                text=f"Packs: {q.remaining}/{q.limit} left this week")
        else:
            lab_quota_label.config(text="Packs: unlimited")

    tk.Label(lab_tab, textvariable=lab_status, fg="gray",
             wraplength=900, justify="left").pack(anchor="w", pady=4)

    # Share button (PROFIT_PLAN آ§3.1 growth loop â€” free on every tier)
    def _do_share_pack():
        sel = history_box.curselection()
        if not sel:
            return messagebox.showinfo(
                "Language Lab", "Select a saved pack to share first.")
        pack_name = lab_history[sel[0]][0]
        path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("All", "*")],
            title="Save shareable lesson pack",
            initialfile=f"share-{pack_name.rsplit('.', 1)[0]}.html")
        if not path:
            return
        res = ctrl.share_lesson_pack(pack_name, destination=path)
        if not res:
            return show_error(res)
        lab_status.set(
            f"Shareable pack saved -> {res.payload['path']} "
            f"({res.payload['bytes']} bytes). Send it to anyone â€” "
            "it opens in any browser, offline.")
        _open_path(str(res.payload["path"]))

    history_frame = ttk.LabelFrame(
        lab_tab, text="Saved packs (double-click to reopen)")
    history_frame.pack(fill="x", pady=4)
    history_box = tk.Listbox(history_frame, height=4)
    history_box.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    history_box.bind("<Double-Button-1>", lambda _e: _reopen_pack())
    ttk.Button(history_frame, text="Reopen",
               command=_reopen_pack).pack(side="left", padx=4)
    ttk.Button(history_frame, text="Share packâ€¦",
               command=_do_share_pack).pack(side="left", padx=4)
    _refresh_lab_history()
    _refresh_lab_quota()

    # -- E.T. live voice conversation (Project E.T., 2026-09-06) ----------
    from desktop_shell.et_ui import build_et_panel

    def _lab_language_code() -> str:
        return _lang_code(lab_target.get())

    et_panel = build_et_panel(
        lab_tab,
        ctrl=ctrl,
        run_async=run_async,
        show_error=show_error,
        open_path=_open_path,
        _open_audio=_open_audio,
        lang_values=None,
        get_lang_code=_lab_language_code,
        level_var=lab_level,
        refresh_license=_refresh_license,
    )

    # -- Curriculum library (L4: the ready-made A1..C1 catalogue) --------
    from desktop_shell.lab_ui import build_library_panel

    library_state = build_library_panel(
        lab_tab,
        ctrl=ctrl,
        run_async=run_async,
        show_error=show_error,
        open_path=_open_path,
        language_getter=_lab_language_code,
        level_getter=lambda: lab_level.get(),
        on_language_change=lambda code: lab_target.set(
            f"{code} ({[n for n in LANG_NAMES if n.startswith(code)][0]})"
            if any(n.startswith(code) for n in LANG_NAMES) else code),
    )

    # -- Exams (L5: the inclusive final test per level) --------------------
    from desktop_shell.exams_ui import build_exams_panel

    def _record_turn_for_exam(language):
        from engines.audio_engine.mic import capture_speech
        try:
            capture = capture_speech(max_seconds=60.0)
            return capture.wav_bytes
        except Exception:  # noqa: BLE001 â€” typed errors handled by UI
            return None

    exams_state = build_exams_panel(
        lab_tab,
        ctrl=ctrl,
        run_async=run_async,
        show_error=show_error,
        open_path=_open_path,
        play_audio=_open_audio,
        language_getter=_lab_language_code,
        record_turn=_record_turn_for_exam,
    )

    # == Playground ==========================================================
    playground_tab = ttk.Frame(tab); tab.add(playground_tab, text="Playground")

    def do_import_files():
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(
            parent=root, title="Import media into the Playground")
        if not paths:
            return
        res = ctrl.import_files(list(paths))
        if not res:
            return show_error(res)
        failed = [r for r in res.payload if not r["ok"]]
        refresh_canvas()
        note = f"Imported {len(res.payload) - len(failed)} file(s)."
        if failed:
            note += f" {len(failed)} failed."
        messagebox.showinfo("Playground import", note)

    def do_scan_inbox():
        res = ctrl.scan_import_inbox()
        if not res:
            return show_error(res)
        imported = sum(1 for r in res.payload if r["ok"])
        refresh_canvas()
        messagebox.showinfo("Import inbox",
                            f"{imported} new file(s) from the inbox.")

    def refresh_canvas():
        canvas_list.delete(*canvas_list.get_children())
        for subkind in ("library", "generated", "inbox"):
            res = ctrl.list_media(subkind)
            if not res.ok:
                continue
            for name in res.payload:
                canvas_list.insert("", "end", values=(subkind, name))

    def on_connector_selected(_event=None):
        name = connector_var.get()
        caps_res = ctrl.connector_capabilities()
        info.delete("1.0", "end")
        if not caps_res.ok:
            return
        entry = next((c for c in caps_res.payload
                      if c["connector"] == name), None)
        if not entry:
            return
        info.insert("end", f"auth: {entry['auth']}\n")
        for item in entry["items"]:
            info.insert("end", f"[{item['kind']}] {item['description']}\n"
                               f"quota: {item['quota_note']}\n")

    # -- connector generate flow (defined after conn_frame widgets) --------

    canvas_bar = ttk.Frame(playground_tab); canvas_bar.pack(fill="x", pady=4)
    ttk.Button(canvas_bar, text="Import filesâ€¦",
               command=do_import_files).pack(side="left")
    ttk.Button(canvas_bar, text="Scan inbox",
               command=do_scan_inbox).pack(side="left", padx=6)
    inbox_note = tk.Label(canvas_bar, fg="gray")
    inbox_note.pack(side="left")

    columns = ("kind", "name")
    canvas_list = ttk.Treeview(playground_tab, columns=columns,
                               show="headings", height=9)
    canvas_list.heading("kind", text="Kind")
    canvas_list.heading("name", text="Artifact")
    canvas_list.pack(fill="both", expand=True)

    conn_frame = ttk.LabelFrame(playground_tab,
                                text="Connectors (free tiers)")
    conn_frame.pack(fill="x", pady=4)
    connector_var = tk.StringVar()
    names_res = ctrl.connector_names()
    ttk.Combobox(conn_frame, textvariable=connector_var, state="readonly",
                 values=names_res.payload if names_res.ok else []).pack(
        side="left", padx=4, pady=4)
    connector_var.trace_add("write", lambda *_: on_connector_selected())
    ttk.Label(conn_frame, text="prompt").pack(side="left")
    prompt_var = tk.StringVar()
    ttk.Entry(conn_frame, textvariable=prompt_var, width=36).pack(
        side="left", padx=4)

    def do_connector_generate():
        prompt = prompt_var.get().strip()
        if not prompt:
            return messagebox.showinfo("Playground", "Enter a prompt first.")

        def work():
            return ctrl.run_connector_job(connector_var.get(),
                                          {"prompt": prompt})

        def done(res):
            gen_conn_btn.config(state="normal", text="Generate")
            if not res:
                output_note.set("")
                return show_error(res)
            refresh_canvas()
            output_note.set(
                f"Saved -> media/generated/"
                f"{res.payload['artifact_name']}")

        output_note.set("workingâ€¦")
        run_async(work, done, busy=gen_conn_btn, busy_text="Workingâ€¦")

    gen_conn_btn = ttk.Button(conn_frame, text="Generate",
                              command=do_connector_generate)
    gen_conn_btn.pack(side="left")
    output_note = tk.StringVar()
    tk.Label(conn_frame, textvariable=output_note,
             fg="green").pack(side="left", padx=6)
    info = tk.Text(conn_frame, height=4, width=80)
    info.pack(fill="x", padx=4, pady=4)

    # -- Skills Arena (L6: practice the four skills with your files) ------
    # The Playground is now the four-skills practice area per the
    # 2026-09-06 owner directive; the media canvas + connectors above
    # stay exactly where they were â€” the Arena adds, never removes.
    from desktop_shell.skills_ui import build_skills_arena

    def _jump_to_et():
        tab.select(lab_tab)  # E.T. lives in the Language Lab

    skills_state = build_skills_arena(
        playground_tab,
        ctrl=ctrl,
        run_async=run_async,
        show_error=show_error,
        open_path=_open_path,
        language_getter=_lab_language_code,
        level_getter=lambda: lab_level.get(),
        jump_to_et=_jump_to_et,
    )

    # == Audio Studio (ACTIVE — unfrozen 2026-09-24) =============================
    studio_tab = ttk.Frame(tab); tab.add(studio_tab, text="Audio Studio")

    LANG_CODES = list(LANG_NAMES)

    # --- audiobooks ---
    ab_frame = ttk.LabelFrame(studio_tab, text="Audiobook â€” text to narrated audio")
    ab_frame.pack(fill="x", padx=6, pady=6)
    last_audiobook: Optional[bytes] = None
    last_podcast: Optional[bytes] = None
    ttk.Label(ab_frame, text="Text").grid(row=0, column=0, sticky="nw")
    ab_text = tk.Text(ab_frame, height=5, width=70)
    ab_text.grid(row=1, column=0, columnspan=4, padx=4, sticky="we")
    ab_lang = tk.StringVar(value="en")
    ab_speed = tk.StringVar(value="1.0")
    installed = ctrl.available_voices()
    known_marked = ctrl.all_known_voices()
    known_plain = [v.split("   ")[0] for v in known_marked]
    ttk.Label(ab_frame, text="Voice language").grid(row=2, column=0, sticky="w")
    ttk.Combobox(ab_frame, textvariable=ab_lang, width=5, state="readonly",
                 values=LANG_CODES).grid(row=2, column=1, sticky="w")
    ttk.Label(ab_frame, text="Speed").grid(row=2, column=2, sticky="e")
    ttk.Combobox(ab_frame, textvariable=ab_speed, width=5, state="readonly",
                 values=["0.8", "1.0", "1.2"]).grid(row=2, column=3, sticky="w")
    ttk.Label(ab_frame, text="Narrator voice").grid(row=2, column=4,
                                                    sticky="w", padx=(10, 0))
    ab_voice = tk.StringVar(value="")
    ab_voice_combo = ttk.Combobox(ab_frame, textvariable=ab_voice, width=34,
                                  state="readonly",
                                  values=["(auto by language)"] + known_marked)
    ab_voice_combo.grid(row=2, column=5, sticky="w")
    ab_voice.set("(auto by language)")
    ab_status = tk.StringVar(value="Paste any text â€” narrated WAV + MP3 land in exports.")
    tk.Label(ab_frame, textvariable=ab_status, fg="gray",
             wraplength=700, justify="left").grid(row=3, column=0,
                                                  columnspan=4, sticky="w")

    def do_audiobook():
        text = ab_text.get("1.0", "end").strip()
        if not text:
            return messagebox.showinfo("Audio Studio", "Paste some text first.")
        ab_status.set(f"Narrating {len(text)} charactersâ€¦")
        root.update_idletasks()
        voice = None if ab_voice.get().startswith("(") \
            else ab_voice.get().split("   ")[0]
        res = ctrl.generate_audiobook(text, ab_lang.get(),
                                      float(ab_speed.get()), voice)
        if not res:
            ab_status.set("Audiobook failed.")
            return show_error(res)
        ab_status.set(f"Done ({res.payload['duration_seconds']}s, "
                      f"{res.payload['voice']}). Opening playerâ€¦")
        nonlocal last_audiobook
        last_audiobook = res.payload["mp3"] or res.payload["wav"]
        if last_audiobook:
            last_audiobook = Path(last_audiobook).read_bytes()
        _open_path(res.payload["mp3"] or res.payload["wav"])

    def _save_as(data_bytes: bytes, default_ext: str, title: str) -> None:
        """Show a save-dialog and write data_bytes to the chosen path."""
        path = filedialog.asksaveasfilename(
            defaultextension=default_ext,
            filetypes=[
                (default_ext[1:].upper() + " files", "*" + default_ext),
                ("All files", "*.*"),
            ],
            title=title,
        )
        if not path:
            return
        Path(path).write_bytes(data_bytes)
        messagebox.showinfo("Saved", f"File saved to:\n{path}")

    def do_save_audiobook():
        """Save the generated audiobook to a user-selected location."""
        if not last_audiobook:
            messagebox.showinfo("Nothing to save", "Generate an audiobook first.")
            return
        _save_as(last_audiobook, ".mp3", "Save Audiobook")

    def do_save_podcast():
        """Save the generated podcast to a user-selected location."""
        if not last_podcast:
            messagebox.showinfo("Nothing to save", "Generate a podcast first.")
            return
        _save_as(last_podcast, ".mp3", "Save Podcast")

    ttk.Button(ab_frame, text="Generate audiobook",
               state="normal",
               command=do_audiobook).grid(row=4, column=0, sticky="w", pady=4)
    ttk.Button(ab_frame, text="Save asâ€¦",
               command=do_save_audiobook).grid(row=4, column=1, sticky="w", padx=4)

    # --- podcasts ---
    pod_frame = ttk.LabelFrame(studio_tab, text="Podcast â€” topic to two-voice episode")
    pod_frame.pack(fill="x", padx=6, pady=6)
    pod_row1 = ttk.Frame(pod_frame); pod_row1.pack(fill="x", pady=2)
    ttk.Label(pod_row1, text="Topic").pack(side="left")
    pod_topic = tk.StringVar()
    ttk.Entry(pod_row1, textvariable=pod_topic, width=34).pack(side="left", padx=4)
    ttk.Button(pod_row1, text="Clear",
               command=lambda: pod_topic.set("")).pack(side="left", padx=4)
    ttk.Label(pod_row1, text="Language").pack(side="left")
    pod_lang = tk.StringVar(value="en")
    ttk.Combobox(pod_row1, textvariable=pod_lang, width=5, state="readonly",
                 values=LANG_CODES).pack(side="left", padx=4)
    ttk.Label(pod_row1, text="Level").pack(side="left")
    pod_level = tk.StringVar(value="beginner")
    ttk.Combobox(pod_row1, textvariable=pod_level, width=11, state="readonly",
                 values=["beginner", "intermediate", "advanced"]).pack(
        side="left", padx=4)
    pod_row2 = ttk.Frame(pod_frame); pod_row2.pack(fill="x", pady=2)
    ttk.Label(pod_row2, text="Host A").pack(side="left")
    pod_host = tk.StringVar(value="Alex")
    ttk.Entry(pod_row2, textvariable=pod_host, width=9).pack(side="left", padx=4)
    ttk.Label(pod_row2, text="Host B").pack(side="left")
    pod_cohost = tk.StringVar(value="Maya")
    ttk.Entry(pod_row2, textvariable=pod_cohost, width=9).pack(side="left", padx=4)
    ttk.Label(pod_row2, text="Voice A").pack(side="left")
    pod_voice_a = tk.StringVar(value="")
    ttk.Combobox(pod_row2, textvariable=pod_voice_a, width=30,
                 state="readonly",
                 values=["(auto)"] + known_marked).pack(side="left", padx=2)
    pod_voice_a.set("(auto)")
    ttk.Label(pod_row2, text="Voice B").pack(side="left")
    pod_voice_b = tk.StringVar(value="")
    ttk.Combobox(pod_row2, textvariable=pod_voice_b, width=30,
                 state="readonly",
                 values=["(auto)"] + known_marked).pack(side="left", padx=2)
    pod_voice_b.set("(auto)")

    pod_row3 = ttk.Frame(pod_frame); pod_row3.pack(fill="x", pady=2)
    ttk.Label(pod_row3, text="Length (minutes)").pack(side="left")
    pod_minutes = tk.StringVar(value="5")
    ttk.Spinbox(pod_row3, from_=1, to=240, textvariable=pod_minutes,
                width=5).pack(side="left", padx=4)
    ttk.Label(pod_row3, text="(segments auto-calculated)").pack(side="left",
                                                                 padx=4)
    pod_status = tk.StringVar(
        value="Two AI hosts discuss the topic entirely in the target "
              "language. Script is saved alongside the audio.")
    tk.Label(pod_frame, textvariable=pod_status, fg="gray",
             wraplength=700, justify="left").pack(anchor="w", pady=2)

    def do_podcast():
        topic = pod_topic.get().strip()
        if not topic:
            return messagebox.showinfo("Audio Studio", "Enter a topic first.")
        pod_status.set(f"Writing script for '{topic}' then recording two "
                       "voicesâ€¦ (a few minutes)")
        root.update_idletasks()
        res = ctrl.generate_podcast(topic, pod_lang.get(), pod_level.get(),
                                     num_segments=6,
                                     duration_minutes=int(pod_minutes.get()),
                                     host_name=pod_host.get(),
                                     co_host_name=pod_cohost.get(),
                                     voice_a=(None if pod_voice_a.get().startswith("(")
                                              else pod_voice_a.get().split("   ")[0]),
                                     voice_b=(None if pod_voice_b.get().startswith("(")
                                              else pod_voice_b.get().split("   ")[0]))
        if not res:
            pod_status.set("Podcast failed.")
            return show_error(res)
        pod_status.set(f"'{res.payload['title']}' ready â€” "
                       f"{res.payload['segments']} segments, "
                       f"voices: {', '.join(res.payload['speakers'])}, "
                       f"{res.payload['duration_seconds']}s. Opening playerâ€¦")
        nonlocal last_podcast
        last_podcast = res.payload["mp3"] or res.payload["wav"]
        if last_podcast:
            last_podcast = Path(last_podcast).read_bytes()
        _open_path(res.payload["mp3"] or res.payload["wav"])

    ttk.Button(pod_frame, text="Generate podcast",
               state="normal",
               command=do_podcast).pack(anchor="w", pady=4)
    ttk.Button(pod_frame, text="Save asâ€¦",
               command=do_save_podcast).pack(anchor="w", padx=4, pady=4)

    # --- voice manager ---
    vm_frame = ttk.LabelFrame(studio_tab, text="Voices (Piper)")
    vm_frame.pack(fill="x", padx=6, pady=6)
    vm_var = tk.StringVar()
    missing_now = [v for v in known_plain
                   if v not in set(ctrl.available_voices())]
    ttk.Label(vm_frame,
              text=f"{len(installed)} installed on this machine. "
                   f"{len(missing_now)} more known to the app:"
              ).pack(anchor="w")
    vm_combo = ttk.Combobox(vm_frame, textvariable=vm_var, state="readonly",
                            width=44, values=missing_now or ["(all known voices installed)"])
    if missing_now:
        vm_combo.current(0)
    vm_combo.pack(side="left", padx=4, pady=4)

    def do_download_voice():
        vid = vm_var.get().strip()
        if not vid or vid.startswith("("):
            return messagebox.showinfo("Voices", "Nothing left to download.")
        vm_status.set(f"Downloading {vid}â€¦ (~70 MB, one time)")
        root.update_idletasks()
        res = ctrl.download_voice(vid.split("   ")[0])
        if not res:
            vm_status.set("Download failed.")
            return show_error(res)
        global installed  # noqa â€” refresh local lists via closure recompute
        installed = ctrl.available_voices()
        vm_status.set(f"Installed {vid}. It now appears in every voice "
                      "dropdown.")

    vm_status = tk.StringVar(value="")
    tk.Label(vm_frame, textvariable=vm_status, fg="green").pack(
        side="left", padx=6)
    ttk.Button(vm_frame, text="Download selected voice",
               command=do_download_voice).pack(side="left", padx=4)

    # == Career ==============================================================
    career_tab = ttk.Frame(tab); tab.add(career_tab, text="Career")

    # -- top section: input + actions (always visible) -----------------------
    career_top = ttk.Frame(career_tab)
    career_top.pack(fill="x", padx=8, pady=(8, 4))

    ttk.Label(career_top, text="Your profile / background",
              font=("", 10, "bold")).pack(anchor="w")
    profile_text = tk.Text(career_top, height=5, width=90)
    profile_text.pack(fill="x", pady=2)
    ttk.Button(career_top, text="Clear profile",
               command=lambda: profile_text.delete("1.0", "end")).pack(anchor="e")

    career_row = ttk.Frame(career_top)
    career_row.pack(fill="x", pady=2)
    ttk.Label(career_row, text="Target role").pack(side="left")
    role_var = tk.StringVar()
    ttk.Entry(career_row, textvariable=role_var, width=30).pack(
        side="left", padx=4)
    current_resume: list[dict] = []

    career_status = tk.StringVar(
        value="Type your background above and click Generate, or upload "
              "an existing resume. Then set a target role and Enhance.")
    tk.Label(career_top, textvariable=career_status, fg="gray",
             wraplength=760, justify="left").pack(anchor="w", pady=2)

    # -- resume preview pane -------------------------------------------------
    out = tk.Text(career_tab, height=10, width=90)
    out.pack(fill="x", padx=8, pady=4)

    # -- upload existing resume ----------------------------------------------
    upload_frame = ttk.LabelFrame(career_tab, text="Upload existing resume")
    upload_frame.pack(fill="x", padx=8, pady=4)
    upload_row = ttk.Frame(upload_frame)
    upload_row.pack(fill="x", padx=6, pady=6)
    ttk.Button(upload_row, text="Select PDF / DOCX / TXT",
               command=lambda: None).pack(side="left")

    # -- connections ---------------------------------------------------------
    conn_frame = ttk.LabelFrame(career_tab, text="Connections")
    conn_frame.pack(fill="x", padx=8, pady=4)
    conn_row = ttk.Frame(conn_frame)
    conn_row.pack(fill="x", padx=6, pady=6)

    ttk.Label(conn_row, text="GitHub username").pack(side="left")
    gh_user = tk.StringVar()
    ttk.Entry(conn_row, textvariable=gh_user, width=20).pack(
        side="left", padx=4)
    gh_status = tk.StringVar(value="")
    gh_btn = ttk.Button(conn_row, text="Import GitHub",
                        command=lambda: None)
    gh_btn.pack(side="left", padx=4)
    tk.Label(conn_row, textvariable=gh_status, fg="gray").pack(side="left")

    ttk.Label(conn_row, text="  |  ").pack(side="left")
    li_status = tk.StringVar(value="")
    li_btn = ttk.Button(conn_row, text="Connect LinkedIn",
                        command=lambda: None)
    li_btn.pack(side="left", padx=4)
    tk.Label(conn_row, textvariable=li_status, fg="gray").pack(side="left")

    # Career memory: restore everything the app already knows about
    # this user (GitHub username, cached projects, LinkedIn basics,
    # last target role) â€” connections survive restarts offline.
    _identity_res = ctrl.get_career_identity()
    if _identity_res.ok and _identity_res.payload:
        _id = _identity_res.payload
        if _id.get("github_username"):
            gh_user.set(_id["github_username"])
            gh_status.set(f"remembered: {_id['github_username']} "
                          f"({len(_id.get('github_projects') or [])} "
                          f"cached projects)")
        if _id.get("linkedin"):
            li_status.set(f"remembered: "
                          f"{_id['linkedin'].get('name')}")
        if _id.get("target_role") and not role_var.get():
            role_var.set(_id["target_role"])

    # -- job search ----------------------------------------------------------
    search_frame = ttk.LabelFrame(career_tab, text="Job Search")
    search_frame.pack(fill="x", padx=8, pady=4)

    search_row = ttk.Frame(search_frame)
    search_row.pack(fill="x", padx=6, pady=4)
    ttk.Label(search_row, text="Role keywords").pack(side="left")
    search_role = tk.StringVar(value="customer support")
    ttk.Entry(search_row, textvariable=search_role, width=25).pack(
        side="left", padx=4)
    ttk.Label(search_row, text="Location").pack(side="left")
    search_loc = tk.StringVar()
    ttk.Entry(search_row, textvariable=search_loc, width=18).pack(
        side="left", padx=4)

    # Company rosters are fully configurable and persisted (job_sources
    # preference). Defaults come from the engine's contact-center/CX list;
    # a user-saved roster survives restarts and feeds both searches and
    # the watchlist.
    sources = ctrl._job_sources()
    roster_frame = ttk.Frame(search_frame)
    roster_frame.pack(fill="x", padx=6, pady=2)
    gh_companies = tk.StringVar(value=",".join(sources["greenhouse_companies"]))
    lever_companies = tk.StringVar(value=",".join(sources["lever_companies"]))
    ashby_companies = tk.StringVar(value=",".join(sources["ashby_companies"]))

    def _do_save_rosters():
        res = ctrl.save_job_sources(
            greenhouse=gh_companies.get(),
            lever=lever_companies.get(),
            ashby=ashby_companies.get())
        if not res:
            return show_error(res)
        search_status.set("Company rosters saved")

        career_status.set("Company rosters saved for all future searches "
                          "and watchlists.")

    ttk.Label(roster_frame, text="Greenhouse boards").pack(side="left")
    ttk.Entry(roster_frame, textvariable=gh_companies, width=38).pack(
        side="left", padx=4)
    ttk.Label(roster_frame, text="Lever").pack(side="left")
    ttk.Entry(roster_frame, textvariable=lever_companies, width=16).pack(
        side="left", padx=4)
    ttk.Label(roster_frame, text="Ashby").pack(side="left")
    ttk.Entry(roster_frame, textvariable=ashby_companies, width=22).pack(
        side="left", padx=4)
    ttk.Button(roster_frame, text="Save rosters",
               command=_do_save_rosters).pack(side="left", padx=4)

    search_status = tk.StringVar(value="")
    job_results_var = []
    job_tree = None

    def _ensure_tree():
        nonlocal job_tree
        if job_tree is not None:
            return job_tree
        cols = ("company", "title", "location", "source", "score")
        tv = ttk.Treeview(search_frame, columns=cols, show="headings",
                          height=6)
        for col, label, w in [
            ("company", "Company", 100), ("title", "Title", 180),
            ("location", "Location", 120), ("source", "Source", 80),
            ("score", "Score", 50),
        ]:
            tv.heading(col, text=label)
            tv.column(col, width=w, anchor="w")
        scroll = ttk.Scrollbar(search_frame, orient="vertical",
                               command=tv.yview)
        tv.configure(yscrollcommand=scroll.set)
        tv.pack(fill="both", expand=True, padx=6)
        scroll.pack(side="right", fill="y")
        job_tree = tv
        return tv

    def _do_search():
        def work():
            return ctrl.search_jobs_now(
                search_role.get(), search_loc.get(),
                greenhouse_companies=gh_companies.get(),
                lever_companies=lever_companies.get(),
                ashby_companies=ashby_companies.get())

        def done(res):
            search_btn.config(state="normal", text="Search now")
            if not res:
                return show_error(res)
            tv = _ensure_tree()
            tv.delete(*tv.get_children())
            job_results_var.clear()
            for row in res.payload:
                job_results_var.append(row)
                tv.insert("", "end", values=(
                    row.get("company", ""), row.get("title", ""),
                    row.get("location", ""), row.get("source", ""),
                    row.get("score", 0)))
            search_status.set(f"{len(res.payload)} matching listings")
            career_status.set(f"Job search: {len(res.payload)} matches.")

        search_status.set("Searching boardsâ€¦")
        run_async(work, done, busy=search_btn, busy_text="Searchingâ€¦")

    search_btns = ttk.Frame(search_frame)
    search_btns.pack(fill="x", padx=6, pady=2)
    search_btn = ttk.Button(search_btns, text="Search now",
                            command=_do_search)
    search_btn.pack(side="left", padx=4)
    tk.Label(search_btns, textvariable=search_status,
             fg="gray").pack(side="left", padx=4)

    def _do_prepare_application():
        if not current_resume:
            return messagebox.showinfo(
                "Career", "Generate or upload a resume first.")
        if job_tree is None:
            return messagebox.showinfo(
                "Career", "Run a job search first.")
        sel = job_tree.selection()
        if not sel:
            return messagebox.showinfo(
                "Career",
                "Select a listing in the results first.")
        idx = job_tree.index(sel[0])
        if idx >= len(job_results_var):
            return
        listing = job_results_var[idx]

        def work():
            return ctrl.prepare_application(listing, current_resume[0])

        def done(res):
            prep_btn.config(state="normal", text="Prepare application")
            if not res:
                return show_error(res)
            pkg = res.payload
            search_status.set(f"Package ready -> {pkg['dir']}")
            career_status.set(
                f"Application package ready for "
                f"{listing.get('company')}.\n"
                f"Files: {', '.join(pkg['files'])}\n"
                f"Apply URL: {pkg['apply_url']}\n"
                f"Open folder and submit manually â€” bots get banned.")
            _refresh_license()

        prep_btn.config(state="disabled", text="Preparingâ€¦")
        career_status.set(
            f"Preparing package for {listing.get('company')} â€” "
            "tailored resume, cover letter, exports. Runs in background.")
        run_async(work, done, busy=prep_btn, busy_text="Preparingâ€¦")

    prep_btn = ttk.Button(search_btns, text="Prepare application",
                          command=_do_prepare_application)
    prep_btn.pack(side="left", padx=4)
    ttk.Label(search_btns, text="  |  ").pack(side="left")
    ttk.Label(search_btns, text="Greenhouse").pack(side="left")
    ttk.Label(search_btns, text="  |  ").pack(side="left")
    ttk.Label(search_btns, text="Lever").pack(side="left")
    ttk.Label(search_btns, text="  |  ").pack(side="left")
    ttk.Label(search_btns, text="RemoteOK").pack(side="left")

    # -- watchlist (auto-check) ---------------------------------------------
    watch_frame = ttk.Frame(search_frame)
    watch_frame.pack(fill="x", padx=6, pady=4)
    watch_status = tk.StringVar(value="")
    auto_check_var = tk.BooleanVar(value=False)
    _auto_check_id = None

    def _do_save_watchlist():
        res = ctrl.save_job_watchlist(
            search_role.get(), search_loc.get(),
            greenhouse_companies=gh_companies.get(),
            lever_companies=lever_companies.get(),
            ashby_companies=ashby_companies.get())
        if not res:
            return show_error(res)
        watch_status.set(f"Watchlist armed: {search_role.get()}")

    def _do_check_watchlist():
        res = ctrl.check_job_watchlist()
        if not res:
            return show_error(res)
        n = len(res.payload["new"])
        total = res.payload["total"]
        if n:
            watch_status.set(f"{n} NEW listings (of {total})!")
            messagebox.showinfo(
                "Watchlist",
                f"{n} new listings found.\n"
                f"Review results in the search tab.")
        else:
            watch_status.set(f"No new listings (checked {total})")

    def _auto_tick():
        nonlocal _auto_check_id
        if not auto_check_var.get():
            _auto_check_id = None
            return
        _do_check_watchlist()
        _auto_check_id = root.after(600000, _auto_tick)

    def _toggle_auto_check():
        nonlocal _auto_check_id
        if auto_check_var.get():
            watch_status.set("Auto-check: every 10 min")
            _auto_tick()
        else:
            if _auto_check_id:
                root.after_cancel(_auto_check_id)
                _auto_check_id = None
            watch_status.set("Auto-check disabled")

    ttk.Button(watch_frame, text="Save as watchlist",
               command=_do_save_watchlist).pack(side="left")
    ttk.Button(watch_frame, text="Check watchlist now",
               command=_do_check_watchlist).pack(side="left", padx=6)
    ttk.Checkbutton(watch_frame, text="Auto-check every 10 min",
                     variable=auto_check_var,
                     command=_toggle_auto_check).pack(side="left", padx=4)
    tk.Label(watch_frame, textvariable=watch_status,
             fg="gray").pack(side="left", padx=4)

    # -- LinkedIn posts (draft locally, publish only on confirm) -----------
    post_frame = ttk.LabelFrame(
        career_tab, text="LinkedIn posts â€” human-sounding, no AI tells")
    post_frame.pack(fill="x", padx=8, pady=4)

    post_goal_var = tk.StringVar(
        value="share that I am looking for customer support / CX roles")
    post_status = tk.StringVar(
        value="Drafts stay local until you review and publish. Style: "
              "first-person, concrete, no 'thrilled to announce', no "
              "hashtag soup.")
    post_row = ttk.Frame(post_frame)
    post_row.pack(fill="x", padx=6, pady=4)
    ttk.Label(post_row, text="Goal").pack(side="left")
    ttk.Entry(post_row, textvariable=post_goal_var, width=52).pack(
        side="left", padx=4)
    post_btn = ttk.Button(post_row, text="Draft post",
                          command=lambda: None)
    post_btn.pack(side="left", padx=4)
    publish_btn = ttk.Button(post_row, text="Publishâ€¦",
                              state="disabled",
                              command=lambda: None)
    publish_btn.pack(side="left", padx=4)
    tk.Label(post_frame, textvariable=post_status, fg="gray",
             wraplength=880, justify="left").pack(anchor="w", padx=6)

    post_preview = tk.Text(post_frame, height=7, width=100)
    post_preview.pack(fill="x", padx=6, pady=(0, 6))
    last_post_text = {"text": ""}

    def _do_draft_post():
        if not current_resume:
            return messagebox.showinfo(
                "Career", "Generate or upload a resume first â€” the "
                "post is grounded in your real experience.")

        def work():
            return ctrl.draft_linkedin_post(current_resume[0],
                                            post_goal_var.get())

        def done(res):
            post_btn.config(state="normal", text="Draft post")
            if not res:
                post_status.set("Draft failed â€” see dialog.")
                return show_error(res)
            draft = res.payload["draft"]
            last_post_text["text"] = draft["post_text"]
            post_preview.delete("1.0", "end")
            post_preview.insert("1.0", draft["post_text"])
            if draft.get("style_notes"):
                post_preview.insert("end",
                                    f"\n\nâ€” style: {draft['style_notes']}")
            post_status.set(
                f"Draft saved (linkedin_posts/{res.payload['saved_as']}). "
                "Edit freely, then Publishâ€¦ â€” nothing posts without "
                "your explicit confirm.")
            publish_btn.config(state="normal")
            _refresh_license()

        run_async(work, done, busy=post_btn, busy_text="Draftingâ€¦")

    def _do_publish_post():
        text = post_preview.get("1.0", "end").strip()
        if not text:
            return messagebox.showinfo(
                "Career", "Draft a post first.")
        confirm = messagebox.askyesno(
            "Publish to LinkedIn",
            "Post this text to YOUR LinkedIn profile?\n\n"
            f"{text[:400]}\n\nThis is the only confirmation â€” "
            "Cancel aborts.")
        if not confirm:
            post_status.set("Publish cancelled â€” draft stays saved.")
            return

        def work():
            return ctrl.publish_linkedin_post(text, confirm=True)

        def done(res):
            publish_btn.config(state="normal", text="Publishâ€¦")
            if not res:
                post_status.set("Publish failed â€” draft still saved.")
                return show_error(res)
            post_status.set(f"Published (post {res.payload['post_id']}).")

        run_async(work, done, busy=publish_btn, busy_text="Publishingâ€¦")

    post_btn.configure(command=_do_draft_post)
    publish_btn.configure(command=_do_publish_post)

    # -- Career Campaign (Campaign tier: apply tracking + interview prep) ---
    campaign_frame = ttk.LabelFrame(
        career_tab, text="Career Campaign â€” tracked applications")
    campaign_frame.pack(fill="x", padx=8, pady=4)

    campaign_status_var = tk.StringVar(value="")
    campaign_records: list[dict] = []

    camp_btns = ttk.Frame(campaign_frame)
    camp_btns.pack(fill="x", padx=6, pady=4)
    ttk.Button(camp_btns, text="Refresh campaign",
               command=lambda: _refresh_campaign()).pack(side="left")
    ttk.Button(camp_btns, text="Track selected listing",
               command=lambda: _track_selected()).pack(side="left",
                                                        padx=4)
    adv_combo = ttk.Combobox(camp_btns, width=12, state="readonly",
                             values=["submitted", "screening",
                                     "interviewing", "offer",
                                     "rejected", "withdrawn"])
    adv_combo.set("submitted")
    adv_combo.pack(side="left", padx=(10, 2))
    ttk.Button(camp_btns, text="Advance â†’",
               command=lambda: _advance_selected()).pack(side="left",
                                                          padx=2)
    ttk.Button(camp_btns, text="Interview prep",
               command=lambda: _prep_selected()).pack(side="left",
                                                      padx=8)
    tk.Label(camp_btns, textvariable=campaign_status_var,
             fg="gray").pack(side="left", padx=6)

    camp_cols = ("company", "title", "status", "updated")
    camp_tree = ttk.Treeview(campaign_frame, columns=camp_cols,
                             show="headings", height=5)
    for col, label, w in [("company", "Company", 130),
                          ("title", "Title", 200),
                          ("status", "Status", 100),
                          ("updated", "Updated", 150)]:
        camp_tree.heading(col, text=label)
        camp_tree.column(col, width=w, anchor="w")
    camp_tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _refresh_campaign():
        res = ctrl.campaign_status()
        if not res:
            return show_error(res)
        data = res.payload
        campaign_records.clear()
        camp_tree.delete(*camp_tree.get_children())
        for rec in data.get("records", []):
            listing = rec.get("listing") or {}
            campaign_records.append(rec)
            camp_tree.insert("", "end", values=(
                listing.get("company", "?"), listing.get("title", "?"),
                rec.get("status", "?"), rec.get("updated_at", "")))
        counts = data.get("counts") or {}
        active = (f"{counts.get('prepared', 0)} prepared, "
                  f"{counts.get('submitted', 0)} submitted, "
                  f"{counts.get('interviewing', 0)} interviewing, "
                  f"{counts.get('offer', 0)} offers")
        campaign_status_var.set(
            f"{data.get('open', 0)} open â€” {active}")

    def _selected_campaign_listing() -> Optional[dict]:
        sel = camp_tree.selection()
        if not sel:
            messagebox.showinfo("Career Campaign",
                                "Select an application in the campaign "
                                "table first (run a search and Track, or "
                                "Prepare an application).")
            return None
        rec = campaign_records[camp_tree.index(sel[0])]
        return rec.get("listing") or {}

    def _track_selected():
        if job_tree is not None and job_tree.selection():
            idx = job_tree.index(job_tree.selection()[0])
            listing = job_results_var[idx] if idx < len(job_results_var) \
                else None
            if not listing:
                return
            res = ctrl.campaign_track(listing)
            if not res:
                return show_error(res)
            search_status.set(f"Tracking {listing.get('company')} â€” "
                              f"{res.payload.get('status')}")
            _refresh_campaign()
            return
        messagebox.showinfo("Career Campaign",
                            "Select a listing in the Job Search results "
                            "first, then Track.")

    def _advance_selected():
        listing = _selected_campaign_listing()
        if not listing:
            return

        def work():
            return ctrl.campaign_advance(listing, adv_combo.get())

        def done(res):
            if not res:
                return show_error(res)
            campaign_status_var.set(
                f"Moved to {res.payload.get('status')} â€” "
                f"{res.payload.get('listing', {}).get('company', '?')}")
            _refresh_campaign()

        run_async(work, done)

    def _prep_selected():
        listing = _selected_campaign_listing()
        if not listing:
            return
        if not current_resume:
            return messagebox.showinfo(
                "Career Campaign",
                "Generate or upload a resume first â€” interview prep "
                "is grounded in your real experience.")

        def work():
            return ctrl.campaign_generate_interview_prep(
                listing, current_resume[0])

        def done(res):
            if not res:
                return show_error(res)
            prep = res.payload["prep"]
            out.delete("1.0", "end")
            out.insert("end", f"INTERVIEW PREP â€” "
                        f"{prep.get('company')}: "
                        f"{prep.get('role')}\n{'=' * 60}\n\n")
            out.insert("end", "LIKELY QUESTIONS:\n")
            for i, q in enumerate(prep.get("likely_questions", []), 1):
                out.insert("end", f"\n{i}. {q.get('question')}\n"
                            f"   -> {q.get('how_to_answer')}\n")
            out.insert("end", "\nYOUR STORY BANK:\n")
            for s in prep.get("story_bank", []):
                out.insert("end", f"\n* {s.get('strength')}\n"
                            f"  {s.get('story')}\n")
            out.insert("end", "\nQUESTIONS TO ASK THEM:\n")
            for q in prep.get("questions_to_ask", []):
                out.insert("end", f"- {q}\n")
            campaign_status_var.set(
                f"Interview prep saved -> {res.payload['path']} "
                "(shown above)")

        run_async(work, done)

    _refresh_campaign()

    # -- define the helper functions ----------------------------------------
    def _render_resume_view(resume: dict, changes=None):
        out.delete("1.0", "end")
        c = resume.get("contact", {})
        out.insert("end",
                   f"{c.get('name', '')}  <{c.get('email', '')}>\n"
                   f"{'-' * 60}\n{resume.get('summary', '')}\n\n")
        for x in resume.get("experience", []):
            out.insert("end",
                       f"* {x.get('title')} @ {x.get('company')} "
                       f"({x.get('dates')})\n"
                       f"  {x.get('description')}\n")
        out.insert("end",
                   f"\nSkills: {', '.join(resume.get('skills', []))}\n")
        if changes is not None:
            out.insert("end",
                       f"\n{'=' * 60}\n"
                       f"CHANGES MADE ({len(changes)}):\n")
            for ch in changes:
                out.insert("end",
                           f"  [{ch.get('field')}] {ch.get('change')}\n"
                           f"      why: {ch.get('reason')}\n")

    def do_generate_resume():
        def work():
            return ctrl.generate_resume(profile_text.get("1.0", "end"))

        def done(res):
            gen_resume_btn.config(state="normal", text="Generate resume")
            if not res:
                return show_error(res)
            current_resume.clear()
            current_resume.append(res.payload["resume"])
            career_status.set(
                f"Saved -> resumes/{res.payload['saved_as']}. "
                "Now set a Target Role and Enhance, or export.")
            _render_resume_view(res.payload["resume"])
            _refresh_license()

        run_async(work, done, busy=gen_resume_btn,
                  busy_text="Generatingâ€¦")

    def do_enhance_resume():
        if not current_resume:
            return messagebox.showinfo(
                "Career",
                "Generate a resume first (or this session has none).")

        def work():
            return ctrl.enhance_resume(current_resume[0], role_var.get())

        def done(res):
            enhance_btn.config(state="normal",
                               text="Enhance for target role")
            if not res:
                return show_error(res)
            current_resume.clear()
            current_resume.append(res.payload["resume"])
            career_status.set(
                f"Enhanced -> resumes/{res.payload['saved_as']}")
            _render_resume_view(res.payload["resume"],
                                res.payload["changes"])

        run_async(work, done, busy=enhance_btn, busy_text="Enhancingâ€¦")

    def do_export_resume(fmt: str):
        if not current_resume:
            return messagebox.showinfo(
                "Career", "Generate a resume first.")
        res = ctrl.export_artifact(current_resume[0], fmt)
        if not res:
            return show_error(res)
        base = self_slug(role_var.get() or "resume")
        saved = ctrl.save_raw_export(res.payload, f"{base}.{fmt}")
        if saved:
            career_status.set(
                f"Exported {fmt.upper()} -> exports/{base}.{fmt}")

    def self_slug(t):
        return "".join(
            c if c.isalnum() else "-" for c in t.lower()
        ).strip("-")[:40] or "resume"

    def _do_upload_resume():
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            filetypes=[("Resume", "*.pdf *.docx *.txt"),
                       ("All", "*")])
        if not path:
            return
        res = ctrl.upload_resume(path)
        if not res:
            return show_error(res)
        current_resume.clear()
        current_resume.append(res.payload["resume"])
        flags = "\n".join(
            res.payload["flags"]
        ) or "(all fields high confidence)"
        career_status.set(
            f"Uploaded -> {res.payload['saved_as']}.\n"
            f"Confidence flags:\n{flags}")
        _render_resume_view(res.payload["resume"])

    def _do_import_github():
        if not current_resume:
            return messagebox.showinfo(
                "Career",
                "Generate or upload a resume first.")
        if not gh_user.get().strip():
            return messagebox.showinfo("Career",
                                       "Enter your GitHub username first.")

        def work():
            return ctrl.import_github_projects(
                gh_user.get(), current_resume[0])

        def done(res):
            gh_btn.config(state="normal", text="Import GitHub")
            if not res:
                gh_status.set("import failed â€” see dialog")
                return show_error(res)
            current_resume.clear()
            current_resume.append(res.payload["resume"])
            cached = " (from memory â€” offline)" if res.payload.get("cached") \
                else ""
            gh_status.set(f"Imported {res.payload['imported']} "
                          f"repos{cached}")
            career_status.set(
                f"GitHub: {res.payload['imported']} projects added"
                f"{cached}. Username and projects are remembered.")
            _render_resume_view(res.payload["resume"])

        gh_status.set("Importing from GitHubâ€¦")
        run_async(work, done, busy=gh_btn, busy_text="Importingâ€¦")

    def _do_linkedin():
        if not current_resume:
            return messagebox.showinfo(
                "Career",
                "Generate or upload a resume first.")

        def work():
            return ctrl.fetch_linkedin_profile(current_resume[0])

        def done(res):
            li_btn.config(state="normal", text="Connect LinkedIn")
            if not res:
                li_status.set("not connected")
                return show_error(res)
            current_resume.clear()
            current_resume.append(res.payload["resume"])
            cached = " (from memory)" if res.payload.get("cached") else ""
            li_status.set(f"LinkedIn: {res.payload['who']}{cached}")
            career_status.set(
                f"LinkedIn profile connected: {res.payload['who']}{cached}")
            _render_resume_view(res.payload["resume"])

        li_status.set("Connectingâ€¦")
        run_async(work, done, busy=li_btn, busy_text="Connectingâ€¦")

    # -- wire the action buttons (functions now exist) ----------------------
    career_btns = ttk.Frame(career_top)
    career_btns.pack(fill="x", pady=(4, 2))
    gen_resume_btn = ttk.Button(career_btns, text="Generate resume",
                                command=do_generate_resume)
    gen_resume_btn.pack(side="left")
    enhance_btn = ttk.Button(career_btns, text="Enhance for target role",
                             command=do_enhance_resume)
    enhance_btn.pack(side="left", padx=6)
    for fmt in ("pdf", "docx"):
        ttk.Button(career_btns, text=f"Export {fmt.upper()}",
                   command=lambda f=fmt: do_export_resume(f)).pack(
            side="left", padx=4)

    # rewire upload button
    for child in upload_row.winfo_children():
        if isinstance(child, ttk.Button):
            child.configure(command=_do_upload_resume)

    # rewire connection buttons
    gh_btn.configure(command=_do_import_github)
    li_btn.configure(command=_do_linkedin)


    # -- final wiring --------------------------------------------------------
    # Focus order (owner directive 2026-09-05): Language Lab first (the
    # flagship), Career second, Playground third; frozen sections last.
    for index, tab_widget in enumerate((lab_tab, career_tab,
                                        playground_tab, journey_tab,
                                        studio_tab)):
        tab.insert(index, tab_widget)
    tab.select(0)  # Language Lab â€” the app's flagship opens first
    root.after(100, _poll_results)
    refresh_health()
    inbox_note.config(text=f"inbox: {ctrl.default_inbox_path()}")
    refresh_canvas()
    if names_res.ok and names_res.payload:
        connector_var.set(names_res.payload[0])  # fires capability render
    root.mainloop()


if __name__ == "__main__":
    run()



