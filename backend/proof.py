import json


def load_proofs():
    try:
        with open("database/proof_data.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {"proofs": []}


def save_proofs(data):
    with open("database/proof_data.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)