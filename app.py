from flask import Flask, render_template, Markup, request, session, redirect, abort
from flask_sslify import SSLify
import requests
import uuid
import config
from db import Transaction, session as db
import shlex
import urllib.parse

app = Flask(__name__)
app.config.from_object('config.flask')
sslify = SSLify(app, permanent=True)

@app.route('/')
def index():
	params = {'key':config.blogger.api_key}
	r = requests.get('https://www.googleapis.com/blogger/v3/blogs/{}/posts'.format(config.blogger.blog_id), params=params)
	content = []
	posts = r.json()['items']
	for post in posts:
		if 'labels' in post:
			if 'home' in post.get('labels'):
				content.append({'title':post.get('title'),'content':Markup(post.get('content'))})
	return render_template('page.html', content=content)

@app.route('/about')
def about():
	params = {'key':config.blogger.api_key}
	r = requests.get('https://www.googleapis.com/blogger/v3/blogs/{}/posts'.format(config.blogger.blog_id), params=params)
	content = []
	posts = r.json()['items']
	for post in posts:
		if 'labels' in post:
			if 'about' in post.get('labels'):
				print(post.get('labels'))
				content.append({'title':post.get('title'),'content':Markup(post.get('content'))})
	return render_template('page.html', content=content)

@app.route('/blog')
def blog():
	params = {'key':config.blogger.api_key}
	r = requests.get('https://www.googleapis.com/blogger/v3/blogs/{}/posts'.format(config.blogger.blog_id), params=params)
	content = []
	posts = r.json()['items']
	for post in posts:
		content.append({'title':post.get('title'),'content':Markup(post.get('content'))})
	return render_template('page.html', content=content)

@app.route('/buy')
def buy():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	transaction = db.query(Transaction).filter(Transaction.session_id == session['id']).first()
	if transaction is None:
		transaction = Transaction(session_id=session['id'])
	db.add(transaction)
	db.commit()
	db.close()
	return render_template('buy.html')

@app.route('/download', methods=['GET','POST'])
def download():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	if request.method == 'GET':
		# first, see if session id from cookie is there and has been associated with a paypal transaction
		transaction = db.query(Transaction).filter(Transaction.session_id == session['id']).first()
		if transaction and transaction.paypal_transaction_id and transaction.email:
			if transaction.payment_status == 'Completed':
				# we've received IPN from paypal notifying that payment is complete for this session
				return render_template('download.html')
			else:
				# paypal transaction has been created but payment is not complete
				return render_template('payment_not_complete.html')
		# no session found - need to enter transaction id, email in order to download.
		return render_template('enter_payment_details.html', data=transaction)
	if request.method == 'POST':
		email = request.form.get('email')
		paypal_transaction_id = request.form.get('paypal_transaction_id')
		transaction = db.query(Transaction).filter(Transaction.email == email, Transaction.paypal_transaction_id == paypal_transaction_id).first()
		if transaction:
			transaction.session_id = session['id']
			db.commit()
			db.close()
			return redirect('/download', code=302)
		else:
			return render_template('transaction_not_found.html')

@app.route('/pdt')
def pdt():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	# verify transaction with paypal now
	if 'tx' in request.args:
		# perform post for PDT verification
		paypal_transaction_id = request.args.get('tx')
		# check to see if there is a record with this transaction id already
		transaction = db.query(Transaction).filter(Transaction.paypal_transaction_id == paypal_transaction_id).first()
		if not transaction:
			transaction = Transaction(paypal_transaction_id=paypal_transaction_id, session_id=session['id'])
			db.add(transaction)
		data = {}
		data['cmd'] = '_notify-synch'
		data['tx'] = paypal_transaction_id
		data['at'] = config.paypal.pdt_token
		url = config.paypal.api_uri
		r = requests.post(url, data=data)
		if r.status_code == 200:
			response_list = shlex.split(r.text)
			if response_list[0] == 'SUCCESS':
				response_data = dict(token.split('=') for token in response_list[1:])
				transaction.payment_status = response_data.get('payment_status')
				transaction.paypal_transaction_id = response_data.get('txn_id')
				transaction.email = urllib.parse.unquote(response_data.get('payer_email'))
				db.commit()
				db.close()
	return render_template('pdt.html', data=transaction)

@app.route('/ipn', methods=['POST'])
def ipn():
	email = request.form.get('payer_email')
	paypal_transaction_id = request.form.get('txn_id')
	payment_status = request.form.get('payment_status')
	session_id = request.form.get('custom')
	# first we will search by transaction ID, which would be to update an existing transaction
	transaction = db.query(Transaction).filter(Transaction.paypal_transaction_id == paypal_transaction_id).first()
	# if that's not found, search by session_id, this will work for users who initiated the purchase through the site and have returned
	if transaction is None:
		transaction = db.query(Transaction).filter(Transaction.session_id == session_id).first()
	# if that's not found, create new instance
	if transaction is None:
		transaction = Transaction()
		db.add(transaction)
	transaction.email = email
	transaction.paypal_transaction_id = paypal_transaction_id
	transaction.payment_status = payment_status
	transaction.session_id = session_id
	# send full post back to paypal
	data = {}
	data['cmd'] = '_notify-validate'
	for key,val in request.form.items():
		data[key] = val
	url = config.paypal.api_uri
	r = requests.post(url, data=data)
	if r.text == 'VERIFIED':
		db.commit()
		db.close()
		return ""
	else:
		abort(404)
