"""Serve the two built React applications from one HTTPS deployment."""

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from .db import ROOT


def mount_frontends(app):
    available = True
    for route, folder in [("shop", "shop-frontend"), ("console", "console-frontend")]:
        build = ROOT / folder / "dist"
        if build.is_dir():
            app.mount("/" + route, StaticFiles(directory=build, html=True), name=route)
        else:
            available = False
    if available:

        @app.get("/", include_in_schema=False)
        def storefront():
            return RedirectResponse("/shop/")
