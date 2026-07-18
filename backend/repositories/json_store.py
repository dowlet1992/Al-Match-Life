import copy
import json
import os
import tempfile


class JsonStore:
    def __init__(self, path, default):
        self.path = path
        self.default = default

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return copy.deepcopy(self.default)

    def save(self, data):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        target_directory = directory or "."
        fd, temp_path = tempfile.mkstemp(
            prefix=".tmp-",
            suffix=".json",
            dir=target_directory,
            text=True,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
                file.write("\n")
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
