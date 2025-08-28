# test_db.py
from app.db.session import get_session
from app.db.models import Patient
from sqlalchemy import text

def main():
    try:
        
        with get_session() as s:
            # raw query just to prove connection
            result = s.execute(text("SELECT 1")).scalar()
            print("Connection test result:", result)

            # ORM test: count patients
            count = s.query(Patient).count()
            print(f"Patient rows in DB: {count}")
            
    except Exception as e:
        print("Connection failed:", e)
    
if __name__ == "__main__":
    main()