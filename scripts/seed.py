from app.database import get_session, Base, engine
from app.models import SiteConfig, TipoSuite, Amenidade, Suite
from sqlalchemy import select


def slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text


def main():
    Base.metadata.create_all(bind=engine)
    with get_session() as db:
        # Site config
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        if site is None:
            site = SiteConfig(
                nome_site="Motel Bela Vista",
                descricao_breve="Conforto, privacidade e atendimento 24h em Rio Pardo/RS.",
                endereco="Rua Guarani, 212, Rio Pardo - RS, 96640-000, Brasil",
                whatsapp="(51)99584-3002",
                telefone="(51)99584-3002",
                maps_embed_url=None,
            )
            db.add(site)

        # Tipos
        tipos_nomes = ["Standard", "Luxo", "Temática"]
        tipos_map = {}
        for nome in tipos_nomes:
            t = db.execute(select(TipoSuite).where(TipoSuite.nome == nome)).scalar_one_or_none()
            if t is None:
                t = TipoSuite(nome=nome, ordem=0)
                db.add(t)
                db.flush()
            tipos_map[nome] = t

        # Amenidades
        amenidades = ["Ar-condicionado", "Wi‑Fi", "TV Smart", "Hidromassagem"]
        amen_map = {}
        for nome in amenidades:
            a = db.execute(select(Amenidade).where(Amenidade.nome == nome)).scalar_one_or_none()
            if a is None:
                a = Amenidade(nome=nome)
                db.add(a)
                db.flush()
            amen_map[nome] = a

        # Suítes com preços exemplo
        suites_ex = [
            ("California", "Standard", "120.00", "260.00"),
            ("Arizona", "Standard", "100.00", "230.00"),
            ("Texas", "Luxo", "110.00", "240.00"),
            ("Dallas", "Temática", "130.00", "280.00"),
        ]
        for titulo, tipo_nome, ph, pp in suites_ex:
            s = db.execute(select(Suite).where(Suite.slug == slugify(titulo))).scalar_one_or_none()
            if s is None:
                s = Suite(
                    titulo=titulo,
                    slug=slugify(titulo),
                    tipo_id=tipos_map.get(tipo_nome).id if tipos_map.get(tipo_nome) else None,
                    descricao=f"Suíte {titulo} com conforto e privacidade.",
                    preco_hora=ph,
                    preco_pernoite=pp,
                    destaque=False,
                    ordem=0,
                )
                s.amenidades = list(amen_map.values())
                db.add(s)

        db.commit()
    print("Seed aplicado com sucesso")


if __name__ == "__main__":
    main()
