from api._base import ApiHandler
from src.web_app.api import dispatch


class handler(ApiHandler):
    route = "/api/health"

    def do_GET(self):
        status, payload = dispatch(self.route, {})
        self._write(status, payload)
