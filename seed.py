"""
Run with: docker compose exec api python -m core.seed
Creates one demo merchant + owner user so the login flow is testable end to end.
"""
from core.db import SessionLocal, set_tenant_context
from core.security import hash_password
from models.merchant import Merchant
from models.user import User


def seed() -> None:
    db = SessionLocal()
    try:
        existing = db.query(Merchant).filter(Merchant.slug == "demo-merchant").first()
        if existing:
            print("Demo merchant already exists — skipping seed.")
            return

        merchant = Merchant(
            name="Demo Builders' Merchant",
            slug="demo-merchant",
            brand_colors={"primary": "#E3572A", "secondary": "#2B4C6F", "accent": "#E8A33D"},
            ai_persona={"tone": "formal", "upsell_aggressiveness": "medium", "emphasized_categories": []},
            status="active",
        )
        db.add(merchant)
        db.flush()  # get merchant.id

        # The users INSERT policy requires app.current_merchant_id to match the
        # row being written — set it now that we know the new merchant's id.
        set_tenant_context(db, merchant.id)

        admin = User(
            merchant_id=merchant.id,
            email="admin@demo-merchant.test",
            password_hash=hash_password("changeme123"),
            role="owner",
        )
        db.add(admin)
        db.commit()
        print(f"Seeded merchant {merchant.id} with admin user admin@demo-merchant.test / changeme123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
