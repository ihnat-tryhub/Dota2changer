"""
Catalog Builder for Dota Skin Studio
=====================================
Извлекает и строит полный каталог скинов (Арканы, Личности, Имморталки, Сеты)
для всех 125 героев Dota 2 из items_game.txt и файлов локализации.
"""

import re
import time
import sqlite3
import logging
import io
import struct
import threading
from pathlib import Path

log = logging.getLogger(__name__)

HERO_MAP = {
    "npc_dota_hero_antimage": ("Anti-Mage", "antimage"),
    "npc_dota_hero_axe": ("Axe", "axe"),
    "npc_dota_hero_bane": ("Bane", "bane"),
    "npc_dota_hero_bloodseeker": ("Bloodseeker", "bloodseeker"),
    "npc_dota_hero_crystal_maiden": ("Crystal Maiden", "crystal_maiden"),
    "npc_dota_hero_drow_ranger": ("Drow Ranger", "drow_ranger"),
    "npc_dota_hero_earthshaker": ("Earthshaker", "earthshaker"),
    "npc_dota_hero_juggernaut": ("Juggernaut", "juggernaut"),
    "npc_dota_hero_mirana": ("Mirana", "mirana"),
    "npc_dota_hero_nevermore": ("Shadow Fiend", "nevermore"),
    "npc_dota_hero_morphling": ("Morphling", "morphling"),
    "npc_dota_hero_phantom_lancer": ("Phantom Lancer", "phantom_lancer"),
    "npc_dota_hero_puck": ("Puck", "puck"),
    "npc_dota_hero_pudge": ("Pudge", "pudge"),
    "npc_dota_hero_shadow_fiend": ("Shadow Fiend", "nevermore"),
    "npc_dota_hero_razor": ("Razor", "razor"),
    "npc_dota_hero_sand_king": ("Sand King", "sand_king"),
    "npc_dota_hero_storm_spirit": ("Storm Spirit", "storm_spirit"),
    "npc_dota_hero_sven": ("Sven", "sven"),
    "npc_dota_hero_tiny": ("Tiny", "tiny"),
    "npc_dota_hero_vengefulspirit": ("Vengeful Spirit", "vengefulspirit"),
    "npc_dota_hero_windrunner": ("Windranger", "windrunner"),
    "npc_dota_hero_zuus": ("Zeus", "zuus"),
    "npc_dota_hero_kunkka": ("Kunkka", "kunkka"),
    "npc_dota_hero_lina": ("Lina", "lina"),
    "npc_dota_hero_lion": ("Lion", "lion"),
    "npc_dota_hero_shadow_shaman": ("Shadow Shaman", "shadow_shaman"),
    "npc_dota_hero_slardar": ("Slardar", "slardar"),
    "npc_dota_hero_tidehunter": ("Tidehunter", "tidehunter"),
    "npc_dota_hero_witch_doctor": ("Witch Doctor", "witch_doctor"),
    "npc_dota_hero_lich": ("Lich", "lich"),
    "npc_dota_hero_riki": ("Riki", "riki"),
    "npc_dota_hero_enigma": ("Enigma", "enigma"),
    "npc_dota_hero_tinker": ("Tinker", "tinker"),
    "npc_dota_hero_sniper": ("Sniper", "sniper"),
    "npc_dota_hero_necrolyte": ("Necrophos", "necrolyte"),
    "npc_dota_hero_warlock": ("Warlock", "warlock"),
    "npc_dota_hero_beastmaster": ("Beastmaster", "beastmaster"),
    "npc_dota_hero_queenofpain": ("Queen of Pain", "queenofpain"),
    "npc_dota_hero_venomancer": ("Venomancer", "venomancer"),
    "npc_dota_hero_faceless_void": ("Faceless Void", "faceless_void"),
    "npc_dota_hero_skeleton_king": ("Wraith King", "skeleton_king"),
    "npc_dota_hero_death_prophet": ("Death Prophet", "death_prophet"),
    "npc_dota_hero_phantom_assassin": ("Phantom Assassin", "phantom_assassin"),
    "npc_dota_hero_pugna": ("Pugna", "pugna"),
    "npc_dota_hero_templar_assassin": ("Templar Assassin", "templar_assassin"),
    "npc_dota_hero_viper": ("Viper", "viper"),
    "npc_dota_hero_luna": ("Luna", "luna"),
    "npc_dota_hero_dragon_knight": ("Dragon Knight", "dragon_knight"),
    "npc_dota_hero_dazzle": ("Dazzle", "dazzle"),
    "npc_dota_hero_rattletrap": ("Clockwerk", "rattletrap"),
    "npc_dota_hero_leshrac": ("Leshrac", "leshrac"),
    "npc_dota_hero_furion": ("Nature's Prophet", "furion"),
    "npc_dota_hero_life_stealer": ("Lifestealer", "life_stealer"),
    "npc_dota_hero_dark_seer": ("Dark Seer", "dark_seer"),
    "npc_dota_hero_clinkz": ("Clinkz", "clinkz"),
    "npc_dota_hero_omniknight": ("Omniknight", "omniknight"),
    "npc_dota_hero_enchantress": ("Enchantress", "enchantress"),
    "npc_dota_hero_huskar": ("Huskar", "huskar"),
    "npc_dota_hero_night_stalker": ("Night Stalker", "night_stalker"),
    "npc_dota_hero_broodmother": ("Broodmother", "broodmother"),
    "npc_dota_hero_bounty_hunter": ("Bounty Hunter", "bounty_hunter"),
    "npc_dota_hero_weaver": ("Weaver", "weaver"),
    "npc_dota_hero_jakiro": ("Jakiro", "jakiro"),
    "npc_dota_hero_batrider": ("Batrider", "batrider"),
    "npc_dota_hero_chen": ("Chen", "chen"),
    "npc_dota_hero_spectre": ("Spectre", "spectre"),
    "npc_dota_hero_doom_bringer": ("Doom", "doom_bringer"),
    "npc_dota_hero_ancient_apparition": ("Ancient Apparition", "ancient_apparition"),
    "npc_dota_hero_ursa": ("Ursa", "ursa"),
    "npc_dota_hero_spirit_breaker": ("Spirit Breaker", "spirit_breaker"),
    "npc_dota_hero_gyrocopter": ("Gyrocopter", "gyrocopter"),
    "npc_dota_hero_alchemist": ("Alchemist", "alchemist"),
    "npc_dota_hero_invoker": ("Invoker", "invoker"),
    "npc_dota_hero_silencer": ("Silencer", "silencer"),
    "npc_dota_hero_obsidian_destroyer": ("Outworld Destroyer", "obsidian_destroyer"),
    "npc_dota_hero_lycan": ("Lycan", "lycan"),
    "npc_dota_hero_brewmaster": ("Brewmaster", "brewmaster"),
    "npc_dota_hero_shadow_demon": ("Shadow Demon", "shadow_demon"),
    "npc_dota_hero_lone_druid": ("Lone Druid", "lone_druid"),
    "npc_dota_hero_chaos_knight": ("Chaos Knight", "chaos_knight"),
    "npc_dota_hero_meepo": ("Meepo", "meepo"),
    "npc_dota_hero_treant": ("Treant Protector", "treant"),
    "npc_dota_hero_ogre_magi": ("Ogre Magi", "ogre_magi"),
    "npc_dota_hero_undying": ("Undying", "undying"),
    "npc_dota_hero_rubick": ("Rubick", "rubick"),
    "npc_dota_hero_disruptor": ("Disruptor", "disruptor"),
    "npc_dota_hero_nyx_assassin": ("Nyx Assassin", "nyx_assassin"),
    "npc_dota_hero_naga_siren": ("Naga Siren", "naga_siren"),
    "npc_dota_hero_keeper_of_the_light": ("Keeper of the Light", "keeper_of_the_light"),
    "npc_dota_hero_wisp": ("Io", "wisp"),
    "npc_dota_hero_visage": ("Visage", "visage"),
    "npc_dota_hero_slark": ("Slark", "slark"),
    "npc_dota_hero_medusa": ("Medusa", "medusa"),
    "npc_dota_hero_troll_warlord": ("Troll Warlord", "troll_warlord"),
    "npc_dota_hero_centaur": ("Centaur Warrunner", "centaur"),
    "npc_dota_hero_magnataur": ("Magnus", "magnataur"),
    "npc_dota_hero_shredder": ("Timbersaw", "shredder"),
    "npc_dota_hero_bristleback": ("Bristleback", "bristleback"),
    "npc_dota_hero_tusk": ("Tusk", "tusk"),
    "npc_dota_hero_skywrath_mage": ("Skywrath Mage", "skywrath_mage"),
    "npc_dota_hero_abaddon": ("Abaddon", "abaddon"),
    "npc_dota_hero_elder_titan": ("Elder Titan", "elder_titan"),
    "npc_dota_hero_legion_commander": ("Legion Commander", "legion_commander"),
    "npc_dota_hero_ember_spirit": ("Ember Spirit", "ember_spirit"),
    "npc_dota_hero_earth_spirit": ("Earth Spirit", "earth_spirit"),
    "npc_dota_hero_abyssal_underlord": ("Underlord", "abyssal_underlord"),
    "npc_dota_hero_terrorblade": ("Terrorblade", "terrorblade"),
    "npc_dota_hero_phoenix": ("Phoenix", "phoenix"),
    "npc_dota_hero_oracle": ("Oracle", "oracle"),
    "npc_dota_hero_techies": ("Techies", "techies"),
    "npc_dota_hero_winter_wyvern": ("Winter Wyvern", "winter_wyvern"),
    "npc_dota_hero_arc_warden": ("Arc Warden", "arc_warden"),
    "npc_dota_hero_monkey_king": ("Monkey King", "monkey_king"),
    "npc_dota_hero_dark_willow": ("Dark Willow", "dark_willow"),
    "npc_dota_hero_pangolier": ("Pangolier", "pangolier"),
    "npc_dota_hero_grimstroke": ("Grimstroke", "grimstroke"),
    "npc_dota_hero_hoodwink": ("Hoodwink", "hoodwink"),
    "npc_dota_hero_void_spirit": ("Void Spirit", "void_spirit"),
    "npc_dota_hero_snapfire": ("Snapfire", "snapfire"),
    "npc_dota_hero_mars": ("Mars", "mars"),
    "npc_dota_hero_dawnbreaker": ("Dawnbreaker", "dawnbreaker"),
    "npc_dota_hero_marci": ("Marci", "marci"),
    "npc_dota_hero_primal_beast": ("Primal Beast", "primal_beast"),
    "npc_dota_hero_muerta": ("Muerta", "muerta"),
    "npc_dota_hero_ringmaster": ("Ringmaster", "ringmaster"),
    "npc_dota_hero_kez": ("Kez", "kez"),
}

