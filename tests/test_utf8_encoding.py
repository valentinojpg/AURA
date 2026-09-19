"""
AURA — Test de Regresión de Codificación UTF-8 (Fase Fix Mojibake)

Verifica que:
1. Los mensajes con caracteres multibyte, tildes, comillas angulares y emojis
   ("¿áéíóú ñ «comillas» emoji 🎉") lleguen idénticos al componente ChatBubble.
2. Sobrevivan al guardado y recarga en ConversationStore.
3. Sobrevivan a un reinicio simulado de la app (nueva instancia de ConversationStore).
4. El cliente HTTP (AIHttpClient) decodifique streams SSE como UTF-8 incluso si el
   servidor no envía charset en Content-Type (previniendo el mojibake de origen).
5. La utilidad scripts/fix_mojibake repare strings corrompidos y preserve strings válidos.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from data.conversation_store import Conversation, ConversationStore, StoredMessage
from ui.components.chat_bubble import ChatBubble
from ai.http_client import AIHttpClient
from scripts.fix_mojibake import repair_string, repair_data_structure


TEST_STRING = "¿áéíóú ñ «comillas» emoji 🎉"


class TestUTF8EncodingRegression(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aura_utf8_test_")
        self.store = ConversationStore(conversations_dir=Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_mock_message_arrives_identical_to_chat_bubble(self):
        """Un mensaje con acentos, tildes, signos y emojis llega IDÉNTICO a ChatBubble."""
        bubble = ChatBubble(role="assistant", content=TEST_STRING)
        self.assertEqual(bubble.content_text, TEST_STRING)
        self.assertEqual(bubble._msg_control.value, TEST_STRING)

        # Actualización de contenido en streaming
        stream_update = TEST_STRING + " — Respuesta ampliada con acentos: éxito total."
        bubble.update_content(stream_update)
        self.assertEqual(bubble.content_text, stream_update)
        self.assertEqual(bubble._msg_control.value, stream_update)

    def test_02_survives_save_and_reload_in_conversation_store(self):
        """Un mensaje UTF-8 complejo sobrevive guardado y recarga en disco."""
        conv = self.store.new_conversation()
        conv.title = f"Test UTF-8: {TEST_STRING}"
        conv.messages.append(StoredMessage(role="user", content=TEST_STRING, timestamp="12:00"))
        conv.messages.append(
            StoredMessage(role="assistant", content=f"Respuesta con {TEST_STRING}", timestamp="12:01")
        )

        save_ok = self.store.save(conv)
        self.assertTrue(save_ok)

        # Recargar en la misma sesión
        loaded = self.store.load(conv.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, f"Test UTF-8: {TEST_STRING}")
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(loaded.messages[0].content, TEST_STRING)
        self.assertEqual(loaded.messages[1].content, f"Respuesta con {TEST_STRING}")

    def test_03_survives_app_restart(self):
        """Simula reinicio completo de la aplicación creando una nueva instancia de Store."""
        conv = self.store.new_conversation()
        conv.title = "Sesión previa al reinicio"
        conv.messages.append(StoredMessage(role="user", content=TEST_STRING, timestamp="10:00"))
        conv.messages.append(StoredMessage(role="assistant", content=f"Persistido: {TEST_STRING}", timestamp="10:01"))
        self.store.save(conv)

        # Simular reinicio de la app creando un nuevo store sobre la misma carpeta
        new_app_session_store = ConversationStore(conversations_dir=Path(self.temp_dir))
        restarted_conv = new_app_session_store.load(conv.id)

        self.assertIsNotNone(restarted_conv)
        self.assertEqual(restarted_conv.messages[0].content, TEST_STRING)
        self.assertEqual(restarted_conv.messages[1].content, f"Persistido: {TEST_STRING}")

        # Comprobar directamente los bytes del archivo JSON en disco
        json_file = Path(self.temp_dir) / f"{restarted_conv.created_at[:10].replace('-', '')}_{restarted_conv.id}.json"
        if not json_file.exists():
            files = list(Path(self.temp_dir).glob(f"*_{restarted_conv.id}.json"))
            self.assertTrue(len(files) > 0)
            json_file = files[0]

        raw_bytes = json_file.read_bytes()
        decoded_utf8 = raw_bytes.decode("utf-8")
        self.assertIn(TEST_STRING, decoded_utf8)
        # Asegurar que no hay mojibake en el archivo JSON
        self.assertNotIn("Ã", decoded_utf8)
        self.assertNotIn("â€", decoded_utf8)

    def test_04_ai_http_client_sse_stream_decodes_utf8_without_mojibake(self):
        """AIHttpClient decodifica streams SSE en UTF-8 aunque falte charset en headers."""
        client = AIHttpClient(provider_name="test_provider")

        # Simular respuesta de provider en streaming (ej: Gemini o OpenAI)
        # Content-Type sin charset=utf-8, que normalmente provoca ISO-8859-1 en requests
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/event-stream"}
        mock_resp.encoding = None

        # Líneas simuladas codificadas en UTF-8 con tildes y emojis
        utf8_lines = [
            f'data: {{"text": "{TEST_STRING}"}}'.encode("utf-8"),
            b'data: {"text": "Volv\xc3\xa9 ma\xc3\xb1ana"}',  # "Volvé mañana" en bytes UTF-8
        ]

        def fake_iter_lines(decode_unicode=True):
            # Comportamiento idéntico a requests.Response.iter_lines cuando resp.encoding es respetado
            for b in utf8_lines:
                if decode_unicode:
                    enc = mock_resp.encoding or "ISO-8859-1"
                    yield b.decode(enc)
                else:
                    yield b

        mock_resp.iter_lines.side_effect = fake_iter_lines

        with patch("requests.request", return_value=mock_resp):
            lines = list(client.stream_lines("https://fake.url"))

        # Verificar que resp.encoding fue fijado a utf-8
        self.assertEqual(mock_resp.encoding, "utf-8")
        self.assertEqual(len(lines), 2)
        self.assertIn(TEST_STRING, lines[0])
        self.assertIn("Volvé mañana", lines[1])
        self.assertNotIn("VolvÃ©", lines[1])

    def test_05_repair_string_fixes_corrupted_mojibake(self):
        """La función de reparación arregla mojibake real y preserva texto limpio."""
        # Caso real del bug reportado por el usuario:
        corrupted = (
            "â€” Â¿CuÃ¡l es la diferencia entre un cirujano y un desarrollador web?\n\n"
            "Vos tocÃ¡s un `<div>` que no tenÃ­as que tocar, terminÃ¡s matando... Ahora volvÃ© a trabajar."
        )
        repaired, changed = repair_string(corrupted)
        self.assertTrue(changed)
        self.assertIn("— ¿Cuál es la diferencia", repaired)
        self.assertIn("tocás", repaired)
        self.assertIn("tenías", repaired)
        self.assertIn("terminás", repaired)
        self.assertIn("volvé", repaired)
        self.assertNotIn("Ã", repaired)
        self.assertNotIn("Â", repaired)

        # Caso texto legítimo con acentos y emojis: NO debe ser modificado
        clean_text = "¿Cuál es el problema? Ninguno. Está 100% perfecto 🎉"
        res_clean, changed_clean = repair_string(clean_text)
        self.assertFalse(changed_clean)
        self.assertEqual(res_clean, clean_text)


if __name__ == "__main__":
    unittest.main()
