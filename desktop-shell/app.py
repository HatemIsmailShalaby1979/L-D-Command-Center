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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ERROR_TITLES = {
    "no_model": "LM Studio not reachable",
    "bad_output": "Model output rejected",
    "input": "Check your input",
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
    root.geometry("780x520")

    status = tk.StringVar(value="checking LM Studio…")

    def refresh_health():
        res = ctrl.check_model_health()
        if res.ok:
            status.set("LM Studio: ready")
            health_label.config(fg="green")
        else:
            status.set(f"LM Studio: {res.detail}")
            health_label.config(fg="red")

    def show_error(res: FlowResult):
        messagebox.showerror(ERROR_TITLES.get(res.error_kind, "Error"),
                             res.detail or "Unknown failure.")

    # -- header -----------------------------------------------------------
    header = ttk.Frame(root); header.pack(fill="x", padx=8, pady=6)
    health_label = ttk.Label(header, textvariable=status, foreground="gray")
    health_label.pack(side="left")
    ttk.Button(header, text="Refresh", command=refresh_health).pack(side="left", padx=6)

    # -- journey tab --------------------------------------------------------
    tab = ttk.Notebook(root); tab.pack(fill="both", expand=True, padx=8, pady=6)
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

    output = tk.Text(journey_tab, height=22)
    output.pack(fill="both", expand=True, pady=6)

    def do_generate():
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
    ttk.Button(actions, text="Generate", command=do_generate).pack(side="left")
    for fmt in ("text", "pdf", "pptx", "xlsx"):
        ttk.Button(actions, text=f"Export {fmt.upper()}",
                   command=lambda f=fmt: do_export(f)).pack(side="left", padx=4)

    refresh_health()
    root.mainloop()


if __name__ == "__main__":
    run()
