
import sys
import sqlite3
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QGroupBox,
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "skins.db"

# Демонстрационный каталог. Пока без изменения игры.
DEMO_SKINS = [
    ("juggernaut_arcana", "Bladeform Legacy", "Juggernaut"),
    ("phantom_assassin_arcana", "Manifold Paradox", "Phantom Assassin"),
    ("pudge_arcana", "Feast of Abscession", "Pudge"),
    ("lina_arcana", "Fiery Soul of the Slayer", "Lina"),
    ("terrorblade_arcana", "Fractal Horns of Inner Abysm", "Terrorblade"),
]


class Storage:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(DB_PATH)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS skins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                hero TEXT NOT NULL
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                skin_id TEXT,
                FOREIGN KEY (skin_id) REFERENCES skins(id)
            )
        """)
        self.connection.commit()
        self.seed_catalog()

    def seed_catalog(self):
        self.connection.executemany(
            "INSERT OR IGNORE INTO skins (id, name, hero) "
            "VALUES (?, ?, ?)",
            DEMO_SKINS,
        )
        self.connection.commit()

    def get_skins(self):
        return self.connection.execute(
            "SELECT id, name, hero FROM skins ORDER BY hero"
        ).fetchall()

    def get_profiles(self):
        return self.connection.execute(
            "SELECT name, skin_id FROM profiles ORDER BY name"
        ).fetchall()

    def save_profile(self, name, skin_id):
        self.connection.execute(
            "INSERT INTO profiles (name, skin_id) VALUES (?, ?)",
            (name, skin_id),
        )
        self.connection.commit()

    def close(self):
        self.connection.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()
        self.skins = self.storage.get_skins()

        self.setWindowTitle("Dota Skin Studio")
        self.resize(760, 540)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        # Левая панель: каталог
        catalog_box = QGroupBox("Каталог косметики")
        catalog_layout = QVBoxLayout(catalog_box)

        self.skin_list = QListWidget()
        for skin_id, name, hero in self.skins:
            self.skin_list.addItem(f"{hero} — {name}")

        self.skin_list.currentRowChanged.connect(
            self.show_skin_details
        )
        catalog_layout.addWidget(self.skin_list)

        # Правая панель: информация и профили
        right = QVBoxLayout()

        self.details = QLabel("Выбери предмет из каталога")
        self.details.setWordWrap(True)
        right.addWidget(self.details)

        right.addWidget(QLabel("Название нового профиля:"))
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Например, My Juggernaut")
        right.addWidget(self.profile_name)

        save_button = QPushButton("Сохранить профиль")
        save_button.clicked.connect(self.save_profile)
        right.addWidget(save_button)

        right.addWidget(QLabel("Сохранённые профили:"))
        self.profile_list = QListWidget()
        right.addWidget(self.profile_list)

        refresh_button = QPushButton("Обновить профили")
        refresh_button.clicked.connect(self.refresh_profiles)
        right.addWidget(refresh_button)

        right.addStretch()

        layout.addWidget(catalog_box, 3)
        layout.addLayout(right, 2)

        self.refresh_profiles()
        if self.skins:
            self.skin_list.setCurrentRow(0)

    def show_skin_details(self, row):
        if not 0 <= row < len(self.skins):
            return

        skin_id, name, hero = self.skins[row]
        self.details.setText(
            f"Герой: {hero}\n"
            f"Предмет: {name}\n"
            f"ID: {skin_id}\n\n"
            "Это запись каталога для прототипа."
        )

    def save_profile(self):
        name = self.profile_name.text().strip()
        row = self.skin_list.currentRow()

        if not name:
            QMessageBox.warning(
                self, "Ошибка", "Введи название профиля."
            )
            return

        if not 0 <= row < len(self.skins):
            QMessageBox.warning(
                self, "Ошибка", "Сначала выбери предмет."
            )
            return

        skin_id = self.skins[row][0]

        try:
            self.storage.save_profile(name, skin_id)
        except sqlite3.IntegrityError:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Такой профиль уже существует.",
            )
            return

        self.profile_name.clear()
        self.refresh_profiles()
        QMessageBox.information(
            self, "Готово", "Профиль сохранён."
        )

    def refresh_profiles(self):
        self.profile_list.clear()
        for name, skin_id in self.storage.get_profiles():
            self.profile_list.addItem(
                f"{name} — {skin_id or 'без предмета'}"
            )

    def closeEvent(self, event):
        self.storage.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()