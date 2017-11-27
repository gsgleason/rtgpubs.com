from config import db
from sqlalchemy import create_engine, Column, String, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
engine = create_engine(db.uri, convert_unicode=True, pool_recycle=280)
Session = sessionmaker(bind=engine, expire_on_commit=True)
session = Session()

class Transaction(Base):
	__tablename__ = 'transactions'

	id = Column(Integer, primary_key=True)
	paypal_transaction_id = Column(String(length=255), unique=True)
	email = Column(String(length=255))
	session_id = Column(String(length=255))
	payment_status = Column(String(length=255))

	def __repr__(self):
		return "<Transaction(id={}, email='{}', paypal_transaction_id='{}', session_id='{}', payment_status={})>".format(self.id, self.email, self.paypal_transaction_id, self.session_id, self.payment_status)

def initDB():
	Base.metadata.drop_all(engine)
	Base.metadata.create_all(engine)


