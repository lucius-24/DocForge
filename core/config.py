import json
import os
from typing import Dict

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".aidoc-styler")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

def get_config() -> Dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def set_config(data: Dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def set_key(key: str, value):
    data = get_config()
    data[key] = value
    set_config(data)

