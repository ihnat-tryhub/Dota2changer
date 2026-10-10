"""
Dota Skin Studio  v0.5.0
========================
• Каталог с косметикой и иконками предметов из файлов игры
• Сбор нескольких слотов одного героя в комплект
• Локальные профили и запуск Dota 2 через Steam
"""

import logging
import sys
import json
import sqlite3
import hashlib
from pathlib import Path

log = logging.getLogger(__name__)

APP_VERSION = "0.5.0"

from PySide6.QtCore import Qt, QThread, Signal, QObject, QRunnable, QThreadPool, QUrl, QSize
from PySide6.QtGui import QPixmap, QColor, QPalette, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QMessageBox, QComboBox,
    QFrame, QFileDialog, QScrollArea,
    QGridLayout, QTabWidget, QGroupBox, QProgressBar,
)

# ─────────────────────────────────────────────────────────────────────────────
# Пути
# ─────────────────────────────────────────────────────────────────────────────

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "skins.db"
SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_DOTA_PATH = Path(r"Q:\SteamLibrary\steamapps\common\dota 2 beta")
ITEMS_GAME_REL = Path("game/dota/scripts/items/items_game.txt")

# ─────────────────────────────────────────────────────────────────────────────
# Демо-каталог
# ─────────────────────────────────────────────────────────────────────────────

SKINS = [
    ("juggernaut_arcana",        "Bladeform Legacy",              "Juggernaut",       "Arcana"),
    ("phantom_assassin_arcana",  "Manifold Paradox",              "Phantom Assassin", "Arcana"),
    ("pudge_arcana",             "Feast of Abscession",           "Pudge",            "Arcana"),
    ("lina_arcana",              "Fiery Soul of the Slayer",      "Lina",             "Arcana"),
    ("terrorblade_arcana",       "Fractal Horns of Inner Abysm",  "Terrorblade",      "Arcana"),
    ("crystal_maiden_set",       "Frost Avalanche",               "Crystal Maiden",   "Set"),
    ("invoker_persona",          "The Magus Cypher",              "Invoker",          "Persona"),
    ("axe_immortal",             "The Burning Scourge",           "Axe",              "Immortal"),
    ("anti_mage_set",            "Brands of the Reaper",          "Anti-Mage",        "Set"),
    ("windranger_arcana",        "Compass of the Rising Gale",    "Windranger",       "Arcana"),
    ("dragon_knight_immortal",   "Davion of Dragon Hold",         "Dragon Knight",    "Immortal"),
    ("storm_spirit_immortal",    "Stormwrought Arbiter",          "Storm Spirit",     "Immortal"),
    ("lion_immortal",            "The Finger of Death",           "Lion",             "Immortal"),
    ("drow_ranger_arcana",       "Tempest Helm of the Thundergod","Drow Ranger",      "Arcana"),
    ("io_arcana",                "Genuine Scepter of Davion",     "Io",               "Arcana"),
]

CATEGORY_COLORS = {
    "Arcana":   "#c0392b",
    "Immortal": "#e67e22",
    "Persona":  "#8e44ad",
    "Set":      "#2980b9",
    "Common":   "#8b929f",
    "Uncommon": "#6cae58",
    "Rare":     "#4d8fd6",
    "Mythical": "#9d62d0",
    "Legendary":"#c58b38",
    "Ancient":  "#c85b4e",
    "Other":    "#555e6b",
}

SLOT_LABELS = {
    "head": "Голова",
    "weapon": "Правая рука",
    "offhand_weapon": "Левая рука",
    "arms": "Руки",
    "shoulder": "Плечи",
    "back": "Спина",
    "belt": "Пояс",
    "legs": "Ноги",
    "neck": "Шея",
    "misc": "Прочее",
    "mount": "Ездовой питомец",
    "tail": "Хвост",
    "set": "Готовый набор",
}


def slot_label(slot: str) -> str:
    normalized = slot.casefold()
    return SLOT_LABELS.get(normalized, normalized.replace("_", " ").title())


class ItemIconSignals(QObject):
    loaded = Signal(str, str, str)


class ItemIconLoader(QRunnable):
    """Извлекает одну иконку предмета из VPK в фоновом пуле."""

    def __init__(self, skin_id: str, hero: str, icon_ref: str,
                 vpk_path: Path, out_file: Path):
        super().__init__()
        self.skin_id = skin_id
        self.hero = hero
        self.icon_ref = icon_ref
        self.vpk_path = vpk_path
        self.out_file = out_file
        self.signals = ItemIconSignals()

    def run(self):
        result = ""
        try:
            if self.vpk_path.is_file() and self.icon_ref:
                import catalog_builder
                if catalog_builder.extract_icon_from_vpk(
                    self.vpk_path, self.icon_ref, self.out_file
                ):
                    result = str(self.out_file)
        except Exception:
            log.debug("Item icon extraction failed: %s", self.skin_id, exc_info=True)
        self.signals.loaded.emit(self.skin_id, result, self.hero)


class CatalogUpdateWorker(QThread):
    progress = Signal(str)
    completed = Signal(int, str)

    def __init__(self, dota_path: Path, parent=None):
        super().__init__(parent)
        self.dota_path = dota_path

    def run(self):
        try:
            import catalog_builder

            self.progress.emit("Обновляю файлы игры…")
            catalog_builder.extract_game_files(self.dota_path, DATA_DIR, force=True)
            self.progress.emit("Собираю предметы и слоты…")
            count = catalog_builder.update_database(DB_PATH, DATA_DIR)
            if count < 1:
                raise RuntimeError(
                    "Каталог получился пустым. Проверь путь к Dota 2 и целостность VPK."
                )
            self.completed.emit(count, "")
        except Exception as exc:
            log.exception("Catalog update failed")
            self.completed.emit(0, str(exc))


def item_icon_cache_path(icon_ref: str, skin_id: str, icon_dir: Path,
                        revision: str = "") -> Path:
    """Возвращает безопасный и стабильный путь к локальному PNG-кэшу."""
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in skin_id)
    for direct in (
        icon_dir / f"{safe_id}.png",
        icon_dir.parent / "icons" / f"{safe_id}.png",
        icon_dir.parent / f"{safe_id}.png",
    ):
        if direct.is_file():
            return direct

    if not icon_ref:
        return icon_dir / f"{safe_id}.png"

    normalized = icon_ref.replace("\\", "/").strip("/")
    base = normalized.rsplit("/", 1)[-1]
    safe_base = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)
    for direct in (
        icon_dir / f"{safe_base}.png",
        icon_dir.parent / "icons" / f"{safe_base}.png",
        icon_dir.parent / f"{safe_base}.png",
    ):
        if direct.is_file():
            return direct

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    version = f"_{revision}" if revision else ""
    return icon_dir / f"{safe_base[:40]}_{digest}{version}.png"


