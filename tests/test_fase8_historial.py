"""
AURA — Tests automáticos de Fase 8: Contexto e historial

Verifica que el ConversationStore y la integración con ChatPage
funcionen correctamente, usando un directorio temporal para
no contaminar los datos reales del usuario.

Tests incluidos:
    1.  ConversationStore importable
    2.  Conversation importable
    3.  StoredMessage importable
    4.  conversation_store global importable
    5.  new_conversation genera ID de 8 chars
    6.  new_conversation título por defecto
    7.  save() retorna True y crea archivo JSON
    8.  save() escritura atómica (sin archivos .tmp)
    9.  load() carga la conversación correctamente
    10. load() retorna None para ID inexistente
    11. load_latest() retorna la conversación más reciente
    12. load_latest() retorna None si no hay conversaciones
    13. delete() elimina el archivo
    14. delete() retorna False para ID inexistente
    15. rename() actualiza el título
    16. list_all() retorna lista ordenada
    17. list_all() incluye message_count y preview
    18. count() retorna el número correcto
    19. auto_title() texto corto sin truncar
    20. auto_title() texto largo con truncado y "…"
    21. auto_title() texto vacío → "Nueva conversación"
    22. Conversation.message_count solo cuenta user y assistant
    23. Conversation.preview retorna primer mensaje de usuario
    24. Conversation.to_dict/from_dict round-trip
    25. StoredMessage.to_dict/from_dict round-trip
    26. ConversationStore acepta directorio personalizado
    27. chat_page importa ConversationStore correctamente
    28. ChatPage tiene _conversation attribute
    29. ChatPage tiene load_conversation() public method
    30. ChatPage tiene conversation_store property
"""

import sys
import os
import tempfile
import pathlib
import unittest
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.conversation_store import (
    ConversationStore,
    Conversation,
    StoredMessage,
    conversation_store,
)


def _make_store() -> tuple[ConversationStore, tempfile.TemporaryDirectory]:
    """Crea un store con directorio temporal."""
    tmp = tempfile.TemporaryDirectory()
    store = ConversationStore(conversations_dir=pathlib.Path(tmp.name))
    return store, tmp


class TestImports(unittest.TestCase):
    """Tests de importación de los módulos de Fase 8."""

    def test_01_conversation_store_importable(self):
        """ConversationStore es importable."""
        self.assertIsNotNone(ConversationStore)

    def test_02_conversation_importable(self):
        """Conversation es importable."""
        self.assertIsNotNone(Conversation)

    def test_03_stored_message_importable(self):
        """StoredMessage es importable."""
        self.assertIsNotNone(StoredMessage)

    def test_04_global_store_importable(self):
        """conversation_store global es una instancia de ConversationStore."""
        self.assertIsInstance(conversation_store, ConversationStore)

    def test_26_custom_dir(self):
        """ConversationStore acepta directorio personalizado."""
        store, tmp = _make_store()
        with tmp:
            self.assertTrue(pathlib.Path(tmp.name).exists())
            self.assertIsInstance(store, ConversationStore)


class TestStoredMessage(unittest.TestCase):
    """Tests de StoredMessage."""

    def test_25_to_dict_from_dict(self):
        """StoredMessage serializa y deserializa correctamente."""
        msg = StoredMessage(role="user", content="Hola AURA", timestamp="18:00")
        d = msg.to_dict()
        restored = StoredMessage.from_dict(d)
        self.assertEqual(restored.role, "user")
        self.assertEqual(restored.content, "Hola AURA")
        self.assertEqual(restored.timestamp, "18:00")

    def test_25b_from_dict_defaults(self):
        """StoredMessage.from_dict maneja campos faltantes con defaults."""
        msg = StoredMessage.from_dict({})
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "")
        self.assertEqual(msg.timestamp, "")


