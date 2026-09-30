"""Pytest suite for the realtime enrichment layer."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components/otp_proxy_m/realtime.py"
)
_spec = importlib.util.spec_from_file_location("otp_proxy_m_realtime", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["otp_proxy_m_realtime"] = _mod
_spec.loader.exec_module(_mod)

LiveTimes = _mod.LiveTimes
extract_stop_ids = _mod.extract_stop_ids
is_enrichable = _mod.is_enrichable
patch_data = _mod.patch_data


def test_is_enrichable():
    assert is_enrichable('{ stop: stops(ids: ["SEM:0501"]) { stoptimesWithoutPatterns { headsign } } }')
    assert not is_enrichable("{ stops(name: \"X\") { gtfsId } }")
    assert not is_enrichable("{ planConnection(...) { edges { node { legs } } } }")


def test_extract_stop_ids():
    q = '{ stop: stops(ids: ["SEM:0501"]) { name } zz: stops(ids: ["SEM:0502", "SE2:0654"]) { name } }'
    assert extract_stop_ids(q) == ["SEM:0501", "SEM:0502", "SE2:0654"]
    assert extract_stop_ids("{ stops(name: \"x\") { gtfsId } }") == []


def test_parse_rest_payload():
    payload = [
        {
            "pattern": {"id": "SEM:C7:1:x", "lastStopName": "Henri Wallon"},
            "times": [
                {
                    "tripId": "SEM:32255069",
                    "serviceDay": 1790719200,
                    "scheduledDeparture": 54256,
                    "realtimeDeparture": 54283,
                    "departureDelay": 27,
                    "realtime": True,
                    "realtimeState": "UPDATED",
                    "occupancy": "Faible",
                },
                {"tripId": None, "serviceDay": 1790719200, "realtime": True},
            ],
        }
    ]
    live = LiveTimes.parse(payload)
    assert set(live.by_trip) == {(1790719200, "SEM:32255069")}
    row = live.by_trip[(1790719200, "SEM:32255069")]
    assert row["departureDelay"] == 27 and row["occupancy"] == "Faible"
    assert LiveTimes.parse({"error": "x"}).by_trip == {}
    assert LiveTimes.parse(None).by_trip == {}


GRAPHQL_DATA = {
    "stop": [
        {
            "gtfsId": "SEM:0501",
            "name": "SMH Village",
            "stoptimesWithoutPatterns": [
                {
                    "serviceDay": 1790719200,
                    "scheduledDeparture": 54253,
                    "realtimeDeparture": 54253,
                    "departureDelay": 0,
                    "realtime": False,
                    "headsign": "Henri Wallon",
                    "trip": {"gtfsId": "SEM:32255069", "route": {"shortName": "C7"}},
                },
                {
                    "serviceDay": 1790719200,
                    "scheduledDeparture": 54000,
                    "realtime": False,
                    "trip": {"gtfsId": "SEM:UNKNOWN1", "route": {"shortName": "C7"}},
                },
            ],
        }
    ]
}

LIVE = LiveTimes.parse(
    [
        {
            "times": [
                {
                    "tripId": "SEM:32255069",
                    "serviceDay": 1790719200,
                    "realtimeDeparture": 54283,
                    "departureDelay": 27,
                    "realtime": True,
                    "realtimeState": "UPDATED",
                    "occupancy": "Faible",
                }
            ]
        }
    ]
)


def test_patch_list_shape():
    out = patch_data(
        {"stops": GRAPHQL_DATA["stop"]}, {"SEM:0501": LIVE.by_trip}
    )
    stm = out["stops"][0]["stoptimesWithoutPatterns"][0]
    assert stm["realtime"] is True
    assert stm["realtimeDeparture"] == 54283
    assert stm["departureDelay"] == 27
    assert stm["realtimeState"] == "UPDATED"
    assert stm["occupancy"] == "Faible"
    # unknown trip untouched
    assert out["stops"][0]["stoptimesWithoutPatterns"][1]["realtime"] is False


def test_patch_object_shape():
    obj = dict(GRAPHQL_DATA)
    obj["stop"] = GRAPHQL_DATA["stop"][0]
    out = patch_data(obj, {"SEM:0501": LIVE.by_trip})
    stm = out["stop"]["stoptimesWithoutPatterns"][0]
    assert stm["realtime"] is True and stm["departureDelay"] == 27


def test_patch_no_live_no_change():
    out = patch_data(GRAPHQL_DATA, {})
    assert out == GRAPHQL_DATA


def test_patch_unknown_stop():
    # pooled index: any (serviceDay, tripId) match enriches, whatever the
    # dict key was — matching is per-stoptime, not per-stop.
    out = patch_data(GRAPHQL_DATA, {"OTHER:1": LIVE.by_trip})
    stm = out["stop"][0]["stoptimesWithoutPatterns"][0]
    assert stm["realtime"] is True


def test_patch_stop_without_gtfsid():
    # openpublictransport queries do not request stop.gtfsId: matching must
    # still work (pooled (serviceDay, tripId) index).
    no_id = dict(GRAPHQL_DATA["stop"][0])
    no_id.pop("gtfsId")
    out = patch_data({"stop": [no_id]}, {"SEM:0501": LIVE.by_trip})
    stm = out["stop"][0]["stoptimesWithoutPatterns"][0]
    assert stm["realtime"] is True and stm["departureDelay"] == 27


def test_patch_multi_stop_pooling():
    stop_b = {
        "name": "Other",
        "stoptimesWithoutPatterns": [
            {
                "serviceDay": 1790719200,
                "realtime": False,
                "trip": {"gtfsId": "SEM:0502TRIP"},
            }
        ],
    }
    live_other = LiveTimes.parse(
        [{"times": [{"tripId": "SEM:0502TRIP", "serviceDay": 1790719200,
                     "realtime": True, "realtimeDeparture": 9999,
                     "departureDelay": 12, "occupancy": "High"}]}]
    )
    out = patch_data(
        {"stops": [*GRAPHQL_DATA["stop"], stop_b]},
        {"SEM:0501": LIVE.by_trip, "SEM:0502": live_other.by_trip},
    )
    assert out["stops"][0]["stoptimesWithoutPatterns"][0]["departureDelay"] == 27
    assert out["stops"][1]["stoptimesWithoutPatterns"][0]["departureDelay"] == 12


def test_early_delay_negative_preserved():
    live_early = LiveTimes.parse(
        [
            {
                "times": [
                    {
                        "tripId": "SEM:32255069",
                        "serviceDay": 1790719200,
                        "realtimeDeparture": 54200,
                        "departureDelay": -53,
                        "realtime": True,
                        "realtimeState": "UPDATED",
                    }
                ]
            }
        ]
    )
    out = patch_data(GRAPHQL_DATA, {"SEM:0501": live_early.by_trip})
    stm = out["stop"][0]["stoptimesWithoutPatterns"][0]
    assert stm["departureDelay"] == -53
    assert stm["realtimeDeparture"] == 54200
