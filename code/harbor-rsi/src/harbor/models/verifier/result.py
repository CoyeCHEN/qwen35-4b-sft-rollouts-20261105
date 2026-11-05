from pydantic import BaseModel


class VerifierResult(BaseModel):
    rewards: dict[str, float | int] | None = None
    return_code: int | None = None
