# desktop-shell/et_ui.py
#
# WHAT: The E.T. conversation panel — Mr./Mrs. E.T. voice chat UI:
#       persona picker, scenario picker, length picker, mic device
#       picker, big record button with live pulse, typing fallback,
#       chat bubbles with per-turn score chips + tap-to-replay audio,
#       and the honest status ladder (listening/transcribing/thinking/
#       speaking/saved) on every async stage.
# WHY:  Project E.T. (2026-09-06). All behavior lives in controller
#       flows; this module is PRESENTATION only, imported lazily by
#       app.py so headless suites never touch Tk (same discipline as
#       app.py's run()). Status lines come from et_persona.status_line
#       — curated, humanized, localized; never generic.
# BREAKS IF DELETED: E.T. has no face — the flagship has no UI.

from __future__ import annotations

from typing import Any, Callable, Optional


def build_et_panel(parent, *, ctrl, run_async, show_error, open_path,
                  _open_audio, lang_values, get_lang_code,
                  level_var, refresh_license) -> dict[str, Any]:
    """Mount the E.T. panel into `parent` (the Language Lab tab).

    Returns the panel's state dict (for tests + future tabs):
    {"frame", "status_var", "add_user_line", "add_et_line", ...}
    All long work goes through run_async — the window never freezes.
    """
    import tkinter as tk
    from tkinter import ttk

    from engines.language_lab.et_persona import (
        MR_ET, MRS_ET, encouragement, status_line,
    )

    frame = ttk.LabelFrame(parent, text="👽 Talk with E.T. — live "
                              "voice conversation practice")
    frame.pack(fill="x", padx=8, pady=6)

    state: dict[str, Any] = {
        "active": False,
        "recording": False,
        "devices": [],
        "language": "es",
        "persona_key": "mr",
    }

    # -- setup row -----------------------------------------------------------
    setup = ttk.Frame(frame)
    setup.pack(fill="x", padx=6, pady=4)

    ttk.Label(setup, text="Practice with").pack(side="left")
    persona_var = tk.StringVar(value=f"{MR_ET.emoji} {MR_ET.name}")
    persona_combo = ttk.Combobox(setup, textvariable=persona_var,
                                 state="readonly", width=12,
                                 values=[f"{MR_ET.emoji} {MR_ET.name}",
                                         f"{MRS_ET.emoji} {MRS_ET.name}"])
    persona_combo.pack(side="left", padx=4)

    ttk.Label(setup, text="Scenario").pack(side="left", padx=(8, 0))
    scenario_var = tk.StringVar()
    scenario_combo = ttk.Combobox(setup, textvariable=scenario_var,
                                  state="readonly", width=24)
    scenario_combo.pack(side="left", padx=4)
    scenario_titles: dict[str, str] = {}

    def _load_scenarios():
        res = ctrl.et_scenario_bank()
        if not res.ok:
            return
        titles = []
        scenario_titles.clear()
        for entry in res.payload:
            label = (f"{'🎯 ' if entry['special'] else ''}"
                     f"{entry['title']}")
            scenario_titles[label] = entry["key"]
            titles.append(label)
        scenario_combo["values"] = titles
        if titles:
            scenario_combo.set(titles[0])
    _load_scenarios()

    ttk.Label(setup, text="Length").pack(side="left", padx=(8, 0))
    length_var = tk.StringVar(value="short (6-8 turns)")
    ttk.Combobox(setup, textvariable=length_var, state="readonly",
                 width=16, values=["short (6-8 turns)",
                                   "medium (10-14 turns)",
                                   "long (18-24 turns)"]).pack(
        side="left", padx=4)

    mic_var = tk.StringVar(value="(default microphone)")
    mic_combo = ttk.Combobox(setup, textvariable=mic_var,
                             state="readonly", width=22)

    def _load_devices():
        res = ctrl.et_microphone_devices()
        if not res.ok or not res.payload:
            mic_combo["values"] = ["(no microphone — typing only)"]
            mic_combo.set("(no microphone — typing only)")
            state["devices"] = []
            return
        labels = ["(default microphone)"]
        state["devices"] = [None]
        for device in res.payload:
            labels.append(f"{device['index']}: {device['name']}")
            state["devices"].append(device["index"])
        mic_combo["values"] = labels
    _load_devices()
    mic_combo.pack(side="left", padx=4)

    start_btn = ttk.Button(setup, text="Start conversation")
    start_btn.pack(side="left", padx=8)

    # -- status line -----------------------------------------------------------
    status_var = tk.StringVar(
        value="Pick a scenario and press Start — E.T. has 33 "
              "situations ready, from renting an apartment to full "
              "mock job interviews.")
    status_label = tk.Label(frame, textvariable=status_var, fg="gray",
                            wraplength=900, justify="left")
    status_label.pack(anchor="w", padx=6, pady=(0, 4))

    def set_status(stage: str, language: str = "en") -> None:
        status_var.set(status_line(stage, language))
        status_label.config(fg="#1e5a48")

    # -- conversation area -----------------------------------------------------
    convo_frame = ttk.Frame(frame)
    convo_frame.pack(fill="both", expand=True, padx=6, pady=2)
    chat_text = tk.Text(convo_frame, height=9, width=110,
                        state="disabled", wrap="word",
                        background="#f7f3ea", relief="flat")
    chat_scroll = ttk.Scrollbar(convo_frame, orient="vertical",
                                command=chat_text.yview)
    chat_text.configure(yscrollcommand=chat_scroll.set)
    chat_text.pack(side="left", fill="both", expand=True)
    chat_scroll.pack(side="right", fill="y")

    # tag styles: learner bubbles right-green, E.T. left-plain, sys gray
    chat_text.tag_configure("user", justify="right", foreground="#1e5a48",
                            font=("", 10, "bold"))
    chat_text.tag_configure("et", justify="left", foreground="#182a23")
    chat_text.tag_configure("sys", justify="center", foreground="#8a7a55")
    chat_text.tag_configure("score", justify="right", foreground="#7a5a12")

    def _chat_insert(text: str, tag: str) -> None:
        chat_text.config(state="normal")
        chat_text.insert("end", text + "\n", tag)
        chat_text.see("end")
        chat_text.config(state="disabled")

    def add_user_line(text: str) -> None:
        _chat_insert(f"🧑 You: {text}", "user")

    def add_et_line(text: str, persona_emoji: str = "👽") -> None:
        _chat_insert(f"{persona_emoji} E.T.: {text}", "et")

    def add_system_line(text: str) -> None:
        _chat_insert(f"— {text} —", "sys")

    def clear_chat() -> None:
        chat_text.config(state="normal")
        chat_text.delete("1.0", "end")
        chat_text.config(state="disabled")

    # -- controls row -----------------------------------------------------------
    controls = ttk.Frame(frame)
    controls.pack(fill="x", padx=6, pady=4)

    record_btn = ttk.Button(controls, text="🎙 Record & talk",
                            state="disabled")
    record_btn.pack(side="left")

    stop_btn = ttk.Button(controls, text="⏹ Stop recording",
                          state="disabled")
    stop_btn.pack(side="left", padx=4)

    replay_menu = ttk.Button(controls, text="🔊 Replay last reply",
                             state="disabled")
    replay_menu.pack(side="left", padx=4)

    end_btn = ttk.Button(controls, text="End conversation",
                         state="disabled")
    end_btn.pack(side="left", padx=4)

    quota_label = tk.Label(controls, text="", fg="gray")
    quota_label.pack(side="left", padx=8)

    def _refresh_et_quota() -> None:
        quota = ctrl.licenses.quota("et_turn")
        if quota.remaining is not None:
            quota_label.config(
                text=f"E.T. turns: {quota.remaining}/{quota.limit} "
                     "left this week")
        else:
            quota_label.config(text="E.T. turns: unlimited")
    _refresh_et_quota()

    # -- typing fallback (ALWAYS available) ---------------------------------
    type_frame = ttk.Frame(frame)
    type_frame.pack(fill="x", padx=6, pady=(2, 6))
    ttk.Label(type_frame, text="Or type:").pack(side="left")
    type_var = tk.StringVar()
    type_entry = ttk.Entry(type_frame, textvariable=type_var)
    type_entry.pack(side="left", fill="x", expand=True, padx=4)
    type_send = ttk.Button(type_frame, text="Send", state="disabled")
    type_send.pack(side="left")

    # -- record pulse -----------------------------------------------------------
    pulse = tk.Canvas(controls, width=26, height=26, highlightthickness=0)
    pulse.pack(side="left", padx=(2, 0))
    pulse_circle = pulse.create_oval(4, 4, 22, 22, fill="#dddddd",
                                     outline="")

    def _set_pulse(level: float) -> None:
        color = "#c08a24" if level > 0.66 else \
            ("#e9d7ae" if level > 0.33 else "#dddddd")
        pulse.itemconfigure(pulse_circle, fill=color)

    # -- session plumbing ---------------------------------------------------------

    _last_reply_audio: dict[str, Any] = {"wav": None}
    _stop_flag: dict[str, bool] = {"stop": False}

    def _persona_key() -> str:
        return "mrs" if MRS_ET.name in persona_var.get() else "mr"

    def _persona() -> Any:
        from engines.language_lab.et_persona import persona_for
        return persona_for(_persona_key())

    def _language() -> str:
        return get_lang_code() if get_lang_code else "es"

    def _length() -> str:
        return length_var.get().split(" ")[0]

    def _device_index() -> Optional[int]:
        try:
            position = mic_combo.current()
            if 0 <= position < len(state["devices"]):
                return state["devices"][position]
        except Exception:  # noqa: BLE001 — UI safety
            pass
        return None

    def _scenario_key() -> str:
        return scenario_titles.get(scenario_var.get(), "restaurant-order")

    def _enable_in_session(enabled: bool) -> None:
        for widget in (record_btn, type_send, end_btn):
            widget.config(state="normal" if enabled else "disabled")
        start_btn.config(state="disabled" if enabled else "normal")
        state["active"] = enabled

    def _start_conversation():
        persona = _persona()
        language = _language()

        def work():
            return ctrl.et_start_session(
                language, level_var.get(), _scenario_key(),
                persona.key, _length(),
                device_index=_device_index())

        def done(res):
            start_btn.config(state="normal", text="Start conversation")
            if not res:
                return show_error(res)
            clear_chat()
            add_system_line(
                f"{persona.emoji} {persona.name} connects — "
                f"scenario: {scenario_var.get()} ({_length()})")
            _enable_in_session(True)
            set_status("thinking", language)
            _generate_opening()

        start_btn.config(state="disabled", text="Starting…")
        run_async(work, done, busy=None)

    def _generate_opening():
        language = _language()
        persona = _persona()

        def work():
            return ctrl.et_opening_line()

        def done(res):
            if not res:
                set_status("error", language)
                return show_error(res)
            add_et_line(res.payload["line"], persona.emoji)
            if res.payload.get("audio"):
                _last_reply_audio["wav"] = res.payload["audio"]
                replay_menu.config(state="normal")
                set_status("speaking", language)
                _open_audio(res.payload["audio"])
            else:
                set_status("listening", language)

        run_async(work, done)

    def _submit_voice():
        if state["recording"]:
            _stop_flag["stop"] = True
            return
        # quota gate FIRST: no one records 30 seconds to be told
        # they're out of turns. The controller re-checks, but this
        # front check avoids opening the stream at all.
        quota = ctrl.licenses.quota("et_turn")
        if not quota.allowed:
            from desktop_shell.controller import FlowResult
            show_error(FlowResult(
                False, error_kind="license", detail=quota.message))
            return
        language = _language()
        _stop_flag["stop"] = False
        state["recording"] = True
        record_btn.config(text="⏹ Stop recording")
        stop_btn.config(state="normal")
        set_status("listening", language)

        def work():
            from engines.audio_engine.mic import capture_speech
            return capture_speech(device=_device_index(),
                                  max_seconds=90.0,
                                  on_level=_set_pulse,
                                  should_stop=lambda: _stop_flag["stop"])

        def done(capture):
            record_btn.config(text="🎙 Record & talk")
            stop_btn.config(state="disabled")
            _set_pulse(0.0)
            state["recording"] = False
            if isinstance(capture, Exception):
                set_status("error", language)
                return show_error(_as_flow_error(capture))
            wav = capture.wav_bytes
            if capture.peak_level < 0.005:
                add_system_line("(that was silence — press record and "
                                "speak, or type below)")
                set_status("listening", language)
                return
            add_system_line(f"🎤 captured {capture.duration_seconds}s "
                            "— decoding…")
            set_status("transcribing", language)

            def turn_work():
                return ctrl.et_submit_voice(wav_bytes=wav,
                                            device_index=_device_index())

            def turn_done(res):
                _handle_turn_result(res, language)

            run_async(turn_work, turn_done)

        run_async(work, done)

    def _as_flow_error(exc: Exception):
        from desktop_shell.controller import FlowResult
        if "No microphone" in str(exc) or "busy" in str(exc).lower():
            return FlowResult(False, error_kind="device", detail=str(exc))
        return FlowResult(False, error_kind="unexpected", detail=str(exc))

    def _submit_text(event=None):
        text = type_var.get().strip()
        if not text:
            return
        type_var.set("")
        language = _language()
        add_user_line(text)

        def work():
            return ctrl.et_submit_text(text)

        def done(res):
            _handle_turn_result(res, language)

        set_status("thinking", language)
        run_async(work, done)

    def _handle_turn_result(res, language: str):
        if not res:
            if getattr(res, "error_kind", "") == "et_repeat":
                # kind re-ask: inline notice, NO scary dialog
                set_status("repeat", language)
                add_system_line(res.detail or "Say it once more.")
                root_after = status_label.after(
                    1500, lambda: set_status("listening", language))
                return
            set_status("error", language)
            return show_error(res)
        payload = res.payload or {}
        if payload.get("closed"):
            add_system_line("Conversation complete — transcript "
                            "saved. Start another one anytime!")
            _enable_in_session(False)
            set_status("saved", language)
            _refresh_et_quota()
            refresh_license() if refresh_license else None
            return
        add_et_line(payload.get("reply", ""), _persona().emoji)
        scores = payload.get("scores") or {}
        if scores:
            summary = " · ".join(f"{k[:3].upper()} {v}/5"
                                for k, v in scores.items())
            _chat_insert(f"   [{summary}]  clarity "
                         f"{payload.get('clarity', '—')}", "score")
        for fix in payload.get("corrections") or []:
            add_system_line(f"✏️ {fix.get('wrong')} → "
                            f"{fix.get('right')} ({fix.get('why')})")
        if payload.get("praise"):
            add_system_line(f"💚 {payload['praise']}")
        if payload.get("audio"):
            _last_reply_audio["wav"] = payload["audio"]
            replay_menu.config(state="normal")
            set_status("speaking", language)
            _open_audio(payload["audio"])
        else:
            set_status("listening", language)
        quota = payload.get("quota") or {}
        if quota.get("remaining") is not None:
            quota_label.config(
                text=f"E.T. turns: {quota['remaining']}/"
                     f"{quota['limit']} left this week")
        if payload.get("notes"):
            add_system_line(f"💡 {payload['notes']}")
        if payload.get("turn_number") and payload.get("max_turns"):
            add_system_line(f"Turn {payload['turn_number']} of "
                            f"{payload['max_turns']}")
        _refresh_et_quota()
        if not payload.get("closed"):
            set_status("listening", language)
            add_system_line(encouragement(_language(),
                                          level_var.get()))

    def _end_conversation():
        def work():
            return ctrl.et_end_session()

        def done(res):
            if not res:
                return show_error(res)
            _enable_in_session(False)
            add_system_line("Session saved. E.T. waves goodbye. "
                            "👋 (transcript in your Library)")
            set_status("saved", _language())

        run_async(work, done)

    def _replay_last():
        if _last_reply_audio["wav"] is None:
            return
        _open_audio(_last_reply_audio["wav"])

    start_btn.config(command=_start_conversation)
    record_btn.config(command=_submit_voice)
    stop_btn.config(command=lambda: _stop_flag.update(stop=True))
    type_send.config(command=_submit_text)
    type_entry.bind("<Return>", _submit_text)
    end_btn.config(command=_end_conversation)
    replay_menu.config(command=_replay_last)

    state.update({
        "frame": frame,
        "status_var": status_var,
        "add_user_line": add_user_line,
        "add_et_line": add_et_line,
        "add_system_line": add_system_line,
        "clear_chat": clear_chat,
        "set_status": set_status,
        "start_button": start_btn,
        "record_button": record_btn,
        "refresh_quota": _refresh_et_quota,
    })
    return state
