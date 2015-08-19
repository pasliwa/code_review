import logging

# noinspection PyUnresolvedReferences
from flask.ext.security.utils import encrypt_password
from app import app
from app import logs
from app import db, user_datastore

def db_create():
    with app.app_context():
        db.create_all()
        db.session.commit()

        admin_role = user_datastore.find_or_create_role(name="admin", description="Administrator")
        user_role = user_datastore.find_or_create_role(name="user", description="User")

        admin = user_datastore.create_user(email="roman.szalla@genesyslab.com", password=encrypt_password("password"),
                                           cc_login="roman.szalla")
        user_datastore.add_role_to_user(admin, admin_role)
        user_datastore.add_role_to_user(admin, user_role)

        admin = user_datastore.create_user(email="maciej.malycha@genesyslab.com", password=encrypt_password("password"),
                                           cc_login="maciej")
        user_datastore.add_role_to_user(admin, admin_role)
        user_datastore.add_role_to_user(admin, user_role)
        
        admin = user_datastore.create_user(email="Piotr.Sliwa@genesys.com", password=encrypt_password("password"),
                                           cc_login="piotr")
        user_datastore.add_role_to_user(admin, admin_role)
        user_datastore.add_role_to_user(admin, user_role)

        db.session.commit()

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(logs.get_console_handler())
    db_create()