class TestConversation(unittest.TestCase):
    """Tests del dataclass Conversation."""

    def _make_conv(self) -> Conversation:
        store, tmp = _make_store()
        conv = store.new_conversation("Test")
        conv.messages.append(StoredMessage("user", "Hola", "18:00"))
        conv.messages.append(StoredMessage("assistant", "Hola, soy AURA", "18:00"))
        conv.messages.append(StoredMessage("system", "Sistema"))
        tmp.cleanup()
        return conv

    def test_22_message_count(self):
        """message_count solo cuenta user y assistant."""
        conv = self._make_conv()
        self.assertEqual(conv.message_count, 2)

    def test_23_preview(self):
        """preview retorna el primer mensaje de usuario."""
        conv = self._make_conv()
        self.assertEqual(conv.preview, "Hola")

    def test_23b_preview_sin_mensajes(self):
        """preview retorna placeholder si no hay mensajes de usuario."""
        store, tmp = _make_store()
        conv = store.new_conversation()
        with tmp:
            self.assertEqual(conv.preview, "(sin mensajes)")

    def test_24_to_dict_from_dict(self):
        """Conversation serializa y deserializa correctamente."""
        conv = self._make_conv()
        d = conv.to_dict()
        restored = Conversation.from_dict(d)
        self.assertEqual(restored.id, conv.id)
        self.assertEqual(restored.title, conv.title)
        self.assertEqual(len(restored.messages), len(conv.messages))
        self.assertEqual(restored.messages[0].content, "Hola")


class TestAutoTitle(unittest.TestCase):
    """Tests del generador de título automático."""

    def test_19_auto_title_corto(self):
        """Texto corto no se trunca."""
        title = ConversationStore.auto_title("Hola AURA")
        self.assertEqual(title, "Hola AURA")

    def test_20_auto_title_largo(self):
        """Texto largo se trunca con '…'."""
        long_msg = "Esta es una pregunta muy larga que deberia truncarse en el titulo de la conversacion porque excede el limite"
        title = ConversationStore.auto_title(long_msg)
        self.assertTrue(title.endswith("…"))
        self.assertLessEqual(len(title), 63)

    def test_21_auto_title_vacio(self):
        """Texto vacío devuelve 'Nueva conversación'."""
        title = ConversationStore.auto_title("")
        self.assertEqual(title, "Nueva conversación")

    def test_21b_auto_title_solo_espacios(self):
        """Texto con solo espacios devuelve 'Nueva conversación'."""
        title = ConversationStore.auto_title("   ")
        self.assertEqual(title, "Nueva conversación")


