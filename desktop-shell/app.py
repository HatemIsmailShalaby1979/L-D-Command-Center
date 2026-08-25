# desktop-shell/app.py
#
# WHAT: The Tkinter desktop window — a THIN layer over ShellController.
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
    alias("desktop_shell", _ROOT / "desktop-shell")
    for dir_name, mod_name in [
        ("audio-engine", "audio_engine"),
        ("career-engine", "career_engine"),
        ("export-engine", "export_engine"),
        ("journey-core", "journey_core"),
        ("language-lab", "language_lab"),
        ("playground-bridge", "playground_bridge"),
    ]:
        alias(f"engines.{mod_name}", _ROOT / "engines" / dir_name)


_install_source_aliases()

ERROR_TITLES = {
    "no_model": "LM Studio not reachable",
    "bad_output": "Model output rejected",
    "input": "Check your input",
    "connector": "Generation service failed",
    "unexpected": "Unexpected error",
}


def run() -> None:  # pragma: no cover — needs a display
    import logging

    import tkinter as tk
    from tkinter import messagebox, ttk

    from desktop_shell.controller import FlowResult, ShellController

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ctrl = ShellController()
    root = tk.Tk()
    root.title("L&D Command Center")
    root.geometry("860x560")

    def show_error(res: FlowResult):
        messagebox.showerror(ERROR_TITLES.get(res.error_kind, "Error"),
                             res.detail or "Unknown failure.")

    # -- header -----------------------------------------------------------
    status = tk.StringVar(value="checking LM Studio…")
    header = ttk.Frame(root); header.pack(fill="x", padx=8, pady=6)
    health_label = tk.Label(header, textvariable=status, fg="gray")
    health_label.pack(side="left")
    ttk.Button(header, text="Refresh",
               command=lambda: refresh_health()).pack(side="left", padx=6)
    ttk.Button(header, text="Probe model",
               command=lambda: run_probe()).pack(side="left")

    # model picker — the user always sees and chooses what is running
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

    def run_probe():
        status.set("probing model capabilities…")
        health_label.config(fg="gray")
        root.update_idletasks()
        res = ctrl.run_capability_probe()
        if not res:
            return show_error(res)
        refresh_health()

    # -- tabs ---------------------------------------------------------------
    tab = ttk.Notebook(root); tab.pack(fill="both", expand=True, padx=8, pady=6)

    # == Learning Journey ====================================================
    journey_tab = ttk.Frame(tab); tab.add(journey_tab, text="Learning Journey")

    form = ttk.Frame(journey_tab); form.pack(fill="x", pady=4)
    topic_var = tk.StringVar()
    level_var = tk.StringVar(value="beginner")
    cards_var = tk.IntVar(value=5)
    last_journey: list[dict] = []

    ttk.Label(form, text="Topic").grid(row=0, column=0, sticky="w")
    ttk.Entry(form, textvariable=topic_var, width=42).grid(row=0, column=1, padx=4)
    ttk.Label(form, text="Level").grid(row=0, column=2)
    ttk.Combobox(form, textvariable=level_var, width=12, state="readonly",
                 values=["beginner", "intermediate", "advanced"]).grid(row=0, column=3, padx=4)
    ttk.Label(form, text="Cards").grid(row=0, column=4)
    ttk.Spinbox(form, from_=1, to=20, textvariable=cards_var, width=4).grid(row=0, column=5, padx=4)

    output = tk.Text(journey_tab, height=20)
    output.pack(fill="both", expand=True, pady=6)

    def do_generate_journey():
        res = ctrl.generate_journey(topic_var.get(), level_var.get(), cards_var.get())
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
    ttk.Button(actions, text="Generate", command=do_generate_journey).pack(side="left")
    for fmt in ("text", "pdf", "pptx", "xlsx"):
        ttk.Button(actions, text=f"Export {fmt.upper()}",
                   command=lambda f=fmt: do_export(f)).pack(side="left", padx=4)

    # == Language Lab ========================================================
    lab_tab = ttk.Frame(tab); tab.add(lab_tab, text="Language Lab")

    lab_form = ttk.Frame(lab_tab); lab_form.pack(fill="x", pady=4)
    lab_topic = tk.StringVar()
    lab_target = tk.StringVar(value="es")
    lab_known = tk.StringVar(value="en")
    lab_level = tk.StringVar(value="beginner")
    lab_status = tk.StringVar(
        value="Generates ONE validated lesson pack (two-voice dialogue, "
              "vocab flashcards, grammar drills, evaluation) and opens the "
              "interactive HTML in your browser. CPU models may take a few "
              "minutes — watch the health bar.")
    ttk.Label(lab_form, text="Topic").grid(row=0, column=0, sticky="w")
    ttk.Entry(lab_form, textvariable=lab_topic, width=30).grid(row=0, column=1,
                                                               padx=4)
    for i, (label, var) in enumerate((("Target", lab_target),
                                      ("Known", lab_known)), start=2):
        ttk.Label(lab_form, text=label).grid(row=0, column=i)
        ttk.Combobox(lab_form, textvariable=var, width=5, state="readonly",
                     values=["en", "es", "fr", "de", "it", "pt", "ru",
                             "zh"]).grid(row=0, column=i + 1, padx=4)
    ttk.Label(lab_form, text="Level").grid(row=0, column=6)
    ttk.Combobox(lab_form, textvariable=lab_level, width=11,
                 state="readonly",
                 values=["beginner", "intermediate", "advanced"]).grid(
        row=0, column=7, padx=4)

    def do_lesson_pack():
        topic = lab_topic.get().strip()
        if not topic:
            return messagebox.showinfo("Language Lab", "Enter a topic first.")
        lab_status.set(f"Generating lesson pack for '{topic}'… "
                       "(one guardrailed generation; please wait)")
        health_label.config(fg="gray")
        root.update_idletasks()
        res = ctrl.generate_lesson_pack(topic, lab_target.get(),
                                        lab_known.get(), lab_level.get())
        if not res:
            lab_status.set("Generation failed.")
            return show_error(res)
        import subprocess
        lab_status.set(f"Saved -> {res.payload}  (opening…)")
        root.update_idletasks()
        subprocess.Popen(["xdg-open", str(res.payload)],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    lab_actions = ttk.Frame(lab_tab); lab_actions.pack(fill="x", pady=4)
    ttk.Button(lab_actions, text="Generate lesson pack",
               command=do_lesson_pack).pack(side="left")
    tk.Label(lab_tab, textvariable=lab_status, fg="gray",
             wraplength=760, justify="left").pack(anchor="w", pady=8)

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

    def do_connector_generate():
        prompt = prompt_var.get().strip()
        if not prompt:
            return messagebox.showinfo("Playground", "Enter a prompt first.")
        output_note.set("working…")
        root.update_idletasks()
        res = ctrl.run_connector_job(connector_var.get(), {"prompt": prompt})
        if not res:
            output_note.set("")
            return show_error(res)
        refresh_canvas()
        output_note.set(
            f"Saved -> media/generated/{res.payload['artifact_name']}")

    canvas_bar = ttk.Frame(playground_tab); canvas_bar.pack(fill="x", pady=4)
    ttk.Button(canvas_bar, text="Import files…",
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

    conn_frame = ttk.LabelFrame(playground_tab, text="Connectors (free tiers)")
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
    ttk.Button(conn_frame, text="Generate",
               command=do_connector_generate).pack(side="left")
    output_note = tk.StringVar()
    tk.Label(conn_frame, textvariable=output_note,
             fg="green").pack(side="left", padx=6)
    info = tk.Text(conn_frame, height=4, width=80)
    info.pack(fill="x", padx=4, pady=4)

    # == Audio Studio ========================================================
    studio_tab = ttk.Frame(tab); tab.add(studio_tab, text="Audio Studio")

    LANG_CODES = ["en", "es", "fr", "de", "it", "pt", "ru", "zh"]

    def _open_path(path: str):
        import subprocess
        subprocess.Popen(["xdg-open", path],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    # --- audiobooks ---
    ab_frame = ttk.LabelFrame(studio_tab, text="Audiobook — text to narrated audio")
    ab_frame.pack(fill="x", padx=6, pady=6)
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
    ab_status = tk.StringVar(value="Paste any text — narrated WAV + MP3 land in exports.")
    tk.Label(ab_frame, textvariable=ab_status, fg="gray",
             wraplength=700, justify="left").grid(row=3, column=0,
                                                  columnspan=4, sticky="w")

    def do_audiobook():
        text = ab_text.get("1.0", "end").strip()
        if not text:
            return messagebox.showinfo("Audio Studio", "Paste some text first.")
        ab_status.set(f"Narrating {len(text)} characters…")
        root.update_idletasks()
        voice = None if ab_voice.get().startswith("(") \
            else ab_voice.get().split("   ")[0]
        res = ctrl.generate_audiobook(text, ab_lang.get(),
                                      float(ab_speed.get()), voice)
        if not res:
            ab_status.set("Audiobook failed.")
            return show_error(res)
        ab_status.set(f"Done ({res.payload['duration_seconds']}s, "
                      f"{res.payload['voice']}). Opening player…")
        _open_path(res.payload["mp3"] or res.payload["wav"])

    ttk.Button(ab_frame, text="Generate audiobook",
               command=do_audiobook).grid(row=4, column=0, sticky="w", pady=4)

    # --- podcasts ---
    pod_frame = ttk.LabelFrame(studio_tab, text="Podcast — topic to two-voice episode")
    pod_frame.pack(fill="x", padx=6, pady=6)
    pod_row1 = ttk.Frame(pod_frame); pod_row1.pack(fill="x", pady=2)
    ttk.Label(pod_row1, text="Topic").pack(side="left")
    pod_topic = tk.StringVar()
    ttk.Entry(pod_row1, textvariable=pod_topic, width=34).pack(side="left", padx=4)
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
                       "voices… (a few minutes)")
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
        pod_status.set(f"'{res.payload['title']}' ready — "
                       f"{res.payload['segments']} segments, "
                       f"voices: {', '.join(res.payload['speakers'])}, "
                       f"{res.payload['duration_seconds']}s. Opening player…")
        _open_path(res.payload["mp3"] or res.payload["wav"])

    ttk.Button(pod_frame, text="Generate podcast",
               command=do_podcast).pack(anchor="w", pady=4)

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
        vm_status.set(f"Downloading {vid}… (~70 MB, one time)")
        root.update_idletasks()
        res = ctrl.download_voice(vid.split("   ")[0])
        if not res:
            vm_status.set("Download failed.")
            return show_error(res)
        global installed  # noqa — refresh local lists via closure recompute
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
    ttk.Button(conn_row, text="Import GitHub",
               command=lambda: None).pack(side="left", padx=4)
    tk.Label(conn_row, textvariable=gh_status, fg="gray").pack(side="left")

    ttk.Label(conn_row, text="  |  ").pack(side="left")
    li_status = tk.StringVar(value="")
    ttk.Button(conn_row, text="Connect LinkedIn",
               command=lambda: None).pack(side="left", padx=4)
    tk.Label(conn_row, textvariable=li_status, fg="gray").pack(side="left")

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
        res = ctrl.search_jobs_now(
            search_role.get(), search_loc.get(),
            greenhouse_companies="stripe,figma,ashbygames,cohere,"
                                 "vercel,linear,posthog,superhuman",
            lever_companies="gitlab,posthog",
            ashby_companies="vercel,linear,posthog")
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

    search_btns = ttk.Frame(search_frame)
    search_btns.pack(fill="x", padx=6, pady=2)
    ttk.Button(search_btns, text="Search now",
               command=_do_search).pack(side="left", padx=4)
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
        res = ctrl.prepare_application(listing, current_resume[0])
        if not res:
            return show_error(res)
        pkg = res.payload
        search_status.set(f"Package ready -> {pkg['dir']}")
        career_status.set(
            f"Application package ready for "
            f"{listing.get('company')}.\n"
            f"Files: {', '.join(pkg['files'])}\n"
            f"Apply URL: {pkg['apply_url']}\n"
            f"Open folder and submit manually — bots get banned.")

    ttk.Button(search_btns, text="Prepare application",
               command=_do_prepare_application).pack(side="left", padx=4)
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
            greenhouse_companies="stripe,figma,ashbygames,cohere,"
                                 "vercel,linear,posthog,superhuman",
            lever_companies="gitlab,posthog",
            ashby_companies="vercel,linear,posthog")
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
        res = ctrl.generate_resume(profile_text.get("1.0", "end"))
        if not res:
            return show_error(res)
        current_resume.clear()
        current_resume.append(res.payload["resume"])
        career_status.set(
            f"Saved -> resumes/{res.payload['saved_as']}. "
            "Now set a Target Role and Enhance, or export.")
        _render_resume_view(res.payload["resume"])

    def do_enhance_resume():
        if not current_resume:
            return messagebox.showinfo(
                "Career",
                "Generate a resume first (or this session has none).")
        res = ctrl.enhance_resume(current_resume[0], role_var.get())
        if not res:
            return show_error(res)
        current_resume.clear()
        current_resume.append(res.payload["resume"])
        career_status.set(
            f"Enhanced -> resumes/{res.payload['saved_as']}")
        _render_resume_view(res.payload["resume"],
                            res.payload["changes"])

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
        res = ctrl.import_github_projects(
            gh_user.get(), current_resume[0])
        if not res:
            return show_error(res)
        current_resume.clear()
        current_resume.append(res.payload["resume"])
        gh_status.set(
            f"Imported {res.payload['imported']} repos")
        career_status.set(
            f"GitHub: {res.payload['imported']} projects added.")
        _render_resume_view(res.payload["resume"])

    def _do_linkedin():
        if not current_resume:
            return messagebox.showinfo(
                "Career",
                "Generate or upload a resume first.")
        res = ctrl.fetch_linkedin_profile(current_resume[0])
        if not res:
            return show_error(res)
        current_resume.clear()
        current_resume.append(res.payload["resume"])
        li_status.set(f"LinkedIn: {res.payload['who']}")
        career_status.set(
            f"LinkedIn profile connected: {res.payload['who']}")
        _render_resume_view(res.payload["resume"])

    # -- wire the action buttons (functions now exist) ----------------------
    career_btns = ttk.Frame(career_top)
    career_btns.pack(fill="x", pady=(4, 2))
    ttk.Button(career_btns, text="Generate resume",
               command=do_generate_resume).pack(side="left")
    ttk.Button(career_btns, text="Enhance for target role",
               command=do_enhance_resume).pack(side="left", padx=6)
    for fmt in ("pdf", "docx"):
        ttk.Button(career_btns, text=f"Export {fmt.upper()}",
                   command=lambda f=fmt: do_export_resume(f)).pack(
            side="left", padx=4)

    # rewire upload button
    for child in upload_row.winfo_children():
        if isinstance(child, ttk.Button):
            child.configure(command=_do_upload_resume)

    # rewire connection buttons
    for child in conn_row.winfo_children():
        if isinstance(child, ttk.Button):
            if child.cget("text") == "Import GitHub":
                child.configure(command=_do_import_github)
            elif child.cget("text") == "Connect LinkedIn":
                child.configure(command=_do_linkedin)


    # -- final wiring --------------------------------------------------------
    refresh_health()
    inbox_note.config(text=f"inbox: {ctrl.default_inbox_path()}")
    refresh_canvas()
    if names_res.ok and names_res.payload:
        connector_var.set(names_res.payload[0])  # fires capability render
    root.mainloop()


if __name__ == "__main__":
    run()
