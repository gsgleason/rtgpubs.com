from flask import Flask, render_template, Markup, request, session, redirect, abort, url_for, flash
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

def pdt_lookup(tx):
	data = {}
	data['cmd'] = '_notify-synch'
	data['tx'] = tx
	data['at'] = config.paypal.pdt_token
	url = config.paypal.api_uri
	r = requests.post(url, data=data)
	if r.status_code == 200:
		response_list = shlex.split(r.text)
		if response_list[0] == 'SUCCESS':
			response_data = dict(token.split('=') for token in response_list[1:])
			return response_data
	return None

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
	return render_template('buy.html')

@app.route('/download', methods=['GET','POST'])
def download():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	if request.method == 'GET':
		# first, see if session id from cookie is there and has been associated with a completed paypal transaction
		transaction = db.query(Transaction).filter(Transaction.session_id == session['id'], Transaction.payment_status == 'Completed').first()
		if transaction:
			return render_template('download.html')
		# no transaction for this session found - need to do lookup
		return redirect(url_for('transaction_lookup'), code=302)
	if request.method == 'POST':
		return ''

@app.route('/transaction_lookup', methods=['GET','POST'])
def transaction_lookup():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	if request.method == 'GET':
		return render_template('transaction_lookup.html')
	if request.method == 'POST':
		email = request.form.get('email')
		paypal_transaction_id = request.form.get('paypal_transaction_id')
		transaction = db.query(Transaction).filter(Transaction.email == email, Transaction.paypal_transaction_id == paypal_transaction_id).first()
		# if not local record, check with paypal
#		This section will look up the transaction on paypal.  This shouldn't ever be necessary.  I'll leave it commented for now.
#		if not transaction:
#			pdt_data = pdt_lookup(paypal_transaction_id)
#			if pdt_data and urllib.parse.unquote(pdt_data.get('payer_email')) == email and pdt_data.get('txn_id') == paypal_transaction_id:
#				transaction = Transaction()
#				transaction.email = urllib.parse.unquote(pdt_data.get('payer_email'))
#				transaction.paypal_transaction_id = pdt_data.get('txn_id')
#				transaction.payment_status = pdt_data.get('payment_status')
#				transaction.session_id = session['id']
#				db.add(transaction)
#				db.commit()
		if transaction:
			transaction.session_id = session['id']
			db.commit()
			db.close()
			return redirect(url_for('download'), code=302)
		flash('Transaction not found', 'danger')
		return render_template('transaction_lookup.html')

@app.route('/pdt')
def pdt():
	if 'tx' not in request.args:
		abort(400)
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	paypal_transaction_id = request.args.get('tx')
	# first, look for transaction that already matches this paypal transaction ID.  This should only happen if the pdt page is visited twice.
	transaction = db.query(Transaction).filter(Transaction.paypal_transaction_id == paypal_transaction_id).first()
	# if that's not there, look for transaction that matches this browser session but has no transaction id
	if not transaction:
		transaction = db.query(Transaction).filter(Transaction.session_id == session['id'], Transaction.paypal_transaction_id == None).first()
	# if there's no record without a transaction id for this browser session, make a new one
	if not transaction:
		transaction = Transaction(paypal_transaction_id=paypal_transaction_id, session_id=session['id'])
		db.add(transaction)
	pdt_data = pdt_lookup(paypal_transaction_id)
	if pdt_data:
		transaction.payment_status = pdt_data.get('payment_status')
		transaction.paypal_transaction_id = pdt_data.get('txn_id')
		transaction.email = urllib.parse.unquote(pdt_data.get('payer_email'))
		transaction.session_id = session['id']
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
		db.close()
		abort(404)
