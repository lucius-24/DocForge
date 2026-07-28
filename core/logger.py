import logging
import os

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _select_log_dir() -> str:
    candidates = []
    env_dir = os.environ.get("AIDOC_LOG_DIR")
    if env_dir:
        candidates.append(env_dir)
    candidates.append(os.path.join(_project_root(), "logs"))
    if os.name == "nt":
        candidates.append(os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "DocForge", "logs"))
    else:
        candidates.append(os.path.join(os.path.expanduser("~"), ".docforge", "logs"))

    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            test_path = os.path.join(d, ".write_test")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(test_path)
            except Exception:
                pass
            return d
        except Exception:
            continue
    return os.path.join(_project_root(), "logs")

log_dir = _select_log_dir()
log_file = os.path.join(log_dir, "app.log")

# Setup File Handler
_file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
_file_handler.setFormatter(_formatter)

logger = logging.getLogger("AIDOC")
logger.setLevel(logging.INFO)
# Clear existing handlers to prevent duplication if re-imported
if logger.hasHandlers():
    logger.handlers.clear()
    
logger.addHandler(_file_handler)

# Also print to console
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
logger.addHandler(_console_handler)

def get_logs():
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def clear_logs():
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.truncate(0)
    except Exception:
        pass
