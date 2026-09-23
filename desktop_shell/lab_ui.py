# desktop-shell/lab_ui.py
#
# WHAT: The Language Lab curriculum library UI — the home + library
#       views per the owner's webapp blueprint: level cards grid with
#       progress, lesson-slot list, generate/open/share per slot,
#       placement card, continue-learning pointer, and the Exams home
#       (L5 plugs in here).
# WHY:  Project E.T. L4. Presentation only — all behavior lives in
#       controller flows; imported lazily by app.py (headless suites
#       never touch Tk). The catalog renders instantly for all 15
#       languages; generation buttons show the honest cooking status.
# BREAKS IF DELETED: The library is a data structure without a face —
#       users lose the "ground to start from" the whole plan promises.

from __future__ import annotations

from typing import Any, Callable, Optional


def build_library_panel(parent, *, ctrl, run_async, show_error,
                        open_path, language_getter, level_getter,
                        on_language_change=None) -> dict[str, Any]:
    """Mount the curriculum library into `parent` (Language Lab tab).

    language_getter(): returns the current target language code.
    level_getter(): returns the currently selected CEFR level hint.
    Returns the panel state (for tests / external refresh).
    """
    import tkinter as tk
    from tkinter import ttk

    frame = ttk.LabelFrame(parent, text="📚 Curriculum library — "
                                       "A1 to C1, guided journey")
    frame.pack(fill="x", padx=8, pady=6)

    state: dict[str, Any] = {"current_language": "es"}

    # -- toolbar ---------------------------------------------------------
    toolbar = ttk.Frame(frame)
    toolbar.pack(fill="x", padx=6, pady=4)

    ttk.Label(toolbar, text="Language").pack(side="left")
    lang_var = tk.StringVar()

    def _language_choices():
        from engines.language_lab.cefr import LANGUAGES
        return list(LANGUAGES)
    lang_combo = ttk.Combobox(toolbar, textvariable=lang_var,
                              state="readonly", width=6,
                              values=_language_choices())
    lang_combo.set(language_getter() or "es")
    lang_combo.pack(side="left", padx=4)

    refresh_btn = ttk.Button(toolbar, text="Refresh library")
    refresh_btn.pack(side="left", padx=6)

    stats_var = tk.StringVar(value="")
    tk.Label(toolbar, textvariable=stats_var, fg="gray").pack(
        side="left", padx=10)

    # -- continue card ----------------------------------------------------
    continue_var = tk.StringVar(value="")
    continue_btn = ttk.Button(frame, text="Continue learning →",
                              state="disabled")
    _continue_slot: dict[str, Any] = {"key": None}

    # -- level cards grid ---------------------------------------------------
    cards = ttk.Frame(frame)
    cards.pack(fill="x", padx=6, pady=4)

    # -- slots list for the selected level ----------------------------------
    slots_frame = ttk.LabelFrame(frame,
                                  text="Lessons in this level")
    slots_frame.pack(fill="x", padx=6, pady=4)

    slots_list = ttk.Treeview(slots_frame,
                              columns=("status", "score", "action"),
                              show="tree", height=7)
    slots_list.heading("#0", text="Lesson")
    slots_list.heading("status", text="Status")
    slots_list.heading("score", text="Score")
    slots_list.heading("action", text="")
    slots_list.column("#0", width=380)
    slots_list.column("status", width=90, anchor="center")
    slots_list.column("score", width=60, anchor="center")
    slots_list.column("action", width=170)
    slots_list.pack(fill="x", padx=4, pady=4)

    slot_status_var = tk.StringVar(
        value="Pick a level card above, then Generate / Open / Share.")
    tk.Label(slots_frame, textvariable=slot_status_var, fg="gray",
             wraplength=880, justify="left").pack(anchor="w",
                                                  padx=4, pady=(0, 4))

    _selected_level: dict[str, str] = {"level": "a1"}
    _selected_slot: dict[str, str] = {"key": ""}
    _level_cards: dict[str, Any] = {}

    # -- population ---------------------------------------------------------

    def _refresh():
        language = lang_var.get() or "es"
        state["current_language"] = language
        for widget in cards.winfo_children():
            widget.destroy()
        _level_cards.clear()
        res = ctrl.curriculum_catalog(language)
        if not res.ok:
            slot_status_var.set("The library could not load — is "
                               "storage healthy? " + (res.detail or ""))
            return show_error(res)
        rows = res.payload
        levels = [r for r in rows if r["kind"] == "level"]

        def _open_level(level_key: str):
            _selected_level["level"] = level_key
            for key, card in _level_cards.items():
                card.configure(
                    relief="raised" if key == level_key else "groove")
            _populate_slots(rows, level_key)

        for row in levels:
            is_locked = row.get("locked")
            color = {"a1": "#3e8e63", "a2": "#2f7f8f", "b1": "#3b6ea5",
                     "b2": "#5e54a0", "c1": "#a06a1c"}.get(
                row.get("level", ""), "#777")
            card = tk.Label(
                cards, text=(
                    f"{row['name']} · {row['title']}\n"
                    f"{row.get('progress', 0)}%"
                    + ("" if is_locked else
                       f" · {row.get('line', '')}")),
                bg=color, fg="white", padx=10, pady=8,
                relief="groove", cursor="hand2", justify="left")
            card.pack(side="left", fill="both", expand=True,
                      padx=3, pady=2)
            if not is_locked:
                card.bind("<Button-1>",
                          lambda e, k=row["level"]: _open_level(k))
            _level_cards[row.get("level", row["name"])] = card

        # stats + continue pointer
        stats = ctrl.curriculum_stats(language)
        if stats.ok:
            payload = stats.payload
            stats_var.set(
                f"{payload['done']}/{payload['total']} lessons done "
                f"· {payload['generated']} generated")
        nxt = ctrl.curriculum_next_lesson(language)
        if nxt.ok and nxt.payload:
            _continue_slot["key"] = nxt.payload["key"]
            continue_var.set(
                f"Next: {nxt.payload['title']} ({nxt.payload['level']}"
                f") — one click, one lesson.")
            continue_btn.config(state="normal")
        else:
            _continue_slot["key"] = None
            continue_var.set(
                "Curriculum complete — every lesson done. Legendary. "
                "👽")
            continue_btn.config(state="disabled")
        _open_level(_selected_level["level"])

    def _populate_slots(rows, level_key: str):
        slots_list.delete(*slots_list.get_children())
        language = state["current_language"]
        slots = [r for r in rows
                 if r["kind"] == "slot" and r["level"] == level_key]
        if not slots:
            slot_status_var.set("No lessons for this level.")
            return
        for row in slots:
            status = row.get("status", "todo")
            score = row.get("score")
            score_text = f"{score}%" if score is not None else "—"
            action = {"todo": "→ Generate",
                      "generated": "→ Open / Share",
                      "done": "→ Revisit"}[status]
            slots_list.insert(
                "", "end", iid=row["key"],
                text=f"{row['title']}",
                values=(status, score_text, action),
                open=False)
        slot_status_var.set(
            f"{len(slots)} lessons · statuses: todo (never opened), "
            "generated (pack ready), done (quiz passed).")

    def _generate_selected():
        key = slots_list.selection() or _continue_slot["key"]
        if isinstance(key, tuple):
            key = key[0] if key else None
        if not key:
            slot_status_var.set("Select a lesson in the list first.")
            return
        language = state["current_language"]
        slot_status_var.set(f"Generating '{key}'… (a few minutes on "
                            "local models — the window stays alive; "
                            "pack lands in your Library + exports)")
        slots_list.selection_set(key)

        def work():
            return ctrl.curriculum_generate_slot(language, key)

        def done(res):
            if not res:
                slot_status_var.set("Generation failed — see dialog.")
                return show_error(res)
            slot_status_var.set(
                f"Saved -> {res.payload['path']} (opening…)")
            _refresh()
            open_path(str(res.payload["path"]))

        run_async(work, done)

    def _open_selected():
        selection = slots_list.selection()
        if not selection:
            slot_status_var.set("Select a lesson first.")
            return
        key = selection[0]
        language = state["current_language"]
        slug = key.replace("_", "-")
        exports = ctrl.list_saved("exports")
        if not exports.ok:
            return
        name = f"{language}-{slug}.html"
        if name in exports.payload:
            open_path(str(ctrl.storage.root / "exports" / name))
            slot_status_var.set(f"Opening {name}…")
        else:
            slot_status_var.set(
                "No pack for this lesson yet — press Generate.")

    def _share_selected():
        selection = slots_list.selection()
        if not selection:
            slot_status_var.set("Select a lesson first.")
            return
        key = selection[0]
        language = state["current_language"]
        slug = key.replace("_", "-")
        packs = ctrl.list_saved("lesson_packs")
        pack_name = f"{language}-{slug}.json"
        if not packs.ok or pack_name not in packs.payload:
            slot_status_var.set("Generate the lesson first, then "
                                "share the pack.")
            return
        res = ctrl.share_lesson_pack(pack_name)
        if not res:
            return show_error(res)
        slot_status_var.set(
            f"Shareable pack -> {res.payload['path']} — send it to "
            "anyone; it opens offline in any browser.")
        open_path(str(res.payload["path"]))

    def _on_slot_double_click(_event):
        status = slots_list.item(slots_list.selection()[0], "values")[0] \
            if slots_list.selection() else "todo"
        if status == "todo":
            _generate_selected()
        else:
            _open_selected()

    # -- buttons row -------------------------------------------------------
    buttons = ttk.Frame(slots_frame)
    buttons.pack(fill="x", padx=4, pady=(0, 6))
    gen_btn = ttk.Button(buttons, text="⚡ Generate lesson",
                          command=_generate_selected)
    gen_btn.pack(side="left")
    ttk.Button(buttons, text="📂 Open pack",
               command=_open_selected).pack(side="left", padx=4)
    ttk.Button(buttons, text="📤 Share pack",
               command=_share_selected).pack(side="left", padx=4)

    def _continue():
        if _continue_slot["key"]:
            key = _continue_slot["key"]
            _selected_level["level"] = key.split("-")[0]
            _refresh()
            slots_list.selection_set(key)
            _generate_selected()

    continue_btn.config(command=_continue)
    continue_btn.pack(fill="x", padx=6, pady=2)
    tk.Label(frame, textvariable=continue_var, fg="#1e5a48",
             wraplength=880, justify="left").pack(anchor="w",
                                                  padx=6, pady=(0, 4))

    refresh_btn.config(command=_refresh)
    slots_list.bind("<Double-Button-1>", _on_slot_double_click)

    def on_lang_change(_event=None):
        state["current_language"] = lang_var.get()
        _refresh()
        if on_language_change:
            on_language_change(lang_var.get())
    lang_combo.bind("<<ComboboxSelected>>", on_lang_change)

    _refresh()
    state.update({
        "frame": frame,
        "refresh": _refresh,
        "lang_var": lang_var,
        "slots_list": slots_list,
    })
    return state