# ─────────────────────────────────────────────────────────────────────────────
# Хранилище
# ─────────────────────────────────────────────────────────────────────────────

class Storage:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS skins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hero TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Other',
                icon TEXT,
                slot TEXT NOT NULL DEFAULT 'set'
            )
        """)

        # Миграция старой базы: добавляем категорию,
        # не удаляя существующие записи.
        columns = {
            row[1]
            for row in self.db.execute("PRAGMA table_info(skins)").fetchall()
        }
        if "category" not in columns:
            self.db.execute(
                "ALTER TABLE skins ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'"
            )
        if "icon" not in columns:
            self.db.execute("ALTER TABLE skins ADD COLUMN icon TEXT")
        if "slot" not in columns:
            self.db.execute("ALTER TABLE skins ADD COLUMN slot TEXT NOT NULL DEFAULT 'set'")

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                skin_id TEXT
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS profile_items (
                profile_name TEXT NOT NULL,
                slot TEXT NOT NULL,
                skin_id TEXT NOT NULL,
                PRIMARY KEY (profile_name, slot)
            )
        """)
        self.db.commit()

        count = self.db.execute("SELECT COUNT(*) FROM skins").fetchone()[0]
        if count == 0:
            populated = False
            try:
                import catalog_builder
                cnt = catalog_builder.update_database(DB_PATH, DATA_DIR)
                if cnt > 0:
                    populated = True
            except Exception:
                pass
            if not populated:
                for skin_id, name, hero, category in SKINS:
                    self.db.execute(
                        "INSERT OR IGNORE INTO skins (id, name, hero, category) VALUES (?, ?, ?, ?)",
                        (skin_id, name, hero, category),
                    )
                self.db.commit()

    def skins(self):
        return self.db.execute(
            "SELECT id, name, hero, category, icon, slot FROM skins ORDER BY hero, slot, name"
        ).fetchall()

    def profiles(self):
        return self.db.execute(
            "SELECT name, skin_id FROM profiles ORDER BY name"
        ).fetchall()

    def save_profile(self, name: str, skin_id: str):
        self.db.execute(
            "INSERT INTO profiles (name, skin_id) VALUES (?, ?)", (name, skin_id)
        )
        self.db.commit()

    def save_loadout(self, name: str, skins: list[tuple]):
        primary_skin_id = skins[0][0] if skins else None
        with self.db:
            self.db.execute(
                "INSERT INTO profiles (name, skin_id) VALUES (?, ?)",
                (name, primary_skin_id),
            )
            self.db.executemany(
                "INSERT INTO profile_items (profile_name, slot, skin_id) VALUES (?, ?, ?)",
                [
                    (name, skin[5] if len(skin) > 5 and skin[5] else "set", skin[0])
                    for skin in skins
                ],
            )

    def profile_items(self, name: str) -> list[str]:
        return [
            row[0]
            for row in self.db.execute(
                "SELECT skin_id FROM profile_items WHERE profile_name=? ORDER BY slot",
                (name,),
            ).fetchall()
        ]

    def profile_item_count(self, name: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM profile_items WHERE profile_name=?", (name,)
        ).fetchone()[0]

    def delete_profile(self, name: str):
        self.db.execute("DELETE FROM profile_items WHERE profile_name=?", (name,))
        self.db.execute("DELETE FROM profiles WHERE name=?", (name,))
        self.db.commit()

    def close(self):
        self.db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Настройки
# ─────────────────────────────────────────────────────────────────────────────

class Settings:
    """Простое JSON-хранилище настроек приложения."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict = {}
        self._load()

    def _load(self):
        try:
            self._data = json.loads(SETTINGS_PATH.read_text("utf-8"))
        except Exception:
            self._data = {}

    def save(self):
        SETTINGS_PATH.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8"
        )

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self.save()


# ─────────────────────────────────────────────────────────────────────────────
# Глобальный стиль
# ─────────────────────────────────────────────────────────────────────────────

STYLE = """
* { outline: none; }
QWidget {
    background-color: #0e1117;
    color: #dde0e8;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow { background: #0e1117; }

QLabel#subtitle { color: #6b7280; font-size: 9pt; }

QLineEdit, QComboBox {
    background: #1a1e2a;
    border: 1px solid #2d3347;
    border-radius: 8px;
    padding: 8px 12px;
    color: #dde0e8;
    selection-background-color: #a84436;
}
QLineEdit:focus, QComboBox:focus { border-color: #c0392b; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: #1a1e2a;
    border: 1px solid #2d3347;
    selection-background-color: #c0392b;
}

QPushButton {
    background: #1e2233;
    border: 1px solid #2d3347;
    border-radius: 8px;
    padding: 9px 16px;
    color: #dde0e8;
}
QPushButton:hover { background: #252a3a; border-color: #4a5068; }
QPushButton:pressed { background: #1a1e2a; }
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #9b2335, stop:1 #c0392b);
    border: none;
    font-weight: bold;
    color: #ffffff;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #b5283d, stop:1 #d44132);
}
QPushButton#danger {
    background: #2a1a1a;
    border: 1px solid #6b2020;
    color: #e07070;
}
QPushButton#danger:hover { background: #3a2020; border-color: #a03030; }
QPushButton#success {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1a6b3a, stop:1 #22884a);
    border: none;
    font-weight: bold;
    color: #ffffff;
}
QPushButton#success:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1e804a, stop:1 #28a055);
}
QPushButton#restore {
    background: #1a2a3a;
    border: 1px solid #2a4a6a;
    color: #70b0e0;
}
QPushButton#restore:hover { background: #20304a; border-color: #3a6090; }

