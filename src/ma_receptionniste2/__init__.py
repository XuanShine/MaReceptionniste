import os


def main(reload: bool = False) -> None:
    import uvicorn

    uvicorn.run(
        "ma_receptionniste2.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
        reload=reload,
    )
