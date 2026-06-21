from pydantic import BaseModel, Field

from app.repositories.user_repo import user_repo


class UserDTO(BaseModel):
    userId: str = ""
    email: str = ""
    displayName: str = ""
    accessToken: str = Field(default="", alias="accessToken")

    model_config = {"populate_by_name": True}


class UserService:
    def login(self, user: UserDTO) -> bool:
        return user_repo.login(
            {
                "userId": user.userId,
                "email": user.email,
                "displayName": user.displayName,
                "accessToken": user.accessToken,
            }
        )


user_service = UserService()