QFrame#panel {
    background: #131623;
    border: 1px solid #1e2438;
    border-radius: 12px;
}
QFrame#card {
    background: #131623;
    border: 1px solid #1e2438;
    border-radius: 10px;
}
QFrame#card:hover {
    border-color: #c0392b;
    background: #1a1e2e;
}

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #0e1117;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2d3347;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #c0392b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QListWidget {
    background: #131623;
    border: 1px solid #1e2438;
    border-radius: 8px;
    padding: 4px;
}
QListWidget::item { padding: 9px 12px; border-radius: 6px; }
QListWidget::item:selected { background: #711e18; color: white; }
QListWidget::item:hover:!selected { background: #1e2438; }

QTabWidget::pane {
    border: 1px solid #1e2438;
    border-radius: 10px;
    background: #0e1117;
}
QTabBar::tab {
    background: #131623;
    border: 1px solid #1e2438;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 10px 22px;
    color: #6b7280;
    font-weight: bold;
    min-width: 90px;
}
QTabBar::tab:selected {
    background: #1e2438;
    color: #ffffff;
    border-bottom: 2px solid #c0392b;
}
QTabBar::tab:hover:!selected { background: #1a1e2a; color: #bbb; }

QGroupBox {
    border: 1px solid #1e2438;
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px;
    font-weight: bold;
    color: #a0a8c0;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; top: -1px; }
"""


# ─────────────────────────────────────────────────────────────────────────────
# Виджет карточки скина
# ─────────────────────────────────────────────────────────────────────────────

class SkinCard(QFrame):
    """Кликабельная карточка с изображением предмета."""

    clicked = Signal(object)

    CARD_W = 210
    CARD_H = 242
    IMAGE_H = 124

    def __init__(self, skin: tuple, pixmap: QPixmap | None = None):
        super().__init__()
        self.skin = skin
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self._selected = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Область иконки косметического предмета
        self._img_label = QLabel()
        self._img_label.setFixedHeight(self.IMAGE_H)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet(
            "background: #0b0e16; border-radius: 10px 10px 0 0;"
        )
        if pixmap:
            self.set_pixmap(pixmap)
        else:
            self._show_placeholder("Загружаем иконку предмета…")
        layout.addWidget(self._img_label)

        # Нижняя часть — текст
        info = QWidget()
        info.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(8, 5, 8, 6)
        info_layout.setSpacing(2)

        _, name, hero, category = skin[:4]
        slot = skin[5] if len(skin) > 5 and skin[5] else "set"
        cat_color = CATEGORY_COLORS.get(category, "#555e6b")

        hero_lbl = QLabel(hero)
        hero_lbl.setStyleSheet(
            "color: #8a8fa8; font-size: 8pt; background: transparent;"
        )
        info_layout.addWidget(hero_lbl)

        slot_lbl = QLabel(slot_label(slot))
        slot_lbl.setStyleSheet(
            "color: #b6bfd5; font-size: 8pt; background: transparent;"
        )
        info_layout.addWidget(slot_lbl)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            "color: #e0e3ed; font-size: 9pt; font-weight: bold; background: transparent;"
        )
        name_lbl.setWordWrap(True)
        name_lbl.setMinimumHeight(34)
        name_lbl.setMaximumHeight(40)
        name_lbl.setToolTip(name)
        info_layout.addWidget(name_lbl)

        cat_lbl = QLabel(f"● {category}")
        cat_lbl.setStyleSheet(
            f"color: {cat_color}; font-size: 8pt; font-weight: bold; background: transparent;"
        )
        info_layout.addWidget(cat_lbl)

        layout.addWidget(info)

    def _show_placeholder(self, text: str):
        self._img_label.setPixmap(QPixmap())
        self._img_label.setText(f"◇\n{text}")
        self._img_label.setStyleSheet(
            "background: #0b0e16; border-radius: 10px 10px 0 0;"
            "color: #687087; font-size: 9pt;"
        )

    def set_pixmap(self, pixmap: QPixmap):
        self._img_label.setText("")
        self._img_label.setStyleSheet(
            "background: #0b0e16; border-radius: 10px 10px 0 0;"
        )
        self._img_label.setPixmap(
            pixmap.scaled(self.CARD_W - 16, self.IMAGE_H - 12,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        )

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.setStyleSheet(
                "QFrame#card { background: #1e1428; border: 2px solid #c0392b;"
                " border-radius: 10px; }"
            )
        else:
            self.setStyleSheet("")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.skin)
        super().mousePressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Страница каталога
# ─────────────────────────────────────────────────────────────────────────────

class CatalogPage(QWidget):
    skin_toggled = Signal(object, bool)
    skin_image_ready = Signal(str, object)

    PAGE_SIZE = 60

    def __init__(self, all_skins: list, image_cache: dict,
                 icon_dir: Path | None = None, vpk_path: Path | None = None,
                 parent=None):
        super().__init__(parent)
        self.all_skins = all_skins
        self.image_cache = image_cache
        self.icon_dir = icon_dir or (DATA_DIR / "icons")
        self.vpk_path = vpk_path
        self._icon_revision = self._vpk_revision(vpk_path)
        self._cards: dict[str, SkinCard] = {}
        self._selected_ids: set[str] = set()
        self._active_icon_loaders: dict[str, ItemIconLoader] = {}
        self._item_icon_cache: dict[str, QPixmap | None] = {}
        self._icon_attempted: set[str] = set()
        self._skin_icon_refs = {
            skin[0]: (skin[4] if len(skin) > 4 else None)
            for skin in all_skins
        }
        self._displayed_skins: list[tuple] = []
        self._icon_pool = QThreadPool(self)
        self._icon_pool.setMaxThreadCount(2)
        self._page_limit = self.PAGE_SIZE

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Поиск и фильтры разделены, чтобы элементы не сжимались в узком окне.
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Поиск по предмету или герою...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search_changed)
        controls.addWidget(self.search, 3)

        controls.addStretch(1)
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("subtitle")
        self.count_lbl.setMinimumWidth(110)
        controls.addWidget(self.count_lbl)

        self.selection_count_lbl = QLabel("В комплекте: 0")
        self.selection_count_lbl.setObjectName("subtitle")
        self.selection_count_lbl.setMinimumWidth(120)
        controls.addWidget(self.selection_count_lbl)
        root.addLayout(controls)

        filters = QHBoxLayout()

        # Выпадающий список всех героев
        self.hero_filter = QComboBox()
        self._populate_heroes()
        self.hero_filter.currentTextChanged.connect(self._on_filter_changed)
        filters.addWidget(self.hero_filter, 2)

        self.slot_filter = QComboBox()
        self.slot_filter.addItem("Все слоты")
        self.slot_filter.addItems(sorted(
            {slot_label(s[5]) for s in all_skins if len(s) > 5 and s[5]},
            key=str.casefold,
        ))
        self.slot_filter.currentTextChanged.connect(self._on_filter_changed)
        filters.addWidget(self.slot_filter, 2)

        self.cat_filter = QComboBox()
        self._populate_categories()
        self.cat_filter.currentTextChanged.connect(self._on_filter_changed)
        filters.addWidget(self.cat_filter, 2)

        self.clear_filters_btn = QPushButton("Сбросить")
        self.clear_filters_btn.clicked.connect(self._clear_filters)
        filters.addWidget(self.clear_filters_btn)
        filters.addStretch(1)
        root.addLayout(filters)

        # Скроллируемая сетка карточек
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QVBoxLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        self._grid_layout.setSpacing(12)

        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.addLayout(self._grid)

        self._empty_lbl = QLabel("Ничего не найдено. Попробуй изменить поиск или фильтры.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setObjectName("subtitle")
        self._empty_lbl.setMinimumHeight(120)
        self._empty_lbl.hide()
        self._grid_layout.addWidget(self._empty_lbl)

        # Кнопка «Показать ещё»
        self._more_btn = QPushButton("⬇  Показать ещё предметы")
        self._more_btn.setStyleSheet(
            "background: #1a1e2e; border: 1px solid #2d3347; border-radius: 8px; "
            "padding: 10px; font-weight: bold; color: #a4b3d6;"
        )
        self._more_btn.clicked.connect(self._load_more)
        self._more_btn.hide()
        self._grid_layout.addWidget(self._more_btn)

        self._scroll.setWidget(self._grid_widget)
        root.addWidget(self._scroll, 1)

        self._refresh()

    def _populate_heroes(self):
        heroes = sorted({s[2] for s in self.all_skins if s[2]})
        self.hero_filter.blockSignals(True)
        self.hero_filter.clear()
        self.hero_filter.addItem("Все герои")
        self.hero_filter.addItems(heroes)
        self.hero_filter.blockSignals(False)

    def _populate_categories(self):
        categories = sorted(
            {s[3] for s in self.all_skins if len(s) > 3},
            key=str.casefold,
        )
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItem("Все редкости")
        self.cat_filter.addItems(categories)
        self.cat_filter.blockSignals(False)

    @staticmethod
    def _vpk_revision(vpk_path: Path | None) -> str:
        try:
            stat = vpk_path.stat()
            raw = f"{stat.st_size}:{stat.st_mtime_ns}"
            return hashlib.sha1(raw.encode("ascii")).hexdigest()[:10]
        except (AttributeError, OSError):
            return "no_vpk"

    def set_skins(self, skins: list):
        self.all_skins = skins
        new_icon_refs = {
            skin[0]: (skin[4] if len(skin) > 4 else None)
            for skin in skins
        }
        active_ids = set(self._active_icon_loaders)
        self._item_icon_cache = {
            skin_id: pixmap
            for skin_id, pixmap in self._item_icon_cache.items()
            if pixmap is not None and self._skin_icon_refs.get(skin_id) == new_icon_refs.get(skin_id)
        }
        self._icon_attempted.intersection_update(active_ids)
        self._skin_icon_refs = new_icon_refs
        for card in self._cards.values():
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        current_hero = self.hero_filter.currentText()
        current_slot = self.slot_filter.currentText()
        current_category = self.cat_filter.currentText()
        self._populate_heroes()
        self._populate_categories()
        self.slot_filter.blockSignals(True)
        self.slot_filter.clear()
        self.slot_filter.addItem("Все слоты")
        self.slot_filter.addItems(sorted(
            {slot_label(s[5]) for s in skins if len(s) > 5 and s[5]},
            key=str.casefold,
        ))
        self.slot_filter.blockSignals(False)
        idx = self.hero_filter.findText(current_hero)
        if idx >= 0:
            self.hero_filter.setCurrentIndex(idx)
        idx = self.slot_filter.findText(current_slot)
        if idx >= 0:
            self.slot_filter.setCurrentIndex(idx)
        idx = self.cat_filter.findText(current_category)
        if idx >= 0:
            self.cat_filter.setCurrentIndex(idx)
        self._page_limit = self.PAGE_SIZE
        self._refresh()

    def set_vpk_path(self, vpk_path: Path | None):
        revision = self._vpk_revision(vpk_path)
        if self.vpk_path == vpk_path and self._icon_revision == revision:
            return
        self.vpk_path = vpk_path
        self._icon_revision = revision
        self._item_icon_cache.clear()
        self._icon_attempted.clear()

    def image_for_skin(self, skin: tuple) -> QPixmap | None:
        return self._item_icon_cache.get(skin[0])

    def set_selected_ids(self, skin_ids):
        self._selected_ids = set(skin_ids)
        self.selection_count_lbl.setText(f"В комплекте: {len(self._selected_ids)}")
        for skin_id, card in self._cards.items():
            card.set_selected(skin_id in self._selected_ids)

    def filter_by_hero(self, hero: str | None):
        target = hero if hero else "Все герои"
        index = self.hero_filter.findText(target)
        if index >= 0 and self.hero_filter.currentIndex() != index:
            self.hero_filter.setCurrentIndex(index)

    def _on_search_changed(self):
        self._page_limit = self.PAGE_SIZE
        self._refresh()

    def _on_filter_changed(self):
        self._page_limit = self.PAGE_SIZE
        self._refresh()

    def _load_more(self):
        self._page_limit += self.PAGE_SIZE
        self._refresh()

    def _clear_filters(self):
        self.search.clear()
        self.hero_filter.setCurrentIndex(0)
        self.slot_filter.setCurrentIndex(0)
        self.cat_filter.setCurrentIndex(0)

    def _get_card(self, skin: tuple) -> SkinCard:
        skin_id = skin[0]
        if skin_id not in self._cards:
            hero = skin[2]
            icon_ref = skin[4] if len(skin) > 4 and skin[4] else ""
            px = self._item_icon_cache.get(skin_id)
            if skin_id not in self._item_icon_cache:
                icon_file = item_icon_cache_path(
                    icon_ref, skin_id, self.icon_dir, self._icon_revision
                )
                if icon_file.is_file():
                    loaded = QPixmap(str(icon_file))
                    if not loaded.isNull():
                        px = loaded
                        self._item_icon_cache[skin_id] = loaded
            card = SkinCard(skin, px)
            card.clicked.connect(self._on_card_clicked)
            if skin_id in self._selected_ids:
                card.set_selected(True)
            if skin_id in self._icon_attempted and self._item_icon_cache.get(skin_id) is None:
                card._show_placeholder("Иконка предмета недоступна")
            self._cards[skin_id] = card
            if px is not None and not px.isNull():
                self.skin_image_ready.emit(skin_id, px)
            if skin_id not in self._item_icon_cache:
                self._start_item_icon_loader(skin)
        return self._cards[skin_id]

    def _start_item_icon_loader(self, skin: tuple):
        skin_id, _, hero, _ = skin[:4]
        if skin_id in self._icon_attempted:
            return
        self._icon_attempted.add(skin_id)

        icon_ref = skin[4] if len(skin) > 4 and skin[4] else ""
        icon_file = item_icon_cache_path(
            icon_ref, skin_id, self.icon_dir, self._icon_revision
        )
        if not icon_ref or self.vpk_path is None or not self.vpk_path.is_file():
            self._item_icon_cache[skin_id] = None
            card = self._cards.get(skin_id)
            if card:
                card._show_placeholder("Иконка предмета недоступна")
            return

        loader = ItemIconLoader(skin_id, hero, icon_ref, self.vpk_path, icon_file)
        loader.signals.loaded.connect(self._on_item_icon_loaded)
        self._active_icon_loaders[skin_id] = loader
        self._icon_pool.start(loader)

    def _on_item_icon_loaded(self, skin_id: str, icon_file: str, hero: str):
        self._active_icon_loaders.pop(skin_id, None)
        pixmap = QPixmap(icon_file) if icon_file else QPixmap()
        if not pixmap.isNull():
            self._item_icon_cache[skin_id] = pixmap
            card = self._cards.get(skin_id)
            if card:
                card.set_pixmap(pixmap)
            self.skin_image_ready.emit(skin_id, pixmap)
            return

        self._item_icon_cache[skin_id] = None
        card = self._cards.get(skin_id)
        if card:
            card._show_placeholder("Иконка предмета недоступна")

    def _on_card_clicked(self, skin: tuple):
        skin_id = skin[0]
        selected = skin_id not in self._selected_ids
        if selected:
            self._selected_ids.add(skin_id)
        else:
            self._selected_ids.discard(skin_id)
        self.set_selected_ids(self._selected_ids)
        self.skin_toggled.emit(skin, selected)

    def _refresh(self, *_):
        query    = self.search.text().casefold().strip()
        hero_val = self.hero_filter.currentText()
        category = self.cat_filter.currentText()
        slot = self.slot_filter.currentText()

        visible = []
        for skin in self.all_skins:
            _, name, hero, kind = skin[:4]
            if hero_val != "Все герои" and hero != hero_val:
                continue
            if category != "Все редкости" and kind != category:
                continue
            item_slot = skin[5] if len(skin) > 5 and skin[5] else "set"
            if slot != "Все слоты" and slot_label(item_slot) != slot:
                continue
            if query and query not in f"{name} {hero} {kind} {slot_label(item_slot)}".casefold():
                continue
            visible.append(skin)

        total_visible = len(visible)
        if hero_val != "Все герои":
            # Если выбран конкретный герой — показываем сразу все его скины
            page_items = visible
            self._more_btn.hide()
            self.count_lbl.setText(f"{total_visible} предметов ({hero_val})")
        else:
            page_items = visible[:self._page_limit]
            if len(visible) > len(page_items):
                self._more_btn.setText(f"⬇  Показать ещё (показано {len(page_items)} из {total_visible})")
                self._more_btn.show()
            else:
                self._more_btn.hide()
            self.count_lbl.setText(f"{total_visible} предметов")

        self._displayed_skins = page_items
        self._layout_cards()

    def _layout_cards(self):
        if not hasattr(self, "_grid"):
            return
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().hide()
        self._empty_lbl.setVisible(not self._displayed_skins)

        spacing = self._grid.horizontalSpacing()
        if spacing < 0:
            spacing = 12
        available = max(1, self._scroll.viewport().width())
        columns = max(1, (available + spacing) // (SkinCard.CARD_W + spacing))
        for col in range(self._grid.columnCount() + 1):
            self._grid.setColumnStretch(col, 0)

        for index, skin in enumerate(self._displayed_skins):
            row, col = divmod(index, columns)
            card = self._get_card(skin)
            self._grid.addWidget(card, row, col)
            card.show()
        self._grid.setColumnStretch(columns, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_cards()

    def stop_loaders(self):
        self._icon_pool.clear()
        self._icon_pool.waitForDone(1500)


# ─────────────────────────────────────────────────────────────────────────────
# Страница комплектов и профилей
# ─────────────────────────────────────────────────────────────────────────────

class ProfilesPage(QWidget):
    loadout_changed = Signal(object, str)

    def __init__(self, store: Storage, all_skins: list,
                 settings: Settings, parent=None):
        super().__init__(parent)
        self.store = store
        self.all_skins = all_skins
        self.settings = settings
        self.selected_items: dict[str, tuple] = {}
        self._item_pixmaps: dict[str, QPixmap] = {}
        self.selected_hero = ""
        self._skins_by_id = {skin[0]: skin for skin in all_skins}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        loadout_group = QGroupBox("Текущий комплект")
        loadout_layout = QVBoxLayout(loadout_group)
        self._loadout_status = QLabel("Выбери предметы одного героя во вкладке «Каталог».")
        self._loadout_status.setObjectName("subtitle")
        self._loadout_status.setWordWrap(True)
        loadout_layout.addWidget(self._loadout_status)

        self.loadout_list = QListWidget()
        self.loadout_list.setMinimumHeight(180)
        self.loadout_list.setIconSize(QSize(52, 52))
        loadout_layout.addWidget(self.loadout_list)

        loadout_actions = QHBoxLayout()
        self._remove_item_btn = QPushButton("Убрать выбранный слот")
        self._remove_item_btn.clicked.connect(self.remove_selected_item)
        loadout_actions.addWidget(self._remove_item_btn)
        self._clear_loadout_btn = QPushButton("Очистить комплект")
        self._clear_loadout_btn.clicked.connect(self.clear_loadout)
        loadout_actions.addWidget(self._clear_loadout_btn)
        loadout_actions.addStretch()
        loadout_layout.addLayout(loadout_actions)
        root.addWidget(loadout_group, 1)

        # ── Форма нового профиля ────────────────────────────────────────────
        new_frame = QGroupBox("Сохранить комплект в профиль")
        new_layout = QHBoxLayout(new_frame)
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Название профиля...")
        new_layout.addWidget(self.profile_name, 1)

        save_btn = QPushButton("＋  Сохранить")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save_profile)
        new_layout.addWidget(save_btn)
        root.addWidget(new_frame)

        # ── Список профилей ─────────────────────────────────────────────────
        root.addWidget(QLabel("Сохранённые комплекты"))
        self.profile_list = QListWidget()
        self.profile_list.setMinimumHeight(150)
        self.profile_list.itemDoubleClicked.connect(lambda _: self.load_profile())
        root.addWidget(self.profile_list, 1)

        btns = QHBoxLayout()
        load_btn = QPushButton("Загрузить комплект")
        load_btn.setObjectName("primary")
        load_btn.clicked.connect(self.load_profile)
        btns.addWidget(load_btn)

        del_btn = QPushButton("🗑  Удалить выбранный")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_profile)
        btns.addWidget(del_btn)

        exp_btn = QPushButton("📤  Экспорт JSON")
        exp_btn.clicked.connect(self.export_profiles)
        btns.addWidget(exp_btn)

        imp_btn = QPushButton("📥  Импорт JSON")
        imp_btn.clicked.connect(self.import_profiles)
        btns.addWidget(imp_btn)

        root.addLayout(btns)
        self._refresh_loadout()
        self.refresh_profiles()

    def toggle_skin(self, skin: tuple, selected: bool) -> bool:
        """Добавляет/убирает предмет, сохраняя один герой и один предмет на слот."""
        skin_id = skin[0]
        slot = skin[5] if len(skin) > 5 and skin[5] else "set"
        hero = skin[2]

        if selected:
            if self.selected_items and self.selected_hero != hero:
                QMessageBox.information(
                    self, "Другой герой",
                    f"Текущий комплект собран для {self.selected_hero}. "
                    "Очисти его, чтобы начать комплект для другого героя.",
                )
                return False
            self.selected_hero = hero
            if slot == "set":
                self.selected_items.clear()
            else:
                self.selected_items.pop("set", None)
            self.selected_items[slot] = skin
        else:
            current = self.selected_items.get(slot)
            if current and current[0] == skin_id:
                self.selected_items.pop(slot, None)

        if not self.selected_items:
            self.selected_hero = ""
        self._refresh_loadout()
        self._emit_loadout_changed()
        return True

    def set_item_image(self, skin_id: str, pixmap: QPixmap):
        if pixmap is None or pixmap.isNull():
            return
        self._item_pixmaps[skin_id] = pixmap
        if any(skin[0] == skin_id for skin in self.selected_items.values()):
            self._refresh_loadout()

    def set_catalog(self, skins: list):
        self.all_skins = skins
        self._skins_by_id = {skin[0]: skin for skin in skins}
        selected = [self._skins_by_id[skin[0]] for skin in self.selected_items.values()
                    if skin[0] in self._skins_by_id]
        self.selected_items = {
            skin[5] if len(skin) > 5 and skin[5] else "set": skin
            for skin in self._normalize_loadout(selected)
        }
        if self.selected_items:
            self.selected_hero = next(iter(self.selected_items.values()))[2]
        else:
            self.selected_hero = ""
        self._item_pixmaps = {
            skin_id: pixmap for skin_id, pixmap in self._item_pixmaps.items()
            if skin_id in self._skins_by_id
        }
        self._refresh_loadout()
        self.refresh_profiles()
        self._emit_loadout_changed()

    def _ordered_items(self):
        return sorted(
            self.selected_items.values(),
            key=lambda skin: (slot_label(skin[5] if len(skin) > 5 else "set").casefold(), skin[1].casefold()),
        )

    @staticmethod
    def _normalize_loadout(skins: list[tuple]) -> list[tuple]:
        if not skins:
            return []
        hero = skins[0][2]
        if any(skin[2] != hero for skin in skins):
            return []
        by_slot = {}
        for skin in skins:
            slot = skin[5] if len(skin) > 5 and skin[5] else "set"
            if slot == "set":
                return [skin]
            by_slot[slot] = skin
        return list(by_slot.values())

    def _refresh_loadout(self):
        self.loadout_list.clear()
        items = self._ordered_items()
        for skin in items:
            slot = skin[5] if len(skin) > 5 and skin[5] else "set"
            pixmap = self._item_pixmaps.get(skin[0])
            icon = QIcon(pixmap) if pixmap is not None else QIcon()
            item = QListWidgetItem(icon, f"{slot_label(slot)}  ·  {skin[1]}")
            item.setData(Qt.ItemDataRole.UserRole, slot)
            item.setToolTip(f"{skin[2]} — {skin[1]}")
            self.loadout_list.addItem(item)

        if items:
            self._loadout_status.setText(
                f"{self.selected_hero} · выбрано слотов: {len(items)}. "
                "Повторный щелчок по карточке снимает выбор."
            )
        else:
            self._loadout_status.setText(
                "Выбери предметы одного героя во вкладке «Каталог»."
            )
        self._remove_item_btn.setEnabled(bool(items))
        self._clear_loadout_btn.setEnabled(bool(items))

    def _emit_loadout_changed(self):
        self.loadout_changed.emit(self._ordered_items(), self.selected_hero)

    def remove_selected_item(self):
        item = self.loadout_list.currentItem()
        if item is None:
            return
        self.selected_items.pop(item.data(Qt.ItemDataRole.UserRole), None)
        if not self.selected_items:
            self.selected_hero = ""
        self._refresh_loadout()
        self._emit_loadout_changed()

    def clear_loadout(self):
        self.selected_items.clear()
        self.selected_hero = ""
        self._refresh_loadout()
        self._emit_loadout_changed()

    def load_profile(self):
        item = self.profile_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Комплекты", "Выбери сохранённый комплект.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        profile_row = next((p for p in self.store.profiles() if p[0] == name), None)
        skin_ids = self.store.profile_items(name)
        if not skin_ids and profile_row and profile_row[1]:
            skin_ids = [profile_row[1]]

        skins = [self._skins_by_id[sid] for sid in skin_ids if sid in self._skins_by_id]
        skins = self._normalize_loadout(skins)
        if not skins:
            QMessageBox.warning(self, "Комплект", "Предметы этого профиля отсутствуют в каталоге.")
            return
        hero = skins[0][2]
        if any(skin[2] != hero for skin in skins):
            QMessageBox.warning(self, "Комплект", "В профиле найдены предметы разных героев.")
            return

        self.selected_items.clear()
        for skin in skins:
            slot = skin[5] if len(skin) > 5 and skin[5] else "set"
            if slot == "set":
                self.selected_items = {"set": skin}
                break
            self.selected_items[slot] = skin
        self.selected_hero = hero
        self._refresh_loadout()
        self._emit_loadout_changed()

    def refresh_profiles(self):
        self.profile_list.clear()
        for name, skin_id in self.store.profiles():
            ids = self.store.profile_items(name) or ([skin_id] if skin_id else [])
            skins = [self._skins_by_id[sid] for sid in ids if sid in self._skins_by_id]
            hero = skins[0][2] if skins else "Каталог изменился"
            desc = ", ".join(skin[1] for skin in skins[:2])
            if len(skins) > 2:
                desc += f" и ещё {len(skins) - 2}"
            item = QListWidgetItem(f"  {name}  —  {hero} · {len(skins)} слотов\n  {desc}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(desc or "В этом профиле нет доступных предметов")
            self.profile_list.addItem(item)

    def save_profile(self):
        name = self.profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Профиль", "Введи название профиля.")
            return
        items = self._ordered_items()
        if not items:
            QMessageBox.warning(self, "Профиль",
                                "Сначала собери комплект из предметов каталога.")
            return
        try:
            self.store.save_loadout(name, items)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Профиль",
                                "Профиль с таким названием уже существует.")
            return
        self.profile_name.clear()
        self.refresh_profiles()

    def delete_profile(self):
        item = self.profile_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Профили",
                                    "Выбери профиль для удаления.")
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(
            self, "Удаление", f"Удалить профиль «{name}»?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_profile(name)
        self.refresh_profiles()

    def export_profiles(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт профилей",
            str(APP_DIR / "profiles.json"), "JSON (*.json)"
        )
        if not path:
            return
        data = []
        for name, skin_id in self.store.profiles():
            ids = self.store.profile_items(name) or ([skin_id] if skin_id else [])
            data.append({"name": name, "skin_id": skin_id, "skin_ids": ids})
        try:
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
            )
        except OSError as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        QMessageBox.information(self, "Экспорт", "Профили экспортированы.")

    def import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт профилей", str(APP_DIR), "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text("utf-8"))
            if not isinstance(data, list):
                raise ValueError("Ожидался список профилей.")
            imported = 0
            for p in data:
                if not isinstance(p, dict):
                    continue
                name = p.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                ids = p.get("skin_ids")
                if not isinstance(ids, list):
                    ids = [p.get("skin_id")] if p.get("skin_id") else []
                skins = [self._skins_by_id[sid] for sid in ids
                         if isinstance(sid, str) and sid in self._skins_by_id]
                skins = self._normalize_loadout(skins)
                if not skins:
                    continue
                try:
                    self.store.save_loadout(name.strip(), skins)
                    imported += 1
                except sqlite3.IntegrityError:
                    continue
        except (OSError, json.JSONDecodeError, ValueError) as e:
            QMessageBox.critical(self, "Ошибка импорта", str(e))
            return
        self.refresh_profiles()
        QMessageBox.information(self, "Импорт",
                                f"Импортировано профилей: {imported}")


# ─────────────────────────────────────────────────────────────────────────────
# Страница настроек
# ─────────────────────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    def __init__(self, settings: Settings, on_catalog_updated=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.on_catalog_updated = on_catalog_updated
        self._catalog_worker: CatalogUpdateWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        # ── Путь к Dota 2 ─────────────────────────────────────────────────
        dota_group = QGroupBox("Путь к Dota 2")
        dota_layout = QVBoxLayout(dota_group)

        desc = QLabel(
            "Укажи корневую папку Dota 2. Программа прочитает каталог предметов "
            "из игрового архива pak01_dir.vpk."
        )
        desc.setObjectName("subtitle")
        desc.setWordWrap(True)
        dota_layout.addWidget(desc)

        path_row = QHBoxLayout()
        self.dota_path_edit = QLineEdit()
        self.dota_path_edit.setText(
            settings.get("dota_path", str(DEFAULT_DOTA_PATH))
        )
        path_row.addWidget(self.dota_path_edit, 1)

        browse_btn = QPushButton("📂  Обзор")
        browse_btn.clicked.connect(self._browse_dota)
        path_row.addWidget(browse_btn)
        dota_layout.addLayout(path_row)

        self._dota_status = QLabel()
        self._dota_status.setWordWrap(True)
        dota_layout.addWidget(self._dota_status)
        self._check_dota_path()

        root.addWidget(dota_group)

        # ── Кнопка сохранения пути ─────────────────────────────────────────
        save_btn = QPushButton("💾  Сохранить путь к Dota 2")
        save_btn.setObjectName("primary")
        save_btn.setFixedWidth(240)
        save_btn.clicked.connect(self._save)
        root.addWidget(save_btn)

        # ── База данных скинов ───────────────────────────────────────────
        catalog_group = QGroupBox("Каталог предметов")
        cat_layout = QVBoxLayout(catalog_group)
        cat_desc = QLabel(
            "Каталог содержит все предметы, арканы, личности и сеты для 125 героев.\n"
            "Если Valve выпустили обновление, можно синхронизировать базу прямо из файлов игры."
        )
        cat_desc.setObjectName("subtitle")
        cat_desc.setWordWrap(True)
        cat_layout.addWidget(cat_desc)

        self._update_btn = QPushButton("🔄  Обновить каталог скинов из игры")
        self._update_btn.setFixedWidth(300)
        self._update_btn.clicked.connect(self._update_catalog)
        cat_layout.addWidget(self._update_btn)
        self._catalog_status = QLabel("Каталог сверяется с файлами игры вручную по кнопке.")
        self._catalog_status.setObjectName("subtitle")
        self._catalog_status.setWordWrap(True)
        cat_layout.addWidget(self._catalog_status)
        self._catalog_progress = QProgressBar()
        self._catalog_progress.setRange(0, 0)
        self._catalog_progress.hide()
        cat_layout.addWidget(self._catalog_progress)
        root.addWidget(catalog_group)

        # ── О программе ───────────────────────────────────────────────────
        about_group = QGroupBox("О программе")
        about_layout = QVBoxLayout(about_group)
        about_txt = QLabel(
            f"<b>Dota Skin Studio</b> v{APP_VERSION}<br><br>"
            "Приложение показывает каталог косметики, помогает собрать комплект "
            "и сохранить его в профиль. Кнопка в шапке запускает Dota 2 через Steam."
        )
        about_txt.setWordWrap(True)
        about_txt.setTextFormat(Qt.TextFormat.RichText)
        about_layout.addWidget(about_txt)
        root.addWidget(about_group)

        root.addStretch()

    def _browse_dota(self):
        path = QFileDialog.getExistingDirectory(
            self, "Выбери папку Dota 2",
            self.dota_path_edit.text() or str(DEFAULT_DOTA_PATH),
        )
        if path:
            self.dota_path_edit.setText(path)
            self._check_dota_path()

    def _check_dota_path(self):
        path = Path(self.dota_path_edit.text().strip())
        items_game = path / ITEMS_GAME_REL
        vpk_file = path / "game/dota/pak01_dir.vpk"
        if items_game.exists():
            self._dota_status.setStyleSheet("color: #2ecc71;")
            self._dota_status.setText("✔  items_game.txt найден.")
        elif vpk_file.exists():
            self._dota_status.setStyleSheet("color: #2ecc71;")
            self._dota_status.setText("✔  Dota 2 обнаружена (архив pak01_dir.vpk найден).")
        else:
            self._dota_status.setStyleSheet("color: #e74c3c;")
            self._dota_status.setText(
                f"✘  Файлы Dota 2 не найдены в указанной папке:\n   {path}"
            )

    def _save(self):
        self.settings.set("dota_path", self.dota_path_edit.text().strip())
        self._check_dota_path()
        if self.on_catalog_updated:
            self.on_catalog_updated()
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    def _update_catalog(self):
        if self._catalog_worker and self._catalog_worker.isRunning():
            return
        dota_path = Path(self.dota_path_edit.text().strip())
        self.settings.set("dota_path", str(dota_path))
        self._check_dota_path()
        self._catalog_worker = CatalogUpdateWorker(dota_path, self)
        self._catalog_worker.progress.connect(self._on_catalog_progress)
        self._catalog_worker.completed.connect(self._on_catalog_update_done)
        self._update_btn.setEnabled(False)
        self._catalog_status.setText("Подготовка обновления каталога…")
        self._catalog_progress.show()
        self._catalog_worker.start()

    def _on_catalog_progress(self, message: str):
        self._catalog_status.setText(message)

    def _on_catalog_update_done(self, count: int, error: str):
        self._catalog_progress.hide()
        self._update_btn.setEnabled(True)
        if error:
            self._catalog_status.setText("Не удалось обновить каталог.")
            QMessageBox.critical(self, "Ошибка обновления каталога", error)
            return
        self._catalog_status.setText(f"Каталог обновлён: {count:,} предметов.".replace(",", " "))
        if self.on_catalog_updated:
            self.on_catalog_updated()
        QMessageBox.information(
            self, "Каталог обновлён",
            f"В каталог добавлено {count:,} предметов и готовых наборов.".replace(",", " "),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Главное окно
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store     = Storage()
        self.settings  = Settings()
        self.all_skins = self.store.skins()
        self.image_cache: dict = {}

        self.setWindowTitle(f"Dota Skin Studio  v{APP_VERSION}")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(root)

        # ── Шапка ──────────────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0a0d14, stop:0.5 #111520, stop:1 #0a0d14);"
            "border-bottom: 1px solid #1e2438;"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)

        logo = QLabel("⚔  DOTA SKIN STUDIO")
        logo.setStyleSheet(
            "font-size: 18pt; font-weight: bold; color: #fff;"
            "letter-spacing: 2px; background: transparent;"
        )
        h_layout.addWidget(logo)
        h_layout.addStretch()

        version_lbl = QLabel(f"v{APP_VERSION}")
        version_lbl.setObjectName("subtitle")
        version_lbl.setStyleSheet("background: transparent;")
        h_layout.addWidget(version_lbl)

        launch_btn = QPushButton("▶  Запустить Dota 2")
        launch_btn.setObjectName("primary")
        launch_btn.clicked.connect(self._launch_dota)
        h_layout.addWidget(launch_btn)

        outer.addWidget(header)

        # ── Вкладки ─────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        outer.addWidget(tabs, 1)

        dota_path = Path(self.settings.get("dota_path", str(DEFAULT_DOTA_PATH)))
        self.catalog_page = CatalogPage(
            self.all_skins,
            self.image_cache,
            icon_dir=DATA_DIR / "icon_cache",
            vpk_path=dota_path / "game/dota/pak01_dir.vpk",
        )
        self.catalog_page.skin_toggled.connect(self._on_skin_toggled)
        self.catalog_page.skin_image_ready.connect(self._on_skin_image_ready)
        tabs.addTab(self.catalog_page, "  🗂  Каталог  ")

        self.profiles_page = ProfilesPage(
            self.store, self.all_skins, self.settings
        )
        self.profiles_page.loadout_changed.connect(self._on_loadout_changed)
        tabs.addTab(self.profiles_page, "  🎮  Комплекты  ")

        self.settings_page = SettingsPage(
            self.settings, on_catalog_updated=self.reload_skins
        )
        tabs.addTab(self.settings_page, "  ⚙  Настройки  ")

    def reload_skins(self):
        self.all_skins = self.store.skins()
        dota_path = Path(self.settings.get("dota_path", str(DEFAULT_DOTA_PATH)))
        self.catalog_page.set_vpk_path(dota_path / "game/dota/pak01_dir.vpk")
        self.catalog_page.set_skins(self.all_skins)
        self.profiles_page.set_catalog(self.all_skins)

    def _on_skin_toggled(self, skin: tuple, selected: bool):
        if not self.profiles_page.toggle_skin(skin, selected):
            self.catalog_page.set_selected_ids(
                skin[0] for skin in self.profiles_page.selected_items.values()
            )

    def _on_loadout_changed(self, skins: list, hero: str):
        self.catalog_page.set_selected_ids(skin[0] for skin in skins)
        for skin in skins:
            pixmap = self.catalog_page.image_for_skin(skin)
            if pixmap is not None:
                self.profiles_page.set_item_image(skin[0], pixmap)
        self.catalog_page.filter_by_hero(hero or None)

    def _on_skin_image_ready(self, skin_id: str, pixmap: QPixmap):
        self.profiles_page.set_item_image(skin_id, pixmap)

    def _launch_dota(self):
        if not QDesktopServices.openUrl(QUrl("steam://run/570")):
            QMessageBox.warning(
                self, "Не удалось запустить Dota 2",
                "Не удалось открыть ссылку Steam. Проверь, что Steam установлен и запущен.",
            )

    def closeEvent(self, event):
        worker = self.settings_page._catalog_worker
        if worker and worker.isRunning():
            worker.wait()
        self.catalog_page.stop_loaders()
        self.store.close()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("Dota Skin Studio v%s starting", APP_VERSION)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Тёмная палитра Fusion
    palette = QPalette()
    dark = QColor("#0e1117")
    palette.setColor(QPalette.ColorRole.Window,          dark)
    palette.setColor(QPalette.ColorRole.WindowText,      QColor("#dde0e8"))
    palette.setColor(QPalette.ColorRole.Base,            QColor("#131623"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#1a1e2a"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     dark)
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor("#dde0e8"))
    palette.setColor(QPalette.ColorRole.Text,            QColor("#dde0e8"))
    palette.setColor(QPalette.ColorRole.Button,          QColor("#1e2233"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#dde0e8"))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor("#c0392b"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
