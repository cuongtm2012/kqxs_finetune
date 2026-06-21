from fastapi import APIRouter

from app.services.user_service import UserDTO, user_service

router = APIRouter(prefix="/ums", tags=["ums"])


@router.post("/login")
def login(user: UserDTO):
    created = user_service.login(user)
    return "New User" if created else "Exist User"
