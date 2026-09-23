# desktop-shell/skills_ui.py
#
# WHAT: The Skills Arena UI — the Playground Paradise rebuilt for
#       practicing the four language skills with your own material:
#       Reading (import txt/PDF/DOCX -> graded pack), Writing (prompt
#       bank + free topic -> rubric eval + corrected version),
#       Listening (import audio -> transcript + questions), and the
#       speaking door pointing at Mr./Mrs. E.T. (interviews included).
#       The legacy media canvas + connectors stay, untouched, right
#       below — the Arena ADDS, never removes.
# WHY:  Owner directive 2026-09-06: the Playground must match the new
#       Language Lab, practice reading/writing/listening/speaking
#       with files/media/text interactively, mock interviews via
#       "just ask Mr. E.T.", and let users choose where/how to save
#       (format dropdown + file dialog). Presentation only; behavior
#       lives in controller flows; everything async (never freezes).
# BREAKS IF DELETED: The Playground reverts to media-only — the
#       four-skills promise vanishes from the app.

from __future__ import annotations

from typing import Any


def build_skills_arena(parent, *, ctrl, run_async, show_error,
                       open_path, language_getter, level_getter,
                       jump_to_et=None) -> dict[str, Any]:
    """Mount the Skills Arena into `parent` (the Playground tab)."""
    import tkinter as tk
    from tkinter import filedialog, ttk

    frame = ttk.LabelFrame(
        parent, text="🏟️ Skills Arena — practice reading, writing, "
                     "listening & speaking with your own material")
    frame.pack(fill="x", padx=8, pady=6)

    state: dict[str, Any] = {}

    # -- shared header ----------------------------------------------------
    header = ttk.Frame(frame)
    header.pack(fill="x", padx=6, pady=4)
    status_var = tk.StringVar(
        value="Four skills, one arena. Import your own files — "
              "everything stays on this machine.")
    tk.Label(header, textvariable=status_var, fg="gray",
             wraplength=900, justify="left").pack(anchor="w")
    quota_label = tk.Label(header, text="", fg="gray")
    quota_label.pack(anchor="w")

    def _refresh_quota():
        quota = ctrl.licenses.quota("writing_eval")
        if quota.remaining is not None:
            quota_label.config(
                text=f"Writing evaluations: {quota.remaining}/"
                     f"{quota.limit} left this week")
        else:
            quota_label.config(text="Writing evaluations: unlimited")

    def _set_status(text: str) -> None:
        status_var.set(text)

    def _lang() -> str:
        return (language_getter() or "es")[:2]

    def _level() -> str:
        level = (level_getter() or "beginner").lower()
        return {"beginner": "a1", "intermediate": "b1",
                "advanced": "c1"}.get(level, level if level in
                                       ("a1", "a2", "b1", "b2", "c1")
                                       else "a2")

    # ================= READING ==========================================
    reading = ttk.LabelFrame(frame, text="📖 Reading — import a "
                                        "document, get a graded pack")
    reading.pack(fill="x", padx=6, pady=4)
    read_row = ttk.Frame(reading)
    read_row.pack(fill="x", padx=6, pady=4)
    read_btn = ttk.Button(read_row, text="Choose file (txt / PDF / "
                                          "DOCX)…")
    read_btn.pack(side="left")

    def _do_reading():
        path = filedialog.askopenfilename(
            parent=frame, title="Choose a document to read",
            filetypes=[("Documents", "*.txt *.pdf *.docx"),
                       ("All files", "*.*")])
        if not path:
            return
        _set_status(f"📖 Reading {path.split('/')[-1]}… building "
                    "glossary + comprehension questions (a few "
                    "minutes — the window stays alive)")

        def work():
            return ctrl.skills_reading_from_file(path, _lang(),
                                                 _level())

        def done(res):
            if not res:
                _set_status("Reading pack failed — see dialog.")
                return show_error(res)
            _set_status(f"📖 Reading pack saved -> {res.payload['path']}"
                        " — opening")
            open_path(str(res.payload["path"]))

        run_async(work, done)

    read_btn.config(command=_do_reading)

    # ================= WRITING ===========================================
    writing = ttk.LabelFrame(frame, text="✍️ Writing — write, get "
                                         "graded + a corrected version")
    writing.pack(fill="x", padx=6, pady=4)
    write_prompt_row = ttk.Frame(writing)
    write_prompt_row.pack(fill="x", padx=6, pady=(4, 0))
    ttk.Label(write_prompt_row, text="Task").pack(side="left")
    task_var = tk.StringVar(
        value="Describe your typical day — morning to night.")
    ttk.Combobox(write_prompt_row, textvariable=task_var, width=60,
                 values=[
                     "Describe your typical day — morning to night.",
                     "Write a short review of a restaurant you love.",
                     "An email to your landlord about a repair.",
                     "Your opinion: should work be 4 days a week?",
                     "(free topic — write whatever you want)",
                 ]).pack(side="left", padx=4)
    write_text = tk.Text(writing, height=6, width=110)
    write_text.pack(fill="x", padx=6, pady=4)
    write_btn_row = ttk.Frame(writing)
    write_btn_row.pack(fill="x", padx=6, pady=(0, 4))
    write_btn = ttk.Button(write_btn_row, text="✍️ Evaluate my writing")
    write_btn.pack(side="left")

    def _do_writing():
        text = write_text.get("1.0", "end").strip()
        if len(text.split()) < 10:
            _set_status("Write a little more first — even three "
                        "sentences gives the coach something to "
                        "praise.")
            return

        def work():
            return ctrl.skills_writing_submit(
                task_var.get(), text, _lang(), _level())

        def done(res):
            write_btn.config(state="normal", text="✍️ Evaluate my "
                                                  "writing")
            if not res:
                _set_status("Writing evaluation unavailable — see "
                            "dialog.")
                return show_error(res)
            evaluation = res.payload["evaluation"]
            summary = " · ".join(f"{k[:3].upper()} {evaluation[k]}/5"
                                 for k in ("grammar", "vocabulary",
                                           "structure", "register"))
            fixed = "\n".join(
                f"✏️ {h['wrong']} → {h['right']} ({h['why']})"
                for h in evaluation.get("highlights") or [])
            _set_status(
                f"💪 {evaluation['strength']}\n"
                f"[{summary}]  next step: {evaluation['next_step']}\n"
                f"Corrected version:\n{evaluation['corrected_text']}\n"
                f"{fixed}\nSaved to your exports.")
            _refresh_quota()

        write_btn.config(state="disabled", text="Grading…")
        run_async(work, done, busy=write_btn, busy_text="Grading…")

    write_btn.config(command=_do_writing)

    # ================= LISTENING =========================================
    listening = ttk.LabelFrame(
        frame, text="🎧 Listening — import audio, get transcript + "
                    "questions")
    listening.pack(fill="x", padx=6, pady=4)
    listen_row = ttk.Frame(listening)
    listen_row.pack(fill="x", padx=6, pady=4)
    listen_btn = ttk.Button(listen_row, text="Choose audio file "
                                              "(wav / mp3 / m4a)…")
    listen_btn.pack(side="left")

    def _do_listening():
        path = filedialog.askopenfilename(
            parent=frame, title="Choose an audio file",
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.ogg *.flac"),
                       ("All files", "*.*")])
        if not path:
            return
        _set_status("🎧 Transcribing your audio with E.T.'s ears, "
                    "then writing questions about it…")

        def work():
            return ctrl.skills_listening_from_file(path, _lang(),
                                                   _level())

        def done(res):
            if not res:
                _set_status("Listening pack failed — see dialog.")
                return show_error(res)
            _set_status(
                f"🎧 Listening pack saved -> {res.payload['path']} "
                "(transcript inside, questions interactive) — "
                "opening")
            open_path(str(res.payload["path"]))

        run_async(work, done)

    listen_btn.config(command=_do_listening)

    # ================= SPEAKING ==========================================
    speaking = ttk.LabelFrame(
        frame, text="🎙 Speaking — this is Mr. & Mrs. E.T.'s room "
                    "(interviews, roleplays, drills)")
    speaking.pack(fill="x", padx=6, pady=4)
    speak_row = ttk.Frame(speaking)
    speak_row.pack(fill="x", padx=6, pady=4)
    speak_note = tk.Label(
        speak_row, text="Voice practice lives with E.T. in the "
                       "Language Lab: 33 scenarios, mock job "
                       "interviews, support-call roleplays — record, "
                       "get evaluated, converse.", fg="gray",
        wraplength=880, justify="left")
    speak_note.pack(side="left", fill="x", expand=True)
    if jump_to_et:
        ttk.Button(speak_row, text="Go talk to E.T. →",
                   command=jump_to_et).pack(side="left", padx=6)

    _refresh_quota()
    state.update({"frame": frame, "status": status_var,
                  "refresh_quota": _refresh_quota})
    return state
