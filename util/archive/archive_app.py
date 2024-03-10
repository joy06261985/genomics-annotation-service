# archive_app.py
#
# Archive Free user data
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import boto3
import json
import requests
import sys
import os
import time

from flask import Flask, request, jsonify
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
from botocore.client import Config

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

app = Flask(__name__)
app.url_map.strict_slashes = False

# Get configuration and add to Flask app object
environment = "archive_app_config.Config"
app.config.from_object(environment)

# config information
region = app.config['AWS_REGION_NAME']
step_function_arn = app.config['AWS_STEP_FUNCTION_ARN']  
s3_bucket_name = app.config['AWS_S3_RESULTS_BUCKET'] 
db_table = app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'] 
vault = app.config['AWS_GLACIER_VAULT'] 
queue_url = app.config["AWS_SQS_URL"]
queue_url_wait = app.config["AWS_SQS_URL_WAIT3MINS"]
wait_time = app.config["AWS_SQS_WAIT_TIME"]
max_messages = app.config["AWS_SQS_MAX_MESSAGES"]

# AWS connection
glacier_client = boto3.client('glacier', region_name=region)
s3 = boto3.client('s3', region_name=region, config=Config(signature_version='s3v4'))
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)
sqs = boto3.client('sqs', region_name=app.config["AWS_REGION_NAME"])
# ref: SFN client
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/stepfunctions.html
stepfunctions = boto3.client('stepfunctions', region_name=region)


@app.route("/", methods=["GET"])
def home():
    return "This is the Archive utility: POST requests to /archive."


# First Endpoint to recieve the sns "job_results" topic from run.py after job completed
@app.route("/archive", methods=["POST"])
def archive_free_user_data():
    try:
        # Extract the JSON content from the request
        sns_message = json.loads(request.data)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return jsonify(message="Invalid JSON format."), 400
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify(message="An error occurred processing your request."), 500

    # Subscription Confirmation
    # Check the type of message and handle subscription confirmation
    if sns_message.get('Type') == 'SubscriptionConfirmation':
        subscribe_url = sns_message.get('SubscribeURL')
        if not subscribe_url:
            print("SubscribeURL not found.")
            return jsonify(message="SubscribeURL not found in the message."), 400

        try:
            response = requests.get(subscribe_url)
        except requests.exceptions.RequestException as e:
            print(f"Failed to confirm SNS Subscription: {e}")
            return jsonify(message="Network error in confirming SNS Subscription."), 500

        if response.status_code == 200:
            print("SNS Subscription confirmed.")
            return jsonify(message="SNS Subscription confirmed."), 200
        else:
            print("Failed to confirm SNS Subscription.")
            return jsonify(message="Failed to confirm SNS Subscription."), 400

    # Notifications
    if sns_message.get('Type') == 'Notification':
        # sqs: job_results_archive to store the message in queue in case job fail
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=int(max_messages),  
            WaitTimeSeconds=int(wait_time)  
        )
        print("job_results_archive sqs received")
        messages = response.get('Messages', [])

        if messages:
            message_body = messages[0]['Body']
            message_data = json.loads(message_body)
            # print("message_data: ", message_data)
            data_body = message_data['Message']
            data = json.loads(data_body)
            
            # check user role before wait 3 mins to archive
            try:
                user_id = data.get('user_id')
                if not user_id:
                    print("User ID not found.")
                    return jsonify(message="User ID not found in the message."), 400

                user_profile = helpers.get_user_profile(id=user_id)
                user_role = user_profile[4]  
                print("Check user role:", user_role)
            except Exception as e:
                print(f"Failed to get user profile: {e}")
                return jsonify(message="Error retrieving user profile."), 500

            # call step function depends on user role
            if user_role == 'free_user':
                try:
                    # ref: start_execution
                    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/stepfunctions/client/start_execution.html
                    response = stepfunctions.start_execution(
                        stateMachineArn=step_function_arn,
                        input=json.dumps(data)
                    )
                    print(f"Step Function started: {response['executionArn']}")

                    # delete sqs message
                    try:
                        sqs.delete_message(
                            QueueUrl=queue_url,
                            ReceiptHandle=messages[0]['ReceiptHandle']
                        )
                        print("messages deleted")
                    except ClientError as e:
                        print(f"messages delete failed: {str(e)}")
                        return jsonify(message="messages delete failed."), 500

                    return jsonify(message="Step Function execution started."), 200
                except ClientError as e:
                    print(f"Error starting Step Function: {e}")
                    return jsonify(message="Failed to start Step Function."), 500
            else:
                print("user role not match")
                # delete sqs message
                try:
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=messages[0]['ReceiptHandle']
                    )
                    print("messages deleted")
                except ClientError as e:
                    print(f"messages delete failed: {str(e)}")
                    return jsonify(message="messages delete failed."), 500
                return jsonify(message="User role not eligible for archiving."), 400
    return jsonify(message="Invalid SNS message type."), 400


