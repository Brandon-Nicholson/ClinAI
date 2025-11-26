# app/db/create_tables.py
from .session import engine
from .models import Base

def main():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")

if __name__ == "__main__":
    main()