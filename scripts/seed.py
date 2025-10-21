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
        amenidades = ["Ar-condicionado", "Wi‑Fi", "TV Smart", "Hidromassagem", "Frigobar"]
        amen_map = {}
        for nome in amenidades:
            a = db.execute(select(Amenidade).where(Amenidade.nome == nome)).scalar_one_or_none()
            if a is None:
                a = Amenidade(nome=nome)
                db.add(a)
                db.flush()
            amen_map[nome] = a

        # Suítes:
        # - 11 suítes com todas as amenidades exceto Hidromassagem
        # - 1 suíte com apenas Hidromassagem
        quartos = [f"Quarto {i}" for i in range(1, 12)]
        suite_hidro = "Suíte Hidromassagem"

        # Monta listas de amenidades conforme regra
        amen_todas_exceto_hidro = [
            amen_map[n]
            for n in amenidades
            if n != "Hidromassagem"
        ]
        amen_so_hidro = [amen_map["Hidromassagem"]]

        # Criar 11 suítes
        for idx, titulo in enumerate(quartos, start=1):
            s = db.execute(select(Suite).where(Suite.slug == slugify(titulo))).scalar_one_or_none()
            if s is None:
                s = Suite(
                    titulo=titulo,
                    slug=slugify(titulo),
                    tipo_id=tipos_map.get("Standard").id if tipos_map.get("Standard") else None,
                    descricao=f"{titulo} com conforto e privacidade.",
                    preco_hora=str(100 + (idx % 3) * 10) + ".00",
                    preco_pernoite=str(220 + (idx % 3) * 10) + ".00",
                    destaque=False,
                    ordem=idx,
                )
                s.amenidades = amen_todas_exceto_hidro
                db.add(s)

        # Criar 1 suíte com apenas hidromassagem
        s = db.execute(select(Suite).where(Suite.slug == slugify(suite_hidro))).scalar_one_or_none()
        if s is None:
            s = Suite(
                titulo=suite_hidro,
                slug=slugify(suite_hidro),
                tipo_id=tipos_map.get("Luxo").id if tipos_map.get("Luxo") else None,
                descricao="Suíte com hidromassagem para momentos especiais.",
                preco_hora="150.00",
                preco_pernoite="320.00",
                destaque=True,
                ordem=0,
            )
            s.amenidades = amen_so_hidro
            db.add(s)

        db.commit()
    print("Seed aplicado com sucesso")


if __name__ == "__main__":
    main()
