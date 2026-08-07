from forgecast.db import SessionLocal, init_db
from forgecast.auth import hash_password
from forgecast import credits
from forgecast.models import User
init_db()
with SessionLocal() as s:
    if not s.query(User).first():
        u = User(email='b@t.local', hashed_password=hash_password('browserpass'))
        s.add(u); s.flush(); credits.grant(s, u.id, 500, note='seed'); s.commit()
