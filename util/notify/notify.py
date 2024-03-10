# notify.py
#
# Notify user of job completion via email
#
# Copyright (C) 2015-2024 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import boto3
import json
from datetime import datetime, timezone, timedelta
from configparser import ConfigParser, ExtendedInterpolation
from botocore.exceptions import ClientError
import sys
import os

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("/home/ubuntu/gas/util/util_config.ini")
config.read("/home/ubuntu/gas/util/notify/notify_config.ini")

# config
region = config.get('aws', 'AwsRegionName')
queue_url = config.get('sqs', 'QueueUrl')

# general static connection to boto3
# connect to sqs  
sqs = boto3.resource('sqs', region_name=region)


def convert_time(timestamp):
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(
        timezone(timedelta(hours=-6))).strftime('%Y-%m-%d %H:%M:%S')

def notify_user(job_id, complete_time, link, recipients):
    # recipients = config.get('gas', 'MailReceiver')
    sender = config.get('gas', 'MailDefaultSender')
    subject = f"Results available for job {job_id}"
    body = f"Your annotation job completed at {complete_time}. Click here to view job details and results: {link}."

    # Debug: Print subject and body to ensure they are not None
    print(f"Subject: {subject}")
    print(f"Body: {body}")
    
    helpers.send_email_ses(recipients, sender, subject, body)


def handle_results_queue():
    while True:
        messages = sqs.Queue(queue_url).receive_messages(
            MaxNumberOfMessages=int(config.get('sqs', 'MaxMessages')),
            WaitTimeSeconds=int(config.get('sqs', 'WaitTime'))
        )

        for message in messages:
            try:
                # Process the message
                print("message: ", message)
                message_body = json.loads(message.body)
                message_data = json.loads(message_body.get("Message", "{}"))
                job_id = message_data.get("job_id")
                complete_time = convert_time(message_data.get("complete_time"))
                link = message_data.get("link")
                user_id = message_data.get("user_id")

                # check user email new fixed
                user_profile = helpers.get_user_profile(id=user_id)
                recipients = user_profile[2]

                print("job_id: ", job_id)
                print("complete_time: ", complete_time)
                print("link: ", link)
                print("recipients: ", recipients)


                # Send the email notification
                notify_user(job_id, complete_time, link, recipients)

                # Delete the message from the queue
                message.delete()
                print(f"Notification sent and message deleted for job ID: {job_id}")
            except json.JSONDecodeError:
                print("Invalid JSON format in message.")
            except KeyError as e:
                print(f"Missing key in message: {e}")
            except Exception as e:
                print(f"Unexpected error when processing message: {e}")

def main():
    # Poll queue for new results and process them
    handle_results_queue()

if __name__ == "__main__":
    main()

# EOF
