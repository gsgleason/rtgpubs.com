from flask import Flask, render_template, Markup, request, session
from flask_sslify import SSLify
import requests
import uuid
from config import blogger
from db import Customer, session

app = Flask(__name__)
app.config.from_object('config.flask')
sslify = SSLify(app, permanent=True)

@app.route('/')
def index():
	params = {'key':blogger.api_key}
	r = requests.get('https://www.googleapis.com/blogger/v3/blogs/{}/posts'.format(blogger.blog_id), params=params)
	content = []
	posts = r.json()['items']
	for post in posts:
		if 'labels' in post:
			if 'home' in post.get('labels'):
				content.append({'title':post.get('title'),'content':Markup(post.get('content'))})
	return render_template('page.html', content=content)

@app.route('/about')
def about():
	params = {'key':blogger.api_key}
	r = requests.get('https://www.googleapis.com/blogger/v3/blogs/{}/posts'.format(blogger.blog_id), params=params)
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
	params = {'key':blogger.api_key}
	r = requests.get('https://www.googleapis.com/blogger/v3/blogs/{}/posts'.format(blogger.blog_id), params=params)
	content = []
	posts = r.json()['items']
	for post in posts:
		content.append({'title':post.get('title'),'content':Markup(post.get('content'))})
	return render_template('page.html', content=content)

@app.route('/buy')
def buy():
	if 'id' not in session:
		session['id'] = uuid.uuid4()
	customer = session.query(Customer).filter(Customer.session_id == session['id']).first()
	if customer is None:
		customer = Customer(session_id=session['id'])
	session.add(customer)
	session.commit()
	return render_template('buy.html')

@app.route('/ipn', methods=['POST'])
def ipn():
	email = request.form.get('payer_email')
	paypal_transaction_id = request.form.get('txn_id')
	payment_status = request.form.get('payment_status')
	session_id = request.form.get('custom')
	# first we will search by transaction ID, which would be to update an existing transaction
	customer = session.query(Customer).filter(Customer.paypal_transaction_id == paypal_transaction_id).first()
	# if that's not found, search by session_id, this will work for users who initiated the purchase through the site and have returned
	if customer is None:
		customer = session.query(Customer).filter(Customer.session_id == session_id).first()
	# if that's not found, create new instance
	if customer is None:
		customer = Customer()
		session.add(customer)
	customer.email = email
	customer.paypal_transaction_id = paypal_transaction_id
	customer.payment_status = payment_status
	customer.session_id = session_id

	# send full post back to paypal
	data = {}
	data['cmd'] = '_notify-validate'
	for key,val in request.form.items():
		data[key] = val
	url = 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr'
	r = requests.post(url, data=data)
	if r.text == 'VERIFIED':
		session.commit()

	return ""