@app.route("/archive_wait3mins", methods=["POST"])
def archive_free_user_data_wait3mins():
    try:
        sns_message = json.loads(request.data)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return jsonify(message="Invalid JSON format."), 400
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify(message="An error occurred processing your request."), 500

    # Subscription Confirmation
    # Check the type of message and handle subscription confirmation
    if sns_message.get('Type') == 'SubscriptionConfirmation':
        subscribe_url = sns_message.get('SubscribeURL')
        if not subscribe_url:
            print("SubscribeURL not found.")
            return jsonify(message="SubscribeURL not found in the message."), 400
        try:
            response = requests.get(subscribe_url)
        except requests.exceptions.RequestException as e:
            print(f"Failed to confirm SNS Subscription: {e}")
            return jsonify(message="Network error in confirming SNS Subscription."), 500

        if response.status_code == 200:
            print("SNS Subscription confirmed.")
            return jsonify(message="SNS Subscription confirmed."), 200
        else:
            print("Failed to confirm SNS Subscription.")
            return jsonify(message="Failed to confirm SNS Subscription."), 400

    # Notification
    # Handle a notification message
    if sns_message.get('Type') == 'Notification':
        # sqs: job_archive to store the message in queue in case job fail
        response = sqs.receive_message(
            QueueUrl=queue_url_wait,
            MaxNumberOfMessages=int(max_messages),  
            WaitTimeSeconds=int(wait_time)  
        )
        print("job_archive sqs received")
        messages = response.get('Messages', [])

        if messages:
            message_body = messages[0]['Body']
            message_data = json.loads(message_body)
            # print("message_data: ", message_data)
            data_body = message_data['Message']
            data = json.loads(data_body)
            print("job_archive data: ", data)
            # check user role before wait 3 mins to archive
            try:
                user_id = data.get('user_id')
                if not user_id:
                    print("User ID not found.")
                    return jsonify(message="User ID not found in the message."), 400

                user_profile = helpers.get_user_profile(id=user_id)
                user_role = user_profile[4]  
                print("Check user role again:", user_role)
            except Exception as e:
                print(f"Failed to get user profile: {e}")
                return jsonify(message="Error retrieving user profile."), 500

            if user_role == 'free_user':
                try:
                    archive(data)
                    # delete message
                    try:
                        sqs.delete_message(
                            QueueUrl=queue_url_wait,
                            ReceiptHandle=messages[0]['ReceiptHandle']
                        )
                        print("messages deleted")
                    except ClientError as e:
                        print(f"messages delete failed: {str(e)}")
                        return jsonify(message="messages delete failed."), 500

                except Exception as e:
                    print(f"Failed to execute the archive work: {e}")
                    return jsonify(message="Failed to execute the archive work."), 500
            else:
                print("user role not match")
                # delete message
                try:
                    sqs.delete_message(
                        QueueUrl=queue_url_wait,
                        ReceiptHandle=messages[0]['ReceiptHandle']
                    )
                    print("messages deleted")
                except ClientError as e:
                    print(f"messages delete failed: {str(e)}")
                    return jsonify(message="messages delete failed."), 500
                return jsonify(message="User role not eligible for archiving."), 400

    return jsonify(message="Invalid SNS message type."), 400




def archive(message_body):
    job_id = message_body.get('job_id')   
    s3_key_result_file = message_body.get('result_file')

    if not job_id or not s3_key_result_file:
        print("Missing required fields in message body.")
        return False

    try:
        try:
            # Get result file object from S3
            result_object = s3.get_object(Bucket=s3_bucket_name, Key=s3_key_result_file)
            result_contents = result_object['Body'].read().decode('utf-8')
            print("Got result file object from S3")
        except ClientError as e:
            print(f"Error getting object from S3: {e}")
            return False

        try:
            # Initiate the archive operation on Glacier
            # ref: upload_archive
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/upload_archive.html
            archive_response = glacier_client.upload_archive(
                vaultName=vault,
                archiveDescription=job_id,
                body=result_contents
            )
            # Extract the archive ID from the response
            archive_id = archive_response['archiveId']
            print("got archive id from glacier")
        except ClientError as e:
            print(f"Error uploading archive to Glacier: {e}")
            return False

        try: 
            # Update the DynamoDB record with the Glacier archive ID
            annotations_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression='SET results_file_archive_id = :val',
                ExpressionAttributeValues={':val': archive_id}
            )
            print("updated archive id to dynamodb")
        except ClientError as e:
            print(f"Error updating DynamoDB: {e}")
            return False

        try:
            # Delete S3 result file
            s3.delete_object(Bucket=s3_bucket_name, Key=s3_key_result_file)
            print("Deleted result file in S3")
        except ClientError as e:
            print(f"Error deleting S3 object: {e}")
        
        print(f"Archiving successful for job: {job_id}")
        return True
    except Exception as e:
        print(f"Error during archiving: {str(e)}")
        return False