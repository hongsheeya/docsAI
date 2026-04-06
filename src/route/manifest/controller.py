import json

config = wiz.model("portal/season/config")

manifest = {
    "name": config.pwa_title,
    "short_name": config.pwa_title,
    "start_url": config.pwa_start_url,
    "display": config.pwa_display,
    "background_color": config.pwa_background_color,
    "theme_color": config.pwa_theme_color,
    "orientation": config.pwa_orientation,
    "icons": [
        {
            "src": config.pwa_icon,
            "type": "image/x-icon",
            "purpose": "any"
        }
    ]
}

wiz.response.send(
    json.dumps(manifest, ensure_ascii=False),
    content_type="application/manifest+json; charset=utf-8"
)
