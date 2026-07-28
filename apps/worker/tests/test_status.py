from loomi_worker.main import get_worker_status


def test_worker_status() -> None:
    status = get_worker_status()

    assert status.service == "Loomi-Brain Worker"
    assert status.status == "ready"
    assert status.version == "0.1.0"
