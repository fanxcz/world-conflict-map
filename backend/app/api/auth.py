from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.auth.security import create_access_token, verify_password
from app.database import get_db
from app.models import User
from app.schemas import LoginIn, TokenOut, UserOut

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
    token = create_access_token(user.email, user.role)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list)
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [
        {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active, "created_at": u.created_at}
        for u in db.query(User).all()
    ]
