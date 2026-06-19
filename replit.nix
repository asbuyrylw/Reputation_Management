# System packages for the full-stack demo: Postgres 16, Python 3.12, Node 20.
# (psycopg ships its own libpq and hashing is stdlib pbkdf2, so no extra system libs.)
# libreoffice-fresh provides headless `soffice` for the optional .docx -> PDF report export
# (report_generator._docx_to_pdf); without it reports still download/email as .docx.
{ pkgs }: {
  deps = [
    pkgs.postgresql_16
    pkgs.python312
    pkgs.nodejs_20
    pkgs.bash
    pkgs.curl
    pkgs.libreoffice-fresh
  ];
}
