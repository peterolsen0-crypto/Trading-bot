from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

PROJECT_DIR = Path(__file__).resolve().parent
SCRIPTS = [
    PROJECT_DIR / name
    for name in (
        "favorite_language.py",
        "full_name.py",
        "hello_world.py",
        "name.py",
        "simple_message.py",
        "simple_messages.py",
        "trading_bot.py",
    )
]


class ProjectRunner:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Python Work — øvelser")
        root.geometry("900x560")
        root.minsize(720, 420)

        style = ttk.Style(root)
        style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("Hint.TLabel", font=("Segoe UI", 10))
        style.configure("Run.TButton", padding=(10, 7))

        container = ttk.Frame(root, padding=18)
        container.pack(fill="both", expand=True)
        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="Python-øvelsene", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Velg en fil for å kjøre den. Utskriften vises her.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(container)
        body.pack(fill="both", expand=True)
        sidebar = ttk.Frame(body, width=225)
        sidebar.pack(side="left", fill="y", padx=(0, 14))
        sidebar.pack_propagate(False)
        ttk.Button(
            sidebar, text="Kjør alle", style="Run.TButton", command=self.run_all
        ).pack(fill="x", pady=(0, 10))
        ttk.Separator(sidebar).pack(fill="x", pady=(0, 8))
        for script in SCRIPTS:
            ttk.Button(
                sidebar,
                text=script.stem.replace("_", " ").title(),
                command=lambda path=script: self.run_scripts([path]),
            ).pack(fill="x", pady=3)

        output_frame = ttk.Frame(body)
        output_frame.pack(side="left", fill="both", expand=True)
        ttk.Label(output_frame, text="Resultat", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(0, 6)
        )
        text_frame = ttk.Frame(output_frame)
        text_frame.pack(fill="both", expand=True)
        self.output = tk.Text(
            text_frame,
            wrap="word",
            font=("Cascadia Mono", 10),
            background="#111827",
            foreground="#e5e7eb",
            insertbackground="#ffffff",
            padx=12,
            pady=10,
            borderwidth=0,
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.run_all()

    def run_all(self) -> None:
        self.run_scripts(SCRIPTS)

    def run_scripts(self, scripts: list[Path]) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        for script in scripts:
            self.output.insert("end", f"> {script.name}\n\n")
            try:
                result = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=PROJECT_DIR,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.output.insert("end", result.stdout or "(Ingen utskrift)\n")
                if result.stderr:
                    self.output.insert("end", f"\nFeil-/statusmelding:\n{result.stderr}")
                if result.returncode:
                    self.output.insert("end", f"\nAvsluttet med kode {result.returncode}.\n")
                else:
                    self.output.insert("end", "\n✓ Ferdig\n")
            except Exception as error:
                self.output.insert("end", f"Kunne ikke kjøre filen: {error}\n")
            self.output.insert("end", "\n" + "─" * 48 + "\n\n")
        self.output.configure(state="disabled")
        self.output.see("1.0")


if __name__ == "__main__":
    window = tk.Tk()
    ProjectRunner(window)
    window.mainloop()

