from pathlib import Path
from fastapi.responses import FileResponse
ASSETS=Path(__file__).with_name('assets')
def install(app):
    @app.get('/assets/teamspace.css')
    def css():return FileResponse(ASSETS/'teamspace.css',media_type='text/css',headers={'Cache-Control':'private, max-age=3600'})
    @app.get('/assets/teamspace.js')
    def js():return FileResponse(ASSETS/'teamspace.js',media_type='application/javascript',headers={'Cache-Control':'private, max-age=3600'})
