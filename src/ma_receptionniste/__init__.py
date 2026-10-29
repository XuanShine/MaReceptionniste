import os

import uvicorn


def main(reload: bool = False) -> None:
    uvicorn.run(
        "ma_receptionniste.web.app:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        reload=reload,
    )
