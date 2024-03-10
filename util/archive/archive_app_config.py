# archive_app_config.py
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
#
# Set app configuration options for archive utility
#
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import os

# Get the IAM username that was stashed at launch time
try:
    with open("/home/ubuntu/.launch_user", "r") as file:
        iam_username = file.read().replace("\n", "")
except FileNotFoundError as e:
    if "LAUNCH_USER" in os.environ:
        iam_username = os.environ["LAUNCH_USER"]
    else:
        # Unable to set username, so exit
        print("Unable to find launch user name in local file or environment!")
        raise e


class Config(object):

    CSRF_ENABLED = True

    AWS_REGION_NAME = "us-east-1"

    # AWS S3 upload parameters
    AWS_S3_INPUTS_BUCKET = "gas-inputs"
    AWS_S3_RESULTS_BUCKET = "gas-results"
    AWS_S3_KEY_PREFIX = f"{iam_username}/"

    # AWS DynamoDB table
    AWS_DYNAMODB_ANNOTATIONS_TABLE = f"{iam_username}_annotations"

    # AWS SQS queues
    AWS_SQS_WAIT_TIME = 10
    AWS_SQS_MAX_MESSAGES = 1
    AWS_SQS_URL="https://sqs.us-east-1.amazonaws.com/127134666975/chenhui1_a16_job_results_archive"
    AWS_SQS_URL_WAIT3MINS="https://sqs.us-east-1.amazonaws.com/127134666975/chenhui1_a16_job_archive"

    # AWS Step Function
    AWS_STEP_FUNCTION_ARN = "arn:aws:states:us-east-1:127134666975:stateMachine:chenhui1_a16_archive"

    # AWS Glacier
    AWS_GLACIER_VAULT = "ucmpcs"

### EOF
