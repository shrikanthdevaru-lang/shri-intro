"""
dictionary.py — SQLite-backed custom vocabulary store.

Stores user-defined words / names / technical terms.  Words are fed into
Whisper's ``prompt`` parameter so the model recognises them correctly.

Includes a Tkinter UI for add / remove / search.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from config import DB_PATH

logger = logging.getLogger(__name__)

# ── default seed words ───────────────────────────────────────────────────────
_SEED_WORDS: list[str] = [
    "Bagalkot",
    "Siddarameshwara",
    "Sanskrit",
    "Vachana",
    "Lingayata",
    "Basavanna",
]


# ─────────────────────────────────────────────────────────────────────────────
# Database layer
# ─────────────────────────────────────────────────────────────────────────────

class VocabularyDB:
    """Thread-safe SQLite wrapper for the custom vocabulary store."""

    def __init__(self, db_path: str = str(DB_PATH)) -> None:
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ── private helpers ───────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vocabulary (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    word    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                    added   TEXT    NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
            # Seed default words on first run
            for word in _SEED_WORDS:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO vocabulary (word) VALUES (?)", (word,)
                    )
                except sqlite3.Error:
                    pass
            conn.commit()
        logger.info("Vocabulary DB initialised at %s", self._path)

    # ── public API ────────────────────────────────────────────────────────

    def add_word(self, word: str) -> bool:
        """Return True if inserted, False if duplicate."""
        word = word.strip()
        if not word:
            return False
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO vocabulary (word) VALUES (?)", (word,)
                )
                conn.commit()
                logger.info("Dictionary: added word (len=%d)", len(word))
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_word(self, word: str) -> bool:
        """Return True if deleted."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM vocabulary WHERE word = ? COLLATE NOCASE", (word,)
            )
            conn.commit()
            return cur.rowcount > 0

    def search(self, query: str = "") -> list[str]:
        """Return words matching *query* (substring, case-insensitive)."""
        pattern = f"%{query}%"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT word FROM vocabulary WHERE word LIKE ? ORDER BY word",
                (pattern,),
            ).fetchall()
        return [r["word"] for r in rows]

    def all_words(self) -> list[str]:
        return self.search("")

    def prompt_string(self) -> str:
        """Return words as a comma-separated string for Whisper's prompt param."""
        words = self.all_words()
        return ", ".join(words)


# ─────────────────────────────────────────────────────────────────────────────
# Tkinter Dictionary Manager UI
# ─────────────────────────────────────────────────────────────────────────────

class DictionaryManagerWindow:
    """Floating Tkinter window to manage the custom vocabulary."""

    def __init__(self, db: VocabularyDB, on_close: Callable | None = None) -> None:
        self._db = db
        self._on_close = on_close
        self._root: tk.Toplevel | None = None

    def open(self) -> None:
        """Open (or bring to front) the dictionary manager window."""
        if self._root and tk.Toplevel.winfo_exists(self._root):
            self._root.lift()
            self._root.focus_force()
            return

        root = tk.Toplevel()
        self._root = root
        root.title("FlowDictate — Custom Dictionary")
        root.geometry("440x520")
        root.resizable(False, True)
        root.configure(bg="#1a1a2e")
        root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._build_ui(root)
        self._refresh_list()

    def _build_ui(self, root: tk.Toplevel) -> None:
        # ── colours / fonts ──────────────────────────────────────────────
        BG = "#1a1a2e"
        CARD = "#16213e"
        ACCENT = "#e94560"
        FG = "#ffffff"
        MUTED = "#a0a0b8"
        FONT = ("SF Pro Display", 13)
        FONT_SM = ("SF Pro Display", 11)

        # ── header ───────────────────────────────────────────────────────
        header = tk.Frame(root, bg=BG, pady=16)
        header.pack(fill="x", padx=20)
        tk.Label(
            header, text="📖  Custom Dictionary", bg=BG, fg=FG,
            font=("SF Pro Display", 16, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text="Words fed to Whisper for better recognition",
            bg=BG, fg=MUTED, font=FONT_SM,
        ).pack(side="left", padx=12)

        # ── search bar ───────────────────────────────────────────────────
        search_frame = tk.Frame(root, bg=BG, padx=20)
        search_frame.pack(fill="x")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_list())

        search_entry = tk.Entry(
            search_frame,
            textvariable=self._search_var,
            bg=CARD, fg=FG, insertbackground=FG,
            font=FONT, relief="flat", bd=8,
        )
        search_entry.pack(fill="x", ipady=6)
        search_entry.insert(0, "")
        # Placeholder effect
        search_entry.bind("<FocusIn>", lambda e: search_entry.configure(fg=FG))

        # ── word list ────────────────────────────────────────────────────
        list_frame = tk.Frame(root, bg=BG, padx=20, pady=10)
        list_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", bg=BG)
        self._listbox = tk.Listbox(
            list_frame,
            bg=CARD, fg=FG, selectbackground=ACCENT, selectforeground=FG,
            font=FONT, relief="flat", bd=0,
            activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self._listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self._listbox.pack(fill="both", expand=True)

        # Word count label
        self._count_var = tk.StringVar(value="0 words")
        tk.Label(root, textvariable=self._count_var, bg=BG, fg=MUTED,
                 font=FONT_SM).pack(pady=(0, 4))

        # ── add word ─────────────────────────────────────────────────────
        add_frame = tk.Frame(root, bg=BG, padx=20, pady=8)
        add_frame.pack(fill="x")

        self._add_var = tk.StringVar()
        add_entry = tk.Entry(
            add_frame,
            textvariable=self._add_var,
            bg=CARD, fg=FG, insertbackground=FG,
            font=FONT, relief="flat", bd=8,
        )
        add_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        add_entry.bind("<Return>", lambda _: self._add_word())

        tk.Button(
            add_frame, text="Add Word",
            command=self._add_word,
            bg=ACCENT, fg=FG, font=("SF Pro Display", 12, "bold"),
            relief="flat", padx=12, pady=6, cursor="hand2",
        ).pack(side="right")

        # ── remove button ─────────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=BG, padx=20, pady=(0, 16))
        btn_frame.pack(fill="x")

        tk.Button(
            btn_frame, text="Remove Selected",
            command=self._remove_selected,
            bg="#2a2a4e", fg=FG, font=FONT_SM,
            relief="flat", padx=10, pady=6, cursor="hand2",
        ).pack(side="right")

    def _refresh_list(self) -> None:
        query = self._search_var.get() if hasattr(self, "_search_var") else ""
        words = self._db.search(query)
        self._listbox.delete(0, tk.END)
        for w in words:
            self._listbox.insert(tk.END, f"  {w}")
        self._count_var.set(f"{len(words)} word{'s' if len(words) != 1 else ''}")

    def _add_word(self) -> None:
        word = self._add_var.get().strip()
        if not word:
            return
        if self._db.add_word(word):
            self._add_var.set("")
            self._refresh_list()
        else:
            messagebox.showinfo("Duplicate", f'"{word}" is already in the dictionary.')

    def _remove_selected(self) -> None:
        selected = self._listbox.curselection()
        if not selected:
            return
        word = self._listbox.get(selected[0]).strip()
        if messagebox.askyesno("Remove Word", f'Remove "{word}" from the dictionary?'):
            self._db.remove_word(word)
            self._refresh_list()

    def _on_window_close(self) -> None:
        if self._on_close:
            self._on_close()
        if self._root:
            self._root.destroy()
            self._root = None
