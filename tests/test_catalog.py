import sqlite3
from pathlib import Path
import pytest
import catalog_builder
from main import hero_image_url, Storage, DB_PATH, DATA_DIR


def test_catalog_database_loaded():
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM skins").fetchone()[0]
    conn.close()
    assert count >= 2000, f"Expected at least 2000 skins, got {count}"


def test_catalog_categories():
    conn = sqlite3.connect(DB_PATH)
    cats = {r[0] for r in conn.execute("SELECT DISTINCT category FROM skins").fetchall()}
    conn.close()
    assert "Arcana" in cats
    assert "Immortal" in cats
    assert "Persona" in cats
    assert "Set" in cats


def test_catalog_heroes_covered():
    conn = sqlite3.connect(DB_PATH)
    heroes = {r[0] for r in conn.execute("SELECT DISTINCT hero FROM skins").fetchall()}
    conn.close()
    assert len(heroes) >= 120, f"Expected at least 120 heroes, got {len(heroes)}"
    assert "Pudge" in heroes
    assert "Juggernaut" in heroes
    assert "Shadow Fiend" in heroes
    assert "Invoker" in heroes
    assert "Anti-Mage" in heroes


def test_hero_image_urls():
    assert hero_image_url("Pudge") == "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/pudge.png"
    assert hero_image_url("Shadow Fiend") == "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/nevermore.png"
    assert hero_image_url("Zeus") == "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/zuus.png"
    assert hero_image_url("Windranger") == "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/windrunner.png"
    assert hero_image_url("Anti-Mage") == "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/antimage.png"