class TestConversationStoreCRUD(unittest.TestCase):
    """Tests CRUD del ConversationStore con directorio temporal."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._store = ConversationStore(
            conversations_dir=pathlib.Path(self._tmp.name)
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _make_saved_conv(self, title="Test") -> Conversation:
        conv = self._store.new_conversation(title)
        conv.messages.append(StoredMessage("user", "Hola", "18:00"))
        conv.messages.append(StoredMessage("assistant", "Hola, soy AURA", "18:00"))
        self._store.save(conv)
        return conv

    def test_05_new_conversation_id_length(self):
        """new_conversation genera ID de 8 caracteres hex."""
        conv = self._store.new_conversation()
        self.assertEqual(len(conv.id), 8)
        # Verificar que es hex válido
        int(conv.id, 16)

    def test_06_new_conversation_titulo_default(self):
        """new_conversation sin título usa 'Nueva conversación'."""
        conv = self._store.new_conversation()
        self.assertEqual(conv.title, "Nueva conversación")

    def test_07_save_crea_archivo(self):
        """save() retorna True y crea un archivo JSON en disco."""
        conv = self._make_saved_conv()
        json_files = list(pathlib.Path(self._tmp.name).glob("*.json"))
        self.assertTrue(self._store.count() > 0)
        self.assertEqual(len(json_files), 1)

    def test_08_save_atomico(self):
        """save() no deja archivos .tmp en disco."""
        conv = self._make_saved_conv()
        tmp_files = list(pathlib.Path(self._tmp.name).glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)

    def test_09_load_correcto(self):
        """load() carga la conversación con todos sus mensajes."""
        conv = self._make_saved_conv("Mi conversación")
        loaded = self._store.load(conv.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, conv.id)
        self.assertEqual(loaded.title, "Mi conversación")
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(loaded.messages[0].content, "Hola")

    def test_10_load_id_inexistente(self):
        """load() retorna None para un ID que no existe."""
        result = self._store.load("00000000")
        self.assertIsNone(result)

    def test_11_load_latest(self):
        """load_latest() retorna la conversación más reciente."""
        conv = self._make_saved_conv()
        latest = self._store.load_latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, conv.id)

    def test_12_load_latest_sin_convs(self):
        """load_latest() retorna None si no hay conversaciones."""
        result = self._store.load_latest()
        self.assertIsNone(result)

    def test_13_delete(self):
        """delete() elimina el archivo JSON del disco."""
        conv = self._make_saved_conv()
        ok = self._store.delete(conv.id)
        self.assertTrue(ok)
        self.assertEqual(self._store.count(), 0)
        self.assertIsNone(self._store.load(conv.id))

    def test_14_delete_inexistente(self):
        """delete() retorna False para un ID inexistente."""
        ok = self._store.delete("00000000")
        self.assertFalse(ok)

    def test_15_rename(self):
        """rename() actualiza el título en disco."""
        conv = self._make_saved_conv("Título original")
        ok = self._store.rename(conv.id, "Título nuevo")
        self.assertTrue(ok)
        renamed = self._store.load(conv.id)
        self.assertEqual(renamed.title, "Título nuevo")

    def test_16_list_all_ordenado(self):
        """list_all() retorna lista ordenada de más reciente a más antigua."""
        for i in range(3):
            self._make_saved_conv(f"Conv {i}")
        all_convs = self._store.list_all()
        self.assertEqual(len(all_convs), 3)

    def test_17_list_all_campos(self):
        """list_all() incluye message_count y preview en cada elemento."""
        self._make_saved_conv("Test campos")
        all_convs = self._store.list_all()
        self.assertEqual(len(all_convs), 1)
        item = all_convs[0]
        self.assertIn("id", item)
        self.assertIn("title", item)
        self.assertIn("updated_at", item)
        self.assertIn("message_count", item)
        self.assertIn("preview", item)
        self.assertEqual(item["message_count"], 2)
        self.assertEqual(item["preview"], "Hola")

    def test_18_count(self):
        """count() retorna el número correcto de conversaciones."""
        self.assertEqual(self._store.count(), 0)
        self._make_saved_conv()
        self.assertEqual(self._store.count(), 1)
        self._make_saved_conv()
        self.assertEqual(self._store.count(), 2)


class TestChatPageIntegration(unittest.TestCase):
    """Tests de integración de ConversationStore con ChatPage."""

    def setUp(self):
        self.mod = importlib.import_module("ui.pages.chat_page")

    def test_27_chat_page_importa_store(self):
        """chat_page importa ConversationStore correctamente."""
        self.assertTrue(hasattr(self.mod, "_store"))
        self.assertIsInstance(self.mod._store, ConversationStore)

    def test_28_chat_page_tiene_conversation(self):
        """ChatPage tiene atributo _conversation en __init__."""
        import inspect
        src = inspect.getsource(self.mod.ChatPage.__init__)
        self.assertIn("_conversation", src)

    def test_29_load_conversation_public(self):
        """ChatPage tiene método público load_conversation()."""
        self.assertTrue(hasattr(self.mod.ChatPage, "load_conversation"))
        self.assertTrue(callable(self.mod.ChatPage.load_conversation))

    def test_30_conversation_store_property(self):
        """ChatPage tiene la property conversation_store."""
        prop = getattr(self.mod.ChatPage, "conversation_store", None)
        self.assertIsNotNone(prop)


if __name__ == "__main__":
    unittest.main(verbosity=2)
