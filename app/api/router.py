from fastapi import APIRouter

api_router = APIRouter()

# Здесь будут подключаться все роуты
# Пример:
# from app.api.auth import router as auth_router
# api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
