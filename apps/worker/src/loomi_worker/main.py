from dataclasses import dataclass

from loomi_worker import __version__


@dataclass(frozen=True)
class WorkerStatus:
    service: str
    status: str
    version: str


def get_worker_status() -> WorkerStatus:
    return WorkerStatus(service="Loomi-Brain Worker", status="ready", version=__version__)


def main() -> None:
    status = get_worker_status()
    print(f"{status.service} {status.version} is {status.status}")


if __name__ == "__main__":
    main()
