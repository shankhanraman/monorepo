from fastapi import Depends, FastAPI, Request

from app.dependencies import caller_identity, cert_hash
from app.routers import users

app = FastAPI(title="users-service")
app.include_router(users.router)


@app.get("/whoami")
def whoami(request: Request, caller: str = Depends(caller_identity)):
    """Any valid lab certificate: shows how the sidecar identified you."""
    return {"service": "users", "caller": caller, "cert_sha256": cert_hash(request)}
