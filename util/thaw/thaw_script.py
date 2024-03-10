# thaw_script.py
#
# Thaws upgraded (premium) user data
#
# Copyright (C) 2015-2024 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import boto3
import json
import os
import sys
import time

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from botocore.client import Config


# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation
config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("/home/ubuntu/gas/util/util_config.ini")
config.read("/home/ubuntu/gas/util/thaw/thaw_script_config.ini")
"""A16
Initiate thawing of archived objects from Glacier
"""
# annotator config
region = config.get('aws', 'AwsRegionName')
db_table = config.get('gas', 'AnnotationsTable')
bucket = config.get('s3', 'ResultsBucketName')
keyPrefix = config.get('s3', 'KeyPrefix')
queue_url = config.get('sqs', 'QueueUrl')
vault = config.get('glacier', 'Vault')
snsTopic = config.get('sns', 'SnsTopic')

# general static connection to boto3
# connect to s3
s3 = boto3.client('s3', region_name=region,
                  config=Config(signature_version='s3v4'))
# connect to db
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)
# connect to sqs               
sqs = boto3.resource('sqs', region_name=region)
glacier_client = boto3.client('glacier', region_name=region)


def handle_thaw_queue():

    # Read messages from the queue
    messages = sqs.Queue(queue_url).receive_messages(
        MaxNumberOfMessages=int(config.get('sqs', 'MaxMessages')),
        WaitTimeSeconds=int(config.get('sqs', 'WaitTime'))
    )

    # Process messages --> initiate restore from Glacier
    for message in messages:
        try:
            sns_message = json.loads(message.body)
            message_data = json.loads(sns_message.get("Message", "{}"))
            archives_data = message_data.get("archives_data")
            print("archives_data: ", archives_data)

            # job_id, user_id, results_file_archive_id
            for data in archives_data:
                dynamodb_job_id = data["job_id"]
                user_id = data["user_id"]
                archive_id = data["results_file_archive_id"]

                try:
                    # Attempt Expedited retrieval
                    # ref: initiate_job
                    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/initiate_job.html
                    response = glacier_client.initiate_job(
                        vaultName=vault,
                        jobParameters={
                            'Type': 'archive-retrieval',
                            'ArchiveId': archive_id,
                            # Valid values are Expedited, Standard, or Bulk. Standard is the default.
                            'Tier': 'Expedited',
                            'SNSTopic': snsTopic,
                            'Description': user_id
                        }
                    )
                    
                    print(f"Expedited retrieval initiated: {response['jobId']}")
                    print("response: ", response)

                    try: 
                        # Update the DynamoDB record with the Glacier archive ID
                        annotations_table.update_item(
                            Key={'job_id': dynamodb_job_id},
                            UpdateExpression='SET thaw_type = :typeVal, thaw_status = :statusVal, thaw_id = :thawIdVal',
                            ExpressionAttributeValues={
                                ':typeVal': 'Expedited',
                                ':statusVal': 'PENDING',
                                ':thawIdVal': response['jobId']}
                        )
                        print("updated thaw status to dynamodb")

                    except ClientError as e:
                        print(f"Error updating DynamoDB: {e}")

                except ClientError as e:
                    # expedited issue error
                    # 'InsufficientCapacityException' is specific to capacity issues with Expedited retrievals in AWS Glacier, 
                    # suggesting that the request could be retried with a different retrieval tier or at a later time.
                    if e.response['Error']['Code'] == 'InsufficientCapacityException':
                        print("Expedited retrieval failed, attempting Standard retrieval.")
                        # If Expedited retrieval fails, fallback to Standard retrieval
                        response = glacier_client.initiate_job(
                            vaultName=vault,
                            jobParameters={
                                'Type': 'archive-retrieval',
                                'ArchiveId': archive_id,
                                'Tier': 'Standard',
                                'SNSTopic': snsTopic,
                                'Description': user_id
                            }
                        )
                        print(f"Standard retrieval initiated: {response['jobId']}")
                        print("response: ", response)

                        try: 
                            # Update the DynamoDB record with the Glacier archive ID
                            annotations_table.update_item(
                                Key={'job_id': dynamodb_job_id},
                                UpdateExpression='SET thaw_type = :typeVal, thaw_status = :statusVal, thaw_id = :thawIdVal',
                                ExpressionAttributeValues={
                                    ':typeVal': 'Standard',
                                    ':statusVal': 'PENDING',
                                    ':thawIdVal': response['jobId']}
                            )
                            print("updated thaw status to dynamodb")
                        except ClientError as e:
                            print(f"Error updating DynamoDB: {e}")
                    else:
                        print(f"Failed to initiate retrieval: {e}")


        except json.JSONDecodeError:
            print("Invalid JSON format in message.")
        except KeyError as e:
            print(f"Missing key in message: {e}")
        except Exception as e:
            print(f"Unexpected error when processing message: {e}")
            continue


        # Delete messages
        try:
            message.delete()
            print("message deleted")
        except (BotoCoreError, ClientError) as e:
            print(f"Error deleting SQS message: {e}")
        except Exception as e:
            print(f"Unexpected error deleting message: {e}")



def main():

    # Get handles to resources

    # Poll queue for new results and process them
    while True:
        handle_thaw_queue()


if __name__ == "__main__":
    main()

### EOF
