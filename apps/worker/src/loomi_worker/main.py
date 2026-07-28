from dataclasses import dataclass
from time import sleep

from loomi_worker import __version__


@dataclass(frozen=True)
class WorkerStatus:
    service: str
    status: str
    version: str


def get_worker_status() -> WorkerStatus:
    return WorkerStatus(service="Loomi-Brain Worker", status="ready", version=__version__)


def serve_worker(poll_seconds: float = 30.0) -> None:
    status = get_worker_status()
    print(f"{status.service} {status.version} is {status.status}")
    while True:
        sleep(poll_seconds)


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve_worker()
        return

    status = get_worker_status()
    print(f"{status.service} {status.version} is {status.status}")


if __name__ == "__main__":
    main()