HERO_SLUGS = {v[0]: v[1] for v in HERO_MAP.values()}


def resolve_hero(raw_id: str) -> str | None:
    if not raw_id:
        return None
    raw_id = raw_id.lower().strip()
    if raw_id in HERO_MAP:
        return HERO_MAP[raw_id][0]
    for k, v in HERO_MAP.items():
        if raw_id.startswith(k):
            return v[0]
    return None


def load_kv_tokens(path: Path) -> dict[str, str]:
    tokens = {}
    if not path.exists():
        return tokens
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for m in re.finditer(r'^\s*"([^"]+)"\s+"([^"]*)"', f.read(), re.MULTILINE):
            k, v = m.group(1), m.group(2)
            tokens[k.lower()] = v
            if k.startswith("#"):
                tokens[k[1:].lower()] = v
    return tokens


class VPKArchive:
    """Минимальный читатель VPK v1/v2 для отдельных файлов и текстур."""

    MAGIC = 0x55AA1234
    DIRECTORY_ARCHIVE = 0x7FFF

    def __init__(self, path: Path):
        self.path = Path(path)
        with self.path.open("rb") as archive:
            header = archive.read(12)
            if len(header) != 12:
                raise ValueError(f"Повреждённый VPK: {self.path}")
            signature, self.version, self.tree_size = struct.unpack("<III", header)
            if signature != self.MAGIC:
                raise ValueError(f"Неверная сигнатура VPK: {self.path}")
            if self.version == 1:
                self.header_size = 12
            elif self.version == 2:
                extra = archive.read(16)
                if len(extra) != 16:
                    raise ValueError(f"Неполный заголовок VPK v2: {self.path}")
                self.header_size = 28
            else:
                raise ValueError(f"Неподдерживаемая версия VPK: {self.version}")
            tree = archive.read(self.tree_size)
            if len(tree) != self.tree_size:
                raise ValueError(f"Неполное дерево файлов VPK: {self.path}")

        self.entries = self._parse_tree(tree)
        if self.path.name.endswith("_dir.vpk"):
            self.archive_prefix = self.path.name[:-len("dir.vpk")]
        else:
            self.archive_prefix = f"{self.path.stem}_"

    @staticmethod
    def _parse_tree(tree: bytes) -> dict[str, tuple[int, int, int, bytes]]:
        entries = {}
        cursor = 0

        def read_string() -> str:
            nonlocal cursor
            end = tree.find(b"\0", cursor)
            if end < 0:
                raise ValueError("Некорректное дерево файлов VPK")
            value = tree[cursor:end].decode("utf-8", errors="replace")
            cursor = end + 1
            return value

        while cursor < len(tree):
            extension = read_string()
            if not extension:
                break
            while cursor < len(tree):
                folder = read_string()
                if not folder:
                    break
                while cursor < len(tree):
                    filename = read_string()
                    if not filename:
                        break
                    if cursor + 18 > len(tree):
                        raise ValueError("Неполная запись в дереве VPK")
                    _, preload_size, archive_index, offset, length, terminator = (
                        struct.unpack_from("<IHHIIH", tree, cursor)
                    )
                    cursor += 18
                    if terminator != 0xFFFF:
                        raise ValueError("Некорректный разделитель в дереве VPK")
                    preload = tree[cursor:cursor + preload_size]
                    if len(preload) != preload_size:
                        raise ValueError("Неполные предварительные данные VPK")
                    cursor += preload_size

                    normalized_folder = "" if folder == " " else folder.strip("/")
                    normalized_ext = "" if extension == " " else f".{extension}"
                    member = "/".join(
                        part for part in (normalized_folder, f"{filename}{normalized_ext}")
                        if part
                    )
                    entries[member.casefold()] = (
                        archive_index, offset, length, preload
                    )
        return entries

    @staticmethod
    def _normalize_member(member: str) -> str:
        return member.replace("\\", "/").lstrip("/").casefold()

    def __contains__(self, member: str) -> bool:
        return self._normalize_member(member) in self.entries

    def get_file(self, member: str) -> io.BytesIO:
        key = self._normalize_member(member)
        if key not in self.entries:
            raise KeyError(member)
        archive_index, offset, length, preload = self.entries[key]
        if archive_index == self.DIRECTORY_ARCHIVE:
            archive_path = self.path
            data_offset = self.header_size + self.tree_size + offset
        else:
            archive_path = self.path.parent / f"{self.archive_prefix}{archive_index:03}.vpk"
            data_offset = offset

        with archive_path.open("rb") as archive:
            archive.seek(data_offset)
            payload = archive.read(length)
        if len(payload) != length:
            raise ValueError(f"Неполные данные файла {member} в VPK")
        return io.BytesIO(preload + payload)


