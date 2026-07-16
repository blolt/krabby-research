"""krabby-fleet-service entry point: runs the app under uvicorn on 127.0.0.1:8080."""
from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("krabby_fleet_service.app:app", host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
