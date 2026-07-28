import os
import webbrowser

import uvicorn


def main():
    host = os.environ.get("AIDOC_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("AIDOC_WEB_PORT", "8008"))
    url = f"http://{host}:{port}/"
    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run("webapp.backend.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
