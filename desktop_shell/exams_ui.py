# desktop-shell/exams_ui.py
#
# WHAT: The Exams panel — the inclusive final test per level: start
#       an exam (A1..C1), answer the six sections interactively
#       (vocabulary/grammar/reading MC, writing textarea, listening
#       with audio player, speaking via E.T.'s mic), submit, and see
#       the full evaluation + recommendations. Plus the placement
#       quiz card and past results.
# WHY:  Owner directive 2026-09-06: one inclusive final test after
#       each level, testing all six skills with full evaluations and
#       recommendations. Presentation only — engine in level_exam.py,
#       seam in controller. Async everywhere; honest cooking status.
# BREAKS IF DELETED: Levels have no summit — the journey has no
#       milestones and no proof of progress.

from __future__ import annotations

from typing import Any


def build_exams_panel(parent, *, ctrl, run_async, show_error,
                      open_path, play_audio, language_getter,
                      record_turn=None) -> dict[str, Any]:
    """Mount the Exams panel into `parent` (Language Lab tab).

    record_turn: optional callable(language) -> (wav_bytes | None)
        supplied by the app to reuse E.T.'s mic capture for the
        speaking section; None = speaking answers typed.
    """
    import tkinter as tk
    from tkinter import ttk

    frame = ttk.LabelFrame(parent, text="🎓 Level exams — prove "
                                        "your level, get the "
                                        "verdict")
    frame.pack(fill="x", padx=8, pady=6)

    state: dict[str, Any] = {"exam": None, "answers": {},
                              "results_shown": False}

    status_var = tk.StringVar(
        value="One inclusive exam per level: vocabulary · grammar · "
              "reading · writing · listening · speaking. 70% to "
              "pass, full evaluation + recommendations either way.")
    tk.Label(frame, textvariable=status_var, fg="gray",
             wraplength=900, justify="left").pack(anchor="w",
                                                  padx=6, pady=2)

    # -- placement card ----------------------------------------------------
    placement_row = ttk.Frame(frame)
    placement_row.pack(fill="x", padx=6, pady=2)
    ttk.Label(placement_row, text="New here?").pack(side="left")
    ttk.Button(placement_row,
               text="Take the 10-minute placement quiz").pack(
        side="left", padx=6)
    placement_result_var = tk.StringVar(value="")
    tk.Label(placement_row, textvariable=placement_result_var,
             fg="#1e5a48").pack(side="left", padx=8)

    # -- exam picker ---------------------------------------------------------
    picker = ttk.Frame(frame)
    picker.pack(fill="x", padx=6, pady=2)
    ttk.Label(picker, text="Level").pack(side="left")
    level_var = tk.StringVar(value="a1")
    ttk.Combobox(picker, textvariable=level_var, state="readonly",
                 width=5, values=["a1", "a2", "b1", "b2",
                                  "c1"]).pack(side="left", padx=4)
    start_btn = ttk.Button(picker, text="Start exam")
    start_btn.pack(side="left", padx=6)
    results_btn = ttk.Button(picker, text="Past results")
    results_btn.pack(side="left", padx=6)

    # -- workspace (exam body or results) ------------------------------------
    body = ttk.Frame(frame)
    body.pack(fill="both", expand=True, padx=6, pady=4)

    def _clear_body():
        for widget in body.winfo_children():
            widget.destroy()

    # ================= placement =========================================
    def _do_placement():
        language = language_getter()
        _set_status("⏳ Generating your placement quiz (12 quick "
                    "questions, A1→B1)…")

        def work():
            return ctrl.placement_start(language)

        def done(res):
            if not res:
                return show_error(res)
            quiz = res.payload
            _run_placement_quiz(quiz)

        run_async(work, done)

    def _run_placement_quiz(quiz):
        _clear_body()
        chosen: list[int] = []

        ttk.Label(body, text="Placement — pick the best answer for "
                             "each. No pressure, no score shown "
                             "until the end.").pack(anchor="w")
        scroll = ttk.Frame(body)
        scroll.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll, height=260)
        scrollbar = ttk.Scrollbar(scroll, orient="vertical",
                                  command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for i, item in enumerate(quiz["items"]):
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=f"{i + 1}. {item['question']}",
                      wraplength=760).pack(anchor="w")
            choice = tk.StringVar(value="")
            chosen.append(-1)

            def _pick(index, value, _i=i):
                chosen[_i] = value
            for oi, option in enumerate(item["options"]):
                ttk.Radiobutton(
                    row, text=option, variable=choice, value=oi,
                    command=lambda _i=i, _oi=oi: _pick(_i, _oi)
                ).pack(anchor="w", padx=16)

        def _grade():
            if any(c < 0 for c in chosen):
                _set_status("Answer all 12 — guessing is allowed "
                            "and costs nothing.")
                return

            def work():
                return ctrl.placement_grade(language_getter(),
                                             chosen)

            def done(res):
                if not res:
                    return show_error(res)
                result = res.payload
                placement_result_var.set(
                    f"Placed at {result['band'].upper()} — "
                    f"{result['rationale']}")
                _set_status(
                    f"🎯 You placed at {result['band'].upper()} "
                    f"({result['correct']}/{result['total']}). "
                    f"{result['rationale']} The library's "
                    "continue-button now points at your level.")

            run_async(work, done)

        ttk.Button(body, text="Grade my placement",
                   command=_grade).pack(pady=6)

    # ================= exam ==============================================
    def _start_exam():
        language = language_getter()
        level = level_var.get()
        _set_status(f"⏳ Writing your complete {level.upper()} exam "
                    "(all six sections — a few minutes on local "
                    "models)…")

        def work():
            return ctrl.level_exam_start(language, level)

        def done(res):
            if not res:
                return show_error(res)
            state["exam"] = res.payload["exam"]
            state["listening_wav"] = res.payload.get("listening_wav")
            _render_exam()

        run_async(work, done)

    def _render_exam():
        exam = state["exam"]
        language = language_getter()
        level = exam["level"]
        _clear_body()
        state["answers"] = {"vocabulary": [-1] * 8,
                             "grammar": {"mc": [-1] * 6,
                                         "fill": [""] * 4},
                             "reading": [-1] * 5,
                             "listening": [-1] * 5}

        # listening audio player
        if state.get("listening_wav"):
            player = ttk.Frame(body)
            player.pack(fill="x", pady=4)
            ttk.Button(player, text="▶ Play listening audio",
                       command=lambda: play_audio(None)).pack(
                side="left")
            ttk.Label(player, text="(listen as many times as you "
                                   "like — real exams play twice; "
                                   "we're kinder)").pack(side="left")

        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)

        def _mc_section(title, items, target_list):
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=title)
            for i, item in enumerate(items):
                row = ttk.Frame(tab)
                row.pack(fill="x", pady=4)
                ttk.Label(row, text=f"{i + 1}. {item['question']}",
                          wraplength=700).pack(anchor="w")

                def _pick(value, _i=i):
                    target_list[_i] = value
                for oi, option in enumerate(item.get("options",
                                                       [])):
                    ttk.Radiobutton(
                        row, text=str(option), value=oi,
                        command=lambda _i=i, _oi=oi: _pick(_oi, _i)
                    ).pack(anchor="w", padx=18)

        _mc_section("Vocabulary", exam["vocabulary"],
                    state["answers"]["vocabulary"])
        # grammar: mc + fill split tabs
        grammar_tab = ttk.Frame(notebook)
        notebook.add(grammar_tab, text="Grammar")
        mc_items = [g for g in exam["grammar"] if g["type"] == "mc"]
        fill_items = [g for g in exam["grammar"]
                      if g["type"] == "fill"]
        for i, item in enumerate(mc_items):
            row = ttk.Frame(grammar_tab)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=f"{i + 1}. {item['question']}",
                      wraplength=700).pack(anchor="w")

            def _pick(value, _i=i):
                state["answers"]["grammar"]["mc"][_i] = value
            for oi, option in enumerate(item.get("options", [])):
                ttk.Radiobutton(
                    row, text=str(option), value=oi,
                    command=lambda _i=i, _oi=oi: _pick(_oi, _i)
                ).pack(anchor="w", padx=18)
        for i, item in enumerate(fill_items):
            row = ttk.Frame(grammar_tab)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=item["sentence_with_blank"]).pack(
                side="left")
            entry = ttk.Entry(row, width=22)

            def _type(_event, _i=i):
                state["answers"]["grammar"]["fill"][_i] = \
                    entry.get()
            entry.bind("<KeyRelease>", _type)
            entry.pack(side="left", padx=6)
        reading_tab = ttk.Frame(notebook)
        notebook.add(reading_tab, text="Reading")
        passage = tk.Text(reading_tab, height=8, width=100,
                          wrap="word")
        passage.insert("1.0", exam["reading"]["passage"])
        passage.config(state="disabled")
        passage.pack(fill="x", padx=4, pady=4)
        for i, item in enumerate(exam["reading"]["questions"]):
            row = ttk.Frame(reading_tab)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=f"{i + 1}. {item['question']}",
                      wraplength=700).pack(anchor="w")

            def _pick(value, _i=i):
                state["answers"]["reading"][_i] = value
            for oi, option in enumerate(item.get("options", [])):
                ttk.Radiobutton(
                    row, text=str(option), value=oi,
                    command=lambda _i=i, _oi=oi: _pick(_oi, _i)
                ).pack(anchor="w", padx=18)

        _mc_section("Listening", exam["listening"]["questions"],
                    state["answers"]["listening"])

        # writing tab
        write_tab = ttk.Frame(notebook)
        notebook.add(write_tab, text="Writing")
        ttk.Label(write_tab, text=exam["writing"]["prompt"],
                  wraplength=700).pack(anchor="w", pady=4)
        ttk.Label(write_tab, text=f"(aim for ~"
                  f"{exam['writing']['min_words']} words)").pack(
            anchor="w")
        write_box = tk.Text(write_tab, height=8, width=100)
        write_box.pack(fill="x", pady=4)

        # speaking tab
        speak_tab = ttk.Frame(notebook)
        notebook.add(speak_tab, text="Speaking")
        speaking_texts: list[dict[str, Any]] = []
        for i, task in enumerate(exam["speaking"]):
            row = ttk.Frame(speak_tab)
            row.pack(fill="x", pady=4)
            label = {"repeat": f'Repeat aloud: "{task["text"]}"',
                     "describe": f'Describe: {task.get("situation")}',
                     "respond": f'Answer aloud: {task.get("prompt")}'}
            ttk.Label(row, text=f"{i + 1}. {label[task['type']]}",
                      wraplength=680).pack(anchor="w")
            entry = ttk.Entry(row, width=70)
            transcript_slot: dict[str, Any] = {"transcript": ""}

            def _type(_event, _slot=transcript_slot, _e=None):
                _slot["transcript"] = entry.get()
            entry.bind("<KeyRelease>", _type)
            entry.pack(anchor="w", padx=18)
            if record_turn is not None:
                def _record(_i=i, _slot=transcript_slot):
                    _set_status(f"🎙 Recording speaking task "
                                f"{_i + 1}… speak now (click stop "
                                "when done)")
                    wav = record_turn(language)
                    if wav:
                        _slot["wav"] = wav
                        _set_status(f"🎤 Task {_i + 1} captured — "
                                    "transcribing…")

                    def work():
                        from engines.audio_engine.stt import (
                            transcribe,
                        )
                        return transcribe(
                            wav, language_getter()).text

                    def done(text):
                        entry.delete(0, "end")
                        entry.insert(0, text)
                        _slot["transcript"] = text
                        _set_status(f"Transcribed: “{text}” — edit "
                                    "if the ears misheard.")
                    run_async(work, done)
                ttk.Button(row, text="🎙 Record",
                           command=_record).pack(side="left",
                                                padx=4)
            speaking_texts.append(transcript_slot)

        # submit bar
        submit_bar = ttk.Frame(body)
        submit_bar.pack(fill="x", pady=6)

        def _submit():
            writing = write_box.get("1.0", "end").strip()
            speaking_tasks = [
                {"transcript": s.get("transcript", ""),
                 "score": None}
                for s in speaking_texts]

            def work():
                return ctrl.level_exam_submit(
                    language_getter(), exam["level"], exam,
                    state["answers"], writing, speaking_tasks)

            def done(res):
                if not res:
                    return show_error(res)
                _render_result(res.payload)

            _set_status("🧠 Grading everything — objective sections "
                        "instantly, writing + speaking by rubric…")
            run_async(work, done)

        ttk.Button(submit_bar, text="Submit exam for grading",
                   command=_submit).pack(side="left")

    def _render_result(result):
        _clear_body()
        state["results_shown"] = True
        overall = result["overall"]
        color = "#2e7d5b" if result["passed"] else "#c08a24"
        header = ttk.Frame(body)
        header.pack(fill="x", pady=4)
        score = tk.Label(header, text=f"{overall}%",
                         font=("", 26, "bold"), fg=color)
        score.pack(side="left", padx=10)
        lines = ttk.Frame(header)
        lines.pack(side="left", fill="x", expand=True)
        tk.Label(lines, text=result["verdict_line"],
                 font=("", 11, "bold"), fg=color,
                 wraplength=700, justify="left").pack(anchor="w")
        sections = " · ".join(
            f"{name} {data['pct']}%"
            for name, data in result["sections"].items())
        tk.Label(lines, text=sections, fg="gray",
                 wraplength=700).pack(anchor="w")

        bands = ttk.Frame(body)
        bands.pack(fill="x", pady=4)
        tk.Label(bands, text="Skill bands: " + " · ".join(
            f"{k.upper()} {v}" for k, v in
            result.get("skill_bands", {}).items()),
            fg="#4d5f56", wraplength=760).pack(anchor="w")

        tk.Label(body, text="Recommendations",
                 font=("", 10, "bold")).pack(anchor="w", pady=(6, 2))
        for tip in result["recommendations"]:
            tk.Label(body, text=f"• {tip}", fg="#4d5f56",
                     wraplength=860, justify="left").pack(anchor="w")

        def _close():
            _clear_body()
            _set_status("Ready for the next exam — or the next "
                        "lesson. The ladder keeps going. 🪜")

        ttk.Button(body, text="Done", command=_close).pack(pady=8)

    def _past_results():
        language = language_getter()

        def work():
            return ctrl.level_exam_results(language)

        def done(res):
            if not res:
                return show_error(res)
            _clear_body()
            results = res.payload
            if not results:
                _set_status("No exam results yet for this language "
                            "— your first {x} is waiting.".format(
                                x=level_var.get().upper()))
                return
            for result in results:
                color = "#2e7d5b" if result.get("passed") else \
                    "#c08a24"
                tk.Label(body,
                         text=f"{result['level'].upper()} — "
                              f"{result['overall']}% "
                              f"({'passed' if result['passed'] else 'retry'})",
                         fg=color, font=("", 10, "bold")).pack(
                    anchor="w", padx=6)
                tk.Label(body, text=result["verdict_line"],
                         fg="gray", wraplength=860,
                         justify="left").pack(anchor="w", padx=6,
                                             pady=(0, 6))

        run_async(work, done)

    def _set_status(text):
        status_var.set(text)

    # wire buttons
    start_btn.config(command=_start_exam)
    results_btn.config(command=_past_results)
    for child in placement_row.winfo_children():
        if isinstance(child, ttk.Button):
            child.config(command=_do_placement)

    state.update({"frame": frame, "status_var": status_var,
                  "refresh": lambda: None})
    return state
