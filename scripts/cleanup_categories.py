#!/usr/bin/env python3
"""
Script para limpiar categorías irrelevantes en la tabla `noticias`.

Uso:
  python scripts/cleanup_categories.py --action [null|other|delete] [--yes]

Opciones:
  null   -> establece `categoria` a NULL para las categorías no permitidas
  other  -> reemplaza por la categoría "Otros"
  delete -> elimina las noticias cuya categoría no esté en la lista permitida

Antes de aplicar cambios mostrará un resumen y pedirá confirmación (a menos que se pase --yes).
"""
from __future__ import annotations
import argparse
from app.database import SessionLocal
from app.models import Noticia

ALLOWED = ['Política','Deportes','Salud','Economía','Música','Tecnología','Entretenimiento','Videojuegos','Tendencias']


def main():
    parser = argparse.ArgumentParser(description="Limpiar categorías irrelevantes en 'noticias'")
    parser.add_argument("--action", choices=["null", "other", "delete", "normalize"], required=True,
                        help="Acción a realizar sobre noticias con categorías no permitidas (normalize: poner 'Tendencias' a no permitidas)")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmación")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        # Obtener categorías distintas
        from sqlalchemy import select, update, delete, func
        distinct_rows = session.execute(select(func.distinct(Noticia.categoria))).all()
        distinct = [r[0] for r in distinct_rows]
        print("Categorías encontradas (distintas):\n", distinct)

        to_remove = [c for c in distinct if c and c not in ALLOWED]
        if not to_remove:
            print("No se encontraron categorías irrelevantes. Nada que hacer.")
            return

        print("\nCategorías irrelevantes detectadas:")
        for c in to_remove:
            count = session.execute("SELECT COUNT(1) FROM noticias WHERE categoria = :c", {"c": c}).scalar()
            print(f"  - {c}: {count} noticia(s)")

        if not args.yes:
            confirm = input(f"\nConfirmas ejecutar '{args.action}' sobre estas categorías? (s/N): ")
            if confirm.strip().lower() != 's':
                print("Operación cancelada.")
                return

        if args.action == 'null':
            stmt = update(Noticia).where(Noticia.categoria.in_(to_remove)).values(categoria=None)
            session.execute(stmt)
            session.commit()
            print("Se estableció categoria=NULL para las categorías listadas.")

        elif args.action == 'other':
            stmt = update(Noticia).where(Noticia.categoria.in_(to_remove)).values(categoria='Otros')
            session.execute(stmt)
            session.commit()
            print("Se reemplazó por 'Otros' las categorías listadas.")

        elif args.action == 'delete':
            # Confirm again because this is destructive
            if not args.yes:
                confirm2 = input("ATENCIÓN: Esto ELIMINARÁ noticias. Confirmar eliminación (s/N): ")
                if confirm2.strip().lower() != 's':
                    print("Operación cancelada.")
                    return
            stmt = delete(Noticia).where(Noticia.categoria.in_(to_remove))
            session.execute(stmt)
            session.commit()
            print("Noticias eliminadas para las categorías listadas.")

        elif args.action == 'normalize':
            # Poner 'Tendencias' para categorías no permitidas
            stmt = update(Noticia).where(Noticia.categoria.in_(to_remove)).values(categoria='Tendencias')
            session.execute(stmt)
            session.commit()
            print("Se normalizó: categorías no permitidas ahora marcadas como 'Tendencias'.")

        print("Operación completada.")
    finally:
        session.close()


if __name__ == '__main__':
    main()
