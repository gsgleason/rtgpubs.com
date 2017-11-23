from config import db
from sqlalchemy import create_engine, Column, String, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

Base = declarative_base()
engine = create_engine(db.uri, convert_unicode=True)
session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

class Customer(Base):
	__tablename__ = 'customers'

	id = Column(Integer, primary_key=True)
	paypal_transaction_id = Column(String)
	email = Column(String)
	session_id = Column(String)
	payment_status = Column(String)

	def __repr__(self):
		return "<Customer(id={}, email='{}', paypal_transaction_id='{}', session_id='{}', payment_status={})>".format(self.id, self.email, self.paypal_transaction_id, self.session_id, self.payment_status)

def initdb():
	Base.metadata.delete_all(engine)
	Base.metadata.create_all(engine)


