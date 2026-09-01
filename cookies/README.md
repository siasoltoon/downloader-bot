# Site-specific yt-dlp cookies

Put exported Netscape-format cookie files here when a site requires authentication or a site-specific session.

Filename rule:

- `example.com.txt` → used for `example.com` and its subdomains
- `youtube.com.txt` → used for `youtube.com` and its subdomains

Cookie files are intentionally ignored by Git. Never commit real cookies or session credentials.

Runtime directory can be changed with `COOKIES_DIR`.
