# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cdt.model import LaundryType, Mode, Location, ModelParams, Slot, Weather, evaluate
from cdt.i18n import STRINGS, Strings, normalize_language
from cdt.texts import fmt_duration, fmt_time, tile_text

TZ = ZoneInfo("Europe/Berlin")
P = ModelParams()
T0 = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)  # 10:00 local time (Sat)
GOOD = Weather(22, 50, wind_kmh=10, sun=0.5)
HUMID = Weather(12, 97, wind_kmh=2)


def slots(ws):
    return [Slot(T0 + timedelta(hours=i), w) for i, w in enumerate(ws)]


def test_fmt_time():
    assert fmt_time(T0 + timedelta(hours=4), T0, TZ) == "14:00"
    assert fmt_time(T0 + timedelta(days=1), T0, TZ, Strings("de")) == "morgen 10:00"
    assert fmt_time(T0 + timedelta(days=2), T0, TZ, Strings("de")) == "Mo 10:00"
    assert fmt_time(T0 + timedelta(days=2), T0, TZ) == "Mon 10:00"


def test_fmt_duration():
    assert fmt_duration(0.3) == "15 min"
    assert fmt_duration(3.4, Strings("de")) == "3,5 h"
    assert fmt_duration(3.4) == "3.5 h"
    assert fmt_duration(12.2) == "12 h"


def test_hang_now_text():
    ev = evaluate(slots([GOOD] * 6 + [HUMID] * 4), T0, None, Location.LINE, LaundryType.NORMAL, P)
    t = tile_text(ev, Location.LINE, T0, TZ, language="de")
    assert t.title.startswith("Gut") or t.title.startswith("Ideal")
    assert t.subtitle == "Möglich bis 16:00"
    assert t.color == "green"


def test_drying_text():
    ev = evaluate(slots([GOOD] * 10), T0, None, Location.LINE, LaundryType.NORMAL, P, hanging=True, progress=45)
    t = tile_text(ev, Location.LINE, T0, TZ, language="de")
    assert t.title == "Trocknet · 59 %"
    assert t.subtitle.startswith("Voraussichtlich trocken ")


def test_later_text():
    ev = evaluate(slots([HUMID] * 4 + [GOOD] * 8), T0, None, Location.LINE, LaundryType.NORMAL, P)
    t = tile_text(ev, Location.LINE, T0, TZ, language="de")
    assert t.title == "Nächstes Fenster 14:00–22:00"


def test_all_languages_complete():
    keys = set(STRINGS["en"])
    for lang, table in STRINGS.items():
        assert set(table) == keys, lang
        assert len(table["weekdays"].split(",")) == 7, lang


def test_language_normalization():
    assert normalize_language("de-DE") == "de"
    assert normalize_language("fr_CA") == "fr"
    assert normalize_language("nl") == "en"
    assert normalize_language(None) == "en"


def test_texts_in_all_languages():
    ev = evaluate(slots([GOOD] * 10), T0, None, Location.LINE, LaundryType.NORMAL, P, hanging=True, progress=45)
    titles = {lang: tile_text(ev, Location.LINE, T0, TZ, language=lang).title for lang in STRINGS}
    assert titles == {
        "en": "Drying · 59 %",
        "de": "Trocknet · 59 %",
        "fr": "Séchage · 59 %",
        "es": "Secando · 59 %",
    }



def test_translation_files_and_card_labels_complete():
    import json, re
    from pathlib import Path
    base = Path(__file__).parents[1] / "custom_components" / "drying_pilot"

    def keys(d, prefix=""):
        out = set()
        for k, v in d.items():
            out |= keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
        return out

    langs = ["en", "de", "fr", "es"]
    tr = {l: keys(json.loads((base / "translations" / f"{l}.json").read_text())) for l in langs}
    for l in langs:
        assert tr[l] == tr["en"], (l, tr["en"] ^ tr[l])
    js = (base / "frontend" / "drying-pilot-card.js").read_text()
    card = {
        l: set(re.findall(r'(\w+): "', re.search(l + r": \{(.*?)\n  \},", js, re.S).group(1)))
        for l in langs
    }
    for l in langs:
        assert card[l] == card["en"], (l, card["en"] ^ card[l])


def test_new_mode_texts():
    medium = Weather(14, 70, wind_kmh=8)
    ev = evaluate(slots([medium] * 4 + [HUMID] * 20), T0, None, Location.LINE, LaundryType.NORMAL, P)
    t = tile_text(ev, Location.LINE, T0, TZ, language="de")
    assert t.title.startswith("Vortrocknen · ca. ") and t.subtitle == "Möglich bis 14:00"
    # pre-drying only later: mode later, still named in the tile
    ev = evaluate(slots([HUMID] * 3 + [medium] * 4 + [HUMID] * 20), T0, None, Location.LINE, LaundryType.NORMAL, P)
    t = tile_text(ev, Location.LINE, T0, TZ, language="de")
    assert ev.mode is Mode.LATER
    assert t.title.startswith("Vortrocknen 13:00–17:00") and t.color == "blue"
    paused = evaluate(slots([HUMID] * 30), T0, None, Location.COVERED, LaundryType.NORMAL, P, hanging=True, progress=10)
    t = tile_text(paused, Location.COVERED, T0, TZ, language="de")
    assert t.title.startswith("Trocknet gerade nicht")
    assert t.subtitle == "In den nächsten 2 Tagen nicht fertig"


def test_range_across_midnight_names_both_days():
    from cdt.texts import fmt_range
    start = T0 + timedelta(hours=12)            # Sat 22:00 local
    end = T0 + timedelta(hours=17)              # Sun 03:00 local
    assert fmt_range(start, end, T0, TZ, Strings("de")) == "22:00–morgen 03:00"
    assert fmt_range(T0, T0 + timedelta(hours=5), T0, TZ) == "10:00–15:00"
