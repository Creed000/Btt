from app.database.session import SessionLocal
from app.models.master import Master


def get_master(master_id: int):

    db = SessionLocal()

    master = (
        db.query(Master)
        .filter(Master.id == master_id)
        .first()
    )

    db.close()

    return master


def get_all_masters():

    db = SessionLocal()

    masters = db.query(Master).all()

    db.close()

    return masters
