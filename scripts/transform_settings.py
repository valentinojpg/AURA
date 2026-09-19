"""
Script auxiliar para transformar ui/pages/settings_page.py
Modularizando secciones opcionales (Audio, RVC, Tema, Fondo) en métodos protegidos
y asegurando compatibilidad con FilePicker.
"""

from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "ui" / "pages" / "settings_page.py"

def main():
    text = SETTINGS_FILE.read_text(encoding="utf-8")

    m3 = "# ── SECCIÓN 3: Audio y Voz ─────────────────────────────────\n"
    m3b = "# ── SECCIÓN 3b: Voz RVC y Síntesis TTS ─────────────────────\n"
    m3c = "# ── SECCIÓN 3c: Tema y Estilos Visuales (Fase 76) ───────────\n"
    m3d = "# ── SECCIÓN 3d: Fondo de Pantalla Personalizado (Fase 78) ─────\n"
    m4 = "# ── SECCIÓN 4: Seguridad y Confirmaciones ───────────────────\n"

    p1 = text.find(m3)
    p2 = text.find(m3b)
    p3 = text.find(m3c)
    p4 = text.find(m3d)
    p5 = text.find(m4)

    assert -1 not in (p1, p2, p3, p4, p5), "No se encontraron todos los marcadores"
    assert p1 < p2 < p3 < p4 < p5, "Marcadores en orden incorrecto"

    audio_body = text[p1 + len(m3):p2]
    rvc_body = text[p2 + len(m3b):p3]
    theme_body = text[p3 + len(m3c):p4]
    bg_body = text[p4 + len(m3d):p5]

    # Modificar bg_body para get_file_picker
    old_picker = """        # FilePicker nativo de Flet
        self._bg_file_picker = ft.FilePicker(on_result=lambda e: self._on_bg_file_picked(e))
        if hasattr(self.app_page, "overlay"):
            self.app_page.overlay.append(self._bg_file_picker)"""

    new_picker = """        # FilePicker nativo de Flet compatible
        self._bg_file_picker = get_file_picker(self._on_bg_file_picked, page=self.app_page)
        if self._bg_file_picker is None:
            _logger.warning("FilePicker no disponible en este entorno; mostrando sección deshabilitada.")
            return self._build_disabled_section_card("Fondo de Pantalla", "FilePicker no disponible en este entorno")
        if hasattr(self.app_page, "services") and self._bg_file_picker not in self.app_page.services:
            self.app_page.services.append(self._bg_file_picker)
        elif hasattr(self.app_page, "overlay") and self._bg_file_picker not in self.app_page.overlay:
            self.app_page.overlay.append(self._bg_file_picker)"""

    assert old_picker in bg_body, "old_picker no encontrado en bg_body"
    bg_body = bg_body.replace(old_picker, new_picker, 1)

    # Modificar _on_pick_bg_click guard
    old_pick_click = """        def _on_pick_bg_click(_e: Any) -> None:
            self._bg_file_picker.pick_files("""

    new_pick_click = """        def _on_pick_bg_click(_e: Any) -> None:
            if not self._bg_file_picker:
                return
            self._bg_file_picker.pick_files("""

    assert old_pick_click in bg_body, "old_pick_click no encontrado en bg_body"
    bg_body = bg_body.replace(old_pick_click, new_pick_click, 1)

    def wrap_method(name: str, title: str, body: str, ret_var: str) -> str:
        indented = "\n".join(("    " + line if line.strip() else "") for line in body.splitlines())
        return f"""    def {name}(self) -> ft.Container:
        \"\"\"Construye la sección de {title}.\"\"\"
        try:
{indented}
            return {ret_var}
        except Exception as ex:
            _logger.warning("Error inicializando sección '{title}': %s", ex)
            return self._build_disabled_section_card("{title}", str(ex))
"""

    audio_method = wrap_method("_build_audio_section", "Dispositivos de Audio y Voz", audio_body, "self._audio_card")
    rvc_method = wrap_method("_build_rvc_section", "Voz RVC y Síntesis TTS", rvc_body, "self._rvc_card")
    theme_method = wrap_method("_build_theme_section", "Tema y Estilos Visuales", theme_body, "self._theme_card")
    bg_method = wrap_method("_build_background_section", "Fondo de Pantalla", bg_body, "self._background_card")

    new_sections_call = """        # ── SECCIÓN 3: Audio y Voz ─────────────────────────────────
        self._audio_card = self._build_audio_section()

        # ── SECCIÓN 3b: Voz RVC y Síntesis TTS ─────────────────────
        self._rvc_card = self._build_rvc_section()

        # ── SECCIÓN 3c: Tema y Estilos Visuales (Fase 76) ───────────
        self._theme_card = self._build_theme_section()

        # ── SECCIÓN 3d: Fondo de Pantalla Personalizado (Fase 78) ─────
        self._background_card = self._build_background_section()

        """

    head = text[:p1]
    tail = text[p5:]

    # En tail, reemplazar firma de _on_bg_file_picked
    old_handler = "    def _on_bg_file_picked(self, e: ft.FilePickerResultEvent) -> None:\n        \"\"\"Callback al seleccionar un archivo en el explorador nativo.\"\"\"\n        if not e.files or len(e.files) == 0:\n            return\n        file_path = e.files[0].path"
    new_handler = "    def _on_bg_file_picked(self, e: Any) -> None:\n        \"\"\"Callback al seleccionar un archivo en el explorador nativo.\"\"\"\n        if not e:\n            return\n        files = getattr(e, \"files\", None)\n        if not files or len(files) == 0:\n            return\n        file_obj = files[0]\n        file_path = getattr(file_obj, \"path\", None) if not isinstance(file_obj, str) else file_obj"

    assert old_handler in tail, "old_handler no encontrado en tail"
    tail = tail.replace(old_handler, new_handler, 1)

    # En tail, blindar _handle_restore_defaults para RVC
    old_rd_rvc = """        # RVC controles
        self._tts_provider_dropdown.value = DEFAULTS.get("TTS_PROVIDER", "rvc")"""
    new_rd_rvc = """        # RVC controles
        if hasattr(self, "_tts_provider_dropdown") and self._tts_provider_dropdown:
            self._tts_provider_dropdown.value = DEFAULTS.get("TTS_PROVIDER", "rvc")"""

    assert old_rd_rvc in tail, "old_rd_rvc no encontrado en tail"
    tail = tail.replace(old_rd_rvc, new_rd_rvc, 1)

    # Insertar métodos antes de def _build
    build_marker = "    def _build(self) -> None:\n"
    build_pos = head.find(build_marker)
    assert build_pos != -1, "build_marker no encontrado en head"

    new_head = head[:build_pos] + audio_method + "\n" + rvc_method + "\n" + theme_method + "\n" + bg_method + "\n" + head[build_pos:]
    new_full_text = new_head + new_sections_call + tail

    SETTINGS_FILE.write_text(new_full_text, encoding="utf-8")
    print(f"Transformación completada con éxito. Tamaño: {len(new_full_text)} caracteres.")

if __name__ == "__main__":
    main()
