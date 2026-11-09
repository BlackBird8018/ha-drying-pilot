# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from cdt.model import LaundryType, Location, ModelParams, Slot, Weather, evaluate
from cdt.notify import ACTION_START, ACTION_STOP, due_notifications

TZ = ZoneInfo("Europe/Berlin")
P = ModelParams()
T0 = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)
GOOD = Weather(22, 50, wind_kmh=10, sun=0.5)
HUMID = Weather(12, 97, wind_kmh=2)
RAIN = Weather(16, 90, wind_kmh=10, rain_mm=1.5, rain_probability=80)
ALL = {"bring_in", "dry", "window_ending", "good_window"}


def slots(ws):
    return [Slot(T0 + timedelta(hours=i), w) for i, w in enumerate(ws)]


def ev_for(ws, now=T0, **kw):
    return evaluate(slots(ws), now, None, Location.LINE, LaundryType.NORMAL, P, **kw)


def test_bring_in_rain_once():
    now = T0 + timedelta(minutes=20)
    ev = ev_for([GOOD] + [RAIN] * 3, now, hanging=True, progress=50)
    notes = due_notifications(ev, True, ALL, set(), None, now, TZ, "de")
    assert [n.key for n in notes] == ["bring_in_rain"]
    assert "Regen ab 11:00" in notes[0].message
    assert notes[0].action == ACTION_STOP
    assert due_notifications(ev, True, ALL, {"bring_in_rain"}, None, now, TZ) == []


def test_dry_notification():
    ev = ev_for([GOOD] * 6, hanging=True, progress=100)
    notes = due_notifications(ev, True, ALL, set(), None, T0, TZ)
    assert [n.key for n in notes] == ["dry"]


def test_window_ending_only_within_lead():
    ev = ev_for([GOOD] * 3 + [HUMID] * 5, hanging=True, progress=0)
    assert due_notifications(ev, True, ALL, set(), None, T0, TZ) == []
    later = T0 + timedelta(hours=2, minutes=10)
    ev = ev_for([GOOD] * 3 + [HUMID] * 5, later, hanging=True, progress=10)
    notes = due_notifications(ev, True, ALL, set(), None, later, TZ)
    assert [n.key for n in notes] == ["window_ending"]


def test_good_window_once_per_day_and_disabled():
    ev = ev_for([GOOD] * 10)
    notes = due_notifications(ev, False, ALL, set(), None, T0, TZ)
    assert [n.key for n in notes] == ["good_window"]
    assert notes[0].action == ACTION_START
    assert due_notifications(ev, False, ALL, set(), date(2026, 7, 4), T0, TZ) == []
    assert due_notifications(ev, False, {"bring_in", "dry"}, set(), None, T0, TZ) == []


def test_english_default_and_french():
    now = T0 + timedelta(minutes=20)
    ev = ev_for([GOOD] + [RAIN] * 3, now, hanging=True, progress=50)
    en = due_notifications(ev, True, ALL, set(), None, now, TZ)[0]
    assert en.title == "Bring in the laundry"
    assert en.message.startswith("Rain from 11:00")
    assert en.action_title == "Brought in"
    fr = due_notifications(ev, True, ALL, set(), None, now, TZ, "fr-FR")[0]
    assert fr.title == "Rentrer le linge"


def test_iron_damp_once():
    ev = ev_for([GOOD] * 10, hanging=True, progress=70)
    notes = due_notifications(ev, True, {"iron_damp"}, set(), None, T0, TZ, "de")
    assert [n.key for n in notes] == ["iron_damp"]
    assert notes[0].title == "Wäsche ist bügelfeucht"
    assert due_notifications(ev, True, {"iron_damp"}, {"iron_damp"}, None, T0, TZ) == []
    early = ev_for([GOOD] * 10, hanging=True, progress=30)
    assert due_notifications(early, True, {"iron_damp"}, set(), None, T0, TZ) == []



def test_predry_window_and_end_notifications():
    medium = Weather(14, 70, wind_kmh=8)
    ev = ev_for([medium] * 4 + [HUMID] * 20)
    notes = due_notifications(ev, False, {"predry_window"}, set(), None, T0, TZ, "de")
    assert [n.key for n in notes] == ["predry_window"]
    assert "ca." in notes[0].message
    assert due_notifications(ev, False, {"predry_window"}, set(), None, T0, TZ, "de", date(2026, 7, 4)) == []

    after = T0 + timedelta(hours=4, minutes=10)
    ev = ev_for([medium] * 4 + [Weather(10, 85, wind_kmh=1)] * 20, after, hanging=True, progress=50)
    notes = due_notifications(ev, True, {"predry_end"}, set(), None, after, TZ, "de")
    assert [n.key for n in notes] == ["predry_end"]
    assert notes[0].title == "Vortrocknen beendet"
