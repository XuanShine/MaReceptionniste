"""Point d'entrée : `uv run reception` ou uvicorn."""

import os

import uvicorn

from hotel_pms.app import create_app

app = create_app()


def main() -> None:
    uvicorn.run(
        app,
        host=os.environ.get("PMS_HOST", "127.0.0.1"),
        port=int(os.environ.get("PMS_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
