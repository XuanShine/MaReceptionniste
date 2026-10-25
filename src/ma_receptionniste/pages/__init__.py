def enregistrer_routes() -> tuple[object, ...]:
    from ma_receptionniste.pages import auth_pages, chambres, clients, fiche, planning, reservations

    return (auth_pages, chambres, clients, fiche, planning, reservations)
