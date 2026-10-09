
import logging
import sys
import json
import sqlite3
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

APP_VERSION = "0.3.0"

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QPushButton, QMessageBox, QComboBox,
    QFrame, QFileDialog, QSplitter, QScrollArea,
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "skins.db"

# Демонстрационные записи. Это каталог приложения,
# а не список предметов, автоматически найденных в игре.
SKINS = [
    ("juggernaut_arcana", "Bladeform Legacy",
     "Juggernaut", "Arcana"),
    ("phantom_assassin_arcana", "Manifold Paradox",
     "Phantom Assassin", "Arcana"),
    ("pudge_arcana", "Feast of Abscession",
     "Pudge", "Arcana"),
    ("lina_arcana", "Fiery Soul of the Slayer",
     "Lina", "Arcana"),
    ("terrorblade_arcana", "Fractal Horns of Inner Abysm",
     "Terrorblade", "Arcana"),
    ("crystal_maiden_set", "Frost Avalanche",
     "Crystal Maiden", "Set"),
    ("invoker_persona", "The Magus Cypher",
     "Invoker", "Persona"),
    ("axe_immortal", "The Burning Scourge",
     "Axe", "Immortal"),
    ("anti_mage_set", "Brands of the Reaper",
     "Anti-Mage", "Set"),
    ("windranger_arcana", "Compass of the Rising Gale",
     "Windranger", "Arcana"),
]

HERO_SLUGS = {
    "Juggernaut": "juggernaut",
    "Phantom Assassin": "phantom_assassin",
    "Pudge": "pudge",
    "Lina": "lina",
    "Terrorblade": "terrorblade",
    "Crystal Maiden": "crystal_maiden",
    "Invoker": "invoker",
    "Axe": "axe",
    "Anti-Mage": "antimage",
    "Windranger": "windrunner",
}


def hero_image_url(hero):
    slug = HERO_SLUGS.get(hero)
    if not slug:
        return None
    return (
        "https://cdn.cloudflare.steamstatic.com/apps/"
        f"dota2/images/dota_react/heroes/{slug}.png"
    )


class ImageLoader(QThread):
    loaded = Signal(str, object)

    def __init__(self, key, url):
        super().__init__()
        self.key = key
        self.url = url

    def run(self):
        try:
            request = urllib.request.Request(
                self.url,
                headers={"User-Agent": f"DotaSkinStudio/{APP_VERSION}"},
            )
            with urllib.request.urlopen(
                request, timeout=5
            ) as response:
                data = response.read(4_000_000)

            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.loaded.emit(self.key, pixmap)
                return

            log.warning("Failed to decode image for %s", self.key)
        except Exception:
            log.debug(
                "Image load failed for %s: %s",
                self.key, self.url, exc_info=True,
            )

        self.loaded.emit(self.key, None)


class Storage:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS skins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hero TEXT NOT NULL
            )
        """)

        # Миграция старой базы: добавляем категорию,
        # не удаляя существующие записи.
        columns = {
            row[1]
            for row in self.db.execute(
                "PRAGMA table_info(skins)"
            ).fetchall()
        }
        if "category" not in columns:
            self.db.execute(
                "ALTER TABLE skins ADD COLUMN category "
                "TEXT NOT NULL DEFAULT 'Other'"
            )

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                skin_id TEXT
            )
        """)

        self.db.commit()

        for skin_id, name, hero, category in SKINS:
            self.db.execute(
                """
                INSERT OR IGNORE INTO skins
                (id, name, hero, category)
                VALUES (?, ?, ?, ?)
                """,
                (skin_id, name, hero, category),
            )

        # Обновляем категории существующих демонстрационных записей.
        for skin_id, name, hero, category in SKINS:
            self.db.execute(
                "UPDATE skins SET category=? WHERE id=?",
                (category, skin_id),
            )

        self.db.commit()

    def skins(self):
        return self.db.execute(
            "SELECT id, name, hero, category "
            "FROM skins ORDER BY hero, name"
        ).fetchall()

    def profiles(self):
        return self.db.execute(
            "SELECT name, skin_id FROM profiles ORDER BY name"
        ).fetchall()

    def save_profile(self, name, skin_id):
        self.db.execute(
            "INSERT INTO profiles (name, skin_id) VALUES (?, ?)",
            (name, skin_id),
        )
        self.db.commit()

    def delete_profile(self, name):
        self.db.execute(
            "DELETE FROM profiles WHERE name=?", (name,)
        )
        self.db.commit()

    def close(self):
        self.db.close()


