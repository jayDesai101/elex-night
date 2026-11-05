from elex.flows import prefect_flow


def test_flow_and_tasks_are_defined() -> None:
    assert prefect_flow.elex_cycle.name == "elex-cycle"
    assert prefect_flow.run_cycle.name == "pipeline-cycle"
    assert callable(prefect_flow.serve)
