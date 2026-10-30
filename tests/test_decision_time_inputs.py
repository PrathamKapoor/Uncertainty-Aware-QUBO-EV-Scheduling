from uncertainty.uncertainty import select_input_at_connection


def test_future_and_undated_inputs_are_not_available_at_connection():
    inputs = [
        {"modifiedAt": "2019-01-01T09:00:00Z", "requestedDeparture": "early"},
        {"modifiedAt": "2019-01-01T11:00:00Z", "requestedDeparture": "future"},
        {"requestedDeparture": "unknown"},
    ]
    selected = select_input_at_connection(inputs, "2019-01-01T10:00:00Z")
    assert selected["requestedDeparture"] == "early"
    assert select_input_at_connection(inputs[1:], "2019-01-01T10:00:00Z") is None
