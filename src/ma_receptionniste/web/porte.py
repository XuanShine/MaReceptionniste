from urllib.parse import urlencode

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

PUBLIC = {"/login", "/register"}


class PorteAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        chemin = request.url.path
        if chemin.startswith("/static") or chemin in PUBLIC:
            return await call_next(request)
        if "user_id" not in request.session:
            return RedirectResponse("/login?" + urlencode({"redirect_to": chemin}), status_code=303)
        return await call_next(request)
