"""Pytest suite for the otp_proxy_m rewrite layer.

Fixtures replicate the exact GraphQL queries sent by
python-openpublictransport==0.2.0 (providers/otp.py) for the otp_custom
provider.

The module is loaded by file path so the test does not import the package
``__init__`` (which requires homeassistant).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / (
    "custom_components/otp_proxy_m/rewrite.py"
)
_spec = importlib.util.spec_from_file_location("otp_proxy_m_rewrite", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["otp_proxy_m_rewrite"] = _mod
_spec.loader.exec_module(_mod)

RewriteError = _mod.RewriteError
reshape_response = _mod.reshape_response
rewrite_payload = _mod.rewrite_payload
rewrite_query = _mod.rewrite_query

# --- fixtures: real queries used by openpublictransport ---------------------

Q_SEARCH = (
    '{ stops(name: "%s") { gtfsId name lat lon parentStation { gtfsId name } '
    "routes { agency { name } } } }"
)

Q_NEAREST = (
    "{ nearest(lat: %f, lon: %f, maxDistance: %d, filterByPlaceTypes: [STOP]) "
    "{ edges { node { place { ... on Stop { gtfsId name lat lon parentStation "
    "{ gtfsId name } routes { agency { name } } } } distance } } } }"
)

Q_STOPTIMES = (
    '{ stop(id: "%s") { name alerts { alertHeaderText alertDescriptionText } '
    "stoptimesWithoutPatterns(numberOfDepartures: %d, startTime: %d) "
    "{ serviceDay scheduledDeparture realtimeDeparture departureDelay realtime "
    "headsign trip { alerts { alertHeaderText alertDescriptionText } route "
    "{ shortName mode color textColor agency { name } alerts { ... } } } } } }"
)

Q_PARENT = '{ stop(id: "%s") { parentStation { gtfsId } } }'


# --- rewrite_query -----------------------------------------------------------


def test_search_query_not_touched():
    body = {"query": Q_SEARCH % "Saint-Martin"}
    out, rewritten = rewrite_payload(json.dumps(body))
    assert out == body and rewritten is False


def test_nearest_query_not_touched():
    body = {"query": Q_NEAREST % (45.166, 5.724, 500)}
    out, rewritten = rewrite_payload(json.dumps(body))
    assert out["query"] == body["query"] and rewritten is False


def test_stoptimes_rewrite():
    q = Q_STOPTIMES % ("SEM:0501", 10, 1790900000)
    out = rewrite_query(q)
    assert "stop(id:" not in out
    assert 'stop: stops(ids: ["SEM:0501"])' in out
    assert "stoptimesWithoutPatterns" in out
    # WAF trigger must be gone
    assert " stop(" not in out and "stop(" not in out


def test_parent_rewrite():
    out = rewrite_query(Q_PARENT % "SEM:0501")
    assert out == (
        '{ stop: stops(ids: ["SEM:0501"]) { parentStation { gtfsId } } }'
    )


def test_stoptimes_no_ws_variant():
    q = '{ stop(id:"SEM:0501") { name } }'
    out = rewrite_query(q)
    assert out == '{ stop: stops(ids: ["SEM:0501"]) { name } }'


def test_stoptimes_ws_variant():
    q = '{ stop ( id: "X:1" ) { name } }'
    assert "stops(ids:" in rewrite_query(q)


def test_multiple_stops():
    q = '{ a: stop(id: "X:1") { name } b: stop(id:"Y:2") { name } }'
    out = rewrite_query(q)
    assert 'a: stop: stops(ids: ["X:1"])' in out
    assert 'b: stop: stops(ids: ["Y:2"])' in out


def test_variables_rejected():
    with pytest.raises(RewriteError):
        rewrite_query("{ stop(id: $id) { name } }")


def test_non_string_id_rejected():
    with pytest.raises(RewriteError):
        rewrite_query("{ stop(id: 42) { name } }")


def test_extra_args_rejected():
    with pytest.raises(RewriteError):
        rewrite_query('{ stop(id: "X", foo: "bar") { name } }')


def test_unbalanced_rejected():
    with pytest.raises(RewriteError):
        rewrite_query('{ stop(id: "X"')


def test_stops_ids_untouched_but_waf_safe():
    q = '{ stops(ids: ["SEM:0501"]) { gtfsId name } }'
    assert rewrite_query(q) == q


def test_substring_in_string_value_not_rewritten():
    # The phrase appears inside a JSON string value: python side sees it in
    # the GraphQL query string only if present there; here it must NOT be
    # rewritten because it is not a stop( field at all.
    q = '{ stops(name: "stop(id: probe") { gtfsId } }'
    assert rewrite_query(q) == q


# --- payload handling --------------------------------------------------------


def test_payload_json_unchanged_when_safe():
    body = {"query": Q_SEARCH % "Verdun"}
    out, rewritten = rewrite_payload(json.dumps(body))
    assert out == body and rewritten is False


def test_payload_rewrites():
    body = {"query": Q_STOPTIMES % ("SEM:0501", 3, 1790900000)}
    out, rewritten = rewrite_payload(json.dumps(body))
    assert rewritten is True
    assert "stop(id:" not in out["query"]
    assert 'stops(ids: ["SEM:0501"])' in out["query"]


def test_payload_invalid_json():
    with pytest.raises(RewriteError):
        rewrite_payload("{not json")


def test_payload_missing_query():
    with pytest.raises(RewriteError):
        rewrite_payload(json.dumps({"variables": {}}))


def test_payload_preserves_variables_dict():
    body = {"query": Q_SEARCH % "X", "variables": {"a": 1}}
    out, rewritten = rewrite_payload(json.dumps(body))
    assert out["variables"] == {"a": 1} and rewritten is False


# --- response reshaping ------------------------------------------------------


def test_reshape_single():
    assert reshape_response({"stop": [{"gtfsId": "X"}]}) == {"stop": {"gtfsId": "X"}}


def test_reshape_null_list():
    assert reshape_response({"stop": [None]}) == {"stop": None}


def test_reshape_empty_list():
    assert reshape_response({"stop": []}) == {"stop": None}


def test_reshape_absent_stop():
    d = {"data": {"something": 1}}
    assert reshape_response(d) == d


def test_reshape_leaves_others():
    d = {"other": [1, 2]}
    assert reshape_response(d) == d