STYLE = """
QWidget {
    background-color: #15171c;
    color: #e8e8ec;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel#title {
    font-size: 23pt;
    font-weight: bold;
    color: #f0f0f0;
}
QLabel#subtitle {
    color: #a3a6b0;
}
QLineEdit, QComboBox {
    background: #22252d;
    border: 1px solid #383c47;
    border-radius: 7px;
    padding: 9px;
    selection-background-color: #a84436;
}
QListWidget {
    background: #1b1e25;
    border: 1px solid #30343e;
    border-radius: 8px;
    padding: 5px;
    outline: none;
}
QListWidget::item {
    padding: 10px;
    border-radius: 5px;
}
QListWidget::item:selected {
    background: #71352f;
    color: white;
}
QPushButton {
    background: #30343e;
    border: 1px solid #444956;
    border-radius: 7px;
    padding: 9px 12px;
}
QPushButton:hover {
    background: #414653;
}
QPushButton#primary {
    background: #a33d32;
    border: 1px solid #c05243;
    font-weight: bold;
}
QPushButton#primary:hover {
    background: #bf4b3d;
}
QFrame#panel {
    background: #1b1e25;
    border: 1px solid #30343e;
    border-radius: 10px;
}
QLabel#heroImage {
    background: #242832;
    border-radius: 8px;
}
QScrollArea {
    border: none;
    background: transparent;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = Storage()
        self.all_skins = self.store.skins()
        self._active_loaders = {}   # hero -> ImageLoader
        self.image_cache = {}
        self.selected_skin = None

        self.setWindowTitle("Dota Skin Studio")
        self.resize(1100, 720)
        self.setMinimumSize(850, 580)
        self.setStyleSheet(STYLE)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)
        self.setCentralWidget(root)

        header = QHBoxLayout()
        titles = QVBoxLayout()

        title = QLabel("DOTA SKIN STUDIO")
        title.setObjectName("title")
        subtitle = QLabel(
            "COSMETIC CATALOG  /  PERSONAL PROFILES"
        )
        subtitle.setObjectName("subtitle")

        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()

        self.count_label = QLabel()
        self.count_label.setObjectName("subtitle")
        header.addWidget(self.count_label)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        # Левая панель: поиск, фильтры, каталог.
        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Поиск по предмету или герою..."
        )
        self.search.textChanged.connect(self.refresh_catalog)
        left_layout.addWidget(self.search)

        self.category = QComboBox()
        self.category.addItems([
            "Все категории", "Arcana", "Immortal",
            "Set", "Persona", "Other"
        ])
        self.category.currentTextChanged.connect(
            self.refresh_catalog
        )
        left_layout.addWidget(self.category)

        self.catalog = QListWidget()
        self.catalog.currentItemChanged.connect(
            self.on_skin_selected
        )
        left_layout.addWidget(self.catalog, 1)

        self.count_label.setText(
            f"{len(self.all_skins)} записей в каталоге"
        )
        splitter.addWidget(left)

        # Правая панель: выбранный предмет и профили.
        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 18, 18, 18)
        right_layout.setSpacing(10)

        self.preview = QLabel("ВЫБЕРИ ПРЕДМЕТ")
        self.preview.setObjectName("heroImage")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(175)
        self.preview.setWordWrap(True)
        right_layout.addWidget(self.preview)

        self.skin_name = QLabel("Каталог косметики")
        self.skin_name.setStyleSheet(
            "font-size: 17pt; font-weight: bold;"
        )
        self.skin_name.setWordWrap(True)
        right_layout.addWidget(self.skin_name)

        self.skin_details = QLabel(
            "Выбери предмет слева, чтобы увидеть подробности."
        )
        self.skin_details.setObjectName("subtitle")
        self.skin_details.setWordWrap(True)
        right_layout.addWidget(self.skin_details)

        right_layout.addSpacing(12)
        right_layout.addWidget(QLabel("Новый профиль"))

        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText(
            "Например, My Juggernaut"
        )
        right_layout.addWidget(self.profile_name)

        save_button = QPushButton("＋  Сохранить профиль")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self.save_profile)
        right_layout.addWidget(save_button)

        right_layout.addWidget(QLabel("Мои профили"))

        self.profile_list = QListWidget()
        self.profile_list.setMaximumHeight(150)
        right_layout.addWidget(self.profile_list)

        delete_button = QPushButton("Удалить выбранный профиль")
        delete_button.clicked.connect(self.delete_profile)
        right_layout.addWidget(delete_button)

        export_button = QPushButton("Экспорт профилей JSON")
        export_button.clicked.connect(self.export_profiles)
        right_layout.addWidget(export_button)

        import_button = QPushButton("Импорт профилей JSON")
        import_button.clicked.connect(self.import_profiles)
        right_layout.addWidget(import_button)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([470, 570])

        self.refresh_catalog()
        self.refresh_profiles()

    def refresh_catalog(self, *_):
        query = self.search.text().casefold().strip()
        category = self.category.currentText()

        self.catalog.clear()
        visible = []

        for skin in self.all_skins:
            skin_id, name, hero, kind = skin

            if category != "Все категории" and kind != category:
                continue

            searchable = f"{name} {hero} {kind}".casefold()
            if query and query not in searchable:
                continue

            visible.append(skin)
            item = QListWidgetItem(f"{hero}\n{name}  ·  {kind}")
            item.setData(Qt.ItemDataRole.UserRole, skin_id)
            self.catalog.addItem(item)

        self.count_label.setText(
            f"Найдено: {len(visible)}"
        )

        if self.catalog.count():
            self.catalog.setCurrentRow(0)
        else:
            self.selected_skin = None
            self.skin_name.setText("Ничего не найдено")
            self.skin_details.setText(
                "Попробуй изменить запрос или категорию."
            )
            self.preview.setPixmap(QPixmap())
            self.preview.setText("НЕТ РЕЗУЛЬТАТОВ")

    def on_skin_selected(self, current, _previous=None):
        if current is None:
            return

        skin_id = current.data(Qt.ItemDataRole.UserRole)
        skin = next(
            (s for s in self.all_skins if s[0] == skin_id),
            None,
        )
        if skin is None:
            return

        self.selected_skin = skin
        _, name, hero, category = skin

        self.skin_name.setText(name)
        self.skin_details.setText(
            f"Герой: {hero}\n"
            f"Категория: {category}\n"
            f"ID записи: {skin_id}\n\n"
            "Это запись каталога. Предмет пока не "
            "применяется к игре."
        )

        self.preview.setPixmap(QPixmap())
        self.preview.setText(f"{hero}\n\nЗагрузка изображения...")

        if hero in self.image_cache:
            self.show_image(hero, self.image_cache[hero])
            return

        url = hero_image_url(hero)
        if not url:
            self.preview.setText(hero)
            return

        # Cancel previous loader for the same hero if still running.
        old = self._active_loaders.pop(hero, None)
        if old is not None and old.isRunning():
            old.quit()

        loader = ImageLoader(hero, url)
        loader.loaded.connect(self.show_image)
        loader.finished.connect(
            lambda h=hero: self._active_loaders.pop(h, None)
        )
        self._active_loaders[hero] = loader
        loader.start()

    def show_image(self, hero, pixmap):
        self.image_cache[hero] = pixmap

        if not self.selected_skin or self.selected_skin[2] != hero:
            return

        if pixmap is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(
                f"{hero}\n\nИзображение недоступно"
            )
            return

        self.preview.setText("")
        self.preview.setPixmap(
            pixmap.scaled(
                420, 190,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def refresh_profiles(self):
        self.profile_list.clear()
        for name, skin_id in self.store.profiles():
            skin = next(
                (s for s in self.all_skins if s[0] == skin_id),
                None,
            )
            description = skin[1] if skin else "Без предмета"
            item = QListWidgetItem(f"{name}  —  {description}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.profile_list.addItem(item)

    def save_profile(self):
        name = self.profile_name.text().strip()

        if not name:
            QMessageBox.warning(
                self, "Профиль", "Введи название профиля."
            )
            return

        if not self.selected_skin:
            QMessageBox.warning(
                self, "Профиль", "Сначала выбери предмет."
            )
            return

        try:
            self.store.save_profile(name, self.selected_skin[0])
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self, "Профиль",
                "Профиль с таким названием уже существует.",
            )
            return

        self.profile_name.clear()
        self.refresh_profiles()

    def delete_profile(self):
        item = self.profile_list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Профили", "Выбери профиль для удаления."
            )
            return

        name = item.data(Qt.ItemDataRole.UserRole)
        answer = QMessageBox.question(
            self, "Удаление",
            f"Удалить профиль «{name}»?",
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.store.delete_profile(name)
        self.refresh_profiles()

    def export_profiles(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт профилей",
            str(APP_DIR / "profiles.json"),
            "JSON (*.json)",
        )
        if not path:
            return

        data = [
            {"name": name, "skin_id": skin_id}
            for name, skin_id in self.store.profiles()
        ]

        try:
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            QMessageBox.critical(
                self, "Ошибка экспорта", str(error)
            )
            return

        QMessageBox.information(
            self, "Экспорт", "Профили экспортированы."
        )

    def import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт профилей",
            str(APP_DIR), "JSON (*.json)",
        )
        if not path:
            return

        try:
            data = json.loads(
                Path(path).read_text(encoding="utf-8")
            )
            if not isinstance(data, list):
                raise ValueError("Ожидался список профилей.")

            imported = 0
            for profile in data:
                if not isinstance(profile, dict):
                    continue

                name = profile.get("name")
                skin_id = profile.get("skin_id")

                if not isinstance(name, str) or not name.strip():
                    continue

                if skin_id is not None and not any(
                    skin[0] == skin_id for skin in self.all_skins
                ):
                    skin_id = None

                try:
                    self.store.save_profile(name.strip(), skin_id)
                    imported += 1
                except sqlite3.IntegrityError:
                    continue

        except (OSError, json.JSONDecodeError, ValueError) as error:
            QMessageBox.critical(
                self, "Ошибка импорта", str(error)
            )
            return

        self.refresh_profiles()
        QMessageBox.information(
            self, "Импорт",
            f"Импортировано профилей: {imported}",
        )

    def closeEvent(self, event):
        for loader in self._active_loaders.values():
            loader.wait(2000)
        self._active_loaders.clear()
        self.store.close()
        event.accept()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("Dota Skin Studio v%s starting", APP_VERSION)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()