from uuid import uuid4


def new_request_id() -> str:
    return str(uuid4())
