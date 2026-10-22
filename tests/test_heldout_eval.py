from eval.run_eval import _load_payload


def test_newticket_is_a_separate_non_overlapping_heldout_set():
    payload = _load_payload("newticket.json")
    benchmark = _load_payload("eval/benchmark_30.json")

    heldout_ids = {ticket["ticket_id"] for ticket in payload["tickets"]}
    benchmark_ids = {ticket["ticket_id"] for ticket in benchmark["tickets"]}

    assert len(payload["tickets"]) == 20
    assert len(payload["gold"]) == 20
    assert heldout_ids.isdisjoint(benchmark_ids)
    assert payload["tickets"][0]["description"].startswith("Under Article 17")
