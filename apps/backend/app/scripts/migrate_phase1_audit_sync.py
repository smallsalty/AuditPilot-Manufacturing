from app.core.db import create_all


if __name__ == "__main__":
    create_all()
    print("Phase 1 audit sync schema ensured.")