_VPK_CACHE: dict[str, tuple[int, int, VPKArchive]] = {}
_VPK_CACHE_LOCK = threading.Lock()


def open_vpk(path: Path) -> VPKArchive:
    path = Path(path)
    stat = path.stat()
    key = str(path.resolve()).casefold()
    signature = (stat.st_size, stat.st_mtime_ns)
    with _VPK_CACHE_LOCK:
        cached = _VPK_CACHE.get(key)
        if cached and cached[:2] == signature:
            return cached[2]
        archive = VPKArchive(path)
        _VPK_CACHE[key] = (*signature, archive)
        return archive


def extract_game_files(dota_path: Path, data_dir: Path, force: bool = False):
    """При необходимости извлекает items_game.txt и локализацию из VPK."""
    data_dir.mkdir(parents=True, exist_ok=True)
    items_game = data_dir / "items_game.txt"
    items_ru = data_dir / "items_russian.txt"
    items_en = data_dir / "items_english.txt"

    if not force and items_game.exists() and items_ru.exists() and items_en.exists():
        return

    vpk_path = dota_path / "game/dota/pak01_dir.vpk"
    if not vpk_path.exists():
        log.warning("pak01_dir.vpk not found at %s", vpk_path)
        if force:
            raise FileNotFoundError(f"Архив игры не найден: {vpk_path}")
        return

    try:
        pak = open_vpk(vpk_path)
        items_game_extracted = False
        if (force or not items_game.exists()) and "scripts/items/items_game.txt" in pak:
            items_game.write_bytes(pak.get_file("scripts/items/items_game.txt").read())
            items_game_extracted = True
        if (force or not items_ru.exists()) and "resource/localization/items_russian.txt" in pak:
            items_ru.write_bytes(pak.get_file("resource/localization/items_russian.txt").read())
        if (force or not items_en.exists()) and "resource/localization/items_english.txt" in pak:
            items_en.write_bytes(pak.get_file("resource/localization/items_english.txt").read())
        if force and not items_game_extracted:
            raise FileNotFoundError("В архиве не найден scripts/items/items_game.txt")
    except Exception as e:
        log.error("Failed to extract files from VPK: %s", e)
        if force:
            raise


