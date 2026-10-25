def enregistrer_routes() -> tuple[object, ...]:
    from ma_gouvernante.pages import auth_pages, chambres, fiche, historique, liste

    return (auth_pages, chambres, fiche, historique, liste)
