from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
import boto3
from werkzeug.utils import secure_filename
import random
import string
import os
from dotenv import load_dotenv
import math

load_dotenv()

app = Flask(__name__)

aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = os.getenv('AWS_REGION')
app.secret_key = os.getenv('FLASK_SECRET_KEY')

s3 = boto3.resource('s3', 
                    aws_access_key_id=aws_access_key_id, 
                    aws_secret_access_key=aws_secret_access_key, 
                    region_name=aws_region)

textract = boto3.client('textract', 
                        aws_access_key_id=aws_access_key_id, 
                        aws_secret_access_key=aws_secret_access_key, 
                        region_name=aws_region)

bucket_name = 'taxechnology2'

def store_all_fields(response):
    stored_info = {}
    for block in response['Blocks']:
        if block['BlockType'] == "KEY_VALUE_SET":
            if 'KEY' in block['EntityTypes']:
                key = ''
                for relationship in block['Relationships']:
                    if relationship['Type'] == 'CHILD':
                        for child_id in relationship['Ids']:
                            for child_block in response['Blocks']:
                                if child_block['Id'] == child_id:
                                    key += child_block.get('Text', '') + ' '
                key = key.strip()
                stored_info[key] = ''
            if 'VALUE' in block['EntityTypes']:
                value = ''
                for relationship in block['Relationships']:
                    if relationship['Type'] == 'CHILD':
                        for child_id in relationship['Ids']:
                            for child_block in response['Blocks']:
                                if child_block['Id'] == child_id:
                                    value += child_block.get('Text', '') + ' '
                value = value.strip()
                stored_info[key] = value
    return stored_info


@app.route('/simulate_received_invoice')
def simulate_received_invoice():
    tax_payer_id = 'NL' + ''.join(random.choices(string.digits, k=9)) + 'B' + ''.join(random.choices(string.digits, k=2))  # generate random tax payer id
    current_subtotal = round(random.uniform(20, 2000), 2)  # generate random SUBTOTAL value between 20 and 2000
    current_vat = round(current_subtotal * 0.21, 2)  # calculate VAT as 21% of SUBTOTAL

    if 'received_vat_dict' not in session:
        session['received_vat_dict'] = {tax_payer_id: current_vat}
    else:
        session['received_vat_dict'][tax_payer_id] = session['received_vat_dict'].get(tax_payer_id, 0.0) + current_vat

    if 'received_subtotal_dict' not in session:
        session['received_subtotal_dict'] = {tax_payer_id: current_subtotal}
    else:
        session['received_subtotal_dict'][tax_payer_id] = session['received_subtotal_dict'].get(tax_payer_id, 0.0) + current_subtotal

    session.modified = True  # to make sure that the changes to mutable objects are saved

    return redirect(url_for('upload_file'))


@app.route('/')
def upload_file():
    net_vat = math.floor(sum(session.get('cumulative_vat_dict', {}).values()) - sum(session.get('received_vat_dict', {}).values()))
    net_subtotal = math.floor(sum(session.get('cumulative_subtotal_dict', {}).values()) - sum(session.get('received_subtotal_dict', {}).values()))

    return render_template('upload.html', 
                           vat_dict=session.get('cumulative_vat_dict', {}), 
                           subtotal_dict=session.get('cumulative_subtotal_dict', {}), 
                           received_vat_dict=session.get('received_vat_dict', {}), 
                           received_subtotal_dict=session.get('received_subtotal_dict', {}), 
                           net_vat=net_vat, 
                           net_subtotal=net_subtotal)


@app.route('/uploader', methods = ['GET', 'POST'])
def uploader_file():
    if request.method == 'POST':
      f = request.files['file']
      filename = secure_filename(f.filename)
      f.save(filename)

      s3.Bucket(bucket_name).upload_file(filename, filename)

      response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket_name, 'Name': filename}},
            FeatureTypes=['TABLES', 'FORMS'],
      )
      
      stored_info = store_all_fields(response)
      tax_payer_id = stored_info.get('Tax payer id:')
      current_vat = float(stored_info.get('VAT', '0.00').replace(',', '.'))
      current_subtotal = float(stored_info.get('SUBTOTAL', '0.00').replace(',', '.'))

      if 'cumulative_vat_dict' not in session:
          session['cumulative_vat_dict'] = {tax_payer_id: current_vat}
      else:
          session['cumulative_vat_dict'][tax_payer_id] = session['cumulative_vat_dict'].get(tax_payer_id, 0.0) + current_vat

      if 'cumulative_subtotal_dict' not in session:
          session['cumulative_subtotal_dict'] = {tax_payer_id: current_subtotal}
      else:
          session['cumulative_subtotal_dict'][tax_payer_id] = session['cumulative_subtotal_dict'].get(tax_payer_id, 0.0) + current_subtotal

      session.modified = True  # to make sure that the changes to mutable objects are saved

      result = '<h2>Extracted Information:</h2>'
      result += '<table style="width:100%; border: 1px solid black;"><tr><th>Field</th><th>Value</th></tr>'
      for key, value in stored_info.items():
        result += f'<tr><td>{key}</td><td>{value}</td></tr>'
      result += '</table>'
      result += f'<h2>Cumulative VAT: {"{:.2f}".format(session["cumulative_vat_dict"].get(tax_payer_id, 0.0))}</h2>'
      result += f'<h2>Cumulative SUBTOTAL: {"{:.2f}".format(session["cumulative_subtotal_dict"].get(tax_payer_id, 0.0))}</h2>'

      return result + '<br><br><button onclick="location.href=\'/\'">Go back</button>'

   
@app.after_request
def add_header(response):
    response.cache_control.no_store = True
    return response

@app.route('/download_invoice')
def download_invoice():
    return send_from_directory('Invoices', 'Factuur.pdf', as_attachment=True)

@app.route('/download_invoice_2')
def download_invoice_2():
    return send_from_directory('Invoices', 'Factuur_2.pdf', as_attachment=True)

@app.route('/download_invoice_3')
def download_invoice_3():
    return send_from_directory('Invoices', 'Factuur_3.pdf', as_attachment=True)
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
