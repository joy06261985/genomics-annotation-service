# annotator.py
#
# NOTE: This file lives on the AnnTools instance
#
# Copyright (C) 2013-2023 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import boto3
import json
import os
import sys
import time
import subprocess
from subprocess import Popen, PIPE
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from botocore.client import Config

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation

config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("annotator_config.ini")

# annotator config
# ref: configparser — Configuration file parser
# https://docs.python.org/3/library/configparser.html
region = config.get('aws', 'AwsRegionName')
db_table = config.get('gas', 'AnnotationsTable')
bucket = config.get('s3', 'ResultsBucketName')
keyPrefix = config.get('s3', 'KeyPrefix')

# general static connection to boto3
# connect to s3
s3 = boto3.client('s3', region_name=region,
                  config=Config(signature_version='s3v4'))
# connect to db
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)
# connect to sqs               
sqs = boto3.resource('sqs', region_name=region)
queue_url = config.get('sqs', 'QueueUrl')

"""
Reads request messages from SQS and runs AnnTools as a subprocess.

Move existing annotator code here
"""
# annotator config
region = config.get('aws', 'AwsRegionName')
db_table = config.get('gas', 'AnnotationsTable')
bucket = config.get('s3', 'ResultsBucketName')
keyPrefix = config.get('s3', 'KeyPrefix')


def handle_requests_queue():

    # Read messages from the queue
    messages = sqs.Queue(queue_url).receive_messages(
        MaxNumberOfMessages=int(config.get('sqs', 'MaxMessages')),
        WaitTimeSeconds=int(config.get('sqs', 'WaitTime'))
    )

    for message in messages:
        try:
            sns_message = json.loads(message.body)
            message_data = json.loads(sns_message.get("Message", "{}"))

            job_id = message_data.get("job_id")
            user_id = message_data.get("user_id")
            input_file_name = message_data.get("input_file_name")
            s3_inputs_bucket = message_data.get("s3_inputs_bucket")
            s3_key_input_file = message_data.get("s3_key_input_file")

        except json.JSONDecodeError:
            print("Invalid JSON format in message.")
        except KeyError as e:
            print(f"Missing key in message: {e}")
        except Exception as e:
            print(f"Unexpected error when processing message: {e}")
            continue

        try:
            # Get the input file S3 object and copy it to a local file
            job_dir = f'/home/ubuntu/gas/ann/outputs/{job_id}'
            os.makedirs(job_dir, exist_ok=True)

            download_path = f'/home/ubuntu/gas/ann/outputs/{job_id}/{input_file_name}'
            print("download path: ", download_path)
            s3.download_file(s3_inputs_bucket,
                             s3_key_input_file, download_path)
            print("file downloaded")
        except NoCredentialsError:
            print("AWS credentials not found.")
        except (BotoCoreError, ClientError) as e:
            print(f"Error downloading file from S3: {e}")
        except Exception as e:
            print(f"Unexpected error downloading file: {e}")
            continue

        try:
            command = f'python /home/ubuntu/gas/ann/run.py {download_path} {job_id} {user_id} {input_file_name}'
            subprocess.Popen(command, shell=True, cwd=job_dir)
            print("file processed")
        except OSError as e:
            print(f"OS error occurred: {e}")
        except Exception as e:
            print(f"Unexpected error launching subprocess: {e}")
            continue

        try:
            # update data to dynamoDB
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
            continue

        try:
            # Delete the message
            message.delete()
            print("message deleted")
        except (BotoCoreError, ClientError) as e:
            print(f"Error deleting SQS message: {e}")
        except Exception as e:
            print(f"Unexpected error deleting message: {e}")


def main():

    # Poll queue for new results and process them
    while True:
        handle_requests_queue()


if __name__ == "__main__":
    main()

# EOF
