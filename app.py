from flask import Flask, render_template, Markup, request, session, redirect, abort, url_for, flash, send_from_directory
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

@app.teardown_appcontext
def shutdown_session(exception=None):
	db.remove()

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
	return render_template('buy.html', button_form = Markup(config.paypal.button_form.format(str(uuid.uuid4()))))

@app.route('/download', methods=['GET','POST'])
def download():
	# first, see if session id from cookie is there and has been associated with a completed paypal transaction
	if 'invoice' in session:
		transaction = db.query(Transaction).filter(Transaction.invoice == session['invoice'], Transaction.payment_status == 'Completed').first()
	else:
		transaction = None
	if not transaction:
		# no transaction for this session found - need to do lookup
		return redirect(url_for('transaction_lookup'), code=302)
	# if we get here, there is a completed transaction for this session
	if request.method == 'GET':
		return render_template('download.html', data=config.book.files)
	if request.method == 'POST':
		ebook_format = request.form.get('ebook_format')
		try:
			transaction.downloads += 1
			db.commit()
			return send_from_directory(config.book.directory, config.book.files[ebook_format], as_attachment=True)
		except:
			abort(404)

@app.route('/transaction_lookup', methods=['GET','POST'])
def transaction_lookup():
	if request.method == 'GET':
		return render_template('transaction_lookup.html', site_key = config.reCaptcha.site_key)
	if request.method == 'POST':
		#first, do recaptcha
		g_recaptcha_response =  request.form.get('g-recaptcha-response')
		if request.headers.getlist("X-Forwarded-For"):
			remote_ip = request.headers.getlist("X-Forwarded-For")[0]
		else:
			remote_ip = request.remote_addr
		secret_key = config.reCaptcha.secret_key
		url = config.reCaptcha.url
		data = {'secret':secret_key,'response':g_recaptcha_response,'remoteip':remote_ip}
		r = requests.post(url,data=data)
		if r.status_code != 200:
			flash('reCAPTCHA service failure','danger')
			return render_template('transaction_lookup.html', site_key = config.reCaptcha.site_key)
		result = r.json()
		if result.get('success') is not True:
			flash('reCAPTCHA error: {}'.format(', '.join(result.get('error-codes'))), 'danger')
			return render_template('transaction_lookup.html', site_key = config.reCaptcha.site_key)
		# at this point, recaptcha was successful
		email = request.form.get('email').strip()
		invoice = request.form.get('invoice').strip()
		transaction = db.query(Transaction).filter(Transaction.email == email, Transaction.invoice == invoice).first()
		if not transaction:
			flash('Transaction not found', 'danger')
			return render_template('transaction_lookup.html', site_key = config.reCaptcha.site_key)
		session['invoice'] = transaction.invoice
		return redirect(url_for('download'), code=302)

@app.route('/pdt')
def pdt():
	if 'tx' not in request.args:
		return redirect(url_for('transaction_lookup'), code=302)
	paypal_transaction_id = request.args.get('tx')
	pdt_data = pdt_lookup(paypal_transaction_id)
	if pdt_data:
		# first, look for transaction that already matches this paypal transaction ID.  This should only happen if the pdt page is visited twice.
		transaction = db.query(Transaction).filter(Transaction.paypal_transaction_id == paypal_transaction_id).first()
		# if there's no record for this transaction, make a new one
		if not transaction:
			transaction = Transaction()
			db.add(transaction)
		transaction.payment_status = pdt_data.get('payment_status')
		transaction.paypal_transaction_id = pdt_data.get('txn_id')
		transaction.email = urllib.parse.unquote(pdt_data.get('payer_email'))
		transaction.invoice = pdt_data.get('invoice')
		session['invoice'] = transaction.invoice
		db.commit()
	return render_template('pdt.html', data=transaction)

@app.route('/ipn', methods=['POST'])
def ipn():
	email = request.form.get('payer_email')
	paypal_transaction_id = request.form.get('txn_id')
	payment_status = request.form.get('payment_status')
	invoice  = request.form.get('invoice')
	# first we will search by transaction ID, which would be to update an existing transaction
	transaction = db.query(Transaction).filter(Transaction.paypal_transaction_id == paypal_transaction_id).first()
	# if that's not found, create new instance
	if transaction is None:
		transaction = Transaction()
		db.add(transaction)
	transaction.email = email
	transaction.paypal_transaction_id = paypal_transaction_id
	transaction.payment_status = payment_status
	transaction.invoice = invoice
	# send full post back to paypal
	data = {}
	data['cmd'] = '_notify-validate'
	for key,val in request.form.items():
		data[key] = val
	url = config.paypal.api_uri
	r = requests.post(url, data=data)
	if r.text == 'VERIFIED':
		db.commit()
		return ""
	else:
		abort(404)
