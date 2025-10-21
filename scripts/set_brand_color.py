from app.database import get_session, engine
from app.models import SiteConfig
from sqlalchemy import select, text

BRAND_HEX = "#D81B60"


def main():
    # ensure columns exist (works for sqlite/postgresql)
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                cols = conn.exec_driver_sql("PRAGMA table_info(site_config)").fetchall()
                names = {c[1] for c in cols}
                if "email" not in names:
                    conn.exec_driver_sql("ALTER TABLE site_config ADD COLUMN email VARCHAR(200)")
                if "primary_color" not in names:
                    conn.exec_driver_sql("ALTER TABLE site_config ADD COLUMN primary_color VARCHAR(20)")
            elif dialect == "postgresql":
                res = conn.execute(text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='site_config'
                    """
                )).fetchall()
                names = {r[0] for r in res}
                if "email" not in names:
                    conn.exec_driver_sql("ALTER TABLE site_config ADD COLUMN email VARCHAR(200)")
                if "primary_color" not in names:
                    conn.exec_driver_sql("ALTER TABLE site_config ADD COLUMN primary_color VARCHAR(20)")
    except Exception:
        pass

    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        if site is None:
            site = SiteConfig(primary_color=BRAND_HEX)
            db.add(site)
        else:
            site.primary_color = BRAND_HEX
        db.commit()
    print(f"primary_color atualizado para {BRAND_HEX}")


if __name__ == "__main__":
    main()
