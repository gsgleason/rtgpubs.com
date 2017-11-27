from flask import Flask, render_template, Markup, request, session, redirect, abort
from flask_sslify import SSLify
import requests
import uuid
import config
from db import Customer, session as db
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
	customer = db.query(Customer).filter(Customer.session_id == session['id']).first()
	if customer is None:
		customer = Customer(session_id=session['id'])
	db.add(customer)
	db.commit()
	db.close()
	return render_template('buy.html')

@app.route('/download', methods=['GET','POST'])
def download():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	if request.method == 'GET':
		# first, see if session id from cookie is there and has been associated with a paypal transaction
		customer = db.query(Customer).filter(Customer.session_id == session['id']).first()
		if customer and customer.paypal_transaction_id and customer.email:
			if customer.payment_status == 'Completed':
				# we've received IPN from paypal notifying that payment is complete for this session
				return render_template('download.html')
			else:
				# paypal transaction has been created but payment is not complete
				return render_template('payment_not_complete.html')
		# no session found - need to enter transaction id, email in order to download.
		return render_template('enter_payment_details.html', data=customer)
	if request.method == 'POST':
		email = request.form.get('email')
		paypal_transaction_id = request.form.get('paypal_transaction_id')
		customer = db.query(Customer).filter(Customer.email == email, Customer.paypal_transaction_id == paypal_transaction_id).first()
		if customer:
			customer.session_id = session['id']
			db.commit()
			db.close()
			return redirect('/download', code=302)
		else:
			return render_template('customer_not_found.html')

@app.route('/pdt')
def download():
	if 'id' not in session:
		session['id'] = str(uuid.uuid4())
	# first, see if session id from cookie is there and has been associated with a paypal transaction
	customer = db.query(Customer).filter(Customer.session_id == session['id']).first()
	if not customer:
		customer = Customer(session_id = session['id'])
	# verify transaction with paypal now
	if 'tx' in request.args:
		# perform post for PDT verification
		paypal_transaction_id = request.args.get('tx')
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
				customer.payment_status = response_data.get('payment_status')
				customer.paypal_transaction_id = response_data.get('txn_id')
				customer.email = urllib.parse.unquote(response_data.get('payer_email'))
				db.commit()
				db.close()
	return render_template('pdt.html', data=customer)

@app.route('/ipn', methods=['POST'])
def ipn():
	email = request.form.get('payer_email')
	paypal_transaction_id = request.form.get('txn_id')
	payment_status = request.form.get('payment_status')
	session_id = request.form.get('custom')
	# first we will search by transaction ID, which would be to update an existing transaction
	customer = db.query(Customer).filter(Customer.paypal_transaction_id == paypal_transaction_id).first()
	# if that's not found, search by session_id, this will work for users who initiated the purchase through the site and have returned
	if customer is None:
		customer = db.query(Customer).filter(Customer.session_id == session_id).first()
	# if that's not found, create new instance
	if customer is None:
		customer = Customer()
		db.add(customer)
	customer.email = email
	customer.paypal_transaction_id = paypal_transaction_id
	customer.payment_status = payment_status
	customer.session_id = session_id

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
