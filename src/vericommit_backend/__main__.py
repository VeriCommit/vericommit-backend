"""Start the API with ``python -m vericommit_backend``."""

import uvicorn

from vericommit_backend.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "vericommit_backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
