from pathlib import Path
import shutil

path = Path("app/ui/dashboard.py")
if not path.exists():
    raise SystemExit("Не найден app/ui/dashboard.py. Запусти из корня Saydo.")
backup = path.with_name(path.stem + ".py.style_backup")
if not backup.exists():
    shutil.copy2(path, backup)
text = path.read_text(encoding="utf-8")

if "from app.core.style import StyleStore" not in text:
    text = text.replace("from app.core.snippets import SnippetStore\n", "from app.core.snippets import SnippetStore\nfrom app.core.style import StyleStore\n", 1)
if "self._styles = StyleStore()" not in text:
    text = text.replace("        self._snippets = SnippetStore()\n", "        self._snippets = SnippetStore()\n        self._styles = StyleStore()\n", 1)

old = (
    '        self._pages["style"] = self._simple_page(\n'
    '            "Стиль",\n'
    '            "Настройте, как Saydo форматирует вашу речь: обычный текст, деловой стиль или более свободная подача.",\n'
    '            "Создать стиль",\n'
    '        )\n'
)
if old in text:
    text = text.replace(old, '        self._pages["style"] = self._style_page()\n', 1)

if "    def _style_page(self) -> QWidget:\n" not in text:
    marker = "    def _settings_page(self) -> QWidget:\n"
    if marker not in text:
        raise SystemExit("Не найден _settings_page().")
    methods = r'''    def _style_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        intro = QLabel("Выберите, как Saydo должен формулировать текст в AI Mode.")
        intro.setObjectName("MutedText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.style_list = QVBoxLayout()
        self.style_list.setSpacing(8)
        layout.addLayout(self.style_list)

        create = QPushButton("+  Создать свой стиль")
        create.setObjectName("PrimaryButton")
        create.setCursor(Qt.PointingHandCursor)
        create.clicked.connect(self._create_style)
        layout.addWidget(create, 0, Qt.AlignLeft)
        layout.addStretch()
        self._refresh_styles()
        return page

    def _refresh_styles(self) -> None:
        if not hasattr(self, "style_list"):
            return
        self._clear_layout(self.style_list)
        selected_id = self._styles.get_selected_id()

        for style in self._styles.load():
            style_id = str(style.get("id", ""))
            card = self._card()
            card.setMinimumHeight(78)
            row = QHBoxLayout(card)
            row.setContentsMargins(18, 14, 14, 14)
            row.setSpacing(14)

            info = QVBoxLayout()
            info.setSpacing(3)
            name = QLabel(str(style.get("name", "Без названия")))
            name.setObjectName("SectionTitle")
            info.addWidget(name)
            desc = QLabel(str(style.get("description", "")))
            desc.setObjectName("MutedText")
            desc.setWordWrap(True)
            info.addWidget(desc)
            row.addLayout(info, 1)

            if style_id == selected_id:
                check = QLabel("✓")
                check.setStyleSheet(f"color: {ACCENT}; font-size: 20px; font-weight: 700;")
                row.addWidget(check)

            button = QPushButton("Выбрано" if style_id == selected_id else "Выбрать")
            button.setObjectName("PrimaryButton" if style_id == selected_id else "SecondaryButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setEnabled(style_id != selected_id)
            button.clicked.connect(lambda checked=False, sid=style_id: self._select_style(sid))
            row.addWidget(button)

            if not bool(style.get("builtin")):
                delete = QPushButton("×")
                delete.setObjectName("IconButton")
                delete.setToolTip("Удалить стиль")
                delete.clicked.connect(lambda checked=False, sid=style_id: self._delete_style(sid))
                row.addWidget(delete)

            self.style_list.addWidget(card)

    def _style_blocked_dialog(self) -> None:
        AIUnavailableDialog(
            self,
            self._palette_for_theme(self.current_theme),
            "Стиль доступен только в AI Mode",
            "Стили меняют подачу текста с помощью языковой модели. Включите AI Mode на главной странице, чтобы выбрать или создать стиль.",
        ).exec()

    def _select_style(self, style_id: str) -> None:
        if self.mode != "ai":
            self._style_blocked_dialog()
            return
        if self._styles.select(style_id):
            self._refresh_styles()

    def _delete_style(self, style_id: str) -> None:
        self._styles.delete(style_id)
        self._refresh_styles()

    def _create_style(self) -> None:
        if self.mode != "ai":
            self._style_blocked_dialog()
            return

        palette = self._palette_for_theme(self.current_theme)
        dialog = QDialog(self)
        dialog.setWindowTitle("Создать стиль")
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        dialog.setFixedWidth(520)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(10, 10, 10, 10)

        card = QFrame()
        card.setStyleSheet(
            f'QFrame {{ background: {palette["card"]}; border: 1px solid {palette["border"]}; border-radius: 18px; }}'
            f'QLineEdit, QPlainTextEdit {{ background: {palette["card_alt"]}; color: {palette["text"]}; border: 1px solid {palette["border"]}; border-radius: 10px; padding: 9px 11px; }}'
            f'QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}'
        )
        outer.addWidget(card)

        form = QVBoxLayout(card)
        form.setContentsMargins(24, 22, 24, 20)
        form.setSpacing(10)

        title = QLabel("Создать свой стиль")
        title.setStyleSheet(f"color: {palette['text']}; font-size: 19px; font-weight: 700; border: none;")
        form.addWidget(title)

        help_text = QLabel("Опишите своими словами, как Saydo должен формулировать текст.")
        help_text.setStyleSheet(f"color: {palette['muted']}; font-size: 13px; border: none;")
        help_text.setWordWrap(True)
        form.addWidget(help_text)

        name = QLineEdit()
        name.setPlaceholderText("Название, например «Мои сообщения»")
        form.addWidget(name)

        description = QLineEdit()
        description.setPlaceholderText("Короткое описание")
        form.addWidget(description)

        prompt = QPlainTextEdit()
        prompt.setPlaceholderText("Например: пиши спокойно и уверенно, избегай канцелярита, сохраняй короткие предложения…")
        prompt.setFixedHeight(120)
        form.addWidget(prompt)

        error = QLabel("")
        error.setStyleSheet(f"color: {palette['muted']}; font-size: 12px; border: none;")
        error.setWordWrap(True)
        form.addWidget(error)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Отмена")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(dialog.reject)

        save = QPushButton("Создать")
        save.setObjectName("PrimaryButton")
        save.setDefault(True)

        def save_style() -> None:
            try:
                self._styles.add(name.text(), description.text(), prompt.toPlainText())
            except ValueError as exc:
                error.setText(str(exc))
                return
            dialog.accept()
            self._refresh_styles()

        save.clicked.connect(save_style)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        form.addLayout(buttons)

        dialog.exec()

'''
    text = text.replace(marker, methods + marker, 1)

# Keep style cards in sync after refresh.
if "        self._refresh_styles()\n" not in text:
    anchor = "        self._refresh_snippets()\n"
    if anchor in text:
        text = text.replace(anchor, anchor + "        self._refresh_styles()\n", 1)

path.write_text(text, encoding="utf-8")
print("Style patch applied:", path)
print("Backup:", backup)
