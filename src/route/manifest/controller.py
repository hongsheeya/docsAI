import json

flask = wiz.response._flask

manifest = {
    "name": "DocsAI",
    "short_name": "DocsAI",
    "description": "AI 기반 문서 작성 및 양식 관리 서비스",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#f8fafc",
    "theme_color": "#0f172a",
    "icons": [
        {
            "src": "/assets/brand/favicon.svg",
            "sizes": "192x192",
            "type": "image/svg+xml"
        },
        {
            "src": "/assets/brand/favicon.svg",
            "sizes": "512x512",
            "type": "image/svg+xml"
        }
    ]
}

resp = flask.Response(
    json.dumps(manifest, ensure_ascii=False, indent=2),
    mimetype="application/manifest+json"
)
wiz.response.response(resp)