def build_skins_catalog(data_dir: Path) -> list[tuple[str, str, str, str, str, str]]:
    """
    Парсит items_game.txt и возвращает список кортежей:
    (skin_id, name, hero, category, icon, slot)
    """
    items_game_path = data_dir / "items_game.txt"
    if not items_game_path.exists():
        log.warning("items_game.txt not found in %s", data_dir)
        return []

    tokens_ru = load_kv_tokens(data_dir / "items_russian.txt")
    tokens_en = load_kv_tokens(data_dir / "items_english.txt")

    def resolve_name(token_or_name: str) -> str:
        if not token_or_name:
            return ""
        clean = token_or_name.lower().strip()
        if clean.startswith("#"):
            clean = clean[1:]
        if clean in tokens_ru:
            return tokens_ru[clean]
        if clean in tokens_en:
            return tokens_en[clean]
        name = token_or_name
        if name.startswith("#DOTA_Item_"):
            name = name[11:].replace("_", " ")
        elif name.startswith("#DOTA_Set_"):
            name = name[10:].replace("_", " ")
        return name

    with open(items_game_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    pos_prefabs = text.find('"prefabs"')
    pos_items = text.find('"items"')
    pos_item_sets = text.find('"item_sets"')
    if pos_prefabs == -1 or pos_items == -1 or pos_item_sets == -1:
        return []

    # В KeyValues предмет может наследовать слот из своего prefab.
    prefab_blocks = re.findall(
        r'^\t\t"([^"\r\n]+)"[ \t]*\r?\n\t\t\{\r?\n(.*?)\r?\n\t\t\}',
        text[pos_prefabs:pos_items],
        re.DOTALL | re.MULTILINE,
    )
    prefab_slots = {}
    for prefab_name, block in prefab_blocks:
        slot_match = re.search(r'"item_slot"\s+"([^"]+)"', block)
        if slot_match:
            prefab_slots[prefab_name] = slot_match.group(1).strip()

    item_blocks = re.findall(
        r'^\t\t"(\d+)"[ \t]*\r?\n\t\t\{\r?\n(.*?)\r?\n\t\t\}',
        text[pos_items:pos_item_sets],
        re.DOTALL | re.MULTILINE,
    )

    items_dict = {}
    for item_id, block in item_blocks:
        m_prefab = re.search(r'"prefab"\s+"([^"]+)"', block)
        prefab = m_prefab.group(1) if m_prefab else ""
        if prefab not in ("wearable", "bundle", "default_item", "taunt", "courier", "ward"):
            continue

        m_name = re.search(r'"name"\s+"([^"]+)"', block)
        name = m_name.group(1) if m_name else ""

        m_item_name = re.search(r'"item_name"\s+"([^"]+)"', block)
        item_name = m_item_name.group(1) if m_item_name else name

        m_rarity = re.search(r'"item_rarity"\s+"([^"]+)"', block)
        rarity = m_rarity.group(1).lower() if m_rarity else "common"

        m_hero = re.search(r'"(npc_dota_hero_[^"]+)"\s+"1"', block)
        raw_hero = m_hero.group(1) if m_hero else ""
        hero = resolve_hero(raw_hero)

        m_img = re.search(r'"image_inventory"\s+"([^"]+)"', block)
        icon_path = m_img.group(1).strip() if m_img else ""

        m_slot = re.search(r'"item_slot"\s+"([^"]+)"', block)
        slot = m_slot.group(1).strip() if m_slot else prefab_slots.get(prefab, "")

        is_persona = "persona" in raw_hero or "persona" in block.lower()

        items_dict[item_id] = {
            "id": item_id,
            "prefab": prefab,
            "name": name,
            "item_name": item_name,
            "rarity": rarity,
            "hero": hero,
            "is_persona": is_persona,
            "icon": icon_path,
            "slot": slot,
        }

    # Индекс сохраняет порядок items_dict: при совпадающих именах
    # первым останется тот же предмет, который выбрал бы прежний перебор.
    items_by_name = {}
    for item in items_dict.values():
        items_by_name.setdefault(item["name"], item)

    pos_after_sets = text.find('"attributes"', pos_item_sets)
    if pos_after_sets == -1:
        pos_after_sets = pos_item_sets + 5_000_000

    set_blocks = re.findall(
        r'^\t\t"([^"\r\n]+)"[ \t]*\r?\n\t\t\{\r?\n(.*?)\r?\n\t\t\}',
        text[pos_item_sets:pos_after_sets],
        re.DOTALL | re.MULTILINE,
    )

    catalog = []
    # 1. Сеты и наборы
    for set_id, block in set_blocks:
        m_name = re.search(r'"name"\s+"([^"]+)"', block)
        set_name_token = m_name.group(1) if m_name else set_id
        display_name = resolve_name(set_name_token)

        m_portrait = re.search(r'"portrait_image"\s+"([^"]+)"', block)
        set_icon = m_portrait.group(1).strip() if m_portrait else ""
        if not set_icon:
            m_inv = re.search(r'"image_inventory"\s+"([^"]+)"', block)
            set_icon = m_inv.group(1).strip() if m_inv else ""

        sub_items = re.findall(r'"([^"]+)"\s+"1"', block)
        set_hero = None
        has_arcana = False
        has_immortal = False
        has_persona = "persona" in set_id.lower() or "persona" in block.lower()

        for item_name_in_set in sub_items:
            it = items_by_name.get(item_name_in_set)
            if it:
                if not set_hero and it["hero"]:
                    set_hero = it["hero"]
                if not set_icon and it["icon"]:
                    set_icon = it["icon"]
                if it["rarity"] == "arcana":
                    has_arcana = True
                elif it["rarity"] == "immortal":
                    has_immortal = True
                if it["is_persona"]:
                    has_persona = True
            if set_hero and (has_arcana or has_immortal or has_persona):
                break

        if not set_hero:
            continue

        category = "Arcana" if has_arcana else ("Persona" if has_persona else ("Immortal" if has_immortal else "Set"))
        catalog.append((f"set_{set_id}", display_name, set_hero, category, set_icon, "set"))

    # 2. Все отдельные носимые предметы с их экипировочным слотом.
    for it in items_dict.values():
        if not it["hero"] or not it["slot"] or it["id"] is None:
            continue
        if not it.get("prefab") == "wearable":
            continue
        rarity = it["rarity"]
        display_name = resolve_name(it["item_name"])
        if not display_name or display_name.startswith("#"):
            display_name = it["name"]

        category = (
            "Persona"
            if it["is_persona"] or "persona" in it["name"].lower()
            else (rarity.title() if rarity else "Other")
        )
        catalog.append((
            f"item_{it['id']}", display_name, it["hero"], category,
            it["icon"], it["slot"],
        ))

    # ID уникален; одинаковые названия могут быть разными предметами/вариантами.
    priority = {
        "Arcana": 10, "Persona": 9, "Immortal": 8, "Ancient": 7,
        "Legendary": 6, "Mythical": 5, "Rare": 4, "Uncommon": 3,
        "Common": 2, "Other": 1, "Set": 0,
    }
    unique = {}
    for item in catalog:
        unique[item[0]] = item

    return sorted(
        unique.values(),
        key=lambda item: (item[2], item[5], -priority.get(item[3], 0), item[1], item[0]),
    )


def extract_icon_from_vpk(vpk_path: Path, icon_path: str, out_file: Path) -> bool:
    """Извлекает PNG-иконку предмета из VPK."""
    if not icon_path or out_file.exists():
        return out_file.exists()
    try:
        pak = open_vpk(vpk_path)
        target_path = f"panorama/images/{icon_path.lower()}_png.vtex_c"
        if target_path in pak:
            data = pak.get_file(target_path).read()
            idx = data.find(b"\x89PNG\r\n\x1a\n")
            if idx != -1:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_bytes(data[idx:])
                return True
    except Exception as e:
        log.debug("Failed extracting icon %s: %s", icon_path, e)
    return False


def update_database(db_path: Path, data_dir: Path) -> int:
    """Парсит файлы и обновляет skins.db."""
    skins = build_skins_catalog(data_dir)
    if not skins:
        return 0

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS skins (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            hero TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Other',
            icon TEXT,
            slot TEXT NOT NULL DEFAULT 'set'
        )
    """)
    cols = {r[1] for r in cur.execute("PRAGMA table_info(skins)").fetchall()}
    if "icon" not in cols:
        cur.execute("ALTER TABLE skins ADD COLUMN icon TEXT")
    if "slot" not in cols:
        cur.execute("ALTER TABLE skins ADD COLUMN slot TEXT NOT NULL DEFAULT 'set'")

    cur.execute("DELETE FROM skins")
    cur.executemany(
        "INSERT INTO skins (id, name, hero, category, icon, slot) VALUES (?, ?, ?, ?, ?, ?)",
        skins
    )
    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM skins").fetchone()[0]
    conn.close()
    log.info("Database updated with %d wearable items (with icons and slots)", count)
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app_dir = Path(__file__).resolve().parent
    data_dir = app_dir / "data"
    db_path = data_dir / "skins.db"
    cnt = update_database(db_path, data_dir)
    print(f"Done! {cnt} skins with icons written to {db_path}")
