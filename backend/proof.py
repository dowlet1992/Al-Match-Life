from backend.repositories.proof_repository import get_proof_repository, normalize_proof_data


def load_proofs():
    return get_proof_repository().load_all()


def save_proofs(data):
    get_proof_repository().save_all(normalize_proof_data(data))
