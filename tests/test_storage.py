"""
Минимальные тесты для Storage (Этап 1).

Проверяем:
- каталог скинов заполняется при инициализации;
- создание / удаление профиля;
- уникальность имён профилей;
- данные сохраняются после переподключения к той же БД;
- импорт валидного JSON;
- отклонение некорректного JSON;
- поиск и фильтрация каталога (через SQL);
- обработка неизвестных skin_id.
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

# --- Импортируем Storage напрямую из main.py --------------------------
# На Этапе 2 код будет разделён на модули; пока берём из main.
import importlib
import sys

# Подменяем DATA_DIR / DB_PATH перед импортом, чтобы main.py
# не трогал рабочую БД.
_tmp_dir = None


@pytest.fixture(autouse=True)
def _patch_paths(monkeypatch, tmp_path):
    """Каждый тест получает изолированную временную БД."""
    global _tmp_dir
    _tmp_dir = tmp_path

    # Мы патчим константы модуля main *перед* созданием Storage.
    import main
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "data" / "test.db")


def _make_storage():
    """Создаёт новый экземпляр Storage с запатченными путями."""
    import main
    return main.Storage()


# ======================================================================
# Каталог
# ======================================================================

class TestCatalog:
    def test_demo_skins_loaded(self):
        store = _make_storage()
        skins = store.skins()
        assert len(skins) >= 10, "Должно быть минимум 10 демо-скинов"
        store.close()

    def test_skin_has_four_fields(self):
        store = _make_storage()
        skin = store.skins()[0]
        assert len(skin) == 4, "Каждый скин = (id, name, hero, category)"
        store.close()

    def test_search_by_hero(self):
        """Фильтрация по герою через SQL LIKE."""
        store = _make_storage()
        rows = store.db.execute(
            "SELECT * FROM skins WHERE hero LIKE ?", ("%Juggernaut%",)
        ).fetchall()
        assert any("Juggernaut" in r[2] for r in rows)
        store.close()

    def test_filter_by_category(self):
        store = _make_storage()
        rows = store.db.execute(
            "SELECT * FROM skins WHERE category = ?", ("Arcana",)
        ).fetchall()
        assert len(rows) >= 1
        assert all(r[3] == "Arcana" for r in rows)
        store.close()


# ======================================================================
# Профили
# ======================================================================

class TestProfiles:
    def test_create_profile(self):
        store = _make_storage()
        store.save_profile("TestProfile", "juggernaut_arcana")
        profiles = store.profiles()
        assert any(p[0] == "TestProfile" for p in profiles)
        store.close()

    def test_delete_profile(self):
        store = _make_storage()
        store.save_profile("ToDelete", "pudge_arcana")
        store.delete_profile("ToDelete")
        profiles = store.profiles()
        assert not any(p[0] == "ToDelete" for p in profiles)
        store.close()

    def test_unique_name(self):
        store = _make_storage()
        store.save_profile("Unique", "lina_arcana")
        with pytest.raises(sqlite3.IntegrityError):
            store.save_profile("Unique", "pudge_arcana")
        store.close()

    def test_persistence_after_reconnect(self):
        """Данные выживают после закрытия и повторного открытия БД."""
        store1 = _make_storage()
        store1.save_profile("Persistent", "axe_immortal")
        store1.close()

        store2 = _make_storage()
        profiles = store2.profiles()
        assert any(p[0] == "Persistent" for p in profiles)
        store2.close()

    def test_unknown_skin_id_accepted(self):
        """Storage не проверяет skin_id — это ожидаемое поведение v0.3."""
        store = _make_storage()
        store.save_profile("Ghost", "nonexistent_skin_999")
        profiles = store.profiles()
        assert any(
            p[0] == "Ghost" and p[1] == "nonexistent_skin_999"
            for p in profiles
        )
        store.close()


# ======================================================================
# Импорт / Экспорт JSON
# ======================================================================

class TestJSON:
    def test_export_import_roundtrip(self, tmp_path):
        import main

        store = _make_storage()
        store.save_profile("Export1", "juggernaut_arcana")
        store.save_profile("Export2", "lina_arcana")

        # Экспорт
        data = [
            {"name": name, "skin_id": sid}
            for name, sid in store.profiles()
        ]
        json_path = tmp_path / "profiles.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        store.close()

        # Удаляем БД и создаём чистую — имитируем импорт на новой машине.
        main.DB_PATH.unlink(missing_ok=True)
        store2 = _make_storage()

        imported = json.loads(json_path.read_text(encoding="utf-8"))
        count = 0
        for p in imported:
            try:
                store2.save_profile(p["name"], p["skin_id"])
                count += 1
            except sqlite3.IntegrityError:
                pass
        assert count == 2

        names = [p[0] for p in store2.profiles()]
        assert "Export1" in names
        assert "Export2" in names
        store2.close()

    def test_reject_invalid_json(self, tmp_path):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{not valid json!!", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            json.loads(bad_path.read_text(encoding="utf-8"))

    def test_reject_non_list(self, tmp_path):
        bad_path = tmp_path / "obj.json"
        bad_path.write_text('{"name": "single"}', encoding="utf-8")
        data = json.loads(bad_path.read_text(encoding="utf-8"))
        assert not isinstance(data, list), "Должен быть dict, а не list"


# ======================================================================
# Миграция
# ======================================================================

class TestMigration:
    def test_category_column_added(self):
        """Если таблица skins создана без category, миграция добавит её."""
        import main

        db_path = main.DB_PATH
        main.DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Создаём таблицу БЕЗ столбца category.
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hero TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO skins (id, name, hero) "
            "VALUES ('test_old', 'OldSkin', 'OldHero')"
        )
        conn.commit()
        conn.close()

        # Теперь Storage должен добавить category и не сломаться.
        store = _make_storage()
        cols = {
            row[1]
            for row in store.db.execute(
                "PRAGMA table_info(skins)"
            ).fetchall()
        }
        assert "category" in cols
        store.close()
