# System packages for the full-stack demo: Postgres 16, Python 3.12, Node 20.
# (psycopg ships its own libpq and hashing is stdlib pbkdf2, so no extra system libs.)
{ pkgs }: {
  deps = [
    pkgs.postgresql_16
    pkgs.python312
    pkgs.nodejs_20
    pkgs.bash
    pkgs.curl
  ];
}
