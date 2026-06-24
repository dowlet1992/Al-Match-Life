import json


def load_feed():
    try:
        with open("database/feed_data.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {"posts": []}


def save_feed(data):
    with open("database/feed_data.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)