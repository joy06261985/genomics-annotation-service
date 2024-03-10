# annotator_webhook.py
#
# Modified to run as a web server that can be called by SNS to process jobs
# Run using: FLASK_APP=annotator_webhook.py flask run
#
# NOTE: This file lives on the AnnTools instance
#
# Copyright (C) 2013-2024 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import boto3
import json
import os
import subprocess
from flask import Flask, request, jsonify

# Create Flask app
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from botocore.client import Config
from configparser import ConfigParser, ExtendedInterpolation
import requests

from annotator_webhook_config import Ann_Config

# Create Flask app
app = Flask(__name__)

# changed the class name in annotator_webhook_config.py
# since I used botocore.client.Config as well
app.config.from_object(Ann_Config)

# """general config"""
bucket = app.config["AWS_S3_RESULTS_BUCKET"]
region = app.config["AWS_REGION_NAME"]
db_table = app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE']
key_prefix = app.config["AWS_S3_KEY_PREFIX"]
base_path = app.config["ANNOTATOR_BASE_DIR"]
job_path = app.config["ANNOTATOR_JOBS_DIR"]
queue_url = app.config["AWS_SQS_URL"]
wait_time = app.config["AWS_SQS_WAIT_TIME"]
max_messages = app.config["AWS_SQS_MAX_MESSAGES"]


# Establish connections to AWS services
s3 = boto3.client('s3', region_name=region, config=Config(signature_version='s3v4'))
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)
# sns = boto3.client('sns', region_name=app.config["AWS_REGION_NAME"])
sqs = boto3.client('sqs', region_name=app.config["AWS_REGION_NAME"])

@app.route("/process-job-request", methods=["POST"])
def process_job_request():
    print("test check")
    # Process the SNS message
    message = json.loads(request.data)
    print("message : ", message)

    # Confirm the SNS subscription
    # ref: Step 1: Make sure your endpoint is ready to process Amazon SNS messages
    # https://docs.aws.amazon.com/sns/latest/dg/SendMessageToHttp.prepare.html
    if message['Type'] == 'SubscriptionConfirmation':
        subscribe_url = message['SubscribeURL']
        # Step 3: Confirm the subscription
        # ref: https://docs.aws.amazon.com/sns/latest/dg/SendMessageToHttp.confirm.html
        response = requests.get(subscribe_url)  # Confirm subscription
        # print("response: ", response)
        if response.ok:
            return jsonify(message="SNS Subscription confirmed."), 200
        else:
            return jsonify(message="Fail to confirm"), 500

    # Process the SNS notification message
    if message['Type'] == 'Notification':
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=int(max_messages),  
            WaitTimeSeconds=int(wait_time)  
        )

        messages = response.get('Messages', [])
        # print("messages: ", messages)

        if messages:
            message_body = messages[0]['Body']
            message_data = json.loads(message_body)
            # print("message_data: ", message_data)
            data_body = message_data['Message']
            data = json.loads(data_body)
            # print("data: ", data)

            try: 
                process_annotation_job(data)
                try:
                    # messages.delete()
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=messages[0]['ReceiptHandle']
                    )
                    print("messages deleted")
                except ClientError as e:
                    print(f"messages delete failed: {str(e)}")
                    return jsonify(message="messages delete failed."), 500

            except Exception as e:
                print(f"Process annotation failed: {str(e)}")
                return jsonify(message="Process annotation failed"), 500

        return jsonify(message="Job processed."), 200

    return jsonify(message="Invalid message type received."), 400


@app.route("/", methods=["GET"])
def annotator_webhook():

    return ("Annotator webhook; POST job to /process-job-request"), 200


def process_annotation_job(message_data):
    # This function contains the core job processing logic from the original script
    try:
        print("process_annotation_job")
        job_id = message_data.get("job_id")
        user_id = message_data.get("user_id")
        input_file_name = message_data.get("input_file_name")
        s3_inputs_bucket = message_data.get("s3_inputs_bucket")
        s3_key_input_file = message_data.get("s3_key_input_file")
    except Exception as e:
        print(f"Unexpected error when processing message: {e}")

    # Get the input file S3 object and copy it to a local file
    try:
        job_dir = f'{job_path}/{job_id}'
        os.makedirs(job_dir, exist_ok=True)

        download_path = f'{job_dir}/{input_file_name}'
        s3.download_file(s3_inputs_bucket, s3_key_input_file, download_path)
    except NoCredentialsError:
        print("AWS credentials not found.")
    except (BotoCoreError, ClientError) as e:
        print(f"Error downloading file from S3: {e}")
    except Exception as e:
        print(f"Unexpected error downloading file: {e}")

    try:
        # Launch the AnnTools pipeline
        command = f'python {base_path}/run.py {download_path} {job_id} {user_id} {input_file_name}'
        subprocess.Popen(command, shell=True, cwd=job_dir)
    except subprocess.CalledProcessError as e:
        print(f"Subprocess failed with exit status {e.returncode}")
    except Exception as e:
        print(f"Unexpected error launching subprocess: {e}")

    try:
        # Update job status to RUNNING
        response = annotations_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET job_status = :status',
            ConditionExpression='job_status = :pending_status',
            ExpressionAttributeValues={
                ':status': 'RUNNING',
                ':pending_status': 'PENDING'
            },
            ReturnValues='UPDATED_NEW'
        )
    # check if the update was successful (the condition was met)
        if 'Attributes' not in response:
            print('Job status is not PENDING, cannot start processing.')
    except (BotoCoreError, ClientError) as e:
        print(f"Error updating DynamoDB: {e}")
    except Exception as e:
        print(f"Unexpected error updating DynamoDB: {e}")

# EOF

